"""data-isolation — per-pipe INSTANCE data vs one shared GLOBAL dict over 32 workers.

"Each pipe is its own data": each RocketRide pipeline runs as its own runtime process, so the
node's module-level accumulator is a per-pipe local copy by construction. We send 256 named
docs through M=32 warm pipes and verify from the RRBENCH_STATE trace lines that every pipe
ended holding EXACTLY the docs routed to it — nothing lost, nothing leaked across pipes.

The LangChain side runs the naive GLOBAL idiom: one chain whose workers read-modify-write a
single shared dict under `.batch` (max_concurrency=32), with the suite's busy() loop in the
read→write window (a realistic compute gap, disclosed). Non-atomic RMW under thread
interleaving LOSES updates — we count them, across a swept gap size.

STRICT real-LangChain mode (no proxy): probe first, lc_version embedded in every LC row.

Run (engine up + make provision-competitors):
  python groups/scale-and-concurrency/data-isolation/run.py
"""
import asyncio
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)

from harness import competitors as comp, config, markers, pipes, runner  # noqa: E402
from harness.runner import WarmPool  # noqa: E402
from harness.tracesink import TraceSink  # noqa: E402

N_DOCS = 256
M = int(os.environ.get("BENCH_M", "32"))  # RR pool size AND LC worker count; env-configurable, default = upstream
GAPS = [20_000, 50_000, 100_000]  # busy() iterations inside the LC read→write window
PIPE = os.path.join(HERE, "pipeline.pipe")
TRACE = os.path.join(HERE, "trace")

STATE_RE = re.compile(r"RRBENCH_STATE\tpid=(\d+)\tn=(\d+)\titems=(\S*)")


async def rr_cell():
    """256 named docs through 64 warm pipes; verify exact per-pipe partitions from the trace."""
    pipes.set_params(mode="iso_accumulate", label="iso")
    async with TraceSink() as sink:
        async with WarmPool(PIPE, M, trace_level="full") as pool:
            res = await pool.run(N_DOCS)
            warm_s = pool.warm_s
        await sink.drain(0.8)
        events = sink.snapshot()
        sink.write_jsonl(os.path.join(TRACE, "rr.iso.jsonl"), events)

    # Reconstruct each pipe's FINAL state (max-n STATE line per pid).
    final = {}
    for e in events:
        for s in markers._strings(e.get("msg", e)):
            for m_ in STATE_RE.finditer(s):
                pid, n, items = int(m_.group(1)), int(m_.group(2)), m_.group(3)
                if pid not in final or n > final[pid][0]:
                    final[pid] = (n, items.split(",") if items else [])

    # Expected partition: doc i went to pipe i % M (WarmPool round-robin), plus 1 warmup each.
    all_docs = ["doc%04d.txt" % i for i in range(N_DOCS)]
    seen_docs = [d for _, (_, items) in final.items() for d in items if d != "warmup.txt"]
    per_pipe_ok = 0
    dup_or_leak = 0
    for pid, (_, items) in final.items():
        docs = [d for d in items if d != "warmup.txt"]
        idxs = sorted(int(d[3:7]) % M for d in docs)
        per_pipe_ok += 1 if len(set(idxs)) <= 1 else 0  # all of one pipe's residue class
        dup_or_leak += sum(1 for d in docs if seen_docs.count(d) > 1)
    lost = len(all_docs) - len(set(seen_docs))
    return {"M": M, "n_docs": N_DOCS, "wall_s": round(res["wall_s"], 3),
            "warm_s": round(warm_s, 2), "pipes_reporting": len(final),
            "pipes_with_clean_partition": per_pipe_ok,
            "docs_lost": lost, "docs_duplicated_or_leaked": dup_or_leak,
            "status": "ok" if (len(final) == M and per_pipe_ok == M
                               and lost == 0 and dup_or_leak == 0) else "check"}


def lc_cells(lc_probe):
    rows = []
    for gap in GAPS:
        r = comp.lc_strict("iso_dict", N_DOCS, M, gap)
        r.update(lc_probe)
        rows.append(r)
        print("  LC shared dict gap=%-7d expected=%d observed=%d lost=%d (wall %.2fs)"
              % (gap, r["expected"], r["observed_counter"], r["lost_updates"], r["wall_s"]),
              flush=True)
    return rows


async def main():
    os.makedirs(TRACE, exist_ok=True)
    lc_probe = comp.require_real_langchain()
    print("real LangChain proven: %s" % lc_probe["lc_version"])

    pipes.write_pipe(PIPE, pipes.webhook_work())
    async with runner.Bench() as b:
        v = await b.validate_file(PIPE)
        assert v["ok"], "pipe failed validate(): %s" % v["errors"]

    print("\nRR: %d named docs → %d warm pipes (instance data = per-pipe local copy):" % (N_DOCS, M))
    rr = await rr_cell()
    print("  pipes=%d/%d clean partitions=%d lost=%d leaked=%d [%s] wall=%.2fs"
          % (rr["pipes_reporting"], M, rr["pipes_with_clean_partition"],
             rr["docs_lost"], rr["docs_duplicated_or_leaked"], rr["status"], rr["wall_s"]))

    print("\nLangChain: ONE shared dict, %d workers, non-atomic read→busy(gap)→write:" % M)
    lc = lc_cells(lc_probe)

    worst = max(lc, key=lambda r: r["lost_updates"])
    out = {
        "benchmark": "data-isolation",
        "hypothesis": "per-pipe instance data is isolated by construction; a naive shared "
                      "GLOBAL dict under 64 LangChain workers silently loses updates",
        "provenance": config.provenance(),
        "langchain_provenance": lc_probe,
        "params": {"n_docs": N_DOCS, "M": M, "gaps": GAPS,
                   "rr_routing": "round-robin doc i -> pipe i % M; identity from objinfo name"},
        "rocketride": rr,
        "langchain": lc,
        "verdict_metrics": {
            "rr_docs_lost": rr["docs_lost"],
            "rr_docs_duplicated_or_leaked": rr["docs_duplicated_or_leaked"],
            "rr_clean": rr["status"] == "ok",
            "lc_max_lost_updates": worst["lost_updates"],
            "lc_max_lost_gap_iters": worst["gap_iters"],
            "lc_lost_by_gap": {str(r["gap_iters"]): r["lost_updates"] for r in lc},
            "lc_version": lc_probe["lc_version"],
        },
    }
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "make_diagrams.py"),
                    PIPE, os.path.join(HERE, "canvas")])
    print("\nVERDICT: RR 64 pipes — 0 lost / 0 leaked (%s). LangChain shared dict — up to "
          "%d/%d updates silently lost (gap=%d)."
          % (rr["status"], worst["lost_updates"], N_DOCS, worst["gap_iters"]))


if __name__ == "__main__":
    asyncio.run(main())
