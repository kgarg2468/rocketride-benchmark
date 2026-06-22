# summary — Pre-registration

> Written to fix the claim **before** the synthesis, so it can't drift to fit the numbers. This is
> the consolidation layer over the repo's concurrency-correctness experiment
> ([`../concurrent-work/`](../concurrent-work/)). It makes **no new measurement**; it re-derives from
> its committed `results.json`.

## The claim (pre-registered, exact wording)
> **For concurrent stateful work, RocketRide is cheaper to build the *correct* version: its default
> idiom is safe with 0 imperative concurrency lines, where the LangChain author must write 14–17
> lines and know up to 5 non-obvious facts — and the natural default still fails outright
> (silently loses 38–84% of updates, crashes, or loses every task to one fault), measured over 10
> reps. RocketRide reaches by-construction isolation with zero concurrency code (verified from its
> native per-pipe runtime trace).**

Scope: **stateful-concurrent work** (many independent items, each touching its own state); an
**authoring + correctness** claim.

## The equal-correctness gate (why the comparison is fair)
A "cheaper to build" claim is fair only if both sides build the **same, correct** thing. We compare
RocketRide's default to the **correct** LangChain variant (`concurrent_percall.py`), never the crashing
one. Measured benchmarks establish that the careful version is *mandatory* — the default idioms
lose data / crash / lose-all — so comparing RocketRide's 0-line default to LangChain's 17-line
correct version is the honest comparison.

## What we claim
- **Authoring-to-correctness is cheaper** (0 vs 17 imperative lines, 0 vs 5 hidden decisions; static).
- **RocketRide's default is safe; LangChain's default is not** — 38–84% silent loss / crash /
  lose-all vs 0 lost / 0 errors / survives, all N=10.
- **Isolation is verified, not asserted** — the per-pipe partition is parsed from RocketRide's
  committed native runtime trace (used here as isolation evidence).

## What we do NOT claim
- **Not raw single-job speed/latency.** We make no claim that RocketRide executes a single request
  faster than LangChain. This is a warm-pool serving comparison; the one-time pool warm-up is recorded
  separately (`warm_s`) and not counted. The throughput gap shown under load is a consequence of the
  *default* LangChain idioms serializing or crashing under concurrency — not a per-call speed contest.
- **Not that LangChain *cannot* do this.** A careful, expert LangChain build (per-call tasks /
  `RunnableParallel`) is correct and genuinely concurrent. The claim is about the *cost to reach*
  correctness on the default path (0 vs 14–17 lines + up to 5 non-obvious facts) and the failure rate of
  the idiomatic default — not an upper bound on what an expert can build.
- **Not isolation by magic.** RocketRide's by-construction safety here is per-pipe *process* isolation
  under the default serving topology, not immunity inside a single process — drive one pipe with shared
  in-process threads and you can reproduce the same class of error. The claim is about the default a
  developer actually gets.
- **Not a general verdict.** Scope is concurrent *stateful* work on a synthetic workload (sqlite +
  bounded compute as an IO/model stand-in). Ratios reproduce; absolute values vary with hardware and
  inputs, and the synthetic ratios are not a prediction for LLM-latency-dominated workloads.

## Method
Real LangChain (`lc_version` per comparison row), **N=10** fresh reps, AST-identical per-doc work both
sides (AST parity gate aborts on divergence), with disclosed pool sizes.
