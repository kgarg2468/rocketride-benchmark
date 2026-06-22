# data-isolation · "each pipe is its own data" vs the shared-dict trap

> **Verdict: ✅ safe by default — exact isolation vs silent data loss.** 256 named docs through **32 warm
> pipes**: every pipe ended holding **exactly its own docs** — clean partitions, **0 lost / 0 leaked, in
> all 10 reps** (verified from in-node `RRBENCH_STATE` trace lines, not client bookkeeping). Under
> concurrent writers, LangChain's shared-state idiom — one shared dict updated by 32 `.batch` workers —
> **silently drops updates, up to 84% in our runs (96–215 of 256 lost)**, no exception, no warning.
> Stock RocketRide gives the author **no shared mutable place to get wrong across pipes** by
> construction. Lost data you don't know about is the worst failure mode here.

## Hypothesis
Each pipeline runs as its own process — isolation is per-pipe, by construction; a
shared mutable global under concurrent workers corrupts unless the author adds discipline. Measure both.

## Method
RocketRide: 256 docs named `doc0000…doc0255`, round-robin over **M=32** warm pipes (pool size via
`BENCH_M`; doc *i* → pipe *i*%M). The node (`iso_accumulate` mode) appends each arriving doc's name to a
**module-level list** — per-process state, i.e. per-pipe instance data — and emits the full list per
event (`RRBENCH_STATE`, captured per run in `trace/rr.iso.jsonl.gz`). Pass = every pipe's final list is
exactly its residue class. LangChain (REAL, strict): one chain whose **M=32** `.batch` workers read-modify-write a single
shared dict, with the suite's `busy(gap)` loop in the read→write window (swept 20k / 50k / 100k); count
`expected − observed`. **10 fresh reps** — `BENCH_M=32` keeps RocketRide's pool size = LangChain's worker
count, so the comparison stays matched.

## Results *(10 reps × 3 gap sizes; langchain-core 0.3.86)*
| Side | Configuration | Outcome |
|---|---|---|
| **Stock RocketRide** | 256 docs → 32 warm pipes, per-pipe instance data | ✅ **0 lost · 0 leaked — every rep (10/10)** |
| Stock LangChain | one shared dict, 32 workers, busy-gap swept 20k–100k | ❌ **silently loses 96–215 of 256 (38–84%)** across the 30 cells |

The RocketRide proof is the node's own emitted state (ground truth inside each pipe process),
cross-checked against the routing plan — not the client's view of what it sent.

## Why updates silently vanish
The 32 `.batch` workers run as threads inside one interpreter, all sharing one dict. Updating an entry is read → compute → write, and under the GIL that three-step sequence is not atomic: the interpreter can switch threads between the read and the write, so two workers read the same old value, each computes its own update, and the second write overwrites — silently drops — the first. There is no exception and no warning; Python offers no automatic protection, and the obvious idiom adds no lock. That window is just the compute each worker does between reading the shared dict and writing it back; we swept it across 20k–100k iterations of the same CPU loop both frameworks run. Widening it raises the collision rate from 38% to 84%, and shrinking it toward no-work-between-read-and-write drives loss toward 0 — with nothing in the window the interpreter rarely switches mid-update. That is the hazard, not a safe harbor: every real read-modify-write does compute between the read and the write, so the non-atomic idiom silently drops a share of updates that grows with the work, and raises no error at any window size. RocketRide gives each pipe its own process, so there is no shared dict to race on — the author has no shared mutable place to get wrong, by construction.

## Provenance
**Fresh local 10× reps** (`run-01/ … run-10/`). RocketRide **0 lost in all 10**; LangChain loss range
96–215/256 across the 30 gap-cells. Each rep on a restarted + primed runtime at M=32 (`BENCH_M`, disclosed
in [`../../harness/NOTICE`](../../harness/NOTICE)). Real LangChain (`lc_version 0.3.86`) per row.

## Reproduce
[`../../harness/REPRODUCE.md`](../../harness/REPRODUCE.md) — `BENCH_M=32`.

## Runnable demo
Beside the stub:
[`demo.pipe`](../../harness/rocketride-bench/groups/scale-and-concurrency/data-isolation/demo.pipe)
(`webhook → parse → question → agent_rocketride → [llm_openai + memory_internal] → response_answers`)
runs two pipes on disjoint doc sets — each ends holding only its own entities (0 leak). Run:
`cd concurrent-work/harness && python run_demo.py instance` (needs `ROCKETRIDE_OPENAI_KEY`); see the
folder [`README.md`](../../harness/rocketride-bench/groups/scale-and-concurrency/data-isolation/README.md).
It shows RocketRide succeeding — the LangChain data loss stays in the table above.
