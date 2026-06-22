# RocketRide Benchmarks — RocketRide vs LangChain

Head-to-head benchmarks comparing **RocketRide** (a declarative AI-pipeline runtime) with **LangChain**
(Python) on what matters when you build real AI workflows: **how much code you write**, and whether it
**stays correct under concurrency**. Every comparison runs **real LangChain** on **identical per-unit work** — an AST parity gate aborts if the per-document processing function diverges between the two frameworks.

| Benchmark | Question | Result |
|---|---|---|
| [`lines-of-code/`](lines-of-code/) | How much code to build the same workflow? | ✅ **One declarative pipeline file vs a multi-file Python package** — **zero concurrency/wiring lines** on the RocketRide side, and **~3.6× fewer characters** (N=5). The same AI-built meeting-notes app is a **~120-line** RocketRide `.pipe` vs a **~690-line** LangChain Python package. |
| [`concurrent-work/`](concurrent-work/) | Does it stay correct under concurrent **stateful** work? | ✅ **Correct by default** (N=10). Under concurrent writers, LangChain's shared-state idiom **silently drops updates — 38–84% (96–215 of 256) across our runs** — and its default idioms also crash or lose every task to one fault; RocketRide is **0 lost · 0 errors · survives** — by construction. |
| [`summary/`](summary/) | The consolidated verdict | ✅ RocketRide reaches isolation + correctness with **0 imperative concurrency lines**, where LangChain needs **14–17 lines + up to 5 non-obvious facts**. |

**Scope:** an authoring-effort and correctness claim for concurrent *stateful* work — **not** a raw-speed claim, and **not** a claim that expert LangChain *can't* reach the same correctness (it can, at the line/decision cost shown). Full boundaries in [`summary/PRE-REGISTRATION.md`](summary/PRE-REGISTRATION.md).

## How we measured

Every "vs LangChain" number runs **real LangChain** (version pinned — langchain-core `0.3.86` — and
recorded per row), on **identical** per-unit work (an AST parity gate aborts the run if the per-document
processing function diverges between the two frameworks), and a strict real-LangChain probe that aborts
unless the competitor is actually imported and executed — every published number is mechanically
re-derivable from the committed `results.json`. The concurrency results are **10 runs each** against a live runtime (build `3.2.1.30`),
with full provenance (runtime hash, CPU, RAM, Python) committed next to every result. Everything is
reproducible from [`concurrent-work/harness/`](concurrent-work/harness/).

Concurrency runs use a warm process pool of resident pipes (a production serving topology — M=8/16 for
the stateful-job benchmark, M=32 for data-isolation; warm-up is recorded separately, not counted).
Inputs are committed synthetic records; the failure modes under test are structural properties of each
framework's concurrency model and appear identically regardless of input content.

## Reproduce
```bash
# Code-volume (no runtime needed):
cd lines-of-code && python measure.py

# Concurrency (needs the pinned RocketRide runtime):
cd concurrent-work/harness/rocketride-bench
make provision && make provision-competitors && make start && make smoke
```
Full recipe — provisioning, the pinned runtime, and the 10× re-run — is in [`concurrent-work/harness/REPRODUCE.md`](concurrent-work/harness/REPRODUCE.md).
