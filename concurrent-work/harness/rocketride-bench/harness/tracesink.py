"""Dedicated DAP trace sink — the canonical evidence-capture path for the suite.

A second, long-lived client connection subscribed to ALL tasks (token="*") BEFORE any run
starts, so it captures every apaevt_flow / apaevt_status_update / apaevt_task / output / sse
event — even for auto-running sources (filesys) whose objects process at use() time, where a
per-run subscription would miss the early events. Each event is stamped with a client receive
monotonic time (perf_counter_ns) for per-node span reconstruction, then written one-per-line
to a committed JSONL that the report cites.

Uses add_monitor (the supported API); set_events is deprecated in the SDK.
"""
import asyncio
import json
import os
import time

from rocketride import RocketRideClient

from . import config

DEFAULT_TYPES = ["flow", "summary", "task", "output", "sse"]


class TraceSink:
    def __init__(self, uri=None, auth=None, types=None):
        self.uri = uri or config.URI
        self.auth = auth or config.AUTH
        self.types = types or list(DEFAULT_TYPES)
        self.events = []          # [{recv_ns, t_epoch, msg}]
        self._t0 = None
        self._client = None

    async def __aenter__(self):
        self._t0 = time.perf_counter_ns()

        async def on_event(msg):
            self.events.append({"recv_ns": time.perf_counter_ns() - self._t0,
                                "t_epoch": time.time(), "msg": msg})

        self._client = RocketRideClient(uri=self.uri, auth=self.auth, on_event=on_event)
        await self._client.connect()
        await self._client.add_monitor({"token": "*"}, self.types)
        return self

    async def __aexit__(self, *exc):
        try:
            await self._client.remove_monitor({"token": "*"}, self.types)
        except Exception:
            pass
        try:
            await self._client.disconnect()
        except Exception:
            pass

    def clear(self):
        self.events.clear()

    def snapshot(self):
        return list(self.events)

    async def drain(self, seconds=0.4):
        """Let trailing SUMMARY/FLOW events arrive after the run reports complete."""
        await asyncio.sleep(seconds)

    # --- persistence -------------------------------------------------------
    def write_jsonl(self, path, events=None):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        rows = events if events is not None else self.events
        with open(path, "w") as f:
            for e in rows:
                f.write(json.dumps(e, default=str) + "\n")
        return path

    # --- views -------------------------------------------------------------
    def of_type(self, event_name, events=None):
        rows = events if events is not None else self.events
        return [e for e in rows if isinstance(e["msg"], dict)
                and e["msg"].get("event") == event_name]

    def flows(self, events=None):
        return self.of_type("apaevt_flow", events)

    def summaries(self, events=None):
        return self.of_type("apaevt_status_update", events)

    def event_names(self, events=None):
        rows = events if events is not None else self.events
        return sorted({e["msg"].get("event") for e in rows if isinstance(e["msg"], dict)})


def load_jsonl(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
