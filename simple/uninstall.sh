#!/usr/bin/env bash
# Remove Wallpaper Lite and put the desktop back the way it was.
set -uo pipefail

APP=io.github.WallpaperLite
DEST="$HOME/.local/share/wallpaper-lite"

if [ -x "$DEST/wallpaper-lite" ]; then
	if ! "$DEST/wallpaper-lite" restore; then
		echo "Could not restore your original look, so nothing was removed." >&2
		echo "Fix the problem above and run uninstall.sh again." >&2
		exit 1
	fi
	"$DEST/wallpaper-lite" stop >/dev/null 2>&1 || true
fi

rm -rf "$DEST" "$HOME/.config/wallpaper-lite" "$HOME/.cache/wallpaper-lite"
rm -f "$HOME/.local/bin/wallpaper-lite" \
	"$HOME/.local/share/applications/$APP.desktop" \
	"$HOME/.config/autostart/wallpaper-lite-desktop.desktop"
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
	rm -rf "$XDG_RUNTIME_DIR/wallpaper-lite"
fi

echo "Wallpaper Lite removed. Your pictures were not touched."
