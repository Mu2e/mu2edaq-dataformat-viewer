#!/usr/bin/env bash
# Start the Mu2e Data Format Viewer (PyQt6 GUI).
# DISPLAY is honored from the environment so the window appears in the
# invoking VNC session. CRS_PORT_LISTEN (exported by the control room
# crs-app launcher) overrides the configured listen port.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${CRS_HOME:-$HOME/controlroom}/log/dataformat-viewer.pid"
mkdir -p "$(dirname "$PID_FILE")" 2>/dev/null || PID_FILE="/tmp/dataformat-viewer.pid"

PYTHON="$SCRIPT_DIR/venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

nohup "$PYTHON" "$SCRIPT_DIR/mu2edaq-dataformat-viewer.py" "$@" \
  >> "${PID_FILE%.pid}.log" 2>&1 &
echo $! > "$PID_FILE"
echo "Data Format Viewer started (PID $(cat "$PID_FILE"))."
