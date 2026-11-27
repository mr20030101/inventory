#!/bin/sh
# Build the SAIMS Linux release: dist/SAIMS-<version>-linux-<arch>.tar.gz
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
# Recreate the venv if it is missing or was made by a different Python.
if ! .venv/bin/python -c "import pip" >/dev/null 2>&1; then
    echo "Creating virtual environment with $("$PY" --version)..."
    rm -rf .venv
    "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/saims.spec

VERSION=$(cat VERSION)
NAME="SAIMS-$VERSION-linux-$(uname -m)"
STAGE="dist/$NAME"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r dist/SAIMS "$STAGE/"
cp packaging/install-linux.sh "$STAGE/install.sh"
cp packaging/saims.desktop "$STAGE/"
cp packaging/saims-512.png "$STAGE/icon.png"
tar -C dist -czf "dist/$NAME.tar.gz" "$NAME"
echo "Built dist/$NAME.tar.gz"
