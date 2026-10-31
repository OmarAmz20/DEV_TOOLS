#!/usr/bin/env bash
# Install Wallpaper Lite for the current user. No sudo, no network, no downloads.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
case "$HOME" in
	*$'\n'*) echo "Wallpaper Lite: HOME contains a newline; refusing to write desktop files." >&2; exit 1 ;;
esac

APP=io.github.WallpaperLite
DEST="$HOME/.local/share/wallpaper-lite"
AUTOSTART="$HOME/.config/autostart/wallpaper-lite-desktop.desktop"

say() { printf '\033[1m%s\033[0m\n' "$*"; }

# --- find a Python that really has GTK 3 and GdkPixbuf ------------------------------
has_gtk() {
	"$1" - 2>/dev/null <<'PY'
import gi, cairo
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf
PY
}
PYTHON=
tried=()
for candidate in /usr/bin/python3 "$(command -v python3 || true)" /usr/local/bin/python3; do
	[ -n "$candidate" ] && [ -x "$candidate" ] || continue
	tried+=("$candidate")
	if has_gtk "$candidate"; then PYTHON=$candidate; break; fi
done
if [ -z "$PYTHON" ]; then
	echo "Wallpaper Lite needs Python 3 with GTK 3 and GdkPixbuf, and none was found." >&2
	echo "Tried: ${tried[*]:-no python3 at all}" >&2
	echo "On Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0" >&2
	exit 1
fi
if [ "${XDG_SESSION_TYPE:-x11}" != x11 ]; then
	echo "Note: this is a ${XDG_SESSION_TYPE} session. The app works, but the fallback"
	echo "      desktop wallpaper needs X11; GNOME's own wallpaper must be writable."
fi

# stop a copy of our helper before replacing the files it runs from
if [ -x "$DEST/wallpaper-lite" ]; then
	"$DEST/wallpaper-lite" stop >/dev/null 2>&1 || true
fi

# --- the app -------------------------------------------------------------------------
say "Installing to $DEST"
rm -rf "$DEST"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.config/autostart"
cp -r wallpaper_lite wallpaper-lite "$DEST/"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +
chmod +x "$DEST/wallpaper-lite"
# Run with the Python that has GTK, not whatever python3 happens to be first later.
PY_ESCAPED=${PYTHON//\\/\\\\}
PY_ESCAPED=${PY_ESCAPED//&/\\&}
PY_ESCAPED=${PY_ESCAPED//|/\\|}
sed -i "1s|^#!.*|#!$PY_ESCAPED|" "$DEST/wallpaper-lite"
ln -sf "$DEST/wallpaper-lite" "$HOME/.local/bin/wallpaper-lite"

# Quote an Exec= path for a .desktop file (spaces, quotes, percent signs).
desktop_exec() {
	local p=${1//\\/\\\\}
	p=${p//\"/\\\"}
	p=${p//%/%%}
	printf '"%s"' "$p"
}
EXEC=$(desktop_exec "$DEST/wallpaper-lite")

cat >"$HOME/.local/share/applications/$APP.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Wallpaper Lite
Comment=Pick a wallpaper and take its colours
Exec=$EXEC
Icon=preferences-desktop-wallpaper
Terminal=false
Categories=Settings;DesktopSettings;GTK;
Keywords=wallpaper;background;colour;color;theme;
StartupNotify=true
DESKTOP

cat >"$AUTOSTART" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Wallpaper Lite (desktop)
Comment=Draw the saved wallpaper when GNOME's own picture setting is locked
Exec=$EXEC desktop
NoDisplay=true
X-GNOME-Autostart-enabled=true
DESKTOP

update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true

# If a wallpaper is already saved, let the helper show it now on locked setups.
if [ -f "$HOME/.config/wallpaper-lite/state.json" ]; then
	(setsid "$DEST/wallpaper-lite" desktop >/dev/null 2>&1 &)
fi

say "Done (using $PYTHON). Open “Wallpaper Lite” from your apps, or run: wallpaper-lite"
