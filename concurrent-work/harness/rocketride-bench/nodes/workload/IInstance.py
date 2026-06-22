# Benchmark-only node (NOT part of RocketRide). Safe to delete.
#
# Per object, performs controllable synthetic work selected by `mode`:
#   cpu   : pure-python busy loop of `iters` iterations   -> HOLDS the GIL
#   sleep : time.sleep(`seconds`)                          -> RELEASES the GIL
#   http  : blocking urllib GET to `url`                   -> RELEASES the GIL (socket recv)
#   none  : no work (startup/overhead baseline)
#   sqlite       : per-doc INSERT+SELECT+commit on a sqlite conn + blocking sleep(io_ms).
#                  conn="module" caches ONE connection at module level (the naive idiom the
#                  LangChain shared-chain trap uses — AST-identical in harness/lc_baselines
#                  sqlite_doc_work); conn="per_call" opens/closes per object. Errors emit
#                  RRBENCH_ERR lines so the harness counts failures from the trace.
#   pdf_extract  : extract text from every page of `pdf`. conn="module" caches ONE shared
#                  fitz.Document (the naive idiom); conn="per_call" opens per object. Emits
#                  RRBENCH_PDF\tchars=..\tsha=.. for corruption checks (checksum vs reference).
#   iso_accumulate : append this object's label to module-level _STATE (per-PROCESS instance
#                  data) and emit RRBENCH_STATE with the full list — the harness verifies each
#                  pipe's state holds exactly its own docs (per-pipe isolation proof).
#
# Params come from a small JSON file written by the harness BEFORE each run (the server
# forwards no per-run env to nodes; use(env=) is config-substitution only). Path =
# $ROCKETRIDE_BENCH_PARAMS or /tmp/rr_bench_params.json. Read ONCE per task process and
# cached (each run is a fresh subprocess), so it adds no per-object overhead. Falls back to
# BENCH_* env (for the local-binary floor path).
#
# Emits one RRBENCH stderr line per object (forwarded by the server as an OUTPUT event):
#   RRBENCH \t label \t mode \t t0_perf \t t1_perf \t tid=.. \t pid=.. \t e0=.. \t e1=..
# giving per-call work span, intra-process thread overlap (perf+tid -> GIL/I/O concurrency),
# and cross-process overlap (epoch+pid -> process-per-run parallelism).
import json
import os
import sys
import time
import threading

from rocketlib import IInstanceBase

_PARAMS = None


def _params():
    global _PARAMS
    if _PARAMS is not None:
        return _PARAMS
    path = os.environ.get("ROCKETRIDE_BENCH_PARAMS") or os.environ.get("BENCH_PARAMS") \
        or "/tmp/rr_bench_params.json"
    p = {}
    try:
        with open(path) as f:
            p = json.load(f)
    except Exception:
        pass
    # env fallbacks (local-binary floor path)
    p.setdefault("mode", os.environ.get("BENCH_MODE", "none"))
    p.setdefault("iters", int(os.environ.get("BENCH_ITERS", "0") or 0))
    p.setdefault("seconds", float(os.environ.get("BENCH_SECONDS", "0") or 0))
    p.setdefault("url", os.environ.get("BENCH_URL", "http://127.0.0.1:8799/"))
    p.setdefault("label", os.environ.get("BENCH_LABEL", ""))
    # scale-and-concurrency params
    p.setdefault("db", os.environ.get("BENCH_DB", "/tmp/rr_bench_sqlite/%d.db"))
    p.setdefault("io_ms", float(os.environ.get("BENCH_IO_MS", "0") or 0))
    p.setdefault("pdf", os.environ.get("BENCH_PDF", ""))
    p.setdefault("conn", os.environ.get("BENCH_CONN", "module"))  # "module" | "per_call"
    _PARAMS = p
    return p


def _busy(iters: int) -> float:
    s = 1.0
    for i in range(1, iters + 1):
        s += (i * i) % 7
    return s


def _sqlite_doc_work(conn, label, io_s):
    """One document's work: write it, read it back, commit, then a blocking I/O wait.
    AST-IDENTICAL in harness/lc_baselines.sqlite_doc_work (the LangChain side runs this exact
    body); concurrent-processing asserts the two sources are identical before any timed run."""
    cur = conn.execute("INSERT INTO docs (content) VALUES (?)", (label,))
    conn.execute("SELECT content FROM docs WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.commit()
    if io_s > 0:
        time.sleep(io_s)


_CONN = None  # the NAIVE module-level connection (conn="module") — one per task process


def _sqlite_conn(p):
    global _CONN
    if _CONN is None:
        import sqlite3

        db = p["db"]
        if "%d" in db:
            db = db % os.getpid()
        d = os.path.dirname(db)
        if d:
            os.makedirs(d, exist_ok=True)
        _CONN = sqlite3.connect(db)
        _CONN.execute("CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, content TEXT)")
    return _CONN


_DOC = None  # the NAIVE module-level fitz.Document (conn="module") — one per task process


def _pdf_doc(path):
    global _DOC
    if _DOC is None:
        import fitz

        _DOC = fitz.open(path)
    return _DOC


def _pdf_extract_all(doc):
    text = "".join(doc[i].get_text() for i in range(doc.page_count))
    return text


_STATE = []  # per-PROCESS instance data (iso_accumulate) — "each pipe is its own data"
_STATE_N = 0


def _obj_name(obj):
    """Best-effort doc identity from the data object (send(objinfo={'name': ...}))."""
    for probe in ("name", "filename", "objname"):
        try:
            v = getattr(obj, probe, None)
            if v:
                return str(v)
        except Exception:
            pass
        try:
            v = obj.get(probe) if hasattr(obj, "get") else None
            if v:
                return str(v)
        except Exception:
            pass
    try:
        info = getattr(obj, "objinfo", None) or (obj.get("objinfo") if hasattr(obj, "get") else None)
        if isinstance(info, dict) and info.get("name"):
            return str(info["name"])
    except Exception:
        pass
    return ""


class IInstance(IInstanceBase):
    def open(self, obj):
        p = _params()
        mode = p["mode"]
        label = p["label"]
        tid = threading.get_ident()
        pid = os.getpid()
        t0, e0 = time.perf_counter(), time.time()
        try:
            if mode == "cpu":
                iters = int(p["iters"])
                if iters > 0:
                    globals()["_SINK"] = _busy(iters)
            elif mode == "sleep":
                secs = float(p["seconds"])
                if secs > 0:
                    time.sleep(secs)
            elif mode == "http":
                import urllib.request

                try:
                    with urllib.request.urlopen(p["url"], timeout=120) as resp:
                        resp.read()
                except Exception as e:  # noqa: BLE001 - benchmark diagnostic
                    sys.stderr.write("RRBENCH_ERR\t%s\n" % e)
            elif mode == "crash":
                # hard crash of the task subprocess (simulates a native/segfault crash) —
                # D5 fault-isolation: in RR this kills only this run's subprocess; the server
                # and sibling runs survive (process-per-run). In-process frameworks die wholesale.
                sys.stderr.write("RRBENCH_CRASH\tpid=%d\n" % pid)
                sys.stderr.flush()
                os._exit(134)
            elif mode == "sqlite":
                import sqlite3

                try:
                    if p["conn"] == "per_call":
                        db = p["db"] % pid if "%d" in p["db"] else p["db"]
                        d = os.path.dirname(db)
                        if d:
                            os.makedirs(d, exist_ok=True)
                        conn = sqlite3.connect(db)
                        conn.execute(
                            "CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, content TEXT)")
                        try:
                            _sqlite_doc_work(conn, label or "doc", float(p["io_ms"]) / 1000.0)
                        finally:
                            conn.close()
                    else:  # "module": the naive shared-connection idiom (the LC-trap mirror)
                        _sqlite_doc_work(_sqlite_conn(p), label or "doc",
                                         float(p["io_ms"]) / 1000.0)
                except Exception as e:  # noqa: BLE001 - the failure IS the measurement
                    sys.stderr.write("RRBENCH_ERR\t%s: %s\n" % (type(e).__name__, e))
                    sys.stderr.flush()
            elif mode == "pdf_extract":
                try:
                    if p["conn"] == "per_call":
                        import fitz

                        doc = fitz.open(p["pdf"])
                        try:
                            text = _pdf_extract_all(doc)
                        finally:
                            doc.close()
                    else:  # "module": the naive shared-Document idiom (the LC-trap mirror)
                        text = _pdf_extract_all(_pdf_doc(p["pdf"]))
                    import hashlib

                    sys.stderr.write("RRBENCH_PDF\tchars=%d\tsha=%s\n"
                                     % (len(text), hashlib.sha256(text.encode()).hexdigest()[:16]))
                    sys.stderr.flush()
                except Exception as e:  # noqa: BLE001 - the failure IS the measurement
                    sys.stderr.write("RRBENCH_ERR\t%s: %s\n" % (type(e).__name__, e))
                    sys.stderr.flush()
            elif mode == "iso_accumulate":
                # per-pipe INSTANCE data: this process's local accumulator. The harness checks
                # each pipe ends with exactly its own docs — nothing lost, nothing leaked in.
                global _STATE_N
                name = _obj_name(obj)
                _STATE_N += 1
                _STATE.append(name or ("anon%d" % _STATE_N))
                sys.stderr.write("RRBENCH_STATE\tpid=%d\tn=%d\titems=%s\n"
                                 % (pid, len(_STATE), ",".join(_STATE)))
                sys.stderr.flush()
        finally:
            t1, e1 = time.perf_counter(), time.time()
            try:
                sys.stderr.write(
                    "RRBENCH\t%s\t%s\t%.6f\t%.6f\ttid=%d\tpid=%d\te0=%.6f\te1=%.6f\n"
                    % (label, mode, t0, t1, tid, pid, e0, e1)
                )
                sys.stderr.flush()
            except Exception:
                pass
