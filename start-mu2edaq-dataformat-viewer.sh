#!/usr/bin/env bash
#
# start-mu2edaq-dataformat-viewer.sh - standardized Mu2e control-room start
# script. Launched as `crs-app start dataformat-viewer`, which exports
# CRS_PORT_LISTEN from apps.yaml. The viewer (a Qt GUI) honors CRS_PORT_LISTEN
# as its default listen port (overriding viewer.port in the config). Runs in
# the background within the VNC session; extra args are passed through.
#
# Port precedence: CRS_PORT_LISTEN env > config file > built-in default (7755).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export CRS_PORT_LISTEN="${CRS_PORT_LISTEN:-7755}"
export DISPLAY="${DISPLAY:-:0}"
PID_FILE="$SCRIPT_DIR/dataformat-viewer.pid"
LOG_FILE="$SCRIPT_DIR/dataformat-viewer.log"

PY=python3
[[ -x ./venv/bin/python ]] && PY=./venv/bin/python

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Data Format Viewer already running (PID $(cat "$PID_FILE"))."
  exit 0
fi
rm -f "$PID_FILE"

echo "Starting Data Format Viewer (listen=$CRS_PORT_LISTEN)"
nohup "$PY" mu2edaq-dataformat-viewer.py "$@" >> "$LOG_FILE" 2>&1 &
bgpid=$!
sleep 1
if ! kill -0 "$bgpid" 2>/dev/null; then
  echo "error: Data Format Viewer failed to start; see $LOG_FILE" >&2
  exit 1
fi
echo "$bgpid" > "$PID_FILE"
echo "Data Format Viewer started (PID $bgpid); log: $LOG_FILE"
