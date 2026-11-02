#!/usr/bin/env bash
# Install 1337-Customizer for the current user. No sudo is required.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
XDG_DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
XDG_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PREFIX="${LEET_PREFIX:-$XDG_DATA/1337-customizer}"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$PREFIX/app"
ICON_DIR="$XDG_DATA/icons/hicolor/scalable/apps"
LAUNCH=0
for arg in "$@"; do
  case "$arg" in
    --launch) LAUNCH=1 ;;
    --help|-h)
      echo "Usage: ./install.sh [--launch]"
      echo "Installs 1337-Customizer to $PREFIX"
      exit 0
      ;;
  esac
done

mkdir -p "$APP_DIR" "$BIN_DIR" "$ICON_DIR" "$XDG_DATA/applications"

# Clean up launchers from the previous Hamiid Studio name.  User data in the
# old XDG folders is migrated by the application on first launch.
rm -f "$HOME/.local/bin/hamiid-studio"
rm -f "$XDG_DATA/applications/io.github.HamiidStudio.desktop"
rm -f "$XDG_DATA/icons/hicolor/scalable/apps/io.github.HamiidStudio.svg"
rm -f "$XDG_CONFIG/autostart/io.github.HamiidStudio.desktop"
rm -rf "$XDG_DATA/hamiid-studio/app"

# Copy the application, data and engine.  User data lives elsewhere and is
# never touched by an update.
rm -rf "$APP_DIR/leet_customizer" "$APP_DIR/data" "$APP_DIR/engine"
cp -a "$HERE/leet_customizer" "$APP_DIR/"
cp -a "$HERE/data" "$APP_DIR/"
cp -a "$HERE/engine" "$APP_DIR/"
cp -a "$HERE/1337-customizer" "$HERE/uninstall.sh" "$APP_DIR/"
cp -a "$HERE/README.md" "$HERE/COMMANDS.md" "$HERE/LICENSE" "$HERE/NOTICE.md" "$APP_DIR/" 2>/dev/null || true
chmod +x "$APP_DIR/1337-customizer" "$APP_DIR/engine/build-mpvpaper.sh" "$APP_DIR/engine/bin/mpvpaper" 2>/dev/null || true

install -m 644 "$HERE/data/1337-customizer.svg" "$ICON_DIR/1337-customizer.svg"
install -m 644 "$HERE/data/1337-customizer.desktop" "$XDG_DATA/applications/1337-customizer.desktop"
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "$XDG_DATA/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$XDG_DATA/applications" 2>/dev/null || true

cat > "$BIN_DIR/1337-customizer" <<EOF
#!/usr/bin/env bash
set -euo pipefail
APP="$APP_DIR"
export PYTHONPATH="\$APP\${PYTHONPATH:+:\$PYTHONPATH}"
for candidate in /usr/lib/girepository-1.0 /usr/lib64/girepository-1.0 /usr/lib/x86_64-linux-gnu/girepository-1.0 /usr/local/lib/girepository-1.0; do
  if [ -d "\$candidate" ]; then
    case ":\${GI_TYPELIB_PATH:-}:" in
      *":\$candidate:"*) ;;
      *) export GI_TYPELIB_PATH="\${GI_TYPELIB_PATH:+\$GI_TYPELIB_PATH:}\$candidate" ;;
    esac
  fi
done
exec "\${LEET_PYTHON:-python3}" -m leet_customizer "\$@"
EOF
chmod +x "$BIN_DIR/1337-customizer"

echo "1337-Customizer installed."
echo "  app:     $APP_DIR"
echo "  command: $BIN_DIR/1337-customizer"
echo "  menu:    1337-Customizer"
if [ "$LAUNCH" = 1 ]; then
  exec "$BIN_DIR/1337-customizer"
fi
