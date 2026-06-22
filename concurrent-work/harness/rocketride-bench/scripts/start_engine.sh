#!/usr/bin/env bash
# Start the genuine RocketRide EAAS server (direct-connect) on ws://localhost:5565 and wait
# until it is healthy. Installs the benchmark-only node(s) into the engine bundle first so the
# service catalog registers them. Idempotent-ish: re-running restarts a fresh engine.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE_DIR="${ENGINE_DIR:-$REPO_DIR/engine}"
PORT="${ROCKETRIDE_PORT:-5565}"
LOG="${ENGINE_LOG:-$REPO_DIR/results/engine.log}"
PIDFILE="$REPO_DIR/results/engine.pid"

if [ ! -x "$ENGINE_DIR/engine" ]; then
  echo "RocketRide runtime not found at $ENGINE_DIR/engine" >&2
  echo "  set \$ENGINE_DIR or run scripts/provision.sh to download the pinned prebuilt." >&2
  exit 1
fi

# Install the benchmark-only synthetic node(s) into the engine's nodes/ (path: nodes.<name>).
# NB: strip the glob's trailing slash — BSD cp -R treats "src/" as "copy CONTENTS of src",
# which scattered the node files into nodes/ root and left nodes/<name>/ STALE on macOS.
for n in "$REPO_DIR"/nodes/*/; do
  n="${n%/}"
  [ -d "$n" ] || continue
  rm -rf "$ENGINE_DIR/nodes/$(basename "$n")"
  cp -R "$n" "$ENGINE_DIR/nodes/"
done

mkdir -p "$(dirname "$LOG")"
cd "$ENGINE_DIR"
echo "starting: $ENGINE_DIR/engine ai/eaas.py --host=0.0.0.0  (port $PORT)"
nohup ./engine ai/eaas.py --host=0.0.0.0 >"$LOG" 2>&1 &
echo $! > "$PIDFILE"

# Readiness = the HTTP server answers at all. /ping returns 401 without auth (that's still a
# live server), so accept any HTTP status; only a connection failure (000) means "not up yet".
for _ in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/ping" 2>/dev/null || echo 000)"
  if [ "$code" != "000" ]; then
    echo "engine healthy on :$PORT (HTTP $code, pid $(cat "$PIDFILE"))"
    ./engine --version 2>&1 | head -1
    exit 0
  fi
  sleep 0.5
done

echo "engine did not become healthy on :$PORT within 30s; see $LOG" >&2
exit 1
