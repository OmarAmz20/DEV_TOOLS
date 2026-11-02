#!/usr/bin/env bash
# Remove 1337-Customizer completely.  This is deliberately thorough: app
# code, launchers, desktop entries, autostart, generated themes, terminal
# includes, caches, logs, saved library and configuration are all covered.
set -euo pipefail

XDG_DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
XDG_STATE="${XDG_STATE_HOME:-$HOME/.local/state}"
XDG_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}"
PREFIX="${LEET_PREFIX:-$XDG_DATA/1337-customizer}"
OLD_PREFIX="$XDG_DATA/hamiid-studio"
BIN="$HOME/.local/bin/1337-customizer"
OLD_BIN="$HOME/.local/bin/hamiid-studio"
KEEP_DATA=0
RESTORE=1
PURGE=0

GOINFRE_BASE="${LEET_GOINFRE:-$HOME/goinfre}"
GOINFRE_ROOT=""
if [ -d "$GOINFRE_BASE" ] && [ -w "$GOINFRE_BASE" ]; then
  GOINFRE_ROOT="$(cd -- "$GOINFRE_BASE" && pwd -P)/1337-customizer"
fi

for arg in "$@"; do
  case "$arg" in
    --keep-data) KEEP_DATA=1 ;;
    --no-restore) RESTORE=0 ;;
    --purge|--all) KEEP_DATA=0; PURGE=1 ;;
    --restore) RESTORE=1 ;;
    --help|-h)
      cat <<'EOF'
Usage: ./uninstall.sh [--keep-data] [--no-restore] [--purge]

By default this restores the desktop changes, then removes the app and every
piece of app-owned data: config, library database, saved looks, photos copied
by the app, caches, logs, generated GTK/terminal themes and launchers.

  --keep-data   keep the library database, saved looks, notes, applied copies
                and configuration; remove only the installed app
  --no-restore  do not restore the previous GTK/terminal/wallpaper state
  --purge       also delete the goinfre Pixi package cache and environments
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Use --help for usage." >&2
      exit 2
      ;;
  esac
done

stop_pid_file() {
  local pidfile="$1"
  if [ -r "$pidfile" ]; then
    local pid
    pid="$(tr -dc '0-9' < "$pidfile" || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
      done
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
}

# Stop every helper ever created by either name.
for state_dir in "$XDG_STATE/1337-customizer" "$XDG_STATE/hamiid-studio"; do
  stop_pid_file "$state_dir/widgetd.pid"
  stop_pid_file "$state_dir/sessiond.pid"
done

# Let the application put the desktop back before its code disappears.  Use
# the checkout launcher when running this script from source.
SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RESTORE_CMD=""
if [ -x "$BIN" ]; then
  RESTORE_CMD="$BIN"
elif [ -x "$SELF_DIR/1337-customizer" ]; then
  RESTORE_CMD="$SELF_DIR/1337-customizer"
fi
if [ "$RESTORE" = 1 ] && [ -n "$RESTORE_CMD" ]; then
  "$RESTORE_CMD" widgets stop >/dev/null 2>&1 || true
  "$RESTORE_CMD" slideshow stop >/dev/null 2>&1 || true
  "$RESTORE_CMD" video stop >/dev/null 2>&1 || true
  "$RESTORE_CMD" restore --scope all >/dev/null 2>&1 || true
fi

# Remove marked blocks from user GTK and terminal configs without touching
# any custom content the user added themselves.
python3 - <<'PY' 2>/dev/null || true
from pathlib import Path
import re

import os
from pathlib import Path as _Path
home = _Path(os.environ.get("XDG_CONFIG_HOME") or _Path.home() / ".config")
files = {
    home / "gtk-3.0/gtk.css": [
        ("/* 1337-customizer:import:begin */", "/* 1337-customizer:import:end */"),
        ("/* hamiid-studio:import:begin */", "/* hamiid-studio:import:end */"),
        ("/* 1337-customizer:begin */", "/* 1337-customizer:end */"),
        ("/* hamiid-studio:begin */", "/* hamiid-studio:end */"),
    ],
    home / "gtk-4.0/gtk.css": [
        ("/* 1337-customizer:import:begin */", "/* 1337-customizer:import:end */"),
        ("/* hamiid-studio:import:begin */", "/* hamiid-studio:import:end */"),
        ("/* 1337-customizer:begin */", "/* 1337-customizer:end */"),
        ("/* hamiid-studio:begin */", "/* hamiid-studio:end */"),
    ],
    home / "kitty/kitty.conf": [
        ("# 1337-customizer:begin", "# 1337-customizer:end"),
        ("# hamiid-studio:begin", "# hamiid-studio:end"),
    ],
    home / "foot/foot.ini": [
        ("# 1337-customizer:begin", "# 1337-customizer:end"),
        ("# hamiid-studio:begin", "# hamiid-studio:end"),
    ],
    home / "ghostty/config": [
        ("# 1337-customizer:begin", "# 1337-customizer:end"),
        ("# hamiid-studio:begin", "# hamiid-studio:end"),
    ],
}
for path, pairs in files.items():
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    updated = text
    for begin, end in pairs:
        updated = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", updated, flags=re.DOTALL)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
PY

# Generated themes and terminal theme files.
THEMES="$XDG_DATA/themes"
rm -rf "$THEMES/L33T-A" "$THEMES/L33T-B"
rm -rf "$THEMES/Hamiid-A" "$THEMES/Hamiid-B"
rm -f "$XDG_CONFIG/kitty/1337-theme.conf" "$XDG_CONFIG/kitty/hamiid-theme.conf"
rm -f "$XDG_CONFIG/foot/1337-theme.ini" "$XDG_CONFIG/foot/hamiid-theme.ini"
rm -f "$XDG_CONFIG/ghostty/1337-theme" "$XDG_CONFIG/ghostty/hamiid-theme"
rm -f "$XDG_CONFIG/alacritty/1337-theme.toml" "$XDG_CONFIG/alacritty/hamiid-theme.toml"
rm -f "$XDG_CONFIG/wezterm/1337-theme.lua" "$XDG_CONFIG/wezterm/hamiid-theme.lua"
rm -rf "$XDG_DATA/fonts/1337-Customizer" "$XDG_DATA/fonts/Hamiid Studio"
if command -v fc-cache >/dev/null 2>&1; then
  fc-cache -f "$XDG_DATA/fonts" >/dev/null 2>&1 || true
fi

# Launchers, desktop entries, icons and autostart.
rm -f "$BIN" "$OLD_BIN"
rm -f "$XDG_DATA/applications/1337-customizer.desktop"
rm -f "$XDG_DATA/applications/io.github.LeetCustomizer.desktop"
rm -f "$XDG_DATA/applications/io.github.HamiidStudio.desktop"
rm -f "$XDG_DATA/icons/hicolor/scalable/apps/1337-customizer.svg"
rm -f "$XDG_DATA/icons/hicolor/scalable/apps/io.github.LeetCustomizer.svg"
rm -f "$XDG_DATA/icons/hicolor/scalable/apps/io.github.HamiidStudio.svg"
rm -f "$XDG_CONFIG/autostart/1337-customizer.desktop"
rm -f "$XDG_CONFIG/autostart/io.github.LeetCustomizer.desktop"
rm -f "$XDG_CONFIG/autostart/io.github.HamiidStudio.desktop"

# Installed application code.  The prefix and the XDG data directory share a
# parent; with --keep-data only the code subtree is removed.
rm -rf "$PREFIX/app"
rm -rf "$OLD_PREFIX/app"

if [ "$KEEP_DATA" = 0 ]; then
  rm -rf "$PREFIX"
  rm -rf "$XDG_CONFIG/1337-customizer"
  rm -rf "$XDG_DATA/1337-customizer"
  rm -rf "$XDG_STATE/1337-customizer"
  rm -rf "$XDG_CACHE/1337-customizer"
  if [ -n "$GOINFRE_ROOT" ]; then
    rm -rf "$GOINFRE_ROOT/cache"
  fi
  # Legacy Hamiid Studio data and config.
  rm -rf "$XDG_CONFIG/hamiid-studio"
  rm -rf "$XDG_DATA/hamiid-studio"
  rm -rf "$XDG_STATE/hamiid-studio"
  rm -rf "$XDG_CACHE/hamiid-studio"
  rm -rf "$XDG_DATA/fonts/1337-Customizer"
  rm -rf "$XDG_DATA/fonts/Hamiid Studio"
  echo "1337-Customizer and all app-owned data removed."
else
  # Keep the library/config, but never keep app code or generated theme files.
  rm -rf "$PREFIX/app"
  rm -rf "$OLD_PREFIX/app"
  echo "1337-Customizer removed. Library, notes, saved looks and configuration were kept."
fi

if [ "$PURGE" = 1 ] && [ -n "$GOINFRE_ROOT" ]; then
  rm -rf "$GOINFRE_ROOT/pixi-cache" "$GOINFRE_ROOT/pixi-home" \
         "$GOINFRE_ROOT/pip-cache" "$GOINFRE_ROOT/uv-cache"
  rmdir "$GOINFRE_ROOT" 2>/dev/null || true
  echo "Pixi package cache and environments removed from $GOINFRE_ROOT."
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q "$XDG_DATA/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q "$XDG_DATA/icons/hicolor" >/dev/null 2>&1 || true
fi
