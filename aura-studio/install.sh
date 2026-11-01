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
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}
USE_PIXI=1
INSTALL_HELPERS=1
PIXI_BIN_DIR=${PIXI_BIN_DIR:-"$HOME/.local/bin"}
PIXI_HOME=${PIXI_HOME:-"$HOME/.pixi"}

for argument in "$@"; do
    case "$argument" in
        --system|--no-pixi) USE_PIXI=0 ;;
        --no-helpers|--no-system-deps) INSTALL_HELPERS=0 ;;
        -h|--help)
            cat <<'USAGE'
Install Aura Studio for the current user.

  ./install.sh                 Pixi environment (recommended)
  ./install.sh --system        use the distro's Python + GTK packages
  ./install.sh --no-helpers    skip installing optional system helpers

Pixi is installed into ~/.local/bin when missing.  The app itself needs no
root; optional helpers (ffmpeg, dconf, feh) may ask for sudo.
USAGE
            exit 0
            ;;
        *) echo "install.sh: unknown option: $argument" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

x11=0
if [ "${XDG_SESSION_TYPE:-}" = "x11" ] || \
   { [ -z "${XDG_SESSION_TYPE:-}" ] && [ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; }; then
    x11=1
fi
case "${XDG_CURRENT_DESKTOP:-}" in
    *GNOME*|*gnome*|*ubuntu*|*Ubuntu*) gnome=1 ;;
    *) gnome=0 ;;
esac

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
    if ! install_pixi_environment; then
        USE_PIXI=0
    fi
fi
if [ "$USE_PIXI" -eq 0 ]; then
    if ! install_system_environment; then
        die "Aura Studio needs GTK 4.10+ and libadwaita 1.6+."
    fi
fi

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

# feh cannot remember a root pixmap across login, so give non-GNOME X11 users a
# tiny autostart entry that puts the last Aura wallpaper back.  GNOME stores it
# in gsettings and does not need this.
if [ "$x11" -eq 1 ] && [ "$gnome" -eq 0 ]; then
    AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
    mkdir -p "$AUTOSTART"
    cat > "$AUTOSTART/io.github.AuraStudio.wallpaper.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Aura Studio wallpaper
Comment=Reapply the last Aura Studio wallpaper after login
Exec=$ROOT/aura-studio reapply-wallpaper
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
    chmod 644 "$AUTOSTART/io.github.AuraStudio.wallpaper.desktop"
fi

printf '\nAura Studio is installed.\n'
printf '  Run:            aura-studio\n'
printf '  Launcher:       %s\n' "$BIN/aura-studio"
printf '  Environment:    %s\n' \
    "$( [ "$USE_PIXI" -eq 1 ] && printf '%s' "$ROOT/.pixi/envs/default" || printf 'system Python' )"
printf '  Pixi:           %s\n' \
    "$( [ "$USE_PIXI" -eq 1 ] && find_pixi || printf 'not used' )"
printf '\nOpen Aura Studio from your app launcher, or run: aura-studio\n'
if ! command -v aura-studio >/dev/null 2>&1; then
    printf 'If the command is not found yet, use: %s/aura-studio (or log in again).\n' "$BIN"
fi
if [ "${XDG_SESSION_TYPE:-}" = "x11" ]; then
    printf 'X11: wallpapers use GNOME settings on GNOME, or feh on other desktops.\n'
    printf '     For transparent windows on non-GNOME X11, install and run picom.\n'
fi
printf 'Uninstall the launcher with ./uninstall.sh (settings and profiles stay).\n\n'
