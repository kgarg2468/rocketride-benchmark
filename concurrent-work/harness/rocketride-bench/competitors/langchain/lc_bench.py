"""Subprocess child: run a REAL LangChain workload and print ONE JSON result line.

Mirrors the etl-transform Node baseline (`subprocess.run(["node","transform.js",...])` ->
`json.loads(stdout)`): run an external competitor as an isolated process and parse its JSON.
Running LangChain out-of-process keeps its import graph + thread pools out of the harness
asyncio loop and out of the RR-engine RSS measurement, and lets us sample the LangChain
process's OWN peak RSS. Both sides run AST-identical work (see harness/lc_baselines.py).

On a missing / partial langchain install it prints {"error": ...} and exits non-zero. For the
STRICT head-to-head kinds (probe/sqlite_workload/iso_dict) the parent then ABORTS — it never
degrades to a proxy, so no committed comparison row is ever produced without real LangChain. Only
the non-strict legacy kinds let the caller fall back to a labeled stdlib proxy for the core suite.

Usage:
  python competitors/langchain/lc_bench.py probe
  python competitors/langchain/lc_bench.py cpu_batch    <iters> <n> [max_concurrency] [trials]
  python competitors/langchain/lc_bench.py sleep_abatch <seconds> <n> [max_concurrency|-] [trials]
  python competitors/langchain/lc_bench.py fanout       <k> <seconds> [trials]
  python competitors/langchain/lc_bench.py sqlite_workload <mode> <n> <io_s> [max_concurrency]
  python competitors/langchain/lc_bench.py iso_dict     <n> <max_concurrency> <gap_iters>

The strict head-to-head kinds (probe/sqlite_workload/iso_dict) are STRICT: their parents
hard-abort on any {"error": ...} result instead of degrading to a proxy — see
harness.competitors.require_real_langchain(). A result carrying "lc_version" is the proof
that real LangChain executed; an EXPECTED workload failure (the workload) is returned as a
normal measurement ({"status": "crash", "error_type": ..., "lc_version": ...}), never as
{"error": ...}.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main(argv):
    if not argv:
        _emit({"error": "usage: lc_bench.py <cpu_batch|sleep_abatch|fanout> <args...>"})
        return 2
    try:
        from harness import lc_baselines as lc
    except Exception as e:  # harness not importable (shouldn't happen) — fail loud as JSON
        _emit({"error": "harness import failed: %r" % e})
        return 1
    if not lc.have_langchain():
        _emit({"error": "langchain not installed"})
        return 1

    # Sample THIS process's peak RSS while the workload runs (the LangChain-side memory figure).
    import psutil
    from harness import measure
    sampler = measure.RSSSampler(lambda: [psutil.Process()], interval=0.02)

    kind = argv[0]
    try:
        sampler.start()
        if kind == "probe":
            res = lc.lc_probe()
        elif kind == "sqlite_workload":
            mode, n, io_s = argv[1], int(argv[2]), float(argv[3])
            mc = int(argv[4]) if len(argv) > 4 else None
            res = lc.lc_sqlite_workload(mode, n, io_s, max_concurrency=mc)
        elif kind == "pdf_batch":
            mode, n, mc, pdf_path = argv[1], int(argv[2]), int(argv[3]), argv[4]
            res = lc.lc_pdf_batch(mode, n, mc, pdf_path)
        elif kind == "iso_dict":
            n, mc, gap = int(argv[1]), int(argv[2]), int(argv[3])
            res = lc.lc_iso_shared_dict(n, mc, gap)
        elif kind == "cpu_batch":
            iters, n = int(argv[1]), int(argv[2])
            mc = int(argv[3]) if len(argv) > 3 else 8
            trials = int(argv[4]) if len(argv) > 4 else 5
            res = lc.lc_batch_cpu(iters, n, max_concurrency=mc, trials=trials)
        elif kind == "sleep_abatch":
            seconds, n = float(argv[1]), int(argv[2])
            mc = int(argv[3]) if len(argv) > 3 and argv[3] != "-" else None
            trials = int(argv[4]) if len(argv) > 4 else 5
            res = lc.lc_abatch_sleep(seconds, n, max_concurrency=mc, trials=trials)
        elif kind == "fanout":
            k, seconds = int(argv[1]), float(argv[2])
            trials = int(argv[3]) if len(argv) > 3 else 3
            res = lc.lc_fanout(k, seconds, trials=trials)
        elif kind == "stream":
            k, inter_ms = int(argv[1]), float(argv[2])
            trials = int(argv[3]) if len(argv) > 3 else 3
            res = lc.lc_stream(k, inter_ms / 1000.0, trials=trials)
        elif kind == "embed":
            import json as _json
            chunks = _json.load(open(argv[1]))
            trials = int(argv[2]) if len(argv) > 2 else 5
            if not lc.have_realstack():
                _emit({"error": "real embedding deps not installed (langchain-huggingface + "
                                "sentence-transformers) — not part of the shipping benches"})
                return 1
            res = {"kind": "embed", "n_chunks": len(chunks),
                   "lc_embed": lc.lc_embed(chunks, trials=trials),
                   "model_alone": lc.model_alone_embed(chunks, trials=trials),
                   "parity_cosine": lc.embed_parity(chunks)}
        else:
            _emit({"error": "unknown kind %r" % kind})
            return 2
    except lc.LangChainNotInstalled as e:
        _emit({"error": str(e)})
        return 1
    except Exception as e:  # any runtime failure -> JSON error, non-zero exit (parent falls back)
        _emit({"error": "%s failed: %r" % (kind, e)})
        return 3
    finally:
        sampler.stop()
        sampler.join()

    res["kind"] = kind
    _emit(res)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
