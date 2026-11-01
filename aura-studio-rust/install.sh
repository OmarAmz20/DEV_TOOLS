#!/bin/sh
# Install Aura Studio for the current user.
#
# By default this uses Pixi: it installs Pixi into ~/.local/bin when missing,
# creates the Python/GTK/libadwaita environment from pixi.toml + pixi.lock,
# then adds a launcher and desktop entry.  No root is required for the app
# itself.  Optional desktop helpers (ffmpeg, dconf, feh) are installed with
# the system package manager when possible.
#
#   ./install.sh                 Pixi environment (recommended)
#   ./install.sh --system        use the distro's Python + GTK packages
#   ./install.sh --no-helpers    skip installing optional system helpers
#   ./install.sh --no-autostart  do not reapply the saved look after login
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}
USE_PIXI=1
INSTALL_HELPERS=1
INSTALL_AUTOSTART=1
PIXI_BIN_DIR=${PIXI_BIN_DIR:-"$HOME/.local/bin"}
PIXI_HOME=${PIXI_HOME:-}

for argument in "$@"; do
    case "$argument" in
        --system|--no-pixi) USE_PIXI=0 ;;
        --no-helpers|--no-system-deps) INSTALL_HELPERS=0 ;;
        --no-autostart) INSTALL_AUTOSTART=0 ;;
        -h|--help)
            cat <<'USAGE'
Install Aura Studio for the current user.

  ./install.sh                 Pixi environment (recommended)
  ./install.sh --system        use the distro's Python + GTK packages
  ./install.sh --no-helpers    skip installing optional system helpers
  ./install.sh --no-autostart  do not reapply the saved look after login

Pixi is installed into ~/.local/bin when missing.  The app itself needs no
root; optional helpers (ffmpeg, dconf, feh) may ask for sudo.

On 42-school machines, ~/goinfre is detected automatically: the Pixi
environment, package cache and thumbnail cache live there instead of in your
small home quota.
USAGE
            exit 0
            ;;
        *) echo "install.sh: unknown option: $argument" >&2; exit 2 ;;
    esac
done

# Keep big files off the home quota on 42-school machines.
GOINFRE_ROOT=""
for candidate in "${AURA_GOINFRE:-}" "$HOME/goinfre"; do
    if [ -n "$candidate" ] && [ -d "$candidate" ] && [ -w "$candidate" ]; then
        AURA_GOINFRE=$(readlink -f -- "$candidate" 2>/dev/null || printf '%s' "$candidate")
        GOINFRE_ROOT="$AURA_GOINFRE/aura-studio"
        mkdir -p "$GOINFRE_ROOT" "$GOINFRE_ROOT/cache"
        : "${PIXI_HOME:=$GOINFRE_ROOT/pixi-home}"
        : "${PIXI_CACHE_DIR:=$GOINFRE_ROOT/pixi-cache}"
        : "${CARGO_HOME:=$GOINFRE_ROOT/cargo-home}"
        : "${CARGO_TARGET_DIR:=$GOINFRE_ROOT/cargo-target}"
        export AURA_GOINFRE PIXI_HOME PIXI_CACHE_DIR CARGO_HOME CARGO_TARGET_DIR
        break
    fi
done
: "${PIXI_HOME:=$HOME/.pixi}"
export PIXI_HOME

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

x11=0
if [ "${XDG_SESSION_TYPE:-}" = "x11" ] || \
   { [ -z "${XDG_SESSION_TYPE:-}" ] && [ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; }; then
    x11=1
fi
find_pixi() {
    for candidate in "$(command -v pixi 2>/dev/null || true)" \
                     "$PIXI_BIN_DIR/pixi" \
                     "$PIXI_HOME/bin/pixi"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$(readlink -f -- "$candidate" 2>/dev/null || printf '%s' "$candidate")"
            return 0
        fi
    done
    return 1
}

prepare_goinfre_environment() {
    [ -n "$GOINFRE_ROOT" ] || return 0
    target="$GOINFRE_ROOT/pixi"
    if [ -L "$ROOT/.pixi" ] && [ -e "$ROOT/.pixi" ]; then
        return 0
    fi
    if [ -L "$ROOT/.pixi" ]; then
        rm -f "$ROOT/.pixi"
    fi
    if [ -e "$ROOT/.pixi" ]; then
        if [ -e "$target" ]; then
            warn "$ROOT/.pixi and $target both exist; keeping the local environment."
            warn "Remove the local .pixi later if you want the goinfre copy to be used."
            return 0
        fi
        say "Moving the Pixi environment into goinfre…"
        if mv "$ROOT/.pixi" "$target" 2>/dev/null; then
            ln -s "$target" "$ROOT/.pixi"
        else
            warn "Could not move $ROOT/.pixi into goinfre; keeping it in place."
        fi
    else
        mkdir -p "$target"
        ln -s "$target" "$ROOT/.pixi"
    fi
}

install_pixi() {
    say "Pixi was not found; installing it into $PIXI_BIN_DIR …"
    mkdir -p "$PIXI_BIN_DIR"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL https://pixi.sh/install.sh | \
            env PIXI_BIN_DIR="$PIXI_BIN_DIR" PIXI_NO_PATH_UPDATE=1 \
                PIXI_NO_TELEMETRY=1 sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://pixi.sh/install.sh | \
            env PIXI_BIN_DIR="$PIXI_BIN_DIR" PIXI_NO_PATH_UPDATE=1 \
                PIXI_NO_TELEMETRY=1 sh
    else
        warn "Pixi is missing and neither curl nor wget is available."
        return 1
    fi
}

check_system_gtk() {
    "$1" - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Adw
if Gtk.get_major_version() != 4 or Gtk.get_minor_version() < 10:
    raise SystemExit("GTK 4.10 or newer is required")
if Adw.MAJOR_VERSION < 1 or (Adw.MAJOR_VERSION == 1 and Adw.MINOR_VERSION < 6):
    raise SystemExit("libadwaita 1.6 or newer is required")
PY
}

install_pixi_environment() {
    PIXI=$(find_pixi || true)
    if [ -z "$PIXI" ]; then
        install_pixi
        PIXI=$(find_pixi || true)
    fi
    if [ -z "$PIXI" ]; then
        warn "Pixi installation failed; trying the system Python instead."
        return 1
    fi
    say "Using Pixi: $PIXI ($("$PIXI" --version 2>/dev/null || echo 'version unknown'))"

    cd "$ROOT"
    say "Installing the project environment from pixi.toml + pixi.lock (first run downloads GTK)…"
    if [ -f "$ROOT/pixi.lock" ]; then
        "$PIXI" install --frozen || "$PIXI" install
    else
        "$PIXI" install
    fi

    if ! "$PIXI" run --frozen --manifest-path "$ROOT/pixi.toml" \
            python -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw' \
            >/dev/null 2>&1; then
        warn "The Pixi environment could not load GTK; removing it and trying the system Python."
        rm -rf "$ROOT/.pixi/envs/default"
        return 1
    fi

    if ! "$PIXI" run --frozen --manifest-path "$ROOT/pixi.toml" \
            sh -c '[ -n "${GSETTINGS_BACKEND:-}" ]' >/dev/null 2>&1; then
        warn "The host dconf/GSettings backend was not detected inside Pixi."
        warn "Wallpaper/theme settings may not reach the desktop; run with --system if needed."
    fi
    return 0
}

install_system_environment() {
    if check_system_gtk "$PYTHON" >/dev/null 2>&1; then
        return 0
    fi
    warn "System Python does not have GTK 4.10+ / libadwaita 1.6+."

    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
    fi
    case "${ID:-} ${ID_LIKE:-}" in
        *debian*|*ubuntu*)
            say "Install them with:"
            say "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gdkpixbuf-2.0"
            ;;
        *fedora*)
            say "Install them with:"
            say "  sudo dnf install python3-gobject gtk4 libadwaita"
            ;;
        *arch*|*manjaro*)
            say "Install them with:"
            say "  sudo pacman -S python-gobject gtk4 libadwaita"
            ;;
        *)
            say "Install PyGObject, GTK 4.10+ and libadwaita 1.6+ for your distribution."
            ;;
    esac
    return 1
}

rust_core_note() {
    if [ -f "$ROOT/aura_core.abi3.so" ]; then
        printf 'keeping the existing build.'
    else
        printf 'Aura will use the Python fallback.'
    fi
}

build_rust_core() {
    [ -f "$ROOT/Cargo.toml" ] || return 0
    say "Building the optional Rust colour/palette core…"
    if [ "$USE_PIXI" -eq 1 ]; then
        PIXI=$(find_pixi || true)
        if [ -n "$PIXI" ]; then
            if "$PIXI" run --frozen --manifest-path "$ROOT/pixi.toml" build-rust; then
                return 0
            fi
            warn "Rust core build failed; $(rust_core_note)"
            return 0
        fi
    fi
    if command -v cargo >/dev/null 2>&1; then
        if ! "$ROOT/scripts/build-rust.sh"; then
            warn "Rust core build failed; $(rust_core_note)"
        fi
    else
        warn "cargo was not found; $(rust_core_note)"
    fi
}

maybe_install_helpers() {
    [ "$INSTALL_HELPERS" -eq 1 ] || return 0

    missing=""
    command -v dconf >/dev/null 2>&1 || missing="$missing dconf"
    command -v ffmpeg >/dev/null 2>&1 || missing="$missing ffmpeg"

    if [ "$x11" -eq 1 ]; then
        command -v feh >/dev/null 2>&1 || missing="$missing feh"
    fi
    [ -n "$missing" ] || return 0

    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
    fi
    packages=""
    case " ${ID:-} ${ID_LIKE:-} " in
        *debian*|*ubuntu*)
            manager="apt-get"
            for helper in $missing; do
                case "$helper" in
                    dconf) packages="$packages dconf-cli" ;;
                    *) packages="$packages $helper" ;;
                esac
            done
            update="apt-get update"
            install="apt-get install -y --no-install-recommends"
            ;;
        *fedora*)
            manager="dnf"
            packages="$missing"
            update=""
            install="dnf install -y"
            ;;
        *arch*|*manjaro*)
            manager="pacman"
            packages=""
            for helper in $missing; do
                case "$helper" in
                    dconf) packages="$packages dconf" ;;
                    *) packages="$packages $helper" ;;
                esac
            done
            update=""
            install="pacman -S --needed --noconfirm"
            ;;
        *)
            warn "Install these optional helpers manually: $missing"
            return 0
            ;;
    esac
    command -v "$manager" >/dev/null 2>&1 || {
        warn "Optional helpers not installed: $missing"
        return 0
    }

    if [ "$(id -u)" -eq 0 ]; then
        SUDO=""
    elif command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        warn "Optional helpers need root: $missing"
        return 0
    fi

    say "Installing optional desktop helpers:$packages"
    if ! $SUDO $install $packages >/dev/null 2>&1; then
        if [ -n "$update" ]; then
            $SUDO $update >/dev/null 2>&1 || true
            $SUDO $install $packages >/dev/null 2>&1 || {
                warn "Could not install helpers:$packages"
                return 0
            }
        else
            warn "Could not install helpers:$packages"
            return 0
        fi
    fi
}

if [ "$USE_PIXI" -eq 1 ]; then
    prepare_goinfre_environment
    if [ -f "$ROOT/.pixi/envs/default/conda-meta/pixi_env_prefix" ]; then
        "$PYTHON" "$ROOT/scripts/fix-pixi-prefix.py" \
            "$ROOT/.pixi/envs/default" >/dev/null 2>&1 || true
    fi
    if ! install_pixi_environment; then
        USE_PIXI=0
    fi
fi
if [ "$USE_PIXI" -eq 0 ]; then
    if ! install_system_environment; then
        die "Aura Studio needs GTK 4.10+ and libadwaita 1.6+."
    fi
fi

build_rust_core
maybe_install_helpers

DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN=${XDG_BIN_HOME:-"$HOME/.local/bin"}
APPS="$DATA_HOME/applications"
ICONS="$DATA_HOME/icons/hicolor/scalable/apps"
mkdir -p "$BIN" "$APPS" "$ICONS"

ln -sfn "$ROOT/aura-studio" "$BIN/aura-studio"
chmod +x "$ROOT/aura-studio" "$ROOT/install.sh" "$ROOT/uninstall.sh"
if [ "$USE_PIXI" -eq 1 ]; then
    printf 'pixi\n' > "$ROOT/.aura-install-mode"
else
    printf 'system\n' > "$ROOT/.aura-install-mode"
fi

cp "$ROOT/data/icons/hicolor/scalable/apps/io.github.AuraStudio.svg" \
    "$ICONS/io.github.AuraStudio.svg"
sed "s|@ROOT@|$ROOT|g" "$ROOT/data/io.github.AuraStudio.desktop.in" \
    > "$APPS/io.github.AuraStudio.desktop"
chmod 644 "$APPS/io.github.AuraStudio.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d "$DATA_HOME/icons/hicolor" ]; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

# Reapply the chosen look after login.  This works on GNOME, X11, Wayland and
# desktops that reset themes, icons, fonts or the wallpaper between sessions.
# The command applies the saved look in the background and exits without
# opening the window.
if [ "$INSTALL_AUTOSTART" -eq 1 ]; then
    if "$BIN/aura-studio" autostart on >/dev/null 2>&1; then
        say "Login reapply enabled: the selected look is restored after you log in."
        # Apply the look that is already saved, without opening the window.
        if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
            "$BIN/aura-studio" apply-saved --quiet --log >/dev/null 2>&1 || true
        fi
    else
        warn "Could not enable login reapply. Run: aura-studio autostart on"
    fi
else
    "$BIN/aura-studio" autostart off >/dev/null 2>&1 || true
fi

printf '\nAura Studio is installed.\n'
printf '  Run:            aura-studio\n'
printf '  Launcher:       %s\n' "$BIN/aura-studio"
printf '  Environment:    %s\n' \
    "$( [ "$USE_PIXI" -eq 1 ] && printf '%s' "$ROOT/.pixi/envs/default" || printf 'system Python' )"
printf '  Pixi:           %s\n' \
    "$( [ "$USE_PIXI" -eq 1 ] && find_pixi || printf 'not used' )"
if [ -f "$ROOT/aura_core.abi3.so" ]; then
    printf '  Rust core:      %s\n' "$ROOT/aura_core.abi3.so"
else
    printf '  Rust core:      Python fallback\n'
fi
if [ -n "$GOINFRE_ROOT" ]; then
    printf '  Goinfre:        %s\n' "$GOINFRE_ROOT"
    if [ "$USE_PIXI" -eq 1 ]; then
        printf '                  (Pixi environment, package cache and thumbnails)\n'
    else
        printf '                  (package cache and thumbnails)\n'
    fi
fi
printf '\nOpen Aura Studio from your app launcher, or run: aura-studio\n'
if ! command -v aura-studio >/dev/null 2>&1; then
    printf 'If the command is not found yet, use: %s/aura-studio (or log in again).\n' "$BIN"
fi
if [ "${XDG_SESSION_TYPE:-}" = "x11" ]; then
    printf 'X11: wallpapers use GNOME settings on GNOME, or feh on other desktops.\n'
    printf '     For transparent windows on non-GNOME X11, install and run picom.\n'
fi
printf 'Login reapply: %s (aura-studio autostart status)\n' \
    "$( [ "$INSTALL_AUTOSTART" -eq 1 ] && printf 'on' || printf 'off' )"
printf 'Uninstall the launcher with ./uninstall.sh (settings and profiles stay).\n\n'
