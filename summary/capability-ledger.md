# Capability ledger — *what you get by default on concurrent stateful work*

**Rule.** Nothing counts for RocketRide without a named field / documented behavior / committed
measurement in **this repo**, and the LangChain side is cited too. All citations point at files
committed in this repo (paths relative to repo root).

## What RocketRide gives you by default (the wins)
| # | Concern | RocketRide (by default) | LangChain (default) | Evidence |
|---|---|---|---|---|
| 1 | **Isolation / state-safety** | 0 lost / 0 errors / survives, 10/10 | naive default loses 38–84% / crashes / loses-all | instance `rocketride.docs_lost=0` vs `lc_lost_by_gap` 96–215/256; pick `node_errors=0` vs `batch_shared.n_err=64`; crash `server_survived_crash=true` vs `in_process_baseline.completed=0` |
| 2 | **Authoring (concurrency code)** | 0 imperative lines, 0 decisions, validated `.pipe` | 14–17 lines + up to 5 decisions | `concurrent-work/runs/authoring-effort/results.json` |

The per-pipe isolation in row 1 is verified from RocketRide's native runtime trace (RRBENCH markers /
`RRBENCH_STATE`): the per-pipe `marker_pids` + `pipes_with_clean_partition` fields are parsed from it
(committed for run-01 under `trace/*.jsonl.gz`), so the isolation evidence is mechanical, not asserted.

## The bottom line
RocketRide wins **isolation and authoring by default** on concurrent stateful work —
with 0 imperative concurrency lines. "Cheaper to build" = *cheaper to reach correct-by-default
isolation*.

**Why (one cause, three symptoms).** Every LangChain failure here comes from running the work as threads in one CPython interpreter under the GIL: the shared dict races (non-atomic read-modify-write → silent lost updates), the SQLite connection is thread-affine (`.batch`'s thread pool → `ProgrammingError`), and a hard abort kills the shared interpreter (no sibling process to fall back to). RocketRide runs each pipe as its own OS process, so under the default per-pipe-process topology all three are structurally absent — that is what "isolation by construction" means mechanically, not just as a slogan. To be exact, this safety is the per-pipe *process* boundary, not thread-level immunity — and we shipped the proof: our honesty cell (`rr_appendix_threads4`, in every `concurrent-processing/run-*/results.json`) shows that opting out of the default topology — one pipe at `threadCount=4` over a shared module-level connection — reproduces the identical `sqlite3.ProgrammingError` (31/32). That is the point, not an exception to it: the root cause is in-process threading under the GIL, and RocketRide's default process-per-pipe model is exactly what keeps the author out of it without writing a line.

## Reproduce the citations
```bash
python3 -c "import json;d=json.load(open('concurrent-work/runs/data-isolation/run-01/results.json'));print(d['verdict_metrics']['lc_lost_by_gap'], 'RR lost', d['rocketride']['docs_lost'])"  # row 1
python3 -c "import json;d=json.load(open('concurrent-work/runs/authoring-effort/results.json'));print('RR', d['rocketride']['imperative_lines'], 'LC', [x['imperative_lines'] for x in d['langchain']])"  # row 2
```
