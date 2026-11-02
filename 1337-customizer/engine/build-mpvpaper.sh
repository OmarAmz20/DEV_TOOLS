#!/usr/bin/env bash
# Build mpvpaper into engine/bin without sudo.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HERE/.build"
SRC="$BUILD/src"
ARCHIVE="$HERE/mpvpaper-src.tar.gz"
BIN="$HERE/bin/mpvpaper"

if [ -x "$BIN" ] && [ "${1:-}" != "--force" ]; then
  if "$BIN" --help >/dev/null 2>&1; then
    echo "Bundled mpvpaper is ready: $BIN"
    exit 0
  fi
fi

for tool in meson ninja pkg-config cc tar; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing build tool: $tool" >&2
    exit 1
  fi
done
for package in mpv wayland-client wayland-protocols wayland-egl egl; do
  if ! pkg-config --exists "$package"; then
    echo "Missing development package: $package" >&2
    echo "On Arch: sudo pacman -S meson ninja wayland-protocols mpv" >&2
    echo "On Ubuntu: sudo apt install meson ninja-build libmpv-dev libwayland-dev wayland-protocols libegl1-mesa-dev" >&2
    exit 1
  fi
done

rm -rf "$BUILD"
mkdir -p "$SRC" "$HERE/bin"
if [ -f "$ARCHIVE" ]; then
  tar -xzf "$ARCHIVE" -C "$SRC" --strip-components=1
else
  echo "Source archive missing: $ARCHIVE" >&2
  exit 1
fi
cd "$SRC"
meson setup build --prefix="$BUILD/install" >/dev/null
meson compile -C build >/dev/null
cp build/mpvpaper "$BIN"
chmod 755 "$BIN"
echo "Built $BIN"
"$BIN" --help | head -n 2
