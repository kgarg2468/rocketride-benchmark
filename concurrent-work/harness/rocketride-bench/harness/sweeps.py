"""Reusable run routines shared by the object-throughput / latency benchmarks.

Keeps each benchmark's run.py thin: it sets the work mode + topology and calls a sweep here.
Every cell commits the LAST trial's full trace to trace/rr.<cell>.jsonl as evidence.
"""
import os

from .markers import distinct, max_overlap, parse_markers, work_span
from . import stats


def _cell_record(res):
    m = parse_markers(res["events"])
    return {
        "wall_s": round(res["wall_s"], 4),
        "work_span_s": round(work_span(m, clock="epoch"), 4),
        "n_markers": len(m),
        "n_pids": len(distinct(m, "pid")),
        "n_tids": len(distinct(m, "tid")),
        "overlap": max_overlap(m, clock="epoch"),
        "errors": sum(1 for s in (e["msg"].get("body", {}).get("output", "")
                                  if isinstance(e["msg"], dict) else "" for e in res["events"])
                      if "RRBENCH_ERR" in str(s)),
    }


async def threadcount_sweep(bench, pipe_path, *, env, n_objects, threadcounts,
                            warmup=1, trials=5, trace_dir=None, on_cell=None):
    """Run pipe_path across threadcounts; per cell do warmup+trials runs, commit the last
    trial's full trace. Returns rows with per-trial work_span + throughput list (for CIs)."""
    rows = []
    val = await bench.validate_file(pipe_path)
    assert val["ok"], "pipe failed validation: %s" % val["errors"]
    for w in threadcounts:
        cells = []
        for t in range(warmup + trials):
            last = (t == warmup + trials - 1)
            trace_out = os.path.join(trace_dir, "rr.tc%d.jsonl" % w) if (last and trace_dir) else None
            res = await bench.run_pipe(pipe_path, trace_level="full" if last else "summary",
                                       threads=w, env=env, expect=n_objects, settle=0.5,
                                       trace_out=trace_out)
            if t >= warmup:
                cells.append(_cell_record(res))
        wsps = [c["work_span_s"] for c in cells if c["work_span_s"] > 0]
        thr = [n_objects / x for x in wsps]
        row = {
            "threadCount": w, "trials": cells,
            "work_span_p50_s": stats.percentile(wsps, 50),
            "throughput_obj_s_p50": stats.percentile(thr, 50),
            "throughput_samples": thr,
            "n_tids": max(c["n_tids"] for c in cells),
            "n_pids": max(c["n_pids"] for c in cells),
            "max_overlap": max(c["overlap"] for c in cells),
        }
        rows.append(row)
        if on_cell:
            on_cell(row)
    return rows


def scaling_ci(rows, lo_tc, hi_tc):
    """Bootstrap CI on throughput(hi_tc)/throughput(lo_tc) — the scaling factor."""
    by = {r["threadCount"]: r for r in rows}
    return stats.ratio_ci(by[hi_tc]["throughput_samples"], by[lo_tc]["throughput_samples"])
