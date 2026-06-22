# Reproduce these benchmarks

Every number in [`../runs/`](../runs/) comes from the integrity-gated runners under
[`rocketride-bench/`](rocketride-bench/) — **with a disclosed 3-line pool-size param** (pinned — see
[`rocketride-bench/NOTICE`](rocketride-bench/NOTICE) and [`NOTICE`](NOTICE)). The only piece not
included is the engine binary (platform-specific); `provision.sh` downloads the pinned public release.

## Prereqs
- macOS arm64/x64 or Linux x64; Python 3.11+; ~2 GB disk for the engine.
- Numbers in `../runs/` are from an Apple M5 Pro — the correctness outcomes (0 lost / 0 errors / survives) reproduce **exactly**; wall-clock times and loss magnitude are hardware-dependent (ratios and orderings reproduce, absolute values vary).

## One-time setup
```bash
cd rocketride-bench
bash scripts/provision.sh                          # downloads the pinned engine (v3.2.1) to ./engine
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-competitors.txt
ENGINE_DIR=./engine bash scripts/start_engine.sh   # EAAS server on ws://localhost:5565
```

## Run the benchmarks (10× into ../runs/)
`run_isolated.sh` does it all: crash 10× back-to-back · authoring 1× (static) · pick 10× @ M={8,16} ·
instance 10× @ M=32 — each warm-pool rep runs on a freshly-restarted engine for a clean measurement.
```bash
# from harness/ (engine provisioned + venv created in rocketride-bench/):
BENCH_PY=$PWD/rocketride-bench/.venv/bin/python REPS=10 bash run_isolated.sh
python aggregate.py        # regenerate ../README.md from ../runs/
```
Or run a single bench directly — pool size via env, **defaults reproduce upstream**:
```bash
cd rocketride-bench
python groups/robustness-and-isolation/fault-isolation/run.py                    # fast, deterministic
python groups/scale-and-concurrency/authoring-effort/run.py                     # static (engine optional)
BENCH_MS=8,16 python groups/scale-and-concurrency/concurrent-processing/run.py         # warm-pool
BENCH_M=32    python groups/scale-and-concurrency/data-isolation/run.py  # warm-pool
```

## Warm-pool operational note
The two **warm-pool** benches (`concurrent-processing`, `data-isolation`) hold their pipes resident
for `ttl=900 s`. `run_isolated.sh` runs each warm-pool rep on a **freshly-restarted + primed** engine
for a clean measurement; `fault-isolation` (`ttl=0`) and `authoring-effort` (static) re-run freely. The
results in `../runs/` are **fresh local 10× reps** (median + spread per bench). Pool sizes are disclosed
(pick M={8,16}, instance M=32); the isolation claims are size-independent. See each bench's
`REPORT.md` → Provenance.

## What "integrity-gated" means here
- **Real LangChain**, out-of-process, version-pinned, `lc_version` in every comparison row — no stdlib
  proxy fallback (the run aborts if real LangChain can't be proven).
- **AST-identical work** both sides — an AST parity gate aborts if the RocketRide node body and the
  LangChain function body ever diverge.
- **Native trace** captured per run (committed for run-01 as gzipped `trace/*.jsonl.gz` in `../runs/`).
- Full provenance (engine sha256, CPU, RAM, Python, langchain-core version) in every `results.json`.
