#!/bin/sh
# Install Aura Studio for the current user.  No sudo needed.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}

if ! "$PYTHON" - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
if Gtk.get_major_version() != 4 or Gtk.get_minor_version() < 10:
    raise SystemExit("GTK 4.10 or newer is required")
if Adw.MAJOR_VERSION < 1 or (Adw.MAJOR_VERSION == 1 and Adw.MINOR_VERSION < 6):
    raise SystemExit("libadwaita 1.6 or newer is required")
PY
then
    echo "Aura Studio needs Python 3 with GTK 4.10+ and libadwaita 1.6+ (python3-gi)." >&2
    echo "On Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" >&2
    exit 1
fi

DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN=${XDG_BIN_HOME:-"$HOME/.local/bin"}
APPS="$DATA_HOME/applications"
ICONS="$DATA_HOME/icons/hicolor/scalable/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"

ln -sfn "$ROOT/aura-studio" "$BIN/aura-studio"
chmod +x "$ROOT/aura-studio"

cp "$ROOT/data/icons/hicolor/scalable/apps/io.github.AuraStudio.svg" \
    "$ICONS/io.github.AuraStudio.svg"
sed "s|@ROOT@|$ROOT|g" "$ROOT/data/io.github.AuraStudio.desktop.in" \
    > "$APPS/io.github.AuraStudio.desktop"
chmod 644 "$APPS/io.github.AuraStudio.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '\nAura Studio is installed.\n'
printf '  Open it from your app launcher, or run: aura-studio\n'
printf '  Run ./uninstall.sh to remove the launcher (your settings stay).\n\n'
