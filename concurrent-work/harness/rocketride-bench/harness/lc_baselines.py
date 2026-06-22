"""Real LangChain baselines — the MEASURED competitor (replaces the labeled stdlib proxies).

Both sides run AST-IDENTICAL work: the CPU leg calls `harness.competitors.busy` (the exact
integer loop `nodes/workload/IInstance._busy` runs), and the "model" leg is the same
fixed-latency `time.sleep` mock the workload `sleep` mode runs. LangChain only adds its
Runnable / orchestration layer, so an RR-vs-LangChain ratio isolates *framework* overhead, not
model speed — the honest analog of `harness/competitors.py`, now executed through real
LangChain. This is what closes the "you benchmarked a strawman, not LangChain" gap.

Mapping (LangChain's own execution model, not a stand-in):
  cpu    -> RunnableLambda(busy).batch(...)       default ThreadPoolExecutor: GIL-bound == ".batch on CPU"
  sleep  -> RunnableLambda(sleep).abatch(...)     genuine I/O overlap            == ".abatch"
  fanout -> RunnableParallel({...}).invoke(one)   K branches overlap             == "RunnableParallel"

Requires `pip install -r requirements-competitors.txt`. The import is GUARDED so the core suite
stays dependency-free; requesting a baseline with LangChain absent raises LangChainNotInstalled.
For every STRICT/published comparison the parent aborts on that (require_real_langchain) rather
than degrading — the stdlib-proxy fallback exists only for the non-competitive core suite and
never backs a committed "vs LangChain" number.
"""
import asyncio
import hashlib
import os
import sqlite3
import time

from .competitors import busy  # the SAME CPU loop the RR node runs (parity by construction)
from .stats import percentile

try:
    import langchain_core
    from langchain_core.runnables import RunnableLambda, RunnableParallel
    _HAVE_LC = True
    _LC_VERSION = langchain_core.__version__
except Exception:  # ImportError, or a partial/broken install
    _HAVE_LC = False
    _LC_VERSION = None


class LangChainNotInstalled(RuntimeError):
    """Raised when a real-LangChain baseline is requested but langchain-core is absent."""


def have_langchain():
    return _HAVE_LC


def lc_version():
    """Installed langchain-core version (recorded in results.json), or None."""
    return _LC_VERSION


def lc_probe():
    """Strict-mode proof that REAL LangChain is importable in THIS interpreter — version,
    interpreter path and the imported package's file (provenance for every strict head-to-head
    LC row). Raises LangChainNotInstalled instead of degrading; the strict benches never use the
    stdlib proxy."""
    import sys

    _require()
    return {"lc_version": _LC_VERSION, "lc_python": sys.executable,
            "langchain_core_file": langchain_core.__file__}


def _require():
    if not _HAVE_LC:
        raise LangChainNotInstalled(
            "real LangChain baseline requested but langchain-core is not installed — run "
            "`make provision-competitors` (pip install -r requirements-competitors.txt)")


# --- Runnable builders (the fairness seam) ----------------------------------
def build_cpu_chain(iters):
    """A LangChain Runnable doing the SAME busy(iters) loop as the RR node."""
    _require()
    return RunnableLambda(lambda _ignored: busy(iters))


def build_sleep_chain(seconds):
    """A LangChain Runnable whose 'model call' is the same fixed-latency sleep mock."""
    _require()
    return RunnableLambda(lambda _ignored: time.sleep(seconds))


def build_fanout_chain(k, seconds):
    """RunnableParallel of K sleep legs — the genuine multi-branch fan-out LangChain does (and
    RocketRide does not: RR walks branches sequentially, so it loses single-input fan-out)."""
    _require()
    leg = build_sleep_chain(seconds)
    return RunnableParallel({"a%d" % i: leg for i in range(k)})


# --- measured baselines (warmup + trials -> samples for a bootstrap CI) -----
def _trial_throughputs(run_once, n, warmup, trials):
    """run_once() executes one full batch of n units; returns per-trial throughput + wall
    samples so the caller can bootstrap a CI on the RR-vs-LangChain ratio."""
    walls, samples = [], []
    for t in range(warmup + trials):
        t0 = time.perf_counter()
        run_once()
        wall = time.perf_counter() - t0
        if t >= warmup:
            walls.append(wall)
            samples.append(n / wall if wall else None)
    return {"throughput_samples": samples, "wall_samples": walls,
            "throughput": percentile([s for s in samples if s], 50),
            "wall_s": percentile(walls, 50), "lc_version": _LC_VERSION}


def lc_batch_cpu(iters, n, max_concurrency=8, warmup=1, trials=5):
    """chain.batch over N CPU items — LangChain's default ThreadPoolExecutor, GIL-bound for CPU
    work (the executed analog of py_threads / "LangChain .batch on CPU"). Expected to TIE RR."""
    _require()
    chain = build_cpu_chain(iters)
    cfg = {"max_concurrency": max_concurrency}
    return _trial_throughputs(lambda: chain.batch([{} for _ in range(n)], config=cfg),
                              n, warmup, trials)


def lc_abatch_sleep(seconds, n, max_concurrency=None, warmup=1, trials=5):
    """await chain.abatch over N sleep items — genuine I/O overlap (the executed analog of
    .abatch). Called from a sync context (the lc_bench subprocess child), so asyncio.run is safe."""
    _require()
    chain = build_sleep_chain(seconds)
    cfg = {"max_concurrency": max_concurrency} if max_concurrency else None

    def run_once():
        asyncio.run(chain.abatch([{} for _ in range(n)], config=cfg))
    return _trial_throughputs(run_once, n, warmup, trials)


def lc_fanout(k, seconds, warmup=1, trials=3):
    """RunnableParallel.invoke over K sleep legs — one input, K parallel branches (the
    llm-agent-fanout / branch-fanout competitor; genuinely overlaps ~ T, so RR loses)."""
    _require()
    chain = build_fanout_chain(k, seconds)
    return _trial_throughputs(lambda: chain.invoke({}), k, warmup, trials)


# --- group 7: concurrent-processing (sqlite + blocking I/O over N docs) ----------
def sqlite_doc_work(conn, label, io_s):
    """One document's work — AST-IDENTICAL with nodes/workload/IInstance._sqlite_doc_work
    (concurrent-processing asserts the two bodies are AST-identical before any timed run)."""
    cur = conn.execute("INSERT INTO docs (content) VALUES (?)", (label,))
    conn.execute("SELECT content FROM docs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.commit()
    if io_s > 0:
        time.sleep(io_s)


def _sqlite_conn_for(db_path):
    d = os.path.dirname(db_path)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, content TEXT)")
    return conn


def build_sqlite_chain_shared(db_path, io_s):
    """The DEFAULT/naive idiom: ONE connection captured at chain-build time, shared by every
    worker thread `.batch` spawns — the documented sqlite3 thread-affinity trap."""
    _require()
    conn = _sqlite_conn_for(db_path)
    return RunnableLambda(lambda x: sqlite_doc_work(conn, "doc%s" % x, io_s))


def build_sqlite_chain_percall(db_path, io_s):
    """The CAREFUL user: a fresh connection per invocation (per-call state). Avoids the trap
    at the cost of remembering to do it — measured as the honesty row."""
    _require()

    def work(x):
        conn = _sqlite_conn_for(db_path)
        try:
            sqlite_doc_work(conn, "doc%s" % x, io_s)
        finally:
            conn.close()
        return x
    return RunnableLambda(work)


def build_sqlite_chain_async_blocking(db_path, io_s):
    """The idiomatic-but-wrong ASYNC chain: an `async def` leg whose body is the same BLOCKING
    sync work. Under `.abatch` everything runs on the one event-loop thread, so the batch
    SERIALIZES (~N x io_s). (A sync-only RunnableLambda would be dispatched to a thread pool
    and overlap — that variant is the batch modes; this is specifically the asyncio trap.)"""
    _require()
    conn = _sqlite_conn_for(db_path)  # one thread (the loop), so no thread-affinity error

    def work(x):
        sqlite_doc_work(conn, "doc%s" % x, io_s)
        return x

    async def awork(x):
        return work(x)
    return RunnableLambda(work, afunc=awork)


def lc_sqlite_workload(mode, n, io_s, max_concurrency=None, db_path=None):
    """Run ONE workload mode over n docs; return outcome + wall + per-item ok/err counts.
    return_exceptions=True is measurement plumbing ONLY (it lets us COUNT the failures —
    naive code without it dies on the first one either way; disclosed in the REPORT)."""
    _require()
    import tempfile

    db_path = db_path or os.path.join(tempfile.mkdtemp(prefix="lc_workload_"), "docs.db")
    mc = max_concurrency or n
    cfg = {"max_concurrency": mc}
    t0 = time.perf_counter()
    outs = []
    if mode == "batch_shared":
        chain = build_sqlite_chain_shared(db_path, io_s)
        outs = chain.batch(list(range(n)), config=cfg, return_exceptions=True)
    elif mode == "batch_percall":
        chain = build_sqlite_chain_percall(db_path, io_s)
        outs = chain.batch(list(range(n)), config=cfg, return_exceptions=True)
    elif mode == "abatch_blocking":
        chain = build_sqlite_chain_async_blocking(db_path, io_s)
        outs = asyncio.run(chain.abatch(list(range(n)), config=cfg, return_exceptions=True))
    elif mode == "seq":
        chain = build_sqlite_chain_percall(db_path, io_s)
        for i in range(n):
            try:
                outs.append(chain.invoke(i))
            except Exception as e:  # noqa: BLE001 - counted below
                outs.append(e)
    else:
        raise ValueError("unknown workload mode %r" % mode)
    wall = time.perf_counter() - t0
    errs = [o for o in outs if isinstance(o, BaseException)]
    first = errs[0] if errs else None
    return {"mode": mode, "n": n, "io_s": io_s, "max_concurrency": mc,
            "wall_s": wall, "n_ok": len(outs) - len(errs), "n_err": len(errs),
            "status": "crash" if errs else "ok",
            "error_type": (type(first).__module__ + "." + type(first).__name__) if first else None,
            "error_example": str(first)[:200] if first else None,
            "lc_version": _LC_VERSION}


# --- PyMuPDF-over-N-docs baseline (not exercised by the shipping benches) -----
def _pdf_extract_all(doc):
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    return text


def lc_pdf_batch(mode, n, max_concurrency, pdf_path):
    """One repeat: extract the full PDF text n times via `.batch`. mode='shared' uses ONE
    fitz.Document captured at chain-build time (the naive idiom; racy C-level corruption /
    segfault — pymupdf/PyMuPDF#832); mode='percall' opens a fresh Document per invocation.
    Per-item sha is compared to the single-threaded reference → n_corrupt. A segfault kills
    this child process — the parent (run_langchain) counts that repeat as a crash."""
    _require()
    import fitz

    ref = hashlib.sha256(_pdf_extract_all(fitz.open(pdf_path)).encode()).hexdigest()[:16]

    if mode == "shared":
        doc = fitz.open(pdf_path)

        def work(x):
            return hashlib.sha256(_pdf_extract_all(doc).encode()).hexdigest()[:16]
    elif mode == "percall":
        def work(x):
            d = fitz.open(pdf_path)
            try:
                return hashlib.sha256(_pdf_extract_all(d).encode()).hexdigest()[:16]
            finally:
                d.close()
    else:
        raise ValueError("unknown pdf mode %r" % mode)

    chain = RunnableLambda(work)
    t0 = time.perf_counter()
    outs = chain.batch(list(range(n)), config={"max_concurrency": max_concurrency},
                       return_exceptions=True)
    wall = time.perf_counter() - t0
    errs = [o for o in outs if isinstance(o, BaseException)]
    shas = [o for o in outs if not isinstance(o, BaseException)]
    return {"mode": mode, "n": n, "max_concurrency": max_concurrency, "wall_s": wall,
            "ref_sha": ref, "n_ok": sum(1 for s in shas if s == ref),
            "n_corrupt": sum(1 for s in shas if s != ref), "n_err": len(errs),
            "error_type": (type(errs[0]).__name__ if errs else None),
            "lc_version": _LC_VERSION}


# --- group 7: data-isolation (shared mutable state under .batch) ----
def lc_iso_shared_dict(n, max_concurrency, gap_iters):
    """GLOBAL data done naively: every `.batch` worker read-modify-writes ONE shared dict,
    with the suite's busy() loop between read and write (a realistic compute gap). The
    non-atomic RMW loses updates under thread interleaving — observed < expected. gap_iters
    is disclosed in the REPORT (0 lost at tiny gaps; the race needs a window)."""
    _require()
    state = {"n": 0, "items": []}

    def work(x):
        cur = state["n"]
        busy(gap_iters)  # the read-modify-write window (same loop as every CPU bench)
        state["n"] = cur + 1
        state["items"].append("doc%04d" % x)
        return x

    chain = RunnableLambda(work)
    t0 = time.perf_counter()
    chain.batch(list(range(n)), config={"max_concurrency": max_concurrency})
    wall = time.perf_counter() - t0
    return {"n": n, "max_concurrency": max_concurrency, "gap_iters": gap_iters,
            "wall_s": wall, "expected": n, "observed_counter": state["n"],
            "lost_updates": n - state["n"], "items_len": len(state["items"]),
            "lc_version": _LC_VERSION}


# --- streaming (langchain-core only) ----------------------------------------
def lc_stream(k, inter_delay_s, warmup=1, trials=3):
    """LangChain `.astream()` over a mock K-token stream with fixed inter-token delay — the
    in-process streaming path (the competitor to RR's server->SSE->client path). Returns TTFT +
    inter-token latency (the framework streaming overhead, model held constant by the mock)."""
    _require()
    from langchain_core.runnables import RunnableGenerator

    async def gen(inputs):
        async for _ in inputs:  # drain the (ignored) upstream input
            pass
        for i in range(k):
            if i:
                await asyncio.sleep(inter_delay_s)
            yield "tok%d" % i

    async def one():
        chain = RunnableGenerator(gen)
        t0 = time.perf_counter()
        recv = []
        async for _tok in chain.astream("go"):
            recv.append(time.perf_counter() - t0)
        return recv

    ttfts, inters = [], []
    for t in range(warmup + trials):
        recv = asyncio.run(one())
        if t >= warmup and recv:
            ttfts.append(recv[0])
            inters.extend(recv[i + 1] - recv[i] for i in range(len(recv) - 1))
    return {"ttft_s": percentile(ttfts, 50), "ttft_samples": ttfts,
            "inter_token_p50_s": percentile(inters, 50), "inter_token_p99_s": percentile(inters, 99),
            "n_tokens": k, "lc_version": _LC_VERSION}


# --- real embedding (Tier-2 realstack: langchain-huggingface + sentence-transformers) ----------
try:
    from langchain_huggingface import HuggingFaceEmbeddings
    _HAVE_HF = True
except Exception:
    _HAVE_HF = False

MINILM = "sentence-transformers/all-MiniLM-L6-v2"  # the SAME model RR's embedding_transformer(miniLM) uses


def have_realstack():
    return _HAVE_HF


def _require_hf():
    if not _HAVE_HF:
        raise LangChainNotInstalled(
            "real embedding baseline needs langchain-huggingface + sentence-transformers — "
            "not part of the shipping benches")


def lc_embed(chunks, warmup=1, trials=5):
    """LangChain HuggingFaceEmbeddings(MiniLM).embed_documents — in-process, ~zero framework
    overhead over the model. Subtract model_alone_embed() to get LangChain's integration cost."""
    _require_hf()
    emb = HuggingFaceEmbeddings(model_name=MINILM)
    return _trial_throughputs(lambda: emb.embed_documents(chunks), len(chunks), warmup, trials)


def model_alone_embed(chunks, warmup=1, trials=5):
    """Bare sentence-transformers encode — the model with NO framework wrapper. This is what we
    SUBTRACT from both RR and LangChain so the remainder is purely framework overhead."""
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(MINILM)
    return _trial_throughputs(lambda: m.encode(chunks, batch_size=32, show_progress_bar=False),
                              len(chunks), warmup, trials)


def embed_parity(chunks):
    """Mean cosine between HuggingFaceEmbeddings and bare sentence-transformers on the same chunks
    (should be ~1.0) — proves the LangChain wrapper doesn't alter the vectors. RR uses the identical
    model, so its vectors match by construction."""
    _require_hf()
    import numpy as np
    from sentence_transformers import SentenceTransformer
    a = np.asarray(HuggingFaceEmbeddings(model_name=MINILM).embed_documents(chunks), dtype=float)
    b = np.asarray(SentenceTransformer(MINILM).encode(chunks), dtype=float)
    cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-9)
    return float(cos.mean())
