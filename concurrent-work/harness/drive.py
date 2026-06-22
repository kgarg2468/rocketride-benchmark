#!/usr/bin/env python3
"""Repeatable concurrency-WIN benchmark driver.

Drives the genuine, integrity-gated RocketRide-vs-LangChain win benchmarks against a live local
RocketRide runtime, N times, capturing each repetition into its own ``run-NN/`` folder.

We feature the isolation / authoring WINS.

Benchmarks
  concurrent-processing        (timed)  64 docs of stateful sqlite+I/O work, AST-identical both
                                   sides: RR warm per-pipe topology is fast AND safe; the SAME
                                   LangChain chain object crashes (.batch) / serializes (.abatch)
                                   / runs sequential. Reps use M in {8,16} warm pipes (16 = 64
                                   docs in ~0.55s).
  fault-isolation         (timed)  one node hard-crash kills only its run; REAL in-process
                                   LangChain .abatch loses ALL concurrent work (0/M).
  data-isolation (timed)  256 docs -> 32 warm pipes: RR holds an exact per-pipe
                                   partition (0 lost / 0 leaked); the naive LangChain shared-dict
                                   idiom silently loses a swept fraction of updates. Deterministic
                                   correctness result -> fewer confirmatory reps.
  authoring-effort       (static) imperative concurrency lines + hidden "decision points" the
                                   author must know. No timing -> run once.

Every benchmark self-gates on AST-identical work (AST parity gate) and a STRICT real-LangChain
probe (lc_version embedded per row; no proxy fallback). Each run's results.json carries full
provenance (engine sha256, CPU, cores, RAM, Python, langchain-core version).

Usage
  ROCKETRIDE_BENCH=/path/to/rocketride-bench python3 drive.py            # all benches, default reps
  python3 drive.py --only concurrent-processing --reps 10                     # one bench
  python3 drive.py --reps 10 --force                                     # re-run, overwrite
The live engine must be up (ws://localhost:5565) and the bench .venv must have langchain + the
rocketride SDK (`make start && make provision-competitors`).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.environ.get("ROCKETRIDE_BENCH", os.path.join(HERE, "rocketride-bench"))
VENV_PY = os.path.join(BR, ".venv", "bin", "python")
TIMEOUT_S = 1200  # per-rep wall cap; a degraded-engine hang is logged + skipped, never blocking

# key -> (group-relative path under the bench repo, default reps). Timed benches get many reps
# (median + spread); the deterministic correctness one gets a few confirmatory reps.
TIMED = {
    "concurrent-processing":        ("groups/scale-and-concurrency/concurrent-processing",        10),
    "fault-isolation":         ("groups/robustness-and-isolation/fault-isolation",      10),
    "data-isolation": ("groups/scale-and-concurrency/data-isolation",  3),
}
STATIC = {
    "authoring-effort":       "groups/scale-and-concurrency/authoring-effort",
}


def _node_errors(results_path):
    """Best-effort: total node_errors across cells (0 expected for every RR win cell)."""
    try:
        with open(results_path) as f:
            d = json.load(f)
    except Exception:
        return None
    rr = d.get("rocketride")
    if isinstance(rr, list):
        return sum(int(c.get("node_errors", 0) or 0) for c in rr if isinstance(c, dict))
    if isinstance(rr, dict):
        return int(rr.get("node_errors", 0) or 0)
    return 0


def run_once(group_rel, out_dir):
    """Run one org runner; copy its results.json + trace/ into out_dir. Returns a record."""
    os.makedirs(out_dir, exist_ok=True)
    runner = os.path.join(BR, group_rel, "run.py")
    group_dir = os.path.join(BR, group_rel)
    log_path = os.path.join(out_dir, "run.log")
    t0 = time.time()
    timed_out, rc = False, None
    with open(log_path, "w") as logf:
        try:
            proc = subprocess.run([VENV_PY, runner], cwd=BR, stdout=logf,
                                  stderr=subprocess.STDOUT, timeout=TIMEOUT_S)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out, rc = True, -999
            logf.write("\n[driver] TIMEOUT after %ss — engine likely degraded; skipping rep\n" % TIMEOUT_S)
    dt = round(time.time() - t0, 1)

    res_src = os.path.join(group_dir, "results.json")
    # only adopt a results.json this rep actually (re)wrote — guards against a stale prior file
    copied = os.path.exists(res_src) and os.path.getmtime(res_src) >= t0 - 1 and not timed_out
    if copied:
        shutil.copy2(res_src, os.path.join(out_dir, "results.json"))
    trace_src = os.path.join(group_dir, "trace")
    if copied and os.path.isdir(trace_src):
        shutil.copytree(trace_src, os.path.join(out_dir, "trace"), dirs_exist_ok=True)

    return {
        "exit": rc,
        "wall_s": dt,
        "timed_out": timed_out,
        "results_written": copied,
        "node_errors": _node_errors(res_src) if copied else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=None, help="override reps for ALL timed benches")
    ap.add_argument("--only", default=None, help="run a single benchmark by key")
    ap.add_argument("--force", action="store_true", help="re-run even if results.json exists")
    args = ap.parse_args()

    if not os.path.exists(VENV_PY):
        sys.exit("bench venv python not found: %s (set ROCKETRIDE_BENCH)" % VENV_PY)

    manifest = {"started": None, "bench_repo": BR, "records": []}
    # timestamp passed in via the shell (Date.* is fine here — plain python, not a workflow)
    manifest["started"] = datetime.datetime.now().isoformat(timespec="seconds")

    benches = TIMED if not args.only else {k: v for k, v in TIMED.items() if k == args.only}
    for key, (group_rel, default_reps) in benches.items():
        reps = args.reps or default_reps
        for rep in range(1, reps + 1):
            out_dir = os.path.join(HERE, "..", "runs", key, "run-%02d" % rep)
            done = os.path.exists(os.path.join(out_dir, "results.json"))
            if done and not args.force:
                print("[skip] %s rep %02d (exists)" % (key, rep), flush=True)
                continue
            print("[run ] %s rep %02d ..." % (key, rep), end="", flush=True)
            rec = run_once(group_rel, out_dir)
            rec.update({"bench": key, "rep": rep})
            manifest["records"].append(rec)
            print(" exit=%d wall=%5.1fs node_errors=%s" %
                  (rec["exit"], rec["wall_s"], rec["node_errors"]), flush=True)

    # static benches once (only if running all, or explicitly selected)
    for key, group_rel in STATIC.items():
        if args.only and args.only != key:
            continue
        out_dir = os.path.join(HERE, "..", "runs", key)
        if os.path.exists(os.path.join(out_dir, "results.json")) and not args.force:
            print("[skip] %s (static, exists)" % key, flush=True)
            continue
        print("[run ] %s (static) ..." % key, end="", flush=True)
        rec = run_once(group_rel, out_dir)
        rec.update({"bench": key, "rep": 0})
        manifest["records"].append(rec)
        print(" exit=%d wall=%5.1fs" % (rec["exit"], rec["wall_s"]), flush=True)

    with open(os.path.join(HERE, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    n_err = [r for r in manifest["records"] if (r.get("node_errors") or 0) > 0 or r["exit"] != 0]
    print("\nDONE. %d records, %d with errors/nonzero-exit." % (len(manifest["records"]), len(n_err)))
    if n_err:
        print("  ATTENTION:", json.dumps(n_err, indent=2))


if __name__ == "__main__":
    main()
