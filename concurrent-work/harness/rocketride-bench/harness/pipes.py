"""Author `.pipe` files programmatically with valid `ui` coordinates.

The SAME authored `.pipe` runs headless via use(filepath=) AND opens in the VS Code extension
canvas (auto_layout gives every node a position). Topology is fixed per benchmark; the work
MODE (cpu/sleep/http) is injected separately via set_params() (the node reads a params file),
so one `.pipe` serves an entire threadCount/params sweep. filesys input paths use the portable
${ROCKETRIDE_BENCH_DATA} placeholder (substituted from use(env=...)) so files stay committable
and machine-independent.
"""
import json
import os

from . import config

DATA_PLACEHOLDER = "${ROCKETRIDE_BENCH_DATA}"


def set_params(mode="none", iters=0, seconds=0.0, url="http://127.0.0.1:8799/", label="",
               **extra):
    """Write the params file the workload node reads (call once, before use()).
    `extra` carries the scale-and-concurrency params (db, io_ms, pdf, conn) straight through."""
    params = {"mode": mode, "iters": int(iters), "seconds": float(seconds),
              "url": url, "label": label}
    params.update(extra)
    with open(config.BENCH_PARAMS, "w") as f:
        json.dump(params, f)
    return config.BENCH_PARAMS


def data_env():
    """env mapping to pass to Bench.run_pipe so ${ROCKETRIDE_BENCH_DATA} resolves."""
    return {"ROCKETRIDE_BENCH_DATA": config.DATA_DIR}


# --- node factories ---------------------------------------------------------
def filesys_node(subdir, cid="src_1"):
    path = DATA_PLACEHOLDER + "/" + subdir.strip("/")
    return {"id": cid, "provider": "filesys",
            "config": {"include": [{"path": path}], "key": "filesys://*",
                       "mode": "Source", "type": "filesys"}}


def workload_node(cid, src, lane="tags"):
    return {"id": cid, "provider": "workload", "config": {},
            "input": [{"from": src, "lane": lane}]}


def webhook_node(cid="webhook_1"):
    """send()-driven source — the warm resident-pipe entry point (group 7 / warm-vs-cold)."""
    return {"id": cid, "provider": "webhook",
            "config": {"hideForm": True, "mode": "Source", "type": "webhook",
                       "parameters": {}}}


# --- layout + assembly ------------------------------------------------------
def _depths(components):
    by_id = {c["id"]: c for c in components}
    memo = {}

    def depth(cid, seen):
        if cid in memo:
            return memo[cid]
        c = by_id.get(cid)
        ins = [e.get("from") for e in (c.get("input") or [])] if c else []
        ins = [s for s in ins if s and s != cid and s not in seen]
        d = 0 if not ins else 1 + max(depth(s, seen | {cid}) for s in ins)
        memo[cid] = d
        return d

    return {c["id"]: depth(c["id"], set()) for c in components}


def auto_layout(components, x0=40, y0=120, dx=220, dy=150):
    """Assign ui.position left→right by topological depth; siblings stacked vertically."""
    depths = _depths(components)
    cols = {}
    for c in components:
        cols.setdefault(depths[c["id"]], []).append(c)
    for d, group in cols.items():
        for i, c in enumerate(group):
            prov = str(c.get("provider", ""))
            h = 135 if prov == "qdrant" else (86 if "agent" in prov else 66)
            c["ui"] = {"position": {"x": x0 + d * dx, "y": y0 + i * dy},
                       "measured": {"width": 150, "height": h},
                       "nodeType": "default", "formDataValid": True}
    return components


def make_pipe(components, source=None, project_id="00000000-0000-4000-8000-0000000000aa"):
    auto_layout(components)
    pipe = {"components": components, "project_id": project_id,
            "viewport": {"x": 0, "y": 0, "zoom": 1}, "version": 1}
    if source is None:
        for c in components:
            if str((c.get("config") or {}).get("mode", "")).lower() == "source":
                source = c["id"]
                break
    if source:
        pipe["source"] = source
    return pipe


def write_pipe(path, pipe):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(pipe, f, indent=2)
        f.write("\n")
    return path


# --- standard benchmark shapes ----------------------------------------------
def filesys_work(subdir, work_id="work_1"):
    """filesys(dir) → workload  (terminal; the item-queue/threadCount workload)."""
    return make_pipe([filesys_node(subdir), workload_node(work_id, "src_1")], source="src_1")


def webhook_work(work_id="work_1"):
    """webhook → workload  (terminal; the warm resident send()-per-doc workload)."""
    return make_pipe([webhook_node(), workload_node(work_id, "webhook_1")],
                     source="webhook_1")


def filesys_chain(subdir, k):
    """filesys(dir) → workload × k chained  (A2 per-node dispatch)."""
    comps = [filesys_node(subdir)]
    prev = "src_1"
    for i in range(k):
        nid = "work_%d" % i
        comps.append(workload_node(nid, prev))
        prev = nid
    return make_pipe(comps, source="src_1")


def filesys_fanout(subdir, k):
    """filesys(dir) → { workload × k } siblings off the SAME source  (B3 branch fan-out)."""
    comps = [filesys_node(subdir)]
    for i in range(k):
        comps.append(workload_node("branch_%d" % i, "src_1"))
    return make_pipe(comps, source="src_1")


def embedding_pipe(subdir, with_embed=True, profile="miniLM"):
    """filesys(docs) → parse → preprocessor_langchain(512) → [embedding_transformer(miniLM)].

    Node configs copied verbatim from the committed working pipe
    authoring-tokens/rr/rag.pipe (the real ingest path, minus the vector store). The
    embedding-overhead benchmark runs this twice — `with_embed=True` (full) and `False`
    (control) — so wall(full) − wall(control) isolates the embedding node's cost (compute +
    cross-process vector serialization), with per-run boot cancelling out."""
    comps = [
        filesys_node(subdir),
        {"id": "parse_1", "provider": "parse", "config": {},
         "input": [{"from": "src_1", "lane": "tags"}]},
        {"id": "prep_1", "provider": "preprocessor_langchain",
         "config": {"profile": "default",
                    "default": {"mode": "strlen", "splitter": "RecursiveCharacterTextSplitter", "strlen": 512},
                    "parameters": {}},
         "input": [{"from": "parse_1", "lane": "text"}]},
    ]
    if with_embed:
        comps.append({"id": "embed_1", "provider": "embedding_transformer",
                      "config": {"profile": profile, "parameters": {}},
                      "input": [{"from": "prep_1", "lane": "documents"}]})
    return make_pipe(comps, source="src_1")
