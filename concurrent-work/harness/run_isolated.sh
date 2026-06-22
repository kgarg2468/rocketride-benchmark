#!/bin/bash
# Restart-isolated 10x runner for the concurrency benchmarks.
#
# Each warm-pool rep runs on a freshly-restarted engine for a clean, independent measurement:
#   restart the engine -> prime it (one quick ttl=0 single run) -> run the bench at the chosen pool
#   size -> record on success (retry up to MAX_ATTEMPTS). fault-isolation (ttl=0) + authoring (static)
#   run directly.
#
# Pool size is a configurable run parameter (BENCH_MS / BENCH_M). The 10x reps run at M={8,16} (pick)
# and M=32 (instance). Outputs land in runs/<bench>/run-NN/. results.json is only written on SUCCESS,
# so rc=0 == a clean rep.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BR="$HERE/rocketride-bench"
ED="${ENGINE_DIR:-$BR/engine}"
export ENGINE_DIR="$ED"               # so each runner's config.provenance() records the engine version + sha256
CB="$HERE/../runs"
PY="${BENCH_PY:-$BR/.venv/bin/python}"   # override with BENCH_PY when running against an external venv
REPS=${REPS:-10}
MAX_ATTEMPTS=${MAX_ATTEMPTS:-5}
CRASH="groups/robustness-and-isolation/fault-isolation"
PICK="groups/scale-and-concurrency/concurrent-processing"
INST="groups/scale-and-concurrency/data-isolation"
AUTH="groups/scale-and-concurrency/authoring-effort"
cd "$BR" || exit 1

restart() {
  bash scripts/stop_engine.sh >/dev/null 2>&1; sleep 2
  ENGINE_DIR="$ED" bash scripts/start_engine.sh >/dev/null 2>&1; sleep 5
  lsof -nP -iTCP:5565 -sTCP:LISTEN >/dev/null 2>&1 || echo "    [ENGINE DOWN after restart!]"
}

prime() {  # wake the engine's pipe machinery with one quick reliable single-pipe run
  timeout 90 "$PY" "$CRASH/run.py" >/dev/null 2>&1 || true
}

copy_out() {  # $1=group_rel  $2=out_dir
  cp "$BR/$1/results.json" "$2/" 2>/dev/null
  [ -d "$BR/$1/trace" ] && cp -R "$BR/$1/trace" "$2/" 2>/dev/null
  return 0   # success == results.json copied; absence of trace/ (static benches) is not a failure
}

run_simple() {  # crash: no restart, no warm pool.  $1=run-NN
  local out="$CB/fault-isolation/$1"; mkdir -p "$out"
  timeout 120 "$PY" "$CRASH/run.py" > "$out/run.log" 2>&1
  if [ $? -eq 0 ] && [ -f "$BR/$CRASH/results.json" ]; then copy_out "$CRASH" "$out"; echo "  OK   fault-isolation $1"
  else echo "  FAIL fault-isolation $1"; fi
}

run_warmpool() {  # restart+prime+retry.  $1=group_rel  $2=key  $3=run-NN  $4=env_assignments
  local grp="$1" key="$2" rn="$3" envv="$4"
  local out="$CB/$key/$rn"; mkdir -p "$out"
  local a=0
  while [ "$a" -lt "$MAX_ATTEMPTS" ]; do
    a=$((a+1)); restart; prime
    env $envv timeout 300 "$PY" "$grp/run.py" > "$out/run.log" 2>&1
    if [ $? -eq 0 ] && [ -f "$BR/$grp/results.json" ]; then copy_out "$grp" "$out"; echo "  OK   $key $rn (attempt $a)"; return 0; fi
    echo "  ...retry $key $rn (attempt $a failed)"
  done
  echo "  FAIL $key $rn after $MAX_ATTEMPTS attempts"; return 1
}

echo "=== fault-isolation x$REPS (back-to-back, no restart) ==="
for r in $(seq -w 1 "$REPS"); do run_simple "run-$r"; done

echo "=== authoring-effort x1 (static / deterministic — reps N/A) ==="
mkdir -p "$CB/authoring-effort"
timeout 120 "$PY" "$AUTH/run.py" > "$CB/authoring-effort/run.log" 2>&1 \
  && copy_out "$AUTH" "$CB/authoring-effort" && echo "  OK   authoring-effort" || echo "  FAIL authoring-effort"

echo "=== concurrent-processing x$REPS  @ M={8,16}  (restart+prime+retry) ==="
for r in $(seq -w 1 "$REPS"); do run_warmpool "$PICK" "concurrent-processing" "run-$r" "BENCH_MS=8,16"; done

echo "=== data-isolation x$REPS  @ M=32  (restart+prime+retry) ==="
for r in $(seq -w 1 "$REPS"); do run_warmpool "$INST" "data-isolation" "run-$r" "BENCH_M=32"; done

echo "=== 10x RUN DONE ==="
