#!/usr/bin/env bash
# Stop the EAAS server started by start_engine.sh.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$REPO_DIR/results/engine.pid"
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill "$PID" 2>/dev/null; then echo "stopped engine pid $PID"; else echo "pid $PID not running"; fi
  rm -f "$PIDFILE"
else
  echo "no $PIDFILE; nothing to stop"
fi
