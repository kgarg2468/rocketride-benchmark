# RocketRide benchmark harness — convenience targets.
#
# Every target below runs the real command it stands for. Run from this directory
# (concurrent-work/harness/rocketride-bench/). The same commands are spelled out in
# scripts/provision.sh and ../REPRODUCE.md, so you can always run them by hand instead.
#
# Quick start:
#   make provision                 # download the pinned runtime + build the venv
#   make provision-competitors     # add the real LangChain baseline (Tier-1 head-to-heads)
#   make start                     # boot the EAAS server on ws://localhost:5565
#   make smoke                     # one fast deterministic bench (fault-isolation)
#   make run-competitive           # all four real-LangChain head-to-heads once each

PY         := .venv/bin/python
ENGINE_DIR ?= ./engine

.PHONY: provision provision-competitors start stop \
        smoke run-competitive

# One-time setup: download the pinned runtime to ./engine and build the harness venv.
provision:
	bash scripts/provision.sh

# Add the REAL LangChain competitor baseline (version pinned in requirements-competitors.txt).
provision-competitors:
	$(PY) -m pip install -r requirements-competitors.txt

# Boot the genuine RocketRide EAAS server on ws://localhost:5565 (installs the bench node first).
start:
	ENGINE_DIR=$(ENGINE_DIR) bash scripts/start_engine.sh

# Stop the EAAS server started by `make start`.
stop:
	bash scripts/stop_engine.sh

# Smallest end-to-end signal: the fast, deterministic fault-isolation bench.
smoke:
	$(PY) groups/robustness-and-isolation/fault-isolation/run.py

# Run all four real-LangChain head-to-heads once each.
run-competitive:
	$(PY) groups/robustness-and-isolation/fault-isolation/run.py
	$(PY) groups/scale-and-concurrency/authoring-effort/run.py
	BENCH_MS=8,16 $(PY) groups/scale-and-concurrency/concurrent-processing/run.py
	BENCH_M=32    $(PY) groups/scale-and-concurrency/data-isolation/run.py
