"""Competitor baselines, run with the SAME work as the workload node.

CPU work is AST-identical to nodes/workload/IInstance.py::_busy so RR-vs-baseline is fair:
  - py_serial         single-threaded Python (the floor)
  - py_threads        ThreadPoolExecutor — GIL-bound stdlib stand-in (the floor/ceiling a one-GIL
                      interpreter reaches). NOTE: the MEASURED LangChain `.batch` baseline is REAL
                      LangChain via run_langchain()/lc_baselines.py — not this proxy.
  - py_processes      ProcessPoolExecutor — true multi-core; the prize a C++/nogil node targets
I/O baselines (asyncio) live alongside. The real, executed LangChain competitor (`.batch`,
`.abatch`, `RunnableParallel`) runs OUT-OF-PROCESS via run_langchain() -> competitors/langchain/
lc_bench.py, so every "vs LangChain" number is real, not a labeled stand-in.
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LC_BENCH = os.path.join(_REPO, "competitors", "langchain", "lc_bench.py")


def busy(iters):
    """Identical to workload._busy — a pure-Python integer busy loop (holds the GIL)."""
    s = 1.0
    for i in range(1, iters + 1):
        s += (i * i) % 7
    return s


def _timed(fn, n):
    t0 = time.perf_counter()
    fn()
    wall = time.perf_counter() - t0
    return {"wall_s": wall, "throughput": n / wall if wall else None}


def py_serial(iters, n):
    return _timed(lambda: [busy(iters) for _ in range(n)], n)


def py_threads(iters, n, workers):
    def run():
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(busy, [iters] * n))
    return _timed(run, n)


def py_processes(iters, n, workers):
    def run():
        with ProcessPoolExecutor(max_workers=workers) as ex:
            list(ex.map(busy, [iters] * n))
    return _timed(run, n)


def py_threads_sleep(seconds, n, workers):
    """N blocking sleeps across a thread pool — sleep releases the GIL, so this overlaps."""
    import time as _t

    def run():
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_t.sleep, [seconds] * n))
    return _timed(run, n)


async def py_asyncio_sleep(seconds, n):
    """N concurrent awaits on one event loop — the idiomatic async I/O baseline."""
    import asyncio as _a

    t0 = time.perf_counter()
    await _a.gather(*[_a.sleep(seconds) for _ in range(n)])
    wall = time.perf_counter() - t0
    return {"wall_s": wall, "throughput": n / wall if wall else None}


def calibrate_iters(target_s=0.25, probe=1_000_000):
    """Find iters that make busy() take ~target_s on THIS machine (so absolute numbers are
    comparable across runs by ratio)."""
    t0 = time.perf_counter()
    busy(probe)
    per = (time.perf_counter() - t0) / probe
    return max(1, int(target_s / per))


def run_langchain(kind, *args, timeout=600):
    """Run the REAL LangChain baseline in an isolated subprocess; return its parsed JSON.

    kind in {cpu_batch, sleep_abatch, fanout} — see competitors/langchain/lc_bench.py. Returns
    {"error": ...} if langchain isn't installed or the child failed. Every PUBLISHED comparison row
    goes through require_real_langchain() first, which aborts (no proxy) unless real LangChain is
    proven — so the soft-error path here only keeps the non-competitive core suite green when the
    optional competitor deps aren't installed; it never produces a committed "vs LangChain" number.
    The child runs under sys.executable (this venv), keeps LangChain's import graph + thread pools
    OUT of the harness process.
    """
    cmd = [sys.executable, LC_BENCH, kind] + [str(a) for a in args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - benchmark plumbing; surface as a soft error
        return {"error": "lc_bench spawn failed: %r" % e}
    for line in reversed((p.stdout or "").splitlines()):  # last non-empty stdout line = the JSON
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {"error": "no JSON from lc_bench (stderr tail: %s)" % (p.stderr or "")[-200:],
            "child_died": p.returncode, "child_signal": -p.returncode if p.returncode < 0 else None}


def require_real_langchain():
    """STRICT mode (group 7): prove REAL LangChain executes in the competitor child, or abort.

    No stdlib-proxy fallback here, ever — a past run shipped 'vs LangChain' numbers where
    LangChain never actually ran (the proxy degraded silently). Returns the probe provenance
    {lc_version, lc_python, langchain_core_file} which callers embed in results.json next to
    every LC row; raises SystemExit with provisioning instructions on any failure."""
    probe = run_langchain("probe")
    if probe.get("error") or not probe.get("lc_version"):
        raise SystemExit(
            "REAL LangChain is required for this benchmark and could not be executed.\n"
            "  probe said: %s\n"
            "  Fix: make provision-competitors   (pip install -r requirements-competitors.txt)\n"
            "  This benchmark NEVER falls back to a proxy — no numbers were produced."
            % (probe.get("error") or probe))
    return probe


def lc_strict(kind, *args, timeout=600):
    """run_langchain() for the strict head-to-head rows: any infrastructure failure (no JSON /
    import error / spawn failure) aborts the benchmark. EXPECTED workload failures come back as
    ordinary measurements carrying lc_version (status='crash'), so they pass through untouched."""
    res = run_langchain(kind, *args, timeout=timeout)
    if res.get("error") or not res.get("lc_version"):
        raise SystemExit(
            "lc_bench %s failed as INFRASTRUCTURE (not a measured outcome): %s\n"
            "  No LC row is written without lc_version proof — aborting this benchmark."
            % (kind, res.get("error") or res))
    return res
