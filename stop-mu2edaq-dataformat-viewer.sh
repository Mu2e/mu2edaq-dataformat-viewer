#!/usr/bin/env bash
# Stop the Mu2e Data Format Viewer.
set -uo pipefail

PID_FILE="${CRS_HOME:-$HOME/controlroom}/log/dataformat-viewer.pid"
[[ -f "$PID_FILE" ]] || PID_FILE="/tmp/dataformat-viewer.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  kill "$(cat "$PID_FILE")"
  rm -f "$PID_FILE"
  echo "Data Format Viewer stopped."
else
  PIDS=$(pgrep -f "mu2edaq-dataformat-viewer.py" || true)
  if [[ -n "$PIDS" ]]; then
    kill $PIDS 2>/dev/null || true
    echo "Data Format Viewer stopped (found by name)."
  else
    echo "Data Format Viewer is not running."
  fi
  rm -f "$PID_FILE" 2>/dev/null || true
fi
exit 0
