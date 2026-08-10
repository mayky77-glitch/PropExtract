#!/usr/bin/env sh
set -eu
PROPEXTRACT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROPEXTRACT_ROOT"

if [ "$(id -u)" -eq 0 ]; then
  PROPEXTRACT_SUDO=""
elif command -v sudo >/dev/null 2>&1; then
  PROPEXTRACT_SUDO="sudo"
else
  echo "sudo is required to install system packages"
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  $PROPEXTRACT_SUDO apt-get update
  $PROPEXTRACT_SUDO apt-get install -y python3 python3-venv python3-tk poppler-utils tesseract-ocr
elif command -v dnf >/dev/null 2>&1; then
  $PROPEXTRACT_SUDO dnf install -y python3 python3-tkinter poppler-utils tesseract
else
  echo "Supported package managers: apt-get and dnf"
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip --isolated install \
  --disable-pip-version-check \
  --no-index \
  --find-links packages/python \
  --require-hashes \
  --only-binary=:all: \
  -r requirements-rns-import.txt
.venv/bin/python -m rns_import_server.runtime
exec sh ./start_linux.sh
