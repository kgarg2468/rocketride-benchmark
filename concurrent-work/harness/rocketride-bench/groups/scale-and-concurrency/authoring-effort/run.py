"""authoring-effort — what the author must WRITE (and know) for "same pipeline, 64 docs".

Static comparison, no timing. RocketRide: ONE declarative .pipe (validated offline against
the catalog; the runtime owns concurrency, isolation and scheduling — there is no concurrency
code to write). LangChain: the author picks one of THREE imperative idioms — and as
concurrent-processing measures, one crashes outright, one silently serializes, one is slow (crash / silent 64x
serialization); the correct one requires knowing thread-affinity rules the API never
surfaces. We count imperative lines and the hidden knowledge ("decision points") per file.

HONESTY: token-count favors LangChain — authoring-tokens (group 5) measured .pipe JSON at
~1.1-2.4x MORE tokens than equivalent LC code, and this report cross-links it. The claim
here is narrower: ZERO imperative concurrency code and a validated artifact, not "fewer
tokens".

Run:  python groups/scale-and-concurrency/authoring-effort/run.py   (engine optional —
validate() runs if the server is up, else recorded as skipped)
"""
import asyncio
import json
import os
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)

from harness import config, pipes  # noqa: E402

LC_FILES = ["concurrent_batch.py", "concurrent_abatch.py", "concurrent_seq.py", "concurrent_percall.py"]
# the hidden knowledge each LC file demands (annotated; the trap is WHICH file you write)
DECISIONS = {
    "concurrent_batch.py": ["batch vs abatch vs loop", "max_concurrency value",
                        ".batch uses threads (implicit)"],
    "concurrent_abatch.py": ["batch vs abatch vs loop", "max_concurrency value",
                         "sync vs async chain legs", "blocking-sync-in-async serializes "
                         "(implicit, silent)"],
    "concurrent_seq.py": ["batch vs abatch vs loop (gave up concurrency)"],
    "concurrent_percall.py": ["batch vs abatch vs loop", "max_concurrency value",
                          ".batch uses threads (implicit)",
                          "sqlite conns are thread-affine (library doc)",
                          "therefore: state per call, never captured (discipline)"],
}


def code_lines(path):
    """Non-blank, non-comment source lines (tokenize-based, docstrings count as code)."""
    lines = set()
    with open(path, "rb") as f:
        for tok in tokenize.tokenize(f.readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                            tokenize.ENCODING, tokenize.INDENT, tokenize.DEDENT,
                            tokenize.ENDMARKER):
                continue
            for ln in range(tok.start[0], tok.end[0] + 1):
                lines.add(ln)
    return len(lines)


async def try_validate(pipe_path):
    try:
        from harness import client as rrclient
        c = await rrclient.connect()
        try:
            v = await rrclient.validate_pipeline(c, rrclient.load_pipe(pipe_path))
        finally:
            await c.disconnect()
        return {"ran": True, "ok": v["ok"], "errors": v["errors"]}
    except Exception as e:  # engine not up — validation recorded as skipped, not faked
        return {"ran": False, "ok": None, "note": "engine not reachable: %r" % e}


def main():
    # the committed RR artifact: the SAME pipe concurrent-processing runs
    rr_pipe = os.path.join(HERE, "rr", "workflow.pipe")
    pipes.write_pipe(rr_pipe, pipes.webhook_work())
    rr_doc = json.load(open(rr_pipe))
    validation = asyncio.run(try_validate(rr_pipe))

    lc_rows = []
    for f in LC_FILES:
        p = os.path.join(HERE, "lc", f)
        lc_rows.append({"file": "lc/" + f, "imperative_lines": code_lines(p),
                        "decision_points": len(DECISIONS[f]), "decisions": DECISIONS[f]})

    out = {
        "benchmark": "authoring-effort",
        "hypothesis": "RR authoring carries zero imperative concurrency code and validates "
                      "offline; LangChain authoring forces an unguided 3-way concurrency "
                      "choice where one crashes, one silently serializes, one is slow (measured in concurrent-processing)",
        "provenance": config.provenance(),
        "rocketride": {
            "file": "rr/workflow.pipe",
            "imperative_lines": 0,
            "components": len(rr_doc["components"]),
            "decision_points": 0,
            "note": "concurrency/isolation owned by the runtime (M pipes, ttl= are "
                    "RUN-time args, not authored code); each pipeline runs as its own process, "
                    "so isolation is per-pipe by construction; artifact is schema-validated",
            "validate": validation,
        },
        "langchain": lc_rows,
        "scope": {
            "note": "this claim is about imperative concurrency lines, not token count",
        },
        "verdict_metrics": {
            "rr_imperative_lines": 0,
            "lc_imperative_lines_min": min(r["imperative_lines"] for r in lc_rows),
            "lc_imperative_lines_max": max(r["imperative_lines"] for r in lc_rows),
            "lc_decision_points_correct_version":
                next(r["decision_points"] for r in lc_rows if r["file"].endswith("percall.py")),
            "lc_natural_idioms_delivering_concurrency": 0,
            "lc_idiom_outcomes": {"batch": "crashes", "abatch": "silently_serializes", "seq": "slow_correct"},
        },
    }
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("RR: rr/workflow.pipe — 0 imperative lines, %d components, validate: %s"
          % (out["rocketride"]["components"],
             "PASS" if validation.get("ok") else ("skipped" if not validation["ran"] else "FAIL")))
    for r in lc_rows:
        print("LC: %-22s %2d imperative lines, %d decision points"
              % (r["file"], r["imperative_lines"], r["decision_points"]))
    print("\nVERDICT: the correct LC version needs %d pieces of hidden knowledge; "
          "one crashes, one silently serializes, one is slow (see concurrent-processing). RR authors zero "
          "concurrency code (this claim is about imperative concurrency lines, not token count)."
          % out["verdict_metrics"]["lc_decision_points_correct_version"])


if __name__ == "__main__":
    main()
