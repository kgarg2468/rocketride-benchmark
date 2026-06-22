#!/usr/bin/env python3
"""Measure RocketRide `.pipe` vs LangChain Python artifact size across the 5 builds, reusing
`artifact_size.py` (committed in this folder). Writes `results.json`.

Each build is the SAME meeting-notes workflow, AI-built (Claude Code) in each framework — built with
the RocketRide pipeline-building skills on one side, and as an idiomatic Python package on the other.

Run:  python measure.py
"""
import json
import os
import statistics as st

from artifact_size import langchain_descriptors, rocketride_descriptors

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.join(HERE, "builds")
RUNS = ["01", "02", "03", "04", "05"]

builds = []
for n in RUNS:
    rr = rocketride_descriptors(os.path.join(B, "rocketride", f"run-{n}", "meeting-notes-assistant.pipe"))
    lc = langchain_descriptors(os.path.join(B, "langchain", f"lc-{n}"))
    builds.append({
        "build": f"run-{n}",
        "rocketride": {"pipe_lines": rr["pipe_lines"], "chars": rr["chars"], "nodes": rr["nodes"]},
        "langchain": {"loc_total": lc["loc_total"], "sloc": lc["sloc"], "chars": lc["chars"], "files": lc["files"]},
        "ratio_lines": round(lc["loc_total"] / rr["pipe_lines"], 1),
        "ratio_chars": round(lc["chars"] / rr["chars"], 1),
    })

rr_lines = [b["rocketride"]["pipe_lines"] for b in builds]
lc_lines = [b["langchain"]["loc_total"] for b in builds]
rr_chars = [b["rocketride"]["chars"] for b in builds]
lc_chars = [b["langchain"]["chars"] for b in builds]
ratios = [b["ratio_lines"] for b in builds]

aggregate = {
    "n_builds": len(builds),
    "workflow": "meeting-notes assistant (transcript -> executive summary + follow-up email)",
    "rocketride_lines": {"min": min(rr_lines), "median": st.median(rr_lines), "max": max(rr_lines)},
    "langchain_lines": {"min": min(lc_lines), "median": st.median(lc_lines), "max": max(lc_lines)},
    "line_ratio_lc_over_rr": {"min": min(ratios), "median": st.median(ratios), "max": max(ratios)},
    "rocketride_chars_median": int(st.median(rr_chars)),
    "langchain_chars_median": int(st.median(lc_chars)),
    "char_ratio_lc_over_rr_median": round(st.median(lc_chars) / st.median(rr_chars), 1),
}

out = {
    "benchmark": "lines-of-code",
    "method": ("Claude Code built the SAME meeting-notes workflow 5x in RocketRide (with the pipeline "
               "skills) and 5x in LangChain (idiomatic Python package). RocketRide artifact = one .pipe "
               "(declarative JSON); LangChain artifact = a Python package. Lines = artifact_size.py "
               "(pipe_lines for the .pipe, loc_total summed over the package's .py files); chars = raw "
               "character count. Reproduce: python measure.py."),
    "aggregate": aggregate,
    "builds": builds,
}
with open(os.path.join(HERE, "results.json"), "w") as f:
    json.dump(out, f, indent=2)

print(json.dumps(aggregate, indent=2))
