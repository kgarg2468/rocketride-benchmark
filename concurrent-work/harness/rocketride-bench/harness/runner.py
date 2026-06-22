"""The benchmark runner — drives the genuine product path and captures committed evidence.

A `Bench` holds two live connections to the standing EAAS server (direct-connect):
  - a TraceSink subscribed to token="*" BEFORE any run (so it never misses early events),
  - a driver client that validates, runs `.pipe` files via use(filepath=), drives sources,
    polls completion, and terminates.

`run_pipe()` runs ONE measured cell: it clears the sink, runs the EXACT authored `.pipe`
headless, captures the trace to a committed JSONL, and returns wall time + the event stream.
"""
import asyncio
import time

from rocketride import RocketRideClient

from . import config
from .client import load_pipe, validate_pipeline
from .tracesink import TraceSink


def send_payload(payload, objinfo=None, mimetype="text/plain"):
    """Build a `drive` callable that pushes one payload into a webhook/chat/dropper source."""
    async def _drive(client, token):
        return await client.send(token, payload,
                                 objinfo=objinfo or {"name": "bench.txt"},
                                 mimetype=mimetype)
    return _drive


class Bench:
    def __init__(self, uri=None, auth=None, trace_types=None):
        self.uri = uri or config.URI
        self.auth = auth or config.AUTH
        self._trace_types = trace_types
        self.driver = None
        self.sink = None

    async def __aenter__(self):
        self.sink = TraceSink(uri=self.uri, auth=self.auth, types=self._trace_types)
        await self.sink.__aenter__()
        self.driver = RocketRideClient(uri=self.uri, auth=self.auth)
        await self.driver.connect()
        return self

    async def __aexit__(self, *exc):
        try:
            if self.driver:
                await self.driver.disconnect()
        except Exception:
            pass
        if self.sink:
            await self.sink.__aexit__(*exc)

    async def _reconnect_driver(self):
        try:
            await self.driver.disconnect()
        except Exception:
            pass
        self.driver = RocketRideClient(uri=self.uri, auth=self.auth)
        await self.driver.connect()

    async def _use(self, **kw):
        """use() bounded by a timeout, with one reconnect+retry (the server occasionally
        stalls a first call after idle)."""
        try:
            return await asyncio.wait_for(self.driver.use(**kw), timeout=120)
        except Exception:
            await self._reconnect_driver()
            return await asyncio.wait_for(self.driver.use(**kw), timeout=120)

    async def _await_complete(self, token, expect=1, max_wait=120.0, interval=0.05):
        deadline = time.perf_counter() + max_wait
        last = None
        while time.perf_counter() < deadline:
            await asyncio.sleep(interval)
            try:
                st = await asyncio.wait_for(self.driver.get_task_status(token), timeout=10)
            except Exception:
                st = None
            if st:
                last = st
                if (st.get("completed") or st.get("completedCount", 0) >= expect
                        or st.get("state", 0) >= 5):
                    break
        return last

    async def validate_file(self, pipe_path, source=None):
        return await validate_pipeline(self.driver, load_pipe(pipe_path), source=source)

    async def run_pipe(self, pipe_path, *, trace_level="full", threads=None, ttl=0,
                       use_existing=None, env=None, drive=None, expect=1, poll=True,
                       settle=0.4, max_wait=120.0, trace_out=None, label=None):
        """Run one measured cell. Returns {token, started, result, status, wall_s, events}."""
        self.sink.clear()
        t0 = time.perf_counter()
        started = await self._use(filepath=pipe_path, pipelineTraceLevel=trace_level,
                                  threads=threads, ttl=ttl, use_existing=use_existing, env=env)
        token = started.get("token")
        result = await drive(self.driver, token) if drive is not None else None
        status = await self._await_complete(token, expect=expect, max_wait=max_wait) if poll else None
        wall = time.perf_counter() - t0
        await self.sink.drain(settle)
        events = self.sink.snapshot()
        if trace_out:
            self.sink.write_jsonl(trace_out, events)
        try:
            await self.driver.terminate(token)
        except Exception:
            pass
        return {"token": token, "started": started, "result": result, "status": status,
                "wall_s": wall, "events": events, "label": label}


async def run_one(pipe_path, **kw):
    """Convenience: open a Bench, run a single cell, tear down."""
    async with Bench() as b:
        return await b.run_pipe(pipe_path, **kw)


class WarmPool:
    """M warm RESIDENT pipeline instances — the production serving topology (group 7).

    Each pipe gets its own client connection (multi-tenant-isolation proved 64 connections
    are fine; one shared websocket would head-of-line-block M concurrent send()s), its own
    project_id clone of the authored pipe, ttl + use_existing residency, and ONE discarded
    warmup send. "Each pipeline instance can only run once at a time" → per pipe, docs go
    sequentially; concurrency comes from M pipes in parallel (each its own runtime
    process — per-pipe process isolation, "each pipe is its own data").

    `warm_s` (M× connect+use+warmup, serialized) is the standing-deployment cost — reported
    separately by callers and excluded from the measured phase.
    """

    def __init__(self, pipe, m, *, threads=1, ttl=900, uri=None, auth=None,
                 trace_level="none", env=None):
        import copy as _copy
        import uuid as _uuid

        self.base = load_pipe(pipe) if isinstance(pipe, str) else pipe
        self.m = m
        self.threads = threads
        self.ttl = ttl
        self.uri = uri or config.URI
        self.auth = auth or config.AUTH
        self.trace_level = trace_level
        self.env = env
        self._copy, self._uuid = _copy, _uuid
        self.clients, self.tokens = [], []
        self.warm_s = None

    async def __aenter__(self):
        t0 = time.perf_counter()
        sem = asyncio.Semaphore(8)  # bounded-concurrent bring-up: 8-at-a-time, matching how a
        # pool manager would warm a fleet of resident pipes.

        pairs = []  # (client, token) appended atomically → always aligned

        async def bring_up(i):
            async with sem:
                c = RocketRideClient(uri=self.uri, auth=self.auth)
                await c.connect()
                self.clients.append(c)  # registered immediately → always cleaned up even on a
                # partial bring-up failure
                cfg = self._copy.deepcopy(self.base)
                cfg["project_id"] = str(self._uuid.uuid4())
                started = await asyncio.wait_for(
                    c.use(pipeline=cfg, threads=self.threads, ttl=self.ttl,
                          use_existing=True, pipelineTraceLevel=self.trace_level,
                          env=self.env, name="warm%d" % i),
                    timeout=180)
                pairs.append((c, started["token"]))
                await c.send(started["token"], "warmup", objinfo={"name": "warmup.txt"},
                             mimetype="text/plain")

        try:
            await asyncio.gather(*[bring_up(i) for i in range(self.m)])
        except BaseException:
            self.tokens = [t for _, t in pairs]
            self.clients = [c for c, _ in pairs] + \
                [c for c in self.clients if c not in [p[0] for p in pairs]]
            await self.__aexit__()  # terminate/disconnect whatever did come up
            raise
        self.clients = [c for c, _ in pairs]
        self.tokens = [t for _, t in pairs]
        self.warm_s = time.perf_counter() - t0
        return self

    async def __aexit__(self, *exc):
        for c, t in zip(self.clients, self.tokens):
            try:
                await c.terminate(t)
            except Exception:
                pass
        for c in self.clients:
            try:
                await c.disconnect()
            except Exception:
                pass

    async def run(self, n_docs, payload_fn=None):
        """Send n_docs through the pool (round-robin, K=n/M sequential per pipe, M pipes
        concurrent). Returns {wall_s, latencies, per_pipe} — per-send RTTs for p50/p99.
        payload_fn(i) -> (payload, objinfo) lets callers name each doc."""
        payload_fn = payload_fn or (lambda i: ("doc %d" % i, {"name": "doc%04d.txt" % i}))
        per_pipe = [[] for _ in range(self.m)]
        for i in range(n_docs):
            per_pipe[i % self.m].append(i)
        lats = []

        async def worker(idx):
            c, t = self.clients[idx], self.tokens[idx]
            for i in per_pipe[idx]:
                payload, objinfo = payload_fn(i)
                s0 = time.perf_counter()
                await c.send(t, payload, objinfo=objinfo, mimetype="text/plain")
                lats.append(time.perf_counter() - s0)

        t0 = time.perf_counter()
        await asyncio.gather(*[worker(i) for i in range(self.m)])
        wall = time.perf_counter() - t0
        return {"wall_s": wall, "latencies": lats,
                "per_pipe": [len(x) for x in per_pipe]}
