# summary · the consolidated verdict

> **RocketRide reaches correct-by-default concurrency with 0 lines of concurrency code.** On concurrent
> stateful work, RocketRide's declarative default is safe by construction — **0 imperative concurrency
> lines** — where a correct LangChain version takes **14–17 lines + up to 5 non-obvious facts** (code a
> developer still owns and maintains, whether hand-written or AI-generated), and the natural default
> still fails outright: silently losing **38–84%** of updates, **crashing**, or **losing every task to
> one fault** (all N=10).

> **0 vs 17 lines of concurrency code · 0 vs 5 hidden gotchas · 0% vs 38–84% data loss · correct by default.**

**Scope — correctness and authoring, not speed.** A hand-tuned correct LangChain variant (`concurrent_percall.py`) *is* genuinely concurrent and, on raw wall-clock, competitive with RocketRide's warm pool — so we make no speed claim, and we compare RocketRide's by-default behavior against LangChain's *correct* variant, never only the crashing one. The win we claim: RocketRide reaches that same correctness with **0 imperative concurrency lines and 0 hidden decisions**, where the correct LangChain path costs **14–17 lines plus 5 non-obvious facts** an author must already know — and the path the API steers you toward still crashes, silently serializes, or loses data.

This is the consolidated view of the concurrency-correctness experiment in
[`../concurrent-work/`](../concurrent-work/) (N=10). Every number traces to a committed `results.json`
there. The full grid is in [`capability-ledger.md`](capability-ledger.md); the pre-registered claim +
method is in [`PRE-REGISTRATION.md`](PRE-REGISTRATION.md).

**Runnable demos.** Each claim also ships a real, runnable pipeline under `concurrent-work/`:
[`concurrent-processing`](../concurrent-work/harness/rocketride-bench/groups/scale-and-concurrency/concurrent-processing/README.md) ·
[`data-isolation`](../concurrent-work/harness/rocketride-bench/groups/scale-and-concurrency/data-isolation/README.md) ·
[`fault-isolation`](../concurrent-work/harness/rocketride-bench/groups/robustness-and-isolation/fault-isolation/README.md) ·
[`authoring-effort`](../concurrent-work/harness/rocketride-bench/groups/scale-and-concurrency/authoring-effort/README.md)
— each a real-node `demo.pipe` driven by `harness/run_demo.py`.

## Method
Real langchain-core `0.3.86` (recorded per row) · identical per-doc work (AST parity gate on the processing function) · runtime
v3.2.1.30 (hash 114509c6) · Apple M5 Pro, 18 cores, 24 GiB · CPython 3.12.13 · **10 runs each**. Pool
sizes: concurrent-processing M={8,16}, data-isolation M=32.

## Authoring cost
| Metric | RocketRide (`rr/workflow.pipe`) | LangChain (`concurrent_percall.py`) |
|---|---:|---:|
| Imperative concurrency lines | **0** | **17** |
| Hidden decision-points | **0** | **5** |
| Components the author maintains | 2 declarative nodes | 1 function + 5 facts to know |
| Natural idioms that deliver concurrency | n/a | **0 of 3** (one crashes, one silently serializes, one is slow) |

The 5 facts the correct version needs (none surfaced by the API): batch-vs-abatch-vs-loop ·
`max_concurrency` · ".batch uses threads" · "sqlite connections are thread-affine" · "create state per
call, never capture it." Source: [`authoring-effort`](../concurrent-work/runs/authoring-effort/REPORT.md).

## What the default idiom does
| Benchmark (N=10) | LangChain default | RocketRide default |
|---|---|---|
| [data-isolation](../concurrent-work/runs/data-isolation/REPORT.md) (M=32) | shared dict → **silently loses 96–215 of 256 (38–84%)** | **0 lost / 0 leaked**, 10/10 |
| [concurrent-processing](../concurrent-work/runs/concurrent-processing/REPORT.md) (M={8,16}) | `.batch` **crashes 0/64**; `.abatch`/seq **serialize** | **completes cleanly, 0 errors**, 10/10 |
| [fault-isolation](../concurrent-work/runs/fault-isolation/REPORT.md) | in-process `.abatch` **loses ALL 0/4** to one crash | server **survives**; only the failing run dies, 10/10 |

RocketRide reaches all three with **0 imperative concurrency lines** — the runtime's per-pipe process
topology owns isolation and scheduling by construction.

**One root cause, three faces.** All three failures trace to the same fact: LangChain's default idioms
run the work as threads inside one CPython interpreter, where the Global Interpreter Lock (GIL) lets only
one thread execute Python bytecode at a time — shared-memory hazards without true parallelism. So a shared
dict races and silently loses updates (a non-atomic read → compute → write, where two threads read the same
old value and the second write overwrites the first), a thread-affine SQLite connection raises
`sqlite3.ProgrammingError` the moment `.batch` hands it to another thread, and a hard crash takes the whole
shared interpreter — every task with it. The two escape hatches each have a catch: `asyncio` serializes the
moment a coroutine makes a blocking call, and `multiprocessing` is parallel but you hand-build the plumbing.
RocketRide runs each pipeline in its own OS process by default — multiprocessing's isolation with none of
the authoring or tuning.

## What you get by default
| Concern | By default |
|---|---|
| Isolation / state-safety | ✅ **RocketRide, by construction** — 0 lost / 0 errors / survives (N=10) |
| Authoring (concurrency code) | ✅ **RocketRide** — 0 vs 14–17 lines + 5 decisions |

## Reproduce
```bash
# Re-run the source benchmarks (10 reps each). One-time setup first — provision the pinned
# runtime + venv (see harness/REPRODUCE.md), then:
cd concurrent-work && bash harness/run_isolated.sh        # full recipe: harness/REPRODUCE.md
# Re-derive these headline numbers from the committed runs:
python3 - <<'PY'
import json, glob, statistics as st
B='concurrent-work/runs'
lost=[v for f in glob.glob(f'{B}/data-isolation/run-*/results.json')
        for v in json.load(open(f))['verdict_metrics']['lc_lost_by_gap'].values()]
print('LangChain lost %d-%d of 256 (%.0f-%.0f%%); RocketRide lost 0'
      % (min(lost), max(lost), 100*min(lost)/256, 100*max(lost)/256))
PY
```
