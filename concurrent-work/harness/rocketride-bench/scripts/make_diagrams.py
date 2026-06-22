"""Generate a committed graph diagram from a .pipe — the headless "canvas view".

Reads components[].input/control edges + provider names and emits Mermaid (renders inline on
GitHub) and Graphviz DOT (PNG too if `dot` is on PATH). This shows the exact pipeline shape in
a report without needing the GUI; the real extension canvas screenshot is an optional add-on.

  python scripts/make_diagrams.py <pipeline.pipe> [out_basename]    # default: alongside the .pipe as canvas.*
"""
import json
import os
import re
import shutil
import subprocess
import sys


def load(path):
    with open(path) as f:
        d = json.load(f)
    return d.get("pipeline", d) if isinstance(d, dict) else d


def _safe(s):
    return re.sub(r"\W", "_", str(s))


def _is_source(c):
    return str((c.get("config") or {}).get("mode", "")).lower() == "source"


def mermaid(pipe):
    out = ["graph LR"]
    for c in pipe.get("components", []):
        cid, prov = c["id"], c.get("provider", "")
        shape = ('([%s])' if _is_source(c) else '["%s"]')
        label = "%s<br/><i>%s</i>" % (cid, prov)
        out.append("  %s%s" % (_safe(cid), shape % label))
    for c in pipe.get("components", []):
        for e in (c.get("input") or []):
            out.append("  %s -->|%s| %s" % (_safe(e.get("from")), e.get("lane", ""), _safe(c["id"])))
        for e in (c.get("control") or []):
            out.append("  %s -.->|%s| %s" % (_safe(e.get("from")), e.get("classType", "tool"), _safe(c["id"])))
    return "\n".join(out) + "\n"


def dot(pipe):
    out = ["digraph pipeline {", "  rankdir=LR;", '  node [shape=box, style=rounded, fontname="Helvetica"];']
    for c in pipe.get("components", []):
        cid, prov = c["id"], c.get("provider", "")
        shape = "shape=stadium" if _is_source(c) else "shape=box"
        out.append('  %s [label="%s\\n%s", %s];' % (_safe(cid), cid, prov, shape))
    for c in pipe.get("components", []):
        for e in (c.get("input") or []):
            out.append('  %s -> %s [label="%s"];' % (_safe(e.get("from")), _safe(c["id"]), e.get("lane", "")))
        for e in (c.get("control") or []):
            out.append('  %s -> %s [style=dashed, label="%s"];' % (_safe(e.get("from")), _safe(c["id"]), e.get("classType", "tool")))
    out.append("}")
    return "\n".join(out) + "\n"


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    pipe_path = argv[0]
    base = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(pipe_path), "canvas")
    pipe = load(pipe_path)
    with open(base + ".mmd", "w") as f:
        f.write(mermaid(pipe))
    with open(base + ".dot", "w") as f:
        f.write(dot(pipe))
    made = [base + ".mmd", base + ".dot"]
    if shutil.which("dot"):
        try:
            subprocess.run(["dot", "-Tpng", base + ".dot", "-o", base + ".png"], check=True)
            made.append(base + ".png")
        except Exception as e:
            print("dot PNG render failed:", e)
    print("wrote:", *(os.path.basename(m) for m in made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
