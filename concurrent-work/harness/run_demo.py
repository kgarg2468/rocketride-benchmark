#!/usr/bin/env python3
"""Run the *demo* (showcase) pipelines and capture a sample output that shows each claim.

These drive the runnable ``demo.pipe`` showcases — NOT the benchmark instruments
(``pipeline.pipe``). See each ``groups/<group>/<bench>/README.md`` for what each demo proves.

The demo pipes reference ``${ROCKETRIDE_OPENAI_KEY}`` / ``${ROCKETRIDE_GOOGLE_KEY}``; the SDK
substitutes them client-side from ``os.environ`` at ``use()`` time. Export them first:

    export ROCKETRIDE_OPENAI_KEY=...     # every demo (gpt-4-1)
    export ROCKETRIDE_GOOGLE_KEY=...     # authoring-effort only (gemini sub-agent)
    python run_demo.py all               # or: pick | instance | crash | authoring

Each demo writes ``demo-output.sample.md`` into its folder. ``--smoke`` runs a 1-item probe and
dumps the raw SDK return + event names (used to verify wiring without burning a full run).
"""
import argparse
import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, "rocketride-bench")
sys.path.insert(0, BR)
from harness.runner import Bench, WarmPool  # noqa: E402

G = os.path.join(BR, "groups")
DEMOS = {
    "pick":      f"{G}/scale-and-concurrency/concurrent-processing",
    "instance":  f"{G}/scale-and-concurrency/data-isolation",
    "crash":     f"{G}/robustness-and-isolation/fault-isolation",
    "authoring": f"{G}/scale-and-concurrency/authoring-effort",
}
pipe = lambda d: os.path.join(DEMOS[d], "demo.pipe")
data = lambda d: os.path.join(DEMOS[d], "demo-data")


def require_keys(names):
    miss = [n for n in names if not os.environ.get(n)]
    if miss:
        sys.exit("Missing env key(s): %s\n  Export them and re-run (see the folder README)." % ", ".join(miss))


def load_jsonl(p):
    with open(p) as f:
        return [json.loads(line) for line in f if line.strip()]


def ev(e):
    m = e.get("msg", e) if isinstance(e, dict) else {}
    return m.get("event"), (m.get("body") or {})


def jget(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, "", [], {}):
            return d[k]
    return None


def answer_text(r):
    """Best-effort: pull the answer string from a send() return (shape confirmed on first run)."""
    if not isinstance(r, dict) or r.get("error"):
        return None
    v = jget(r, "answers", "answer", "text", "result", "output", "response", "content")
    if isinstance(v, list):
        v = "\n".join(str(x.get("text", x) if isinstance(x, dict) else x) for x in v)
    if isinstance(v, dict):
        v = jget(v, "text", "answer", "content") or json.dumps(v)
    return v if isinstance(v, str) else (json.dumps(v) if v is not None else None)


def write_sample(demo, title, body):
    out = os.path.join(DEMOS[demo], "demo-output.sample.md")
    with open(out, "w") as f:
        f.write("# %s — sample run\n\n" % title)
        f.write("> Captured from a live run of `demo.pipe`. LLM output is illustrative (real models, "
                "non-deterministic). Re-run with `python ../../../run_demo.py %s`.\n\n" % demo)
        f.write(body)
    print("  wrote", out)
    return out


# ----------------------------------------------------------------------------- pick
async def run_pick(m=16, smoke=False):
    require_keys(["ROCKETRIDE_OPENAI_KEY"])
    docs = load_jsonl(os.path.join(data("pick"), "meetings.jsonl"))
    if smoke:
        docs = docs[:2]
        m = 2
    async with WarmPool(pipe("pick"), m, ttl=900, trace_level="none") as pool:
        per = [[] for _ in range(m)]
        for i in range(len(docs)):
            per[i % m].append(i)
        res = [None] * len(docs)

        async def worker(idx):
            c, t = pool.clients[idx], pool.tokens[idx]
            for i in per[idx]:
                d = docs[i]
                res[i] = await c.send(t, d["text"], objinfo={"name": d["id"] + ".txt"}, mimetype="text/plain")

        t0 = time.perf_counter()
        await asyncio.gather(*[worker(i) for i in range(m)])
        wall = time.perf_counter() - t0
        warm = pool.warm_s
    ok = [i for i, r in enumerate(res) if answer_text(r)]
    if smoke:
        print("PICK smoke raw[0]:", json.dumps(res[0])[:1500])
        return
    body = ["**Concurrency:** %d docs across **%d warm pipes** (each its own runtime process).\n" % (len(docs), m),
            "| metric | value |", "|---|---|",
            "| docs completed | **%d / %d** |" % (len(ok), len(docs)),
            "| node errors | **%d** |" % (len(docs) - len(ok)),
            "| warm-pool bring-up | %.2f s |" % warm,
            "| run wall (all %d docs) | %.2f s |" % (len(docs), wall), "",
            "### Sample summaries\n"]
    for i in ok[:4]:
        body.append("- **%s** → %s" % (docs[i]["id"], answer_text(res[i])))
    write_sample("pick", "concurrent-processing · 64 docs of real per-doc work", "\n".join(body) + "\n")
    return {"m": m, "completed": len(ok), "failed": len(docs) - len(ok), "wall_s": round(wall, 2)}


# ------------------------------------------------------------------- instance (isolation)
async def run_instance(smoke=False):
    require_keys(["ROCKETRIDE_OPENAI_KEY"])
    A = load_jsonl(os.path.join(data("instance"), "set-a.jsonl"))
    B = load_jsonl(os.path.join(data("instance"), "set-b.jsonl"))
    if smoke:
        A, B = A[:2], B[:2]
    async with WarmPool(pipe("instance"), 2, ttl=900, trace_level="none") as pool:
        async def feed(idx, docs):
            c, t = pool.clients[idx], pool.tokens[idx]
            last = None
            for d in docs:
                last = await c.send(t, d["text"], objinfo={"name": d["id"] + ".txt"}, mimetype="text/plain")
            return last
        ra, rb = await asyncio.gather(feed(0, A), feed(1, B))
    if smoke:
        print("INSTANCE smoke raw_a:", json.dumps(ra)[:1500])
        return
    ea, eb = [d["entity"] for d in A], [d["entity"] for d in B]
    body = ["Two pipes run concurrently; each appends the entity it extracts to its **own run-scoped "
            "memory** and returns its full list. Isolation is by construction — neither pipe can see "
            "the other's data.\n",
            "**Pipe A** fed: %s" % ", ".join(ea),
            "**Pipe A returned:**\n\n```\n%s\n```\n" % (answer_text(ra) or "(none)"),
            "**Pipe B** fed: %s" % ", ".join(eb),
            "**Pipe B returned:**\n\n```\n%s\n```\n" % (answer_text(rb) or "(none)")]
    write_sample("instance", "data-isolation · each pipe is its own data", "\n".join(body) + "\n")
    return {"a": answer_text(ra), "b": answer_text(rb)}


# ----------------------------------------------------------------------- crash (containment)
async def run_crash(smoke=False):
    require_keys(["ROCKETRIDE_OPENAI_KEY"])
    os.environ["ROCKETRIDE_DEMO_DOCS"] = os.path.join(data("crash"), "docs")
    async with Bench(trace_types=["summary", "flow", "task", "output"]) as b:
        r = await b.run_pipe(pipe("crash"), trace_level="full", ttl=0, drive=None,
                             expect=4, poll=True, max_wait=180, settle=1.5)
    st = r["status"] or {}
    if smoke:
        print("CRASH status:", json.dumps(st)[:1800])
        return
    keep = {k: st.get(k) for k in ("totalCount", "completedCount", "failedCount", "serviceUp", "warnings", "errors")}
    body = ["A folder of 4 good docs + **1 deliberately-malformed `.docx`**. Each file is its own run "
            "(its own process). The malformed file's run fails; the good runs complete; the server "
            "survives.\n",
            "| metric | value |", "|---|---|",
            "| total files | %s |" % keep.get("totalCount"),
            "| completed | **%s** |" % keep.get("completedCount"),
            "| failed | **%s** (the malformed file) |" % keep.get("failedCount"),
            "| server up after the fault | **%s** |" % keep.get("serviceUp"), "",
            "```json\n%s\n```\n" % json.dumps(keep, indent=2)]
    write_sample("crash", "fault-isolation · a fault stays contained", "\n".join(body) + "\n")
    return keep


# ------------------------------------------------------------------- authoring (declarative)
async def run_authoring(smoke=False):
    require_keys(["ROCKETRIDE_OPENAI_KEY", "ROCKETRIDE_GOOGLE_KEY"])
    transcript = open(os.path.join(data("authoring"), "transcript.txt")).read()
    async with Bench(trace_types=["summary", "flow", "task", "output"]) as b:
        async def drive(client, token):
            return await client.send(token, transcript, objinfo={"name": "transcript.txt"}, mimetype="text/plain")
        r = await b.run_pipe(pipe("authoring"), trace_level="full", ttl=0, drive=drive,
                             expect=1, poll=True, max_wait=240, settle=2.0)
    ans = answer_text(r["result"])
    if smoke:
        print("AUTHORING status:", json.dumps(r["status"])[:800])
        print("AUTHORING raw_result:", json.dumps(r["result"])[:1800])
        return
    body = ["One declarative `.pipe`: a Deep Agent orchestrator fans out to **2 parallel sub-agents** "
            "(Summary Writer on gpt-4-1, Action-Item Extractor on gemini) — **3 LLM calls across 2 "
            "providers, 0 lines of orchestration/concurrency code**.\n",
            "**Returned answer:**\n\n```markdown\n%s\n```\n" % (ans or "(none)")]
    write_sample("authoring", "authoring-effort · declarative multi-agent app", "\n".join(body) + "\n")
    return {"answer": ans}


RUNNERS = {"pick": run_pick, "instance": run_instance, "crash": run_crash, "authoring": run_authoring}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("demo", choices=list(RUNNERS) + ["all"])
    ap.add_argument("--m", type=int, default=16, help="warm pipes for pick")
    ap.add_argument("--smoke", action="store_true", help="1-item probe, dump raw shapes")
    args = ap.parse_args()
    todo = list(RUNNERS) if args.demo == "all" else [args.demo]
    for d in todo:
        print("\n=== %s ===" % d, flush=True)
        kw = {"smoke": args.smoke}
        if d == "pick":
            kw["m"] = args.m
        try:
            out = await RUNNERS[d](**kw)
            if out:
                print("  ->", json.dumps(out)[:400])
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("  FAILED:", type(e).__name__, e)


if __name__ == "__main__":
    asyncio.run(main())
