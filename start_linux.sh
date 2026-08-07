#!/usr/bin/env sh
set -eu
PROPEXTRACT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROPEXTRACT_PYTHON="$PROPEXTRACT_ROOT/.venv/bin/python"
if [ ! -x "$PROPEXTRACT_PYTHON" ]; then
  echo "Virtual environment not found. Run: python3 -m venv .venv"
  echo "Then run: .venv/bin/python -m pip install -r requirements-rns-import.txt"
  exit 1
fi
printf '%s\n' "Open http://127.0.0.1:8765 in a browser"
exec "$PROPEXTRACT_PYTHON" -m rns_import_server.app serve --host 127.0.0.1 --port 8765
