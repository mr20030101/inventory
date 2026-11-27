#!/bin/sh
# Installs SAIMS for the current user (no root needed).
# Run from the extracted release folder:  ./install.sh      Uninstall:  ./install.sh --uninstall
set -e
APP_DIR="$HOME/.local/opt/saims"
BIN="$HOME/.local/bin/saims"
DESKTOP="$HOME/.local/share/applications/saims.desktop"
ICON="$HOME/.local/share/icons/hicolor/512x512/apps/saims.png"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "$1" = "--uninstall" ]; then
    rm -rf "$APP_DIR" "$BIN" "$DESKTOP" "$ICON"
    echo "SAIMS removed. Your data is kept in ~/.local/share/saims"
    exit 0
fi

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
cp -r "$HERE/SAIMS/." "$APP_DIR/"
ln -sf "$APP_DIR/SAIMS" "$BIN"
cp "$HERE/icon.png" "$ICON"
sed "s|@EXEC@|$APP_DIR/SAIMS|" "$HERE/saims.desktop" > "$DESKTOP"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$(dirname "$DESKTOP")" || true
echo "Installed. Launch \"SAIMS\" from your applications menu, or run: saims"
