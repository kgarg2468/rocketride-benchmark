# fault-isolation · does a hard node crash stay contained?

> **Verdict: ✅ safe by default.** A node that hard-crashes (`os._exit(134)`, like a native segfault)
> kills **only its own run** — the server survives and the next run succeeds. When real LangChain runs
> the same 4 tasks in one interpreter, the hard process abort **terminates the shared interpreter and
> every task in it (0/4)** — there is no other process to fall back to. RocketRide runs each pipeline as
> its own process, so the abort is confined to the failing run **by construction** — no decision to get
> wrong. **Consistent across 10 fresh reps.**

## Hypothesis
Each pipeline runs as its own process, so a crashing node takes down only its run, not the server or
sibling runs. When many tasks share one interpreter, a hard process abort terminates the interpreter and
every task in it — there is nothing left to isolate them.

## Method
RocketRide: note the server pid; run a healthy pipeline; run one whose `workload` node calls
`os._exit(134)`; confirm the server pid is unchanged (survived); run a healthy pipeline again
(recovery). In-process competitor (**real LangChain**): one interpreter runs 4 tasks together (via
`RunnableLambda(leg).abatch`) where task #2 calls `os._exit(134)` — the abort kills the whole
interpreter, not just that task. A strict probe (`require_real_langchain`) records `lc_version` in
every row and **aborts the bench unless real LangChain is actually imported and executed** — no proxy
fallback; a healthy probe then confirms it runs 4/4 before the crash probe counts survivors.

## Results *(from each `run-0N/results.json`)*
| | RocketRide | real in-process LangChain |
|---|---|---|
| server / process survives the crash? | **✅ yes (same pid)** | **❌ process DIED (exit 134)** |
| healthy run after crash | ✅ recovered | — |
| tasks completed | isolated to 1 run | **0 / 4** |

`rr_isolation_holds = true`, `inproc_lost_all = true` — identical across all 10 reps.

## Provenance
**10 fresh local reps** (`run-01/ … run-10/`), runtime v3.2.1.30 (`114509c6`). Real LangChain
**`lc_version 0.3.86`** is recorded in every `run-0N/results.json`, proven per rep by the strict probe
(no proxy fallback). Deterministic; every rep agrees. (`fault-isolation` uses `ttl=0` single runs —
no warm pool — so it re-runs fast and clean.)

## Inference
Because each run is its own runtime process, even a native-level crash is contained — the server and
other runs are untouched, and new runs work immediately. A shared interpreter can't contain a hard
process abort: when real in-process LangChain runs the 4 tasks in one interpreter, the abort terminates
the interpreter and takes every concurrent task with it (0/4). This is the same reason one crashed browser
tab doesn't take down the rest of the browser: each tab — like each RocketRide pipe — is its own OS
process, and an OS process boundary is a wall a crash cannot cross.

## Reproduce
[`../../harness/REPRODUCE.md`](../../harness/REPRODUCE.md) — fast, no warm pool needed.

## Runnable demo
Beside the stub:
[`demo.pipe`](../../harness/rocketride-bench/groups/robustness-and-isolation/fault-isolation/demo.pipe)
(`filesys → parse → question → prompt → llm_openai → response_answers`) reads a folder of good docs +
one malformed file — only the bad file's run fails, the server survives, the good runs complete. Run:
`cd concurrent-work/harness && python run_demo.py crash` (needs `ROCKETRIDE_OPENAI_KEY`); see the folder
[`README.md`](../../harness/rocketride-bench/groups/robustness-and-isolation/fault-isolation/README.md).
This is a contained *soft* fault (a real parse error), not the table's hard `os._exit`.
