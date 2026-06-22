# authoring-effort · what you must write (and know) for "same pipeline, 64 docs"

> **Verdict: ✅ zero imperative concurrency code vs an unguided 3-way trap.** RocketRide's artifact is
> one declarative `.pipe` (2 components, schema-`validate()`d offline, **0 imperative lines**) —
> concurrency, isolation and scheduling are runtime-owned run arguments. The equivalent LangChain
> program is **14–17 imperative lines plus a forced choice among three invocation idioms** — and (per
> [concurrent-processing](../concurrent-processing/)) **one crashes outright, one silently serializes,
> one is slow**. The correct version needs **5 pieces of knowledge the API never surfaces**.

## Hypothesis
The authoring gap isn't size — it's that LangChain makes the AUTHOR own the concurrency model (an
invisible correctness decision), while RocketRide's author ships a validated dataflow and the runtime
owns execution.

## Method
Static artifacts, committed side by side; no timing. `rr/workflow.pipe` (the same pipe concurrent-processing
runs: webhook → workload) is `validate()`-checked against the live catalog. The four `lc/concurrent_*.py`
files are the four ways a LangChain author writes the same job, exactly as concurrent-processing executes
them. Imperative lines = tokenize-based non-blank/non-comment count; decision points = the annotated
knowledge each file demands (listed verbatim in `results.json`).

## Results *(from `results.json`)*
| Artifact | Imperative lines | Hidden decisions | Outcome ([concurrent-processing](../concurrent-processing/)) |
|---|---:|---:|---|
| **`rr/workflow.pipe`** | **0** (2 components) | **0** | ✅ 64/64, 0 errors |
| `lc/concurrent_batch.py` | 14 | 3 | ❌ crash (`sqlite3.ProgrammingError`) |
| `lc/concurrent_abatch.py` | 17 | 4 | ⚠️ silently serializes |
| `lc/concurrent_seq.py` | 14 | 1 | ⚠️ 64× work |
| `lc/concurrent_percall.py` | 17 | **5** | ✅ fast and safe |

The five decisions the *correct* version demands: batch-vs-abatch-vs-loop · `max_concurrency` ·
".batch uses threads" (implicit) · "sqlite connections are thread-affine" (library doc) · "therefore
create state per call, never capture it" (discipline). RocketRide externalizes all five into run
arguments (`M` pipes, `ttl=`) — each pipeline runs as its own process, so isolation is per-pipe, by
construction.

**Scope — this is an authoring claim, not a speed claim.** The correct `concurrent_percall.py` *is* genuinely concurrent and fast; the point is that reaching that correctness costs **17 imperative lines + 5 facts** an author must already know, where RocketRide's default needs **0** — and the idiom the API actually steers you toward (`.batch`) still crashes.

## Why each hidden fact is load-bearing
These aren't style preferences — each is the only thing standing between the author and a specific failure, and none is surfaced by the API. (1) ".batch uses threads": under CPython's GIL, threads share memory without true parallelism, so any captured connection or dict is now a shared-state hazard. (2) "SQLite connections are thread-affine": a connection may only be used on the thread that created it, so a `.batch` thread pool over a captured connection raises `sqlite3.ProgrammingError` — the crash in concurrent-processing. (3) "therefore create state per call, never capture it": the only fix is to open a fresh connection inside each call so no connection ever crosses a thread boundary. (4) batch-vs-abatch-vs-loop and (5) `max_concurrency` then decide whether the safe version is also concurrent (`.abatch` would re-serialize on the blocking call). RocketRide externalizes all five: each pipe is its own process, so state is per-process by construction and the author writes none of this.

## Provenance
**Fresh local** static run (`results.json`). Runtime optional for this one; `validate()` ran against the
live catalog (PASS).

## Reproduce
[`../../harness/REPRODUCE.md`](../../harness/REPRODUCE.md) (runtime optional for this bench).

## Runnable demo
Beside the runtime-generated bench artifact:
[`demo.pipe`](../../harness/rocketride-bench/groups/scale-and-concurrency/authoring-effort/demo.pipe)
is a real declarative multi-agent app (a Deep Agent orchestrator + 2 parallel sub-agents on OpenAI +
Gemini) — 3 LLM calls, **0 orchestration lines**. Run:
`cd concurrent-work/harness && python run_demo.py authoring` (needs `ROCKETRIDE_OPENAI_KEY` +
`ROCKETRIDE_GOOGLE_KEY`); see the folder
[`README.md`](../../harness/rocketride-bench/groups/scale-and-concurrency/authoring-effort/README.md).
