"""Parse the `workload` node's RRBENCH stderr markers (forwarded as OUTPUT events).

Each marker is the TRUE in-process timing (perf_counter measured inside the node), plus the
OS thread id and process id — the ground truth we cross-check the client-stamped flow spans
against. Marker format (see nodes/workload/IInstance.py):

    RRBENCH \t label \t mode \t t0_perf \t t1_perf \t tid=.. \t pid=.. \t e0=epoch \t e1=epoch
"""
import re

MARKER_RE = re.compile(
    r"RRBENCH\t([^\t]*)\t([^\t]*)\t([0-9.]+)\t([0-9.]+)\ttid=(\d+)\tpid=(\d+)\te0=([0-9.]+)\te1=([0-9.]+)"
)


def _strings(obj):
    """Yield every string anywhere inside an event message."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def parse_markers(events):
    """events = [{recv_ns, t_epoch, msg}, ...] → list of marker dicts."""
    rows = []
    for e in events:
        msg = e.get("msg", e) if isinstance(e, dict) else e
        for s in _strings(msg):
            if "RRBENCH\t" not in s:
                continue
            for m in MARKER_RE.finditer(s):
                label, mode, t0, t1, tid, pid, e0, e1 = m.groups()
                rows.append({
                    "label": label, "mode": mode,
                    "t0": float(t0), "t1": float(t1), "span": float(t1) - float(t0),
                    "tid": int(tid), "pid": int(pid),
                    "e0": float(e0), "e1": float(e1),
                    "recv_ns": e.get("recv_ns") if isinstance(e, dict) else None,
                })
    return rows


def work_span(rows, clock="epoch"):
    """Wall span covering all markers (last finish − first start)."""
    if not rows:
        return 0.0
    a, b = ("e0", "e1") if clock == "epoch" else ("t0", "t1")
    return max(r[b] for r in rows) - min(r[a] for r in rows)


def max_overlap(rows, clock="epoch"):
    """Max number of marker intervals overlapping at any instant.
    epoch+pid → cross-process parallelism; perf+tid → intra-process (GIL/I/O) concurrency.
    overlap==1 ⇒ strictly sequential; overlap==N ⇒ N ran simultaneously."""
    a, b = ("e0", "e1") if clock == "epoch" else ("t0", "t1")
    pts = []
    for r in rows:
        pts.append((r[a], 1))
        pts.append((r[b], -1))
    pts.sort(key=lambda x: (x[0], x[1]))
    cur = best = 0
    for _, delta in pts:
        cur += delta
        best = max(best, cur)
    return best


def distinct(rows, key):
    return sorted({r[key] for r in rows})
