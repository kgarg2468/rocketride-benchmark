"""Reconstruct per-node spans from apaevt_flow enter/leave events.

IMPORTANT (disclosed in every report): apaevt_flow events carry NO server timestamp, so a span
is computed from the CLIENT receive clock (perf_counter_ns) and therefore INCLUDES DAP/IPC
delivery jitter. Spans are an ESTIMATE; the ground-truth in-process timing is the workload
RRBENCH marker (see markers.py). Line numbers are 1-based into the committed JSONL, so a report
can cite e.g. `trace/rr.tc4.jsonl:142-158`.
"""


def _body(ev):
    msg = ev.get("msg") if isinstance(ev, dict) else None
    return msg.get("body", {}) if isinstance(msg, dict) else {}


def _is_flow(ev):
    return isinstance(ev.get("msg"), dict) and ev["msg"].get("event") == "apaevt_flow"


def reconstruct_spans(events):
    """events (in JSONL order) → per-node spans.

    apaevt_flow `op` is begin|enter|leave|end and `pipes` is a LIFO path stack: on enter/begin
    the deepest element (pipes[-1]) is the thing entered (a node id, or the object name for
    begin); on leave/end pipes is already popped to the parent. So we keep one LIFO stack per
    object (keyed by source + object id) and pop it on leave/end — pairing each push with its
    close regardless of nesting. `kind` distinguishes node-level (enter/leave) from the
    whole-object bracket (begin/end)."""
    stacks = {}
    spans = []
    for i, e in enumerate(events):
        if not _is_flow(e):
            continue
        b = _body(e)
        op = str(b.get("op", "")).lower()
        ns = e.get("recv_ns")
        line = i + 1  # 1-based JSONL line
        key = (b.get("source"), b.get("id"))
        pipes = b.get("pipes") or []
        node = pipes[-1] if pipes else None
        lane = (b.get("trace") or {}).get("lane")
        if op in ("enter", "begin"):
            stacks.setdefault(key, []).append({
                "node": node, "kind": "object" if op == "begin" else "node",
                "lane": lane, "enter_line": line, "enter_ns": ns})
        elif op in ("leave", "end"):
            st = stacks.get(key)
            if st:
                top = st.pop()
                spans.append({
                    "node": top["node"], "kind": top["kind"], "lane": top["lane"],
                    "object": b.get("id"), "source": b.get("source"),
                    "enter_line": top["enter_line"], "leave_line": line,
                    "enter_ns": top["enter_ns"], "leave_ns": ns,
                    "span_s": (ns - top["enter_ns"]) / 1e9
                    if (ns is not None and top["enter_ns"] is not None) else None,
                })
    return spans


def span_table(spans):
    """Aggregate spans per node: count + total + max span (seconds)."""
    agg = {}
    for s in spans:
        a = agg.setdefault(s["node"], {"node": s["node"], "count": 0, "total_s": 0.0, "max_s": 0.0})
        a["count"] += 1
        if s["span_s"] is not None:
            a["total_s"] += s["span_s"]
            a["max_s"] = max(a["max_s"], s["span_s"])
    return sorted(agg.values(), key=lambda x: -x["total_s"])


def last_status(events):
    """Most recent apaevt_status_update body (carries metrics + tokens)."""
    body = {}
    for e in events:
        msg = e.get("msg") if isinstance(e, dict) else None
        if isinstance(msg, dict) and msg.get("event") == "apaevt_status_update":
            body = msg.get("body", {}) or body
    return body


def cost_usd(events):
    """RR self-reported cost: tokens.total / 100 = $ (from the last status update)."""
    body = last_status(events)
    tokens = body.get("tokens") if isinstance(body, dict) else None
    if isinstance(tokens, dict) and tokens.get("total") is not None:
        try:
            return float(tokens["total"]) / 100.0
        except (TypeError, ValueError):
            return None
    return None
