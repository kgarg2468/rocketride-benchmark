# concurrent-work — RocketRide vs base LangChain on concurrent **stateful** work

**The claim, scoped tightly:** on concurrent *stateful* work, **stock RocketRide is safe by default** — its per-pipe process topology does, with zero concurrency code, what a LangChain user has to *know* to do (thread-affinity, a lock, a process pool). Stock LangChain's most natural idioms **crash, silently lose data, or lose everything to one fault.**

Every number runs **real LangChain** (`lc_version` per row), **identical per-unit work** (AST parity gate), and a **native trace**, with full provenance — re-run from [`harness/`](harness/).

## Scorecard — *stock vs stock*

| Benchmark | Stock LangChain (default idiom) | **Stock RocketRide (default)** |
|---|---|---|
| [concurrent-processing](runs/concurrent-processing/REPORT.md) | `.batch` (shared conn) **CRASHES 0/64** (`sqlite3.ProgrammingError`); `.abatch`/seq serialize **6.7 s** | ✅ **safe — M=16 warm pool, 0.587 s (range 0.494–0.698), 0 errors** (10/10 reps clean) |
| [fault-isolation](runs/fault-isolation/REPORT.md) | in-process `.abatch` (one interpreter) **loses ALL 0/4** to one crash | ✅ **survives** — only the crashing run dies (10/10 reps) |
| [data-isolation](runs/data-isolation/REPORT.md) | one shared dict, 32 workers → **silently loses 96–215 of 256** (38–84%) | ✅ **0 lost / 0 leaked** — each pipe its own data (10/10 reps) |
| [authoring-effort](runs/authoring-effort/REPORT.md) | **14–17** imperative lines + up to **5** hidden decisions; one crashes, one silently serializes, one is slow — none deliver concurrency | ✅ **0** imperative concurrency lines (validated `.pipe`) |

*Fresh local 10× reps (crash/pick/instance; authoring is static). Runtime `3.2.1.30 hash: 114509c6` · Apple M5 Pro · langchain-core `0.3.86`. **The isolation/correctness outcomes are exact and deterministic — 0 lost / 0 errors / survives, every rep. Wall-clock times and the loss magnitude (0.587 s; 38–84%) are hardware-dependent: orderings and ratios reproduce, absolute values vary.***

> **Warm pool & cold start.** The 0.587 s is steady-state on a warm resident pool (a production serving topology); one-time pool warm-up (~8–11 s, recorded as `warm_s`) is amortized and not counted. A cold one-shot RocketRide job would lose a wall-clock race to LangChain's 6.7 s — deliberately not the claim; the claim is correctness/isolation by construction.
> **Data-loss window.** The 38–84% band is swept over the per-record compute window between read and write (20k–100k iters of the same CPU loop both sides run); at a negligible window loss falls toward ~0, but any real update does compute there, where the non-atomic idiom silently drops a growing share with no error.

## Why this is fair

- **Same work, both sides** — the per-doc work is AST-identical (AST parity gate aborts if it ever diverges). The only difference is *how each framework is used by default* — and of LangChain's three natural idioms one crashes, one silently serializes, and one is slow, while RocketRide's default is safe by construction.
- **Pool size is a disclosed run parameter** (pick M={8,16}, instance M=32) for runtime stability; the isolation claims are size-independent. See [`harness/NOTICE`](harness/NOTICE).
- **"Concurrent" here means *stateful* work.** An expert async LangChain build genuinely runs *stateless* I/O — like two LLM calls — concurrently (our own [`lines-of-code`](../lines-of-code/) build does exactly that with `RunnableParallel`). What the default idioms don't deliver is concurrency on *stateful* CPU/DB work, where the GIL and SQLite thread-affinity bite — and that is what this benchmark tests.

## Read at any depth

- **This file** — the scorecard.
- **[`runs/`](runs/)** `<bench>/REPORT.md` — Verdict · Hypothesis · Method · Results · Provenance, with committed `results.json` + native `trace/` (10 reps each for the timed/stateful benches).
- **[`harness/`](harness/)** — the runners + everything to reproduce ([`REPRODUCE.md`](harness/REPRODUCE.md)).
