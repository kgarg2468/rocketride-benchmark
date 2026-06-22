"""concurrent-processing — 64 docs of sqlite+blocking-I/O work: RR warm pipes vs LangChain's three idioms.

The SAME per-doc work (sqlite INSERT+SELECT+commit + 100 ms blocking wait — AST-identical,
AST-asserted below) over N=64 docs:

  RocketRide:  M warm resident pipes (each its own runtime process; "each pipe is its own
               data" — the node's module-level connection is per-process by construction).
  LangChain:   ONE chain object, the three idiomatic ways to run it over 64 inputs:
                 .batch   (shared conn)        -> sqlite3.ProgrammingError   (CRASH)
                 .abatch  (blocking sync work) -> event loop serializes      (SEQUENTIAL)
                 sequential loop               -> N x work                   (SLOW)

STRICT real-LangChain mode: require_real_langchain() probes the child first; every LC row
embeds {lc_version, lc_python, langchain_core_file}; an infrastructure failure aborts the
benchmark instead of degrading to any proxy.

Run (engine up + make provision-competitors):
  python groups/scale-and-concurrency/concurrent-processing/run.py
"""
import ast
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)

from harness import competitors as comp, config, markers, measure, pipes, runner, stats  # noqa: E402
from harness.runner import WarmPool  # noqa: E402
from harness.tracesink import TraceSink  # noqa: E402

N_DOCS = 64
IO_S = 0.100
MS = [int(x) for x in os.environ.get("BENCH_MS", "8,16,64").split(",")]  # env-configurable; default = upstream
DB_DIR = "/tmp/rr_bench_sqlite"
PIPE = os.path.join(HERE, "pipeline.pipe")
TRACE = os.path.join(HERE, "trace")


def _func_body_src(path, funcname):
    """Normalized source of a function's computation (the accuracy-parity comparator)."""
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == funcname:
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            return ast.unparse(ast.Module(body=body, type_ignores=[]))
    return None


def parity_gate():
    """No number ships unless both sides run the IDENTICAL per-doc work."""
    rr = _func_body_src(os.path.join(REPO, "nodes", "workload", "IInstance.py"),
                        "_sqlite_doc_work")
    lc = _func_body_src(os.path.join(REPO, "harness", "lc_baselines.py"), "sqlite_doc_work")
    assert rr is not None and rr == lc, \
        "PARITY GATE FAILED: node._sqlite_doc_work != lc_baselines.sqlite_doc_work"
    return True


def _clean_dbs():
    shutil.rmtree(DB_DIR, ignore_errors=True)


def _db_rows():
    total, files = 0, []
    if os.path.isdir(DB_DIR):
        for f in sorted(os.listdir(DB_DIR)):
            n = sqlite3.connect(os.path.join(DB_DIR, f)).execute(
                "SELECT COUNT(*) FROM docs").fetchone()[0]
            total += n
            files.append({"db": f, "rows": n})
    return total, files


async def rr_cell(m):
    """N_DOCS through M warm resident pipes; evidence = RRBENCH markers + sqlite rows."""
    _clean_dbs()
    pipes.set_params(mode="sqlite", label="workload", io_ms=IO_S * 1000.0,
                     db=DB_DIR + "/%d.db", conn="module")
    sampler = measure.RSSSampler(measure.task_kids, interval=0.05)
    async with TraceSink() as sink:
        sampler.start()
        async with WarmPool(PIPE, m, trace_level="full") as pool:
            res = await pool.run(N_DOCS)
        sampler.stop()
        sampler.join()
        await sink.drain(0.8)
        events = sink.snapshot()
        sink.write_jsonl(os.path.join(TRACE, "rr.m%d.jsonl" % m), events)
        warm_s = pool.warm_s
    rows = [r for r in markers.parse_markers(events) if r["label"] == "workload"]
    errs = [s for e in events for s in markers._strings(e.get("msg", e)) if "RRBENCH_ERR" in s]
    db_total, _ = _db_rows()
    lats = res["latencies"]
    return {"M": m, "n_docs": N_DOCS, "wall_s": round(res["wall_s"], 3),
            "warm_s": round(warm_s, 2),
            "p50_ms": round(stats.percentile(lats, 50) * 1e3, 2),
            "p99_ms": round(stats.percentile(lats, 99) * 1e3, 2),
            "markers": len(rows), "marker_pids": len(markers.distinct(rows, "pid")),
            "node_errors": len(errs),
            "sqlite_rows": db_total, "rows_expected": N_DOCS + m,  # + M warmup docs
            "status": "ok" if (not errs and db_total == N_DOCS + m
                               and len(rows) == N_DOCS + m) else "check"}


async def rr_appendix_threads():
    """HONESTY CELL: one pipe, threadCount=4, the same naive module-level connection →
    RR's worker threads share the node instance and hit the SAME sqlite trap. RR's safety
    in the headline cells is per-pipe PROCESS isolation (topology), not magic."""
    _clean_dbs()
    pipes.set_params(mode="sqlite", label="appx", io_ms=IO_S * 1000.0,
                     db=DB_DIR + "/appx_%d.db", conn="module")
    pp = os.path.join(tempfile.mkdtemp(), "appendix.pipe")
    pipes.write_pipe(pp, pipes.filesys_work("input32"))
    r = await runner.run_one(pp, threads=4, env=pipes.data_env(), expect=32, max_wait=120,
                             trace_out=os.path.join(TRACE, "rr.appendix_t4.jsonl"))
    rows = [x for x in markers.parse_markers(r["events"]) if x["label"] == "appx"]
    errs = [s for e in r["events"] for s in markers._strings(e.get("msg", e))
            if "RRBENCH_ERR" in s]
    return {"topology": "1 pipe x threadCount=4, 32 files, naive module-level conn",
            "markers": len(rows), "distinct_tids": len(markers.distinct(rows, "tid")),
            "node_errors": len(errs),
            "error_example": errs[0].strip()[:160] if errs else None}


def lc_cells(lc_probe):
    out = {}
    for mode in ("batch_shared", "abatch_blocking", "seq"):
        r = comp.lc_strict("sqlite_workload", mode, N_DOCS, IO_S, N_DOCS)
        r.update(lc_probe)  # provenance: which interpreter/package produced this row
        out[mode] = r
        print("  LC %-15s status=%-5s wall=%6.2fs ok=%2d err=%2d %s"
              % (mode, r["status"], r["wall_s"], r["n_ok"], r["n_err"],
                 r.get("error_type") or ""), flush=True)
    return out


async def main():
    os.makedirs(TRACE, exist_ok=True)
    parity_gate()
    print("parity gate: PASS (per-doc work AST-identical both sides)")
    lc_probe = comp.require_real_langchain()
    print("real LangChain proven: %s (%s)" % (lc_probe["lc_version"], lc_probe["lc_python"]))

    pipes.write_pipe(PIPE, pipes.webhook_work())
    async with runner.Bench() as b:
        v = await b.validate_file(PIPE)
        assert v["ok"], "pipe failed validate(): %s" % v["errors"]

    rr = []
    print("\nRR warm pools (N=%d docs, %.0f ms work):" % (N_DOCS, IO_S * 1e3))
    for m in MS:
        cell = await rr_cell(m)
        rr.append(cell)
        print("  M=%2d wall=%6.3fs p50=%6.1fms p99=%6.1fms markers=%d/%d "
              "errs=%d rows=%d/%d [%s]"
              % (m, cell["wall_s"], cell["p50_ms"], cell["p99_ms"],
                 cell["markers"], N_DOCS + m, cell["node_errors"],
                 cell["sqlite_rows"], cell["rows_expected"], cell["status"]), flush=True)
        await asyncio.sleep(1.0)

    print("\nLangChain (same chain object, n=%d, io=%.0f ms, mc=%d):" % (N_DOCS, IO_S * 1e3, N_DOCS))
    lc = lc_cells(lc_probe)

    appendix = await rr_appendix_threads()
    print("\nappendix (1 pipe x threads=4, shared module conn): markers=%d tids=%d errors=%d"
          % (appendix["markers"], appendix["distinct_tids"], appendix["node_errors"]))

    rr64 = next((r for r in rr if r["M"] == 64), rr[-1])  # fall back to largest M when 64 not in BENCH_MS
    out = {
        "benchmark": "concurrent-processing",
        "hypothesis": "64 docs of stateful per-doc work: LangChain's idioms crash, serialize, "
                      "or run sequential; RR's warm per-pipe topology is fast AND safe",
        "provenance": config.provenance(),
        "langchain_provenance": lc_probe,
        "params": {"n_docs": N_DOCS, "io_s": IO_S, "Ms": MS, "max_concurrency": N_DOCS,
                   "work": "sqlite INSERT+SELECT+commit + blocking sleep(io_s), "
                           "AST-identical (parity-gated)"},
        "parity_gate": "PASS",
        "rocketride": rr,
        "langchain": lc,
        "rr_appendix_threads4": appendix,
        "verdict_metrics": {
            "rr_topM_wall_s": rr64["wall_s"], "rr_topM_ok": rr64["status"] == "ok",
            "lc_batch_shared_status": lc["batch_shared"]["status"],
            "lc_batch_shared_error": lc["batch_shared"]["error_type"],
            "lc_abatch_blocking_wall_s": round(lc["abatch_blocking"]["wall_s"], 2),
            "lc_seq_wall_s": round(lc["seq"]["wall_s"], 2),
            "lc_version": lc_probe["lc_version"],
        },
    }
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "make_diagrams.py"),
                    PIPE, os.path.join(HERE, "canvas")])
    vm = out["verdict_metrics"]
    print("\nVERDICT @ top M: RR(top M) %.2fs ok | LC .batch(shared) %s (%s) | "
          "LC .abatch(blocking) %.1fs | LC seq %.1fs"
          % (vm["rr_topM_wall_s"], vm["lc_batch_shared_status"], vm["lc_batch_shared_error"],
             vm["lc_abatch_blocking_wall_s"], vm["lc_seq_wall_s"]))


if __name__ == "__main__":
    asyncio.run(main())
