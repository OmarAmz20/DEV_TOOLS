#!/bin/sh
# Remove Aura Studio's launcher, icon and X11 autostart entry.
# Your pictures, profiles and current desktop look are left alone.
#
#   ./uninstall.sh            remove the launcher only
#   ./uninstall.sh --purge    also delete the local Pixi environment
set -eu

PURGE=0
for argument in "$@"; do
    case "$argument" in
        --purge) PURGE=1 ;;
        -h|--help)
            cat <<'USAGE'
Remove Aura Studio's launcher, icon and X11 autostart entry.

  ./uninstall.sh            remove the launcher only
  ./uninstall.sh --purge    also delete the local Pixi environment

Your pictures, profiles and current desktop look are left alone.
USAGE
            exit 0
            ;;
        *) echo "uninstall.sh: unknown option: $argument" >&2; exit 2 ;;
    esac
done

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN=${XDG_BIN_HOME:-"$HOME/.local/bin"}/aura-studio
DESKTOP="$DATA_HOME/applications/io.github.AuraStudio.desktop"
ICON="$DATA_HOME/icons/hicolor/scalable/apps/io.github.AuraStudio.svg"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/io.github.AuraStudio.wallpaper.desktop"

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
if [ -f "$AUTOSTART" ] && grep -q "$ROOT/aura-studio" "$AUTOSTART" 2>/dev/null; then
    rm -f "$AUTOSTART"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d "$DATA_HOME/icons/hicolor" ]; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

rm -f "$ROOT/.aura-install-mode"
if [ "$PURGE" -eq 1 ]; then
    rm -rf "$ROOT/.pixi"
    printf '\nAura Studio launcher and Pixi environment removed.\n'
else
    printf '\nAura Studio launcher removed.\n'
    printf 'The Pixi environment is still in %s/.pixi (use --purge to remove it).\n' "$ROOT"
fi
printf 'Your settings and profiles are still in ~/.config/aura-studio.\n'
printf 'If you want your original desktop look back first, run: %s/aura-studio restore\n\n' "$ROOT"
