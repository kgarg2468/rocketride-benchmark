# concurrent-processing · 64 docs of stateful work — stock RocketRide vs LangChain's default idioms

> **Verdict: ✅ safe by default.** Identical per-doc work (sqlite `INSERT`+`SELECT`+`commit` + 100 ms
> blocking wait — AST-parity-gated) over **64 docs**: stock RocketRide's warm per-pipe
> topology finishes **M=16 0.59 s (median of 10; range 0.49–0.70), 0 errors every rep**, while the SAME
> LangChain chain object — used the way the API steers you — **crashes** under `.batch`
> (`sqlite3.ProgrammingError`, 0/64), **serializes** under `.abatch` (6.7 s), and is **slow**
> sequentially (6.7 s). RocketRide's **default just works** where LangChain's default fails — the win is
> *isolation by construction*.

## Hypothesis
Run the same pipeline over 64 docs in LangChain and its natural idioms crash / serialize / go
sequential; stock RocketRide is safe. Test it literally — same work both sides, LangChain's own idioms.

## Method
Per-doc work: sqlite `INSERT`+`SELECT`+`commit` + `time.sleep(0.100)` (a blocking model/IO stand-in).
The function body is **AST-identical** in `nodes/workload/IInstance._sqlite_doc_work` and
`harness/lc_baselines.sqlite_doc_work` — a parity gate aborts the run if they ever diverge. RocketRide:
**M ∈ {8, 16}** warm resident pipes (pool size via `BENCH_MS`; `use(ttl=900, use_existing=True)`), 64
docs round-robin, the **naive module-level connection** (per-pipe-safe because each pipe is its own
runtime process). LangChain (REAL, strict, `lc_version` per row): one chain object, the three idioms below.
**10 fresh reps**, each on a restarted + primed runtime (`harness/run_isolated.sh`).

## Results *(median of 10 reps; M5 Pro, langchain-core 0.3.86)*
| Configuration | Wall (64 docs) | Outcome |
|---|---:|---|
| **Stock RocketRide, 16 warm pipes** | **0.587 s** (0.494–0.698) | ✅ 64/64, **0 errors** (10/10 reps) |
| Stock RocketRide, 8 warm pipes | ~1.0 s | ✅ 64/64, 0 errors (10/10) |
| Stock LangChain `.batch` (shared conn) | 0.01 s | ❌ **CRASH** — 0/64 (`sqlite3.ProgrammingError`) |
| Stock LangChain `.abatch` (blocking) | 6.66 s | ⚠️ **SERIALIZED** — blocking work runs one-at-a-time |
| Stock LangChain sequential loop | 6.71 s | ⚠️ **SLOW** — 64× work |

RocketRide's **default** is safe by construction with zero concurrency code, while LangChain's three
natural idioms each miss: one crashes outright, one silently serializes, one is just slow — none deliver
concurrent execution.

## Why these three idioms each miss
All three run inside one CPython interpreter, where the Global Interpreter Lock (GIL) lets only one thread execute Python bytecode at a time — so threads give you shared-memory hazards without true parallelism, and the two escape hatches each have a catch. `.batch` dispatches the 64 docs to a worker thread pool, but the module-level SQLite connection was created on the main thread and SQLite connections are thread-affine — using one from another thread raises `sqlite3.ProgrammingError`, so every worker crashes (0/64). `.abatch` looks concurrent, but each task makes a blocking call (`time.sleep`, our model/IO stand-in) inside the async function, and a blocking call freezes the single-threaded `asyncio` event loop until that item finishes — so the 64 items serialize (6.7 s). The sequential loop is correct but is just 64× the work (6.7 s). RocketRide sidesteps all three: each pipe is its own OS process, so the module-level connection is per-process-safe and the 64 docs run on M truly-parallel processes — multiprocessing's isolation without authoring or tuning any of it.

## Warm pool, stated plainly
Bringing the resident pipes up is a one-time cost of ~8–11 s (M=16 median warm-up ≈9.9 s; M=8 ≈7.9 s; recorded as `warm_s` in every `results.json`). It is paid once and amortized across every subsequent job — the way a production server holds workers resident and doesn't charge its boot time to each request — so the 0.587 s above is steady-state serving throughput, not a per-job number. A single cold, one-shot RocketRide job pays the full spin-up and would lose a wall-clock race to LangChain's ~6.7 s; that is deliberately not the claim. What this benchmark claims is correctness and isolation by construction (LangChain's default `.batch` crashes 0/64; RocketRide completes 64/64 with 0 errors), with steady-state throughput a secondary result — cold-start latency is out of scope.

## Provenance
**Fresh local 10× reps** (`run-01/ … run-10/`), median + range. Each rep ran on a restarted + primed
runtime at pool sizes M={8,16} (`BENCH_MS`, disclosed in [`../../harness/NOTICE`](../../harness/NOTICE));
**0 node_errors in all 10**. Real LangChain (`lc_version 0.3.86`) per row; AST parity gate PASS; native
trace committed.

## Reproduce
[`../../harness/REPRODUCE.md`](../../harness/REPRODUCE.md) — `BENCH_MS=8,16`; warm-pool benches use
`harness/run_isolated.sh` (restart + prime + retry per rep).

## Runnable demo
A real-node showcase of this claim sits beside the stub:
[`demo.pipe`](../../harness/rocketride-bench/groups/scale-and-concurrency/concurrent-processing/demo.pipe)
(`webhook → parse → question → prompt → llm_openai → response_answers`) summarizes 64 real documents
across M warm pipes. Run: `cd concurrent-work/harness && python run_demo.py pick` (needs
`ROCKETRIDE_OPENAI_KEY`); details in the folder
[`README.md`](../../harness/rocketride-bench/groups/scale-and-concurrency/concurrent-processing/README.md).
It shows RocketRide succeeding — the LangChain failure stays in the table above.
