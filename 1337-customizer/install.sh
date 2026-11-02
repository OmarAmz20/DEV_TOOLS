#!/usr/bin/env bash
# Install 1337-Customizer for the current user. No sudo is required.
#
# Python packages are managed with Pixi.  When ~/goinfre exists the Pixi
# package cache, detached environments and the app cache are kept there.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
XDG_DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PREFIX="${LEET_PREFIX:-$XDG_DATA/1337-customizer}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$PREFIX/app"
ICON_DIR="$XDG_DATA/icons/hicolor/scalable/apps"
LAUNCH=0
USE_PIXI=1

# shellcheck source=scripts/env.sh
. "$HERE/scripts/env.sh"
: "${PIXI_HOME:=$HOME/.pixi}"
export PIXI_HOME

for arg in "$@"; do
  case "$arg" in
    --launch) LAUNCH=1 ;;
    --system|--no-pixi) USE_PIXI=0 ;;
    --no-launch) : ;;
    --help|-h)
      echo "Usage: ./install.sh [--launch] [--system]"
      echo "Installs 1337-Customizer to $PREFIX"
      echo "  --launch   open the studio after installing"
      echo "  --system   use the distribution Python instead of Pixi"
      exit 0
      ;;
  esac
done

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }

mkdir -p "$APP_DIR" "$BIN_DIR" "$ICON_DIR" "$XDG_DATA/applications"

# Clean up launchers from the previous Hamiid Studio name.  User data in the
# old XDG folders is migrated by the application on first launch.
rm -f "$HOME/.local/bin/hamiid-studio"
rm -f "$XDG_DATA/applications/io.github.HamiidStudio.desktop"
rm -f "$XDG_DATA/icons/hicolor/scalable/apps/io.github.HamiidStudio.svg"
rm -f "$XDG_CONFIG/autostart/io.github.HamiidStudio.desktop"
rm -rf "$XDG_DATA/hamiid-studio/app"

# Copy the application, data, engine and Pixi manifest.  User data lives
# elsewhere and is never touched by an update.
rm -rf "$APP_DIR/leet_customizer" "$APP_DIR/data" "$APP_DIR/engine" "$APP_DIR/scripts"
cp -a "$HERE/leet_customizer" "$APP_DIR/"
cp -a "$HERE/data" "$APP_DIR/"
cp -a "$HERE/engine" "$APP_DIR/"
cp -a "$HERE/scripts" "$APP_DIR/"
cp -a "$HERE/1337-customizer" "$HERE/uninstall.sh" "$APP_DIR/"
cp -a "$HERE/pixi.toml" "$HERE/pixi.lock" "$APP_DIR/" 2>/dev/null || true
cp -a "$HERE/README.md" "$HERE/COMMANDS.md" "$HERE/LICENSE" "$HERE/NOTICE.md" "$APP_DIR/" 2>/dev/null || true
chmod +x "$APP_DIR/1337-customizer" "$APP_DIR/engine/build-mpvpaper.sh" "$APP_DIR/engine/bin/mpvpaper" 2>/dev/null || true

install -m 644 "$HERE/data/1337-customizer.svg" "$ICON_DIR/1337-customizer.svg"
install -m 644 "$HERE/data/1337-customizer.desktop" "$XDG_DATA/applications/1337-customizer.desktop"
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "$XDG_DATA/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$XDG_DATA/applications" 2>/dev/null || true

find_pixi() {
  leet_find_pixi 2>/dev/null || true
}

install_pixi() {
  say "Pixi was not found; installing it into $BIN_DIR …"
  mkdir -p "$BIN_DIR"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL https://pixi.sh/install.sh | \
      env PIXI_BIN_DIR="$BIN_DIR" PIXI_HOME="$PIXI_HOME" \
        PIXI_NO_PATH_UPDATE=1 PIXI_NO_TELEMETRY=1 sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://pixi.sh/install.sh | \
      env PIXI_BIN_DIR="$BIN_DIR" PIXI_HOME="$PIXI_HOME" \
        PIXI_NO_PATH_UPDATE=1 PIXI_NO_TELEMETRY=1 sh
  else
    warn "Pixi is missing and neither curl nor wget is available."
    return 1
  fi
}

pixi_environment_ok() {
  "$1" run --frozen --manifest-path "$APP_DIR/pixi.toml" python - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
from PIL import Image
import cairo  # noqa: F401
if Gtk.get_major_version() != 4 or Gtk.get_minor_version() < 14:
    raise SystemExit("GTK 4.14 or newer is required")
if Adw.MAJOR_VERSION < 1 or (Adw.MAJOR_VERSION == 1 and Adw.MINOR_VERSION < 5):
    raise SystemExit("libadwaita 1.5 or newer is required")
PY
}

system_environment_ok() {
  "${LEET_PYTHON:-python3}" - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
from PIL import Image  # noqa: F401
PY
}

install_pixi_environment() {
  PIXI="$(find_pixi)"
  if [ -z "$PIXI" ]; then
    install_pixi || true
    PIXI="$(find_pixi)"
  fi
  if [ -z "$PIXI" ]; then
    warn "Pixi installation failed; trying the system Python instead."
    return 1
  fi

  say "Using Pixi: $PIXI ($("$PIXI" --version 2>/dev/null || echo 'version unknown'))"
  say "Installing Python, GTK, libadwaita and Pillow packages from pixi.toml …"
  leet_prepare_pixi_config "$APP_DIR"
  if [ -f "$APP_DIR/pixi.lock" ]; then
    if ! "$PIXI" install --frozen --manifest-path "$APP_DIR/pixi.toml"; then
      "$PIXI" install --manifest-path "$APP_DIR/pixi.toml" || return 1
    fi
  else
    "$PIXI" install --manifest-path "$APP_DIR/pixi.toml" || return 1
  fi

  if ! pixi_environment_ok "$PIXI"; then
    warn "The Pixi environment could not load GTK, libadwaita and Pillow."
    warn "Trying the system Python instead."
    return 1
  fi
  return 0
}

if [ "$USE_PIXI" -eq 1 ]; then
  if ! install_pixi_environment; then
    USE_PIXI=0
  fi
fi

if [ "$USE_PIXI" -eq 0 ] && ! system_environment_ok; then
  warn "The system Python is missing GTK 4, libadwaita or Pillow."
  warn "Install the distro packages listed in README.md, or use Pixi."
fi

if [ "$USE_PIXI" -eq 1 ]; then
  printf 'pixi\n' > "$APP_DIR/.leet-install-mode"
else
  printf 'system\n' > "$APP_DIR/.leet-install-mode"
fi

cat > "$BIN_DIR/1337-customizer" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$APP_DIR/1337-customizer" "\$@"
EOF
chmod +x "$BIN_DIR/1337-customizer"

if ! command -v 1337-customizer >/dev/null 2>&1; then
  warn "$BIN_DIR is not on PATH."
  warn "Open from a terminal with: $BIN_DIR/1337-customizer"
  warn "Or add this to your shell profile: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo "1337-Customizer installed."
echo "  app:     $APP_DIR"
echo "  command: $BIN_DIR/1337-customizer"
echo "  open:    1337-customizer"
echo "  menu:    1337-Customizer"
if [ "$USE_PIXI" -eq 1 ]; then
  echo "  python:  Pixi environment ($APP_DIR/.pixi)"
else
  echo "  python:  system Python (${LEET_PYTHON:-python3})"
fi
if [ -n "$LEET_GOINFRE_ROOT" ]; then
  echo "  goinfre: $LEET_GOINFRE_ROOT"
  echo "           (Pixi packages/environments and app cache)"
fi
if [ "$LAUNCH" = 1 ]; then
  exec "$BIN_DIR/1337-customizer"
fi
