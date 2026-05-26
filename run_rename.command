#!/bin/bash
# macOS double-click launcher for rename_workorder.py
#
# Usage:
#   - Double-click this file in Finder to process the configured folder.
#   - Or set WORKORDER_DIR before launching, e.g.:
#       WORKORDER_DIR="$HOME/Desktop/workorders" open run_rename.command
#   - If no WORKORDER_DIR is set, the Python script will pop a folder picker.

set -u

# Make Homebrew Python and common paths discoverable
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Load API key from ~/.workorder_rename.conf (if present)
if [ -f "$HOME/.workorder_rename.conf" ]; then
    # shellcheck disable=SC1090
    set -a
    . "$HOME/.workorder_rename.conf"
    set +a
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/rename_workorder.py"

if [ ! -f "$PY_SCRIPT" ]; then
    echo "Cannot find rename_workorder.py next to this launcher."
    echo "Expected at: $PY_SCRIPT"
    echo "Press any key to close..."
    read -r -n 1
    exit 1
fi

echo "===================================="
echo " convienece-store workorder image renamer"
echo "===================================="
echo

# If WORKORDER_DIR is set and valid, pass it; otherwise let Python show its picker.
if [ "${WORKORDER_DIR:-}" != "" ] && [ -d "$WORKORDER_DIR" ]; then
    echo "Folder: $WORKORDER_DIR"
    /usr/bin/python3 "$PY_SCRIPT" --folder "$WORKORDER_DIR"
else
    /usr/bin/python3 "$PY_SCRIPT"
fi
EXIT_CODE=$?

echo
echo "Finished (exit=$EXIT_CODE). Press any key to close this window..."
read -r -n 1
