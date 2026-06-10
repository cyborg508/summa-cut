#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export QT_QPA_PLATFORM="wayland;xcb"
exec "$(dirname "$0")/.venv/bin/python" "$(dirname "$0")/special_mode_app.py" >>"$HOME/.summa-cut-special-mode.log" 2>&1
