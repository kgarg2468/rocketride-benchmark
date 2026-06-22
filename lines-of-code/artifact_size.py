#!/usr/bin/env python3
"""Structural size descriptors for a build artifact — reported PER SIDE, never as one
cross-language LOC number. A 250-line JSON config and a 630-line Python program are not the
same unit, and the .pipe delegates orchestration to the managed runtime (so its line/node
count understates the machinery it invokes). So we describe each side's structure separately.

  artifact_size.py langchain  <dir>          # a folder of .py files (.venv / site-packages excluded)
  artifact_size.py rocketride <file.pipe>    # the .pipe JSON

Prints a summary and writes artifact_size.json next to the input (override with --out). Pure stdlib.
"""
import glob
import json
import os
import re
import sys


def _count_leaves(o):
    if isinstance(o, dict):
        return sum(_count_leaves(v) for v in o.values())
    if isinstance(o, list):
        return sum(_count_leaves(v) for v in o)
    return 1


def langchain_descriptors(d):
    pyfiles = [f for f in glob.glob(os.path.join(d, "**", "*.py"), recursive=True)
               if ".venv" not in f and "__pycache__" not in f and "/site-packages/" not in f]
    loc = sloc = chars = funcs = classes = imports = 0
    for f in sorted(pyfiles):
        try:
            lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        for ln in lines:
            loc += 1
            chars += len(ln) + 1
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            sloc += 1
            if re.match(r"(async\s+)?def\s", s):
                funcs += 1
            elif s.startswith("class "):
                classes += 1
            elif s.startswith(("import ", "from ")):
                imports += 1
    return {
        "kind": "python-package",
        "files": len(pyfiles),
        "loc_total": loc,
        "sloc": sloc,                       # non-blank, non-comment
        "functions": funcs,
        "classes": classes,
        "import_lines": imports,
        "chars": chars,
        "author_maintained_components": funcs + classes,
    }


def rocketride_descriptors(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    lines = raw.count("\n") + 1
    nodes = providers = params = 0
    provset = set()
    try:
        j = json.loads(raw)
        comps = j.get("components", []) if isinstance(j, dict) else []
        nodes = len(comps)
        for c in comps:
            p = c.get("provider")
            if p:
                provset.add(p)
            params += _count_leaves(c.get("config", {}) or {})
        providers = len(provset)
    except ValueError:
        pass
    return {
        "kind": "rocketride-pipe",
        "pipe_lines": lines,
        "nodes": nodes,
        "distinct_providers": providers,
        "provider_set": sorted(provset),
        "configured_params": params,        # leaf values the author set
        "chars": len(raw),
        "author_maintained_components": nodes,
        "note": "the .pipe delegates orchestration to the managed runtime; line/node counts "
                "UNDERSTATE the machinery invoked. Not comparable to Python LOC as one unit.",
    }


def main(argv):
    if len(argv) < 2 or argv[0] not in ("langchain", "rocketride"):
        print(__doc__)
        return 2
    side, target = argv[0], argv[1]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    if side == "langchain":
        d = target if os.path.isdir(target) else os.path.dirname(target)
        res = langchain_descriptors(d)
    else:
        res = rocketride_descriptors(target)
    res["side"] = side
    res["source"] = os.path.abspath(target)
    print(json.dumps(res, indent=2))
    if not out:
        base = target if os.path.isdir(target) else os.path.dirname(os.path.abspath(target))
        out = os.path.join(base, "artifact_size.json")
    json.dump(res, open(out, "w"), indent=2)
    print("\nwrote %s" % out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
