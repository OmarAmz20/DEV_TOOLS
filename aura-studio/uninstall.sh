#!/bin/sh
# Remove Aura Studio's launcher and icon.  Your pictures, profiles and the
# current desktop look are left alone.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN=${XDG_BIN_HOME:-"$HOME/.local/bin"}/aura-studio
DESKTOP="$DATA_HOME/applications/io.github.AuraStudio.desktop"
ICON="$DATA_HOME/icons/hicolor/scalable/apps/io.github.AuraStudio.svg"

if [ -f "$DESKTOP" ] && grep -q "$ROOT/aura-studio" "$DESKTOP" 2>/dev/null; then
    rm -f "$DESKTOP"
fi
if [ -L "$BIN" ]; then
    target=$(readlink "$BIN" || true)
    case "$target" in
        "$ROOT/aura-studio") rm -f "$BIN" ;;
    esac
fi
rm -f "$ICON"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d "$DATA_HOME/icons/hicolor" ]; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '\nAura Studio launcher removed.\n'
printf 'Your settings and profiles are still in ~/.config/aura-studio.\n'
printf 'If you want your original desktop look back first, run: %s/aura-studio restore\n\n' "$ROOT"
