#!/bin/zsh

SCRIPT_DIR=${0:A:h}
cd "$SCRIPT_DIR" || exit 1

if /usr/bin/nc -z 127.0.0.1 8765 >/dev/null 2>&1; then
  /usr/bin/open http://127.0.0.1:8765/
  exit 0
fi

exec /usr/bin/python3 "$SCRIPT_DIR/push_test_ui.py"
