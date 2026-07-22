#!/usr/bin/env bash
# bootstrap.sh -- set up the Python virtual environment for
# mu2edaq-dataformat-viewer (PyQt6 GUI) and install/update its dependencies.
#
# Usage: ./bootstrap.sh [--dev]
#
# Requires Python 3.9+ and a DISPLAY (X11/GUI environment) to run the app.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/venv"
DEV=0

for arg in "$@"; do
    case "$arg" in
        --dev) DEV=1 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: python3 not found. Install Python 3.9+ first." >&2
    exit 1
fi

PYVER=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "error: Python >= 3.9 required, found $PYVER" >&2; exit 1;
}
echo "Using Python $PYVER at $(command -v "$PYTHON")"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment in $VENV"
    "$PYTHON" -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip >/dev/null

# mu2edaq-discovery (auto-discovery protocol) -- best effort: prefer a
# sibling checkout, fall back to GitHub; the app degrades gracefully to
# no discovery when it is absent.
if ! python -c 'import mu2edaq_discovery' 2>/dev/null; then
    if [ -d "$HERE/../mu2edaq-discovery" ]; then
        pip install -e "$HERE/../mu2edaq-discovery" \
            && echo "Installed mu2edaq-discovery from sibling checkout"
    else
        pip install 'git+https://github.com/Mu2e/mu2edaq-discovery' 2>/dev/null \
            && echo "Installed mu2edaq-discovery from GitHub" \
            || echo "note: mu2edaq-discovery not installed; auto-discovery disabled"
    fi
fi

echo "Installing dependencies from requirements.txt"
pip install -r "$HERE/requirements.txt"

if [ "$DEV" = 1 ]; then
    echo "Installing dev tools (pytest)"
    pip install pytest
fi

echo ""
echo "Bootstrap complete. Activate with:  source venv/bin/activate"
echo "Start the viewer with:              ./start-mu2edaq-dataformat-viewer.sh"
