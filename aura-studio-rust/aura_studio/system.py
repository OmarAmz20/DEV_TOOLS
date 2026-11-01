"""The part that touches the desktop: wallpaper backends, GTK colours, terminals.

Aura keeps a snapshot of everything it changes before the first apply and
puts it back from *Restore original look*.  Wallpapers use the best backend
that is actually running (DankMaterialShell, awww, hyprpaper, swaybg, feh or
GNOME's gsettings), so the same app works on Wayland and X11.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

from gi.repository import Gio, GLib

from . import library, palette, store

HOME = os.path.expanduser("~")
CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local/share")
STATE_HOME = os.environ.get("XDG_STATE_HOME") or os.path.join(HOME, ".local/state")
THEMES_DIR = os.path.join(DATA_HOME, "themes")
GTK3_CSS = os.path.join(CONFIG_HOME, "gtk-3.0/gtk.css")
GTK4_CSS = os.path.join(CONFIG_HOME, "gtk-4.0/gtk.css")
KITTY_CONF = os.path.join(CONFIG_HOME, "kitty/kitty.conf")
KITTY_THEME = os.path.join(CONFIG_HOME, "kitty/aura-theme.conf")
MARKER = "/* aura-studio */"
KITTY_MARKER = "include aura-theme.conf # aura-studio"
OUR_THEMES = ("Aura A", "Aura B")
TERMINAL = "/org/gnome/terminal/legacy/profiles:"
SWAYBG_PID = os.path.join(store.CONFIG_DIR, "swaybg.pid")
DESKTOP_PID = os.path.join(store.CONFIG_DIR, "desktop-wallpaper.pid")
DESKTOP_LOG = os.path.join(store.CONFIG_DIR, "desktop-wallpaper.log")
DESKTOP_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "x11_wallpaper.py")
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(APP_ROOT, "aura-studio")
AUTOSTART_DIR = os.path.join(CONFIG_HOME, "autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "io.github.AuraStudio.apply.desktop")
LEGACY_AUTOSTART_FILE = os.path.join(
    AUTOSTART_DIR, "io.github.AuraStudio.wallpaper.desktop")

TOUCHED = [
    ("org.gnome.desktop.interface", "gtk-theme"),
    ("org.gnome.desktop.interface", "color-scheme"),
    ("org.gnome.desktop.interface", "icon-theme"),
    ("org.gnome.desktop.interface", "cursor-theme"),
    ("org.gnome.desktop.interface", "cursor-size"),
    ("org.gnome.desktop.interface", "font-name"),
    ("org.gnome.desktop.interface", "document-font-name"),
    ("org.gnome.desktop.interface", "monospace-font-name"),
    ("org.gnome.desktop.interface", "text-scaling-factor"),
    ("org.gnome.desktop.background", "picture-uri"),
    ("org.gnome.desktop.background", "picture-uri-dark"),
    ("org.gnome.desktop.background", "picture-options"),
    ("org.gnome.desktop.background", "primary-color"),
    ("org.gnome.desktop.screensaver", "picture-uri"),
    ("org.gnome.desktop.screensaver", "picture-options"),
]


# --- tiny process / settings helpers ----------------------------------------------

def _run(command, timeout=12):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, 1, "", str(error))


def _dconf(*args):
    if not shutil.which("dconf"):
        return ""
    return _run(["dconf", *args]).stdout.strip()


def _dconf_write(path, value):
    """Write a dconf value and report success instead of guessing from output."""
    if not shutil.which("dconf"):
        return False
    return _run(["dconf", "write", path, str(value)], timeout=8).returncode == 0


def _schema(name):
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(name, True) is None:
        return None
    return Gio.Settings.new(name)


def _has_key(settings, key):
    schema = settings.get_property("settings-schema")
    return bool(schema is not None and schema.has_key(key))


def _get_string(schema, key, default=""):
    host = _host_setting_value(schema, key)
    if isinstance(host, str):
        return host
    settings = _schema(schema)
    if settings is None or not _has_key(settings, key):
        return default
    try:
        return settings.get_string(key)
    except Exception:
        return default


def _get_double(schema, key, default=1.0):
    host = _host_setting_value(schema, key)
    if isinstance(host, (int, float)) and not isinstance(host, bool):
        return float(host)
    settings = _schema(schema)
    if settings is None or not _has_key(settings, key):
        return default
    try:
        return settings.get_double(key)
    except Exception:
        return default


def _get_int(schema, key, default=0):
    host = _host_setting_value(schema, key)
    if isinstance(host, int) and not isinstance(host, bool):
        return host
    settings = _schema(schema)
    if settings is None or not _has_key(settings, key):
        return default
    try:
        return settings.get_int(key)
    except Exception:
        return default


def _set_variant(schema, key, value: GLib.Variant):
    written = False
    settings = _schema(schema)
    if (settings is not None and _has_key(settings, key)
            and settings.is_writable(key)):
        try:
            settings.set_value(key, value)
            written = True
        except Exception:
            pass
    # Inside Pixi, Gio may be pointing at an isolated backend.  Writing the
    # host's dconf as well makes the change visible to gnome-shell and apps.
    if _host_gsettings_enabled():
        written = _host_gsettings_set(schema, key, value.print_(True)) or written
    return written


def _set_string(schema, key, value):
    return _set_variant(schema, key, GLib.Variant("s", value))


def _set_double(schema, key, value):
    return _set_variant(schema, key, GLib.Variant("d", float(value)))


def _set_int(schema, key, value):
    return _set_variant(schema, key, GLib.Variant("i", int(value)))


def _sync():
    with contextlib.suppress(Exception):
        Gio.Settings.sync()


# --- backend detection ------------------------------------------------------------

_BACKEND = None
_BACKEND_PREFERENCE = None


def _dms_available():
    if not shutil.which("dms"):
        return False
    result = _run(["dms", "ipc", "call", "outputs", "current"], timeout=5)
    return result.stdout.strip().startswith("[")


def _dms_screens():
    result = _run(["dms", "ipc", "call", "outputs", "current"], timeout=5)
    try:
        screens = json.loads(result.stdout)
        return [str(screen) for screen in screens]
    except (ValueError, TypeError):
        return []


def _dms_output(*args):
    result = _run(["dms", "ipc", "call", *args], timeout=20)
    return (result.stdout + result.stderr).strip()


def _awww_installed():
    return bool(shutil.which("awww") and shutil.which("awww-daemon"))


def _hyprland():
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) or \
        "hyprland" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def _wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _gnome_session():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "gnome" in desktop or "ubuntu" in desktop


_DESKTOP_PYTHON = False


def _desktop_python():
    """A Python that can import the host's GTK 3, or None.

    The Pixi environment only contains GTK 4.  The tiny desktop-window helper
    uses the system GTK 3, which is already installed on Ubuntu.
    """
    global _DESKTOP_PYTHON
    if _DESKTOP_PYTHON is not False:
        return _DESKTOP_PYTHON
    candidates = [
        os.environ.get("AURA_DESKTOP_PYTHON"),
        "/usr/bin/python3",
        shutil.which("python3"),
    ]
    probe = ("import gi; gi.require_version('Gtk', '3.0'); "
             "gi.require_version('GdkPixbuf', '2.0'); "
             "from gi.repository import Gtk, GdkPixbuf")
    for candidate in candidates:
        if not candidate:
            continue
        result = _run([candidate, "-c", probe], timeout=8)
        if result.returncode == 0:
            _DESKTOP_PYTHON = candidate
            return candidate
    _DESKTOP_PYTHON = None
    return None


def _desktop_window_available():
    return bool(os.environ.get("DISPLAY")) and not _wayland() and \
        os.path.isfile(DESKTOP_HELPER) and _desktop_python() is not None


def _desktop_pid():
    try:
        with open(DESKTOP_PID, encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_is_desktop_helper(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return b"x11_wallpaper.py" in handle.read()
    except OSError:
        return False


def _stop_desktop_window():
    pid = _desktop_pid()
    if pid and _pid_is_desktop_helper(pid):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.1)
        if _pid_alive(pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
    with contextlib.suppress(FileNotFoundError):
        os.remove(DESKTOP_PID)


_DESKTOP_ENV_DROP = {
    "LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME",
    "GI_TYPELIB_PATH", "GSETTINGS_SCHEMA_DIR", "GSETTINGS_BACKEND",
    "GIO_EXTRA_MODULES", "GDK_BACKEND", "GDK_SCALE", "GDK_DPI_SCALE",
    "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR", "GTK_PATH",
    "GTK_THEME", "GTK_MODULES", "GTK_DEBUG", "XDG_DATA_DIRS",
    "CONDA_PREFIX", "VIRTUAL_ENV",
}


def _host_environment():
    """The host's own tools and settings backend, without the Pixi stack."""
    env = {key: value for key, value in os.environ.items()
           if key not in _DESKTOP_ENV_DROP
           and not key.startswith(("PIXI_", "CONDA_", "MAMBA_"))}
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    env["GSETTINGS_BACKEND"] = "dconf"
    return env


def _desktop_environment():
    """Keep the helper on the host's GTK 3, not the Pixi GTK 4 stack."""
    env = _host_environment()
    env["GDK_BACKEND"] = "x11"
    return env


def _host_gsettings_enabled():
    # ``memory`` means a test or an intentionally isolated session.  Never
    # write the host's dconf database behind the caller's back in that case.
    return (os.environ.get("GSETTINGS_BACKEND", "").lower() != "memory"
            and os.path.isfile("/usr/bin/gsettings"))


def _host_gsettings(*args, timeout=8):
    if not _host_gsettings_enabled():
        return None
    try:
        return subprocess.run(["/usr/bin/gsettings", *args],
                              capture_output=True, text=True, timeout=timeout,
                              env=_host_environment(), check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _host_gsettings_writable(schema, key):
    result = _host_gsettings("writable", schema, key)
    return bool(result is not None and result.returncode == 0
                and result.stdout.strip().lower() == "true")


def _host_gsettings_set(schema, key, value):
    result = _host_gsettings("set", schema, key, str(value))
    return bool(result is not None and result.returncode == 0)


def _host_gsettings_get(schema, key):
    result = _host_gsettings("get", schema, key)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _host_setting_value(schema, key):
    text = _host_gsettings_get(schema, key)
    if text is None:
        return None
    try:
        return GLib.Variant.parse(None, text, None, None).unpack()
    except Exception:
        return None


def _gnome_set_string(schema, key, value):
    """Write a GNOME string through Gio and, when possible, the host dconf.

    The second write matters inside the Pixi environment: it guarantees that
    gnome-shell itself sees the wallpaper even if the bundled GLib stack is
    using an isolated GSettings backend.
    """
    written = _set_string(schema, key, value)
    if _host_gsettings_enabled():
        written = _host_gsettings_set(schema, key, value) or written
    return written


def _start_desktop_window(path, mode="fill"):
    python = _desktop_python()
    if not python:
        raise RuntimeError("no system Python with GTK 3 for the desktop window")
    _stop_desktop_window()
    os.makedirs(store.CONFIG_DIR, exist_ok=True)
    with open(DESKTOP_LOG, "wb") as log:
        process = subprocess.Popen(
            [python, DESKTOP_HELPER, path, mode],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            env=_desktop_environment(),
            start_new_session=True, close_fds=True)
    with open(DESKTOP_PID, "w", encoding="utf-8") as handle:
        handle.write(str(process.pid))
    for _ in range(10):
        if process.poll() is not None:
            break
        time.sleep(0.1)
    if process.poll() is not None:
        with contextlib.suppress(FileNotFoundError):
            os.remove(DESKTOP_PID)
        try:
            with open(DESKTOP_LOG, encoding="utf-8", errors="replace") as handle:
                details = handle.read().strip().splitlines()[-3:]
        except OSError:
            details = []
        raise RuntimeError("desktop wallpaper window failed"
                           + (f": {'; '.join(details)}" if details else ""))


def _gnome_ready():
    settings = _schema("org.gnome.desktop.background")
    if settings is not None and settings.is_writable("picture-uri"):
        return True
    # Installed schema but a Pixi/GSettings backend mismatch: the host's own
    # gsettings can still be the reliable path.  Skip this in tests and in
    # explicitly isolated sessions.
    return _host_gsettings_writable("org.gnome.desktop.background", "picture-uri")


def backend_available(name):
    """Whether one named backend can work in the current session."""
    if name == "gnome":
        return _gnome_session() and _gnome_ready()
    if name == "desktop":
        return _desktop_window_available()
    if name == "feh":
        # GNOME Shell always draws above the X root pixmap, so feh is not a
        # usable backend there even though the binary is installed.
        return bool(shutil.which("feh")) and not _wayland() and not _gnome_session()
    if name == "dms":
        return _dms_available()
    if name == "hyprpaper":
        return _hyprland() and bool(shutil.which("hyprpaper"))
    if name == "awww":
        return _wayland() and _awww_installed() and not _gnome_session()
    if name == "swaybg":
        return _wayland() and bool(shutil.which("swaybg")) and not _gnome_session()
    return False


def _auto_backend_name(gnome_ready=None):
    gnome_ready = _gnome_ready() if gnome_ready is None else gnome_ready
    if _gnome_session():
        if gnome_ready:
            return "gnome"
        # GNOME ignores feh and wlroots daemons.  On Xorg the sticky desktop
        # window is the only user-level fallback; on Wayland there is none.
        if not _wayland() and _desktop_window_available():
            return "desktop"
        return "none"
    if _dms_available():
        return "dms"
    if _hyprland() and shutil.which("hyprpaper"):
        return "hyprpaper"
    if _wayland() and _awww_installed():
        return "awww"
    if _wayland() and shutil.which("swaybg"):
        return "swaybg"
    if not _wayland() and _gnome_session() and _desktop_window_available():
        # GNOME Shell ignores the X root pixmap.  When its background key is
        # locked, a desktop window is the only user-level way to show a picture.
        return "desktop"
    if shutil.which("feh") and not _wayland():
        return "feh"
    if not _wayland() and _desktop_window_available():
        return "desktop"
    if gnome_ready:
        return "gnome"
    return "none"


def _preferred_backend(preferred=None):
    # The environment is a deliberate per-launch override, so it wins over
    # both the saved setting and a config snapshot handed in by the caller.
    from_environment = os.environ.get("AURA_WALLPAPER_BACKEND", "").strip()
    if from_environment:
        return from_environment
    if preferred and preferred != "auto":
        return preferred
    try:
        return store.load_config().get("wallpaper_backend", "auto")
    except Exception:
        return "auto"


def detect_backend(refresh=False, preferred=None):
    """The wallpaper backend that is actually usable right now.

    ``preferred`` (or the ``wallpaper_backend`` setting) pins a backend.  If it
    is unavailable Aura falls back to automatic detection instead of failing,
    which keeps Ubuntu sessions working when, for example, gsettings is locked.
    """
    global _BACKEND, _BACKEND_PREFERENCE
    preferred = _preferred_backend(preferred)
    if preferred not in store.WALLPAPER_BACKENDS:
        preferred = "auto"
    if _BACKEND is not None and not refresh and _BACKEND_PREFERENCE == preferred:
        return _BACKEND
    gnome_ready = _gnome_ready()
    automatic = _auto_backend_name(gnome_ready)
    chosen = automatic
    if preferred != "auto":
        if backend_available(preferred):
            chosen = preferred
        else:
            chosen = automatic
    if chosen == "none":
        _BACKEND = {"name": "none", "label": "not detected", "preferred": preferred,
                    "fallback": False}
    else:
        _BACKEND = {
            "name": chosen,
            "label": store.WALLPAPER_BACKEND_LABELS.get(chosen, chosen),
            "preferred": preferred,
            "fallback": preferred not in ("auto", chosen),
        }
    _BACKEND_PREFERENCE = preferred
    return _BACKEND


def backend_label():
    backend = detect_backend()
    if backend.get("fallback"):
        return f"{backend['label']} (fallback)"
    return backend["label"]


def backend_choices():
    """Backends suitable for the Look & Feel menu, with an availability mark."""
    choices = []
    for name in store.WALLPAPER_BACKENDS:
        label = store.WALLPAPER_BACKEND_LABELS[name]
        if name == "auto":
            choices.append((name, label, True))
        else:
            choices.append((name, label, backend_available(name)))
    return choices


def session_label():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").strip()
    kind = "Wayland" if _wayland() else ("X11" if os.environ.get("DISPLAY") else "")
    if desktop:
        name = desktop.split(":")[0]
        return f"{name} ({kind})" if kind else name
    return kind or "unknown session"


def _dms_current_wallpapers():
    wallpapers = {}
    if not _dms_available():
        return wallpapers
    try:
        with open(os.path.join(STATE_HOME, "DankMaterialShell/session.json"),
                  encoding="utf-8") as handle:
            session = json.load(handle)
    except (OSError, ValueError):
        session = {}
    wallpapers["__per_monitor__"] = bool(session.get("perMonitorWallpaper"))
    global_path = session.get("wallpaperPath", "")
    if global_path:
        wallpapers["__global__"] = global_path
    for screen in _dms_screens():
        value = _dms_output("wallpaper", "getFor", screen)
        if value and not value.startswith("ERROR"):
            wallpapers[screen] = value
    return wallpapers


FEH_MODE_FLAGS = {
    "fill": "--bg-fill",
    "fit": "--bg-max",
    "stretch": "--bg-scale",
    "center": "--bg-center",
    "tile": "--bg-tile",
    "span": "--bg-max",
}
SWAYBG_MODES = {
    "fill": "fill",
    "fit": "fit",
    "stretch": "stretch",
    "center": "center",
    "tile": "tile",
    "span": "fit",
}
GNOME_PICTURE_OPTIONS = {
    "fill": "zoom",
    "fit": "scaled",
    "stretch": "stretched",
    "center": "centered",
    "tile": "wallpaper",
    "span": "spanned",
}
AWWW_RESIZE_MODES = {
    "fill": "crop",
    "fit": "fit",
    "stretch": "fit",
    "center": "no",
    "tile": "no",
    "span": "fit",
}


def _wallpaper_mode(mode):
    return mode if mode in store.WALLPAPER_MODES else "fill"


def apply_wallpaper(path, mode="fill", preferred=None):
    """Put *path* on the desktop.  Returns details for state.json."""
    path = os.path.realpath(path)
    if not os.path.isfile(path) or not library.is_wallpaper(path):
        raise ValueError(f"not a picture or video: {path}")
    mode = _wallpaper_mode(mode)
    applied = path
    from_video = False
    if library.is_video(path):
        still = library.still_for(path, 1920)
        if not still:
            raise ValueError("couldn't read a frame from this video (is ffmpeg installed?)")
        applied = still
        from_video = True

    backend = detect_backend(refresh=True, preferred=preferred)
    name = backend["name"]
    # Snapshot the previous look even when the caller only changes the
    # wallpaper; this used to be skipped by ``set --no-colors``.
    with store.locked():
        _save_originals()
    if name != "desktop":
        _stop_desktop_window()
    if name == "dms":
        output = _dms_output("wallpaper", "set", applied)
        if "SUCCESS" not in output:
            if "Per-monitor" in output or "per-monitor" in output:
                screens = _dms_screens()
                if not screens:
                    raise RuntimeError("DankMaterialShell did not report any screens")
                successes = 0
                for screen in screens:
                    result = _dms_output("wallpaper", "setFor", screen, applied)
                    successes += "SUCCESS" in result
                if not successes:
                    raise RuntimeError("DankMaterialShell refused the wallpaper")
            else:
                raise RuntimeError(output or "DankMaterialShell refused the wallpaper")
    elif name == "awww":
        _ensure_awww()
        result = _run(["awww", "img", applied,
                       "--resize", AWWW_RESIZE_MODES[mode],
                       "--transition-type", "wipe",
                       "--transition-duration", "0.6"], timeout=20)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "awww failed")
    elif name == "hyprpaper":
        _run(["hyprctl", "hyprpaper", "preload", applied], timeout=10)
        result = _run(["hyprctl", "hyprpaper", "wallpaper", f",{applied}"], timeout=10)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "hyprpaper failed")
    elif name == "swaybg":
        _stop_swaybg()
        process = subprocess.Popen(
            [shutil.which("swaybg"), "-m", SWAYBG_MODES[mode], "-i", applied],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
        os.makedirs(store.CONFIG_DIR, exist_ok=True)
        with open(SWAYBG_PID, "w", encoding="utf-8") as handle:
            handle.write(str(process.pid))
    elif name == "feh":
        result = _run(["feh", "--no-fehbg", FEH_MODE_FLAGS[mode], applied], timeout=15)
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "feh failed")
    elif name == "desktop":
        _start_desktop_window(applied, mode)
    elif name == "gnome":
        uri = Gio.File.new_for_path(applied).get_uri()
        if not _gnome_set_string("org.gnome.desktop.background", "picture-uri", uri):
            raise RuntimeError("GNOME's wallpaper setting is locked")
        _gnome_set_string("org.gnome.desktop.background", "picture-uri-dark", uri)
        _gnome_set_string("org.gnome.desktop.background", "picture-options",
                          GNOME_PICTURE_OPTIONS[mode])
        _sync()
    else:
        if _gnome_session():
            raise RuntimeError(
                "GNOME's wallpaper setting is locked. Unlock "
                "org.gnome.desktop.background picture-uri, or run 'aura-studio "
                "doctor' to see the available backends.")
        raise RuntimeError("no wallpaper backend found (install awww, hyprpaper, "
                           "swaybg, feh, or use an X11 session)")

    with store.locked():
        _record_applied(dms_wallpapers=_dms_current_wallpapers()
                        if name == "dms" else None)

    return {
        "path": applied,
        "source": path,
        "backend": name,
        "mode": mode,
        "from_video": from_video,
        "fallback": bool(backend.get("fallback")),
    }


def _ensure_awww():
    if _run(["awww", "query"], timeout=5).returncode == 0:
        return
    daemon = shutil.which("awww-daemon")
    if not daemon:
        raise RuntimeError("awww-daemon is not installed")
    subprocess.Popen([daemon], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(30):
        time.sleep(0.1)
        if _run(["awww", "query"], timeout=3).returncode == 0:
            return
    raise RuntimeError("awww-daemon did not start")


def _stop_swaybg():
    try:
        with open(SWAYBG_PID, encoding="utf-8") as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 15)
    except (OSError, ValueError):
        pass
    with contextlib.suppress(FileNotFoundError):
        os.remove(SWAYBG_PID)


# --- session preferences ----------------------------------------------------------

def current_preferences():
    return {
        "icon_theme": _get_string("org.gnome.desktop.interface", "icon-theme"),
        "cursor_theme": _get_string("org.gnome.desktop.interface", "cursor-theme"),
        "cursor_size": _get_int("org.gnome.desktop.interface", "cursor-size", 24),
        "font": _get_string("org.gnome.desktop.interface", "font-name"),
        "mono_font": _get_string("org.gnome.desktop.interface", "monospace-font-name"),
        "text_scale": _get_double("org.gnome.desktop.interface", "text-scaling-factor", 1.0),
        "gtk_theme": _get_string("org.gnome.desktop.interface", "gtk-theme"),
        "color_scheme": _get_string("org.gnome.desktop.interface", "color-scheme"),
    }


def _theme_name(directory):
    path = os.path.join(directory, "index.theme")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("Name="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    except OSError:
        pass
    return os.path.basename(directory)


def _theme_dirs():
    return [
        os.path.join(DATA_HOME, "icons"),
        os.path.join(HOME, ".icons"),
        "/usr/share/icons",
    ]


def icon_themes():
    names = set()
    for root in _theme_dirs():
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for entry in entries:
            path = os.path.join(root, entry)
            if entry.startswith(".") or not os.path.isdir(path):
                continue
            if os.path.isdir(os.path.join(path, "cursors")) and \
                    not os.path.exists(os.path.join(path, "index.theme")):
                continue
            if os.path.exists(os.path.join(path, "index.theme")):
                names.add(_theme_name(path))
    return sorted(names, key=str.lower)


def cursor_themes():
    names = set()
    for root in _theme_dirs():
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for entry in entries:
            path = os.path.join(root, entry)
            if not entry.startswith(".") and os.path.isdir(os.path.join(path, "cursors")):
                names.add(entry)
    return sorted(names, key=str.lower)


def terminal_targets():
    """Terminals Aura can write colours for on this machine."""
    targets = []
    if os.path.exists(KITTY_CONF):
        targets.append("kitty")
    if _gnome_terminal():
        targets.append("gnome-terminal")
    return targets


def selected_terminal_targets(options=None, config=None):
    """The detected terminals the user has enabled, in stable order."""
    available = terminal_targets()
    if options is not None:
        chosen = options.get("terminal_targets")
    else:
        chosen = (config or store.load_config()).get("terminal_targets")
    if chosen is None:
        return available
    return [target for target in available if target in chosen]


def terminal_labels(targets=None):
    return [store.TERMINAL_TARGET_LABELS.get(target, target)
            for target in (terminal_targets() if targets is None else targets)]


def _gnome_terminal():
    if not shutil.which("dconf"):
        return False
    if shutil.which("gnome-terminal"):
        return True
    return _schema("org.gnome.Terminal.ProfilesList") is not None


def lock_screen_available():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" not in desktop and "ubuntu" not in desktop:
        return False
    settings = _schema("org.gnome.desktop.screensaver")
    return bool(settings is not None and settings.is_writable("picture-uri"))


# --- login autostart --------------------------------------------------------------

def _exec_quote(value):
    """Quote one Exec= argument the way desktop-entry files expect."""
    value = str(value)
    if not any(character in value for character in ' \t"\\'):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _launcher_argv():
    if os.path.isfile(LAUNCHER):
        return [LAUNCHER]
    return [sys.executable, "-m", "aura_studio"]


def autostart_delay(config=None):
    config = config or store.load_config()
    try:
        return max(0, min(300, int(config.get("autostart_delay", 8))))
    except (TypeError, ValueError):
        return 8


def autostart_command(profile=None, delay=8, log=True):
    argv = [*_launcher_argv(), "apply-saved"]
    if profile:
        argv += ["--profile", str(profile)]
    if delay:
        argv += ["--delay", str(int(delay))]
    if log:
        argv.append("--log")
    argv.append("--quiet")
    return " ".join(_exec_quote(argument) for argument in argv)


def autostart_entry(profile=None, delay=8):
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Aura Studio look\n"
        "Comment=Reapply your saved Aura Studio look after login\n"
        f"Exec={autostart_command(profile, delay)}\n"
        "Icon=io.github.AuraStudio\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "X-GNOME-Autostart-Phase=Applications\n"
    )


def autostart_enabled():
    return os.path.isfile(AUTOSTART_FILE)


def set_autostart(enabled, profile=None, delay=8):
    """Install or remove the login entry that reapplies the saved look."""
    if not enabled:
        for path in (AUTOSTART_FILE, LEGACY_AUTOSTART_FILE):
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)
        return False
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    store.write_text(AUTOSTART_FILE, autostart_entry(profile, delay))
    os.chmod(AUTOSTART_FILE, 0o644)
    with contextlib.suppress(FileNotFoundError):
        os.remove(LEGACY_AUTOSTART_FILE)
    return True


# --- originals / restore ----------------------------------------------------------

def _settings_snapshot():
    snapshots = {}
    for schema, key in TOUCHED:
        value = _current_setting(schema, key)
        if value is not None:
            snapshots[f"{schema} {key}"] = value
    return snapshots


def _terminal_uid():
    uid_file = os.path.join(store.CONFIG_DIR, "terminal-profile")
    try:
        with open(uid_file, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _terminal_snapshot():
    return {
        "default": _dconf("read", f"{TERMINAL}/default"),
        "list": _dconf("read", f"{TERMINAL}/list"),
        "uid": _terminal_uid(),
    }


def _record_applied(dms_wallpapers=None):
    """Remember exactly what Aura wrote, so Restore leaves later edits alone."""
    originals = store.load_originals()
    if not originals:
        return
    applied = {
        "settings": _settings_snapshot(),
        "terminal": _terminal_snapshot(),
        "saved_at": time.time(),
    }
    if dms_wallpapers is not None:
        applied["dms_wallpapers"] = dms_wallpapers
    originals["applied"] = applied
    store.save_originals(originals)


def _save_originals():
    if os.path.exists(store.ORIGINALS):
        return
    kitty = {"conf": KITTY_CONF, "include_added": False}
    if os.path.exists(KITTY_CONF):
        with contextlib.suppress(OSError):
            with open(KITTY_CONF, encoding="utf-8", errors="replace") as handle:
                kitty["include_added"] = KITTY_MARKER not in handle.read()
    store.save_originals({
        "settings": _settings_snapshot(),
        "terminal": _terminal_snapshot(),
        "kitty": kitty,
        "dms_wallpapers": _dms_current_wallpapers(),
        "saved_at": time.time(),
    })


def _current_setting(schema, key):
    host = _host_gsettings_get(schema, key)
    if host is not None:
        return host
    settings = _schema(schema)
    if settings is None or not _has_key(settings, key):
        return None
    try:
        return settings.get_value(key).print_(True)
    except Exception:
        return None


def _restore_settings(originals):
    applied = (originals.get("applied") or {}).get("settings") or {}
    for name, value in originals.get("settings", {}).items():
        try:
            schema, key = name.split(" ", 1)
        except ValueError:
            continue
        # With a new-style originals file, only undo values that still belong
        # to Aura.  A font, wallpaper or theme the user changed afterwards is
        # intentionally left alone.
        if applied and name in applied:
            if _current_setting(schema, key) != applied[name]:
                continue
        try:
            variant = GLib.Variant.parse(None, value, None, None)
        except Exception:
            continue
        _set_variant(schema, key, variant)


def _terminal_ids(value):
    return re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value or "")


def _restore_terminal(originals):
    terminal = originals.get("terminal", {})
    applied = (originals.get("applied") or {}).get("terminal") or {}
    uid = _terminal_uid()
    current_default = _dconf("read", f"{TERMINAL}/default")
    current_list = _dconf("read", f"{TERMINAL}/list")

    if applied:
        # Only remove our profile from the list, keeping profiles the user
        # added later.  Only restore the default when it is still ours.
        if uid and uid in _terminal_ids(current_list):
            ids = [item for item in _terminal_ids(current_list) if item != uid]
            if ids:
                _dconf_write(f"{TERMINAL}/list", str(ids))
            else:
                _dconf("reset", f"{TERMINAL}/list")
        if uid and current_default.strip(" '\"") == uid:
            if terminal.get("default"):
                _dconf_write(f"{TERMINAL}/default", terminal["default"])
            else:
                _dconf("reset", f"{TERMINAL}/default")
    elif terminal:
        # Legacy originals file: preserve the old all-or-nothing behaviour.
        if terminal.get("default"):
            _dconf("write", f"{TERMINAL}/default", terminal["default"])
        else:
            _dconf("reset", f"{TERMINAL}/default")
        if terminal.get("list"):
            _dconf("write", f"{TERMINAL}/list", terminal["list"])
        else:
            _dconf("reset", f"{TERMINAL}/list")

    if uid:
        _dconf("reset", "-f", f"{TERMINAL}/:{uid}/")
    uid_file = os.path.join(store.CONFIG_DIR, "terminal-profile")
    with contextlib.suppress(FileNotFoundError):
        os.remove(uid_file)


def _restore_kitty(originals):
    kitty = originals.get("kitty", {})
    if not kitty:
        return
    changed = False
    conf = os.path.realpath(KITTY_CONF)
    if kitty.get("include_added") and os.path.exists(conf):
        with contextlib.suppress(OSError):
            with open(conf, encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            kept = [line for line in lines if line.strip() != KITTY_MARKER]
            store.write_text(conf, "".join(kept))
            changed = True
    with contextlib.suppress(FileNotFoundError):
        os.remove(KITTY_THEME)
        changed = True
    if changed:
        _run(["pkill", "-USR1", "-x", "kitty"], timeout=5)


def _restore_dms_wallpapers(originals):
    wallpapers = originals.get("dms_wallpapers", {})
    if not wallpapers or not _dms_available():
        return
    applied = (originals.get("applied") or {}).get("dms_wallpapers")
    current = _dms_current_wallpapers() if applied else {}

    def owned(key):
        if not applied:
            return True
        return key in applied and current.get(key) == applied.get(key)

    global_path = wallpapers.get("__global__")
    if (not wallpapers.get("__per_monitor__") and global_path
            and os.path.exists(global_path) and owned("__global__")):
        _dms_output("wallpaper", "set", global_path)
        return
    screens = _dms_screens()
    restored = False
    for screen in screens:
        path = wallpapers.get(screen)
        if path and os.path.exists(path) and owned(screen):
            result = _dms_output("wallpaper", "setFor", screen, path)
            restored = restored or "SUCCESS" in result
    if (global_path and os.path.exists(global_path)
            and owned("__global__") and not restored):
        _dms_output("wallpaper", "set", global_path)


# --- themes -----------------------------------------------------------------------

def _theme_dir(name):
    for base in (THEMES_DIR, os.path.join(HOME, ".themes"), "/usr/share/themes"):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            return path
    return None


def _write_themes(dark):
    adw = _theme_dir("adw-gtk3-dark" if dark else "adw-gtk3")
    if adw:
        base3 = Gio.File.new_for_path(os.path.join(adw, "gtk-3.0", "gtk.css")).get_uri()
    else:
        base3 = ("resource:///org/gtk/libgtk/theme/Adwaita/"
                 f"gtk-contained{'-dark' if dark else ''}.css")
    base4 = ("resource:///org/gtk/libgtk/theme/Default/"
             f"Default-{'dark' if dark else 'light'}.css")
    colours = Gio.File.new_for_path(store.THEME_CSS).get_uri()
    for name in OUR_THEMES:
        directory = os.path.join(THEMES_DIR, name)
        store.write_text(os.path.join(directory, "index.theme"),
                         "[X-GNOME-Metatheme]\n"
                         f"Name={name}\nType=X-GNOME-Metatheme\n"
                         "Comment=Made by Aura Studio from your wallpaper\n")
        for version, base in (("gtk-3.0", base3), ("gtk-4.0", base4)):
            css = f'@import url("{base}");\n@import url("{colours}");\n'
            store.write_text(os.path.join(directory, version, "gtk.css"), css)
            store.write_text(os.path.join(directory, version, "gtk-dark.css"), css)


def _switch_theme():
    current = _get_string("org.gnome.desktop.interface", "gtk-theme")
    chosen = OUR_THEMES[1] if current == OUR_THEMES[0] else OUR_THEMES[0]
    _set_string("org.gnome.desktop.interface", "gtk-theme", chosen)


def _import_line():
    return f'@import url("{Gio.File.new_for_path(store.THEME_CSS).get_uri()}"); {MARKER}\n'


def _add_import(path):
    path = os.path.realpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        text = ""
    lines = [line if MARKER not in line else _import_line()
             for line in text.splitlines(True)]
    if not any(MARKER in line for line in lines):
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.append("\n")
        lines.append(_import_line())
    store.write_text(path, "".join(lines))


def _remove_import(path):
    path = os.path.realpath(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return
    kept = "".join(line for line in text.splitlines(True) if MARKER not in line)
    if kept.strip():
        store.write_text(path, kept)
    else:
        with contextlib.suppress(OSError):
            os.remove(path)


def _apply_desktop_options(options):
    if options.get("icon_theme"):
        _set_string("org.gnome.desktop.interface", "icon-theme", options["icon_theme"])
    if options.get("cursor_theme"):
        _set_string("org.gnome.desktop.interface", "cursor-theme", options["cursor_theme"])
    if options.get("cursor_size"):
        _set_int("org.gnome.desktop.interface", "cursor-size", options["cursor_size"])
    if options.get("font"):
        _set_string("org.gnome.desktop.interface", "font-name", options["font"])
        _set_string("org.gnome.desktop.interface", "document-font-name", options["font"])
    if options.get("mono_font"):
        _set_string("org.gnome.desktop.interface", "monospace-font-name", options["mono_font"])
    if options.get("text_scale"):
        _set_double("org.gnome.desktop.interface", "text-scaling-factor",
                    options["text_scale"])


def _kitty_has_include():
    try:
        with open(os.path.realpath(KITTY_CONF), encoding="utf-8", errors="replace") as handle:
            return KITTY_MARKER in handle.read()
    except OSError:
        return False


def _apply_kitty(p):
    conf = os.path.realpath(KITTY_CONF)
    if not os.path.exists(conf):
        return False
    store.write_text(KITTY_THEME, palette.kitty_theme(p))
    if not _kitty_has_include():
        with open(conf, "a", encoding="utf-8") as handle:
            handle.write(f"\n{KITTY_MARKER}\n")
    _run(["pkill", "-USR1", "-x", "kitty"], timeout=5)
    return True


def _gnome_terminal_uid():
    uid_file = os.path.join(store.CONFIG_DIR, "terminal-profile")
    try:
        with open(uid_file, encoding="utf-8") as handle:
            uid = handle.read().strip()
        if uid:
            return uid
    except OSError:
        pass
    uid = str(uuid.uuid4())
    store.write_text(uid_file, uid + "\n")
    return uid


def _apply_gnome_terminal(p):
    if not _gnome_terminal():
        return False
    uid = _gnome_terminal_uid()
    ids = _terminal_ids(_dconf("read", f"{TERMINAL}/list"))
    if uid not in ids:
        ids = ids or ["b1dcc9dd-5262-4d8d-a863-c897e6d979b9"]
        _dconf_write(f"{TERMINAL}/list", str(ids + [uid]))
    _dconf_write(f"{TERMINAL}/default", f"'{uid}'")
    path = f"{TERMINAL}/:{uid}/"
    values = {
        "visible-name": "'Aura Studio'",
        "use-theme-colors": "false",
        "background-color": f"'{p['paper']}'",
        "foreground-color": f"'{p['ink']}'",
        "bold-color-same-as-fg": "true",
        "palette": str(p["ansi"]),
        "cursor-colors-set": "true",
        "cursor-background-color": f"'{p['accent']}'",
        "cursor-foreground-color": f"'{p['on_accent']}'",
        "highlight-colors-set": "true",
        "highlight-background-color": f"'{p['accent']}'",
        "highlight-foreground-color": f"'{p['on_accent']}'",
    }
    written = True
    for key, value in values.items():
        written = _dconf_write(path + key, value) and written
    return written


def _apply_terminal(p, targets=None):
    targets = terminal_targets() if targets is None else targets
    if "kitty" in targets:
        _apply_kitty(p)
    if "gnome-terminal" in targets:
        _apply_gnome_terminal(p)
    # The snippets are useful even when no terminal is installed: users can
    # copy them into another terminal or a hook.
    mode_dir = os.path.join(store.EXPORTS, "terminal")
    store.write_text(os.path.join(mode_dir, "kitty.conf"), palette.kitty_theme(p))
    a = p["ansi"]
    store.write_text(os.path.join(mode_dir, "ansi.txt"),
                     "\n".join(f"{i:>2}  {value}" for i, value in enumerate(a)) + "\n")


def _user_service_exists(name):
    if not shutil.which("systemctl"):
        return False
    result = _run(["systemctl", "--user", "list-unit-files", name,
                   "--no-legend", "--no-pager"], timeout=5)
    return result.returncode == 0 and name in result.stdout


def _apply_lock_screen(still):
    if not still or not lock_screen_available():
        return
    uri = Gio.File.new_for_path(still).get_uri()
    if _gnome_set_string("org.gnome.desktop.screensaver", "picture-uri", uri):
        _gnome_set_string("org.gnome.desktop.screensaver", "picture-options", "zoom")
        # Only poke the optional greeter when the unit actually exists; stock
        # Ubuntu has no codam-web-greeter and systemd would log an error.
        if _user_service_exists("codam-web-greeter.service"):
            _run(["systemctl", "--user", "try-restart",
                  "codam-web-greeter.service"], timeout=5)


def _run_hooks(p, mode):
    try:
        names = sorted(os.listdir(store.HOOKS))
    except OSError:
        return
    env = {**os.environ, "AURA_MODE": mode, "AURA_STATE": store.STATE}
    env.update({f"AURA_{key.upper()}": value for key, value in p.items() if key != "ansi"})
    env.update({f"AURA_ANSI_{i}": value for i, value in enumerate(p["ansi"])})
    for name in names:
        path = os.path.join(store.HOOKS, name)
        if not name.startswith(".") and os.path.isfile(path) and os.access(path, os.X_OK):
            subprocess.Popen([path], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)


def custom_css_text():
    """Optional user CSS appended to every generated theme."""
    try:
        if os.path.getsize(store.CUSTOM_CSS) > 256_000:
            return ""
        with open(store.CUSTOM_CSS, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def apply_theme(p, mode, options, still=None):
    """Apply a palette (both modes, or one mode) and the chosen desktop options."""
    dark = mode == "dark"
    colours = p.get(mode, p) if isinstance(p, dict) else p
    if not palette.valid_mode(colours):
        raise ValueError("invalid palette colours")
    try:
        opacity = max(0.15, min(1.0, float(options.get("glass_opacity", 0.72))))
    except (TypeError, ValueError):
        opacity = 0.72
    css = palette.gtk_css(colours, dark, bool(options.get("glass")), opacity)
    custom = custom_css_text().strip()
    if custom:
        css += ("\n/* --- custom.css from " + store.CUSTOM_CSS +
                " (yours; Aura leaves it in place) --- */\n" + custom + "\n")
    with store.locked():
        _save_originals()
        if options.get("recolour_gtk", True):
            store.write_text(store.THEME_CSS, css)
            _write_themes(dark)
            _add_import(GTK3_CSS)
            _add_import(GTK4_CSS)
            _set_string("org.gnome.desktop.interface", "color-scheme",
                        "prefer-dark" if dark else "default")
            _switch_theme()
            _set_string("org.gnome.desktop.background", "primary-color", colours["paper"])
        _apply_desktop_options(options)
        if options.get("terminal", True):
            _apply_terminal(colours, selected_terminal_targets(options))
        if options.get("lock_screen", False):
            _apply_lock_screen(still)
        _sync()
        _record_applied()
    _run_hooks(colours, mode)
    return css


def restore():
    """Undo every setting Aura changed and remove its generated themes."""
    with store.locked():
        originals = store.load_originals()
        _restore_settings(originals)
        _restore_terminal(originals)
        _restore_kitty(originals)
        _restore_dms_wallpapers(originals)
        _stop_swaybg()
        _stop_desktop_window()
        for path in (GTK3_CSS, GTK4_CSS):
            _remove_import(path)
        with contextlib.suppress(FileNotFoundError):
            os.remove(store.THEME_CSS)
        for name in OUR_THEMES:
            shutil.rmtree(os.path.join(THEMES_DIR, name), ignore_errors=True)
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(os.path.join(store.EXPORTS, "terminal"))
        current = _get_string("org.gnome.desktop.interface", "gtk-theme")
        if current in OUR_THEMES:
            _set_string("org.gnome.desktop.interface", "gtk-theme", "Adwaita")
        _sync()
        store.save_state({})
        store.remove_originals()
    return True


# --- exporting --------------------------------------------------------------------

def export_palette(kind, p, mode, path):
    """Write an export file.  *kind* is css, json or kitty."""
    if kind == "css":
        text = palette.css_for_export(p, mode == "dark")
    elif kind == "json":
        text = json.dumps(palette.palette_json(p), indent=2, ensure_ascii=False) + "\n"
    elif kind == "kitty":
        text = palette.kitty_theme(p.get(mode, p))
    else:
        raise ValueError(f"unknown export: {kind}")
    store.write_text(path, text)
    return path


def app_theme_css():
    """The generated CSS, for previewing colours inside Aura's own window."""
    try:
        with open(store.THEME_CSS, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def status():
    state = store.load_state()
    config = store.load_config()
    backend = detect_backend(refresh=True)
    return {
        "backend": backend_label(),
        "backend_name": backend["name"],
        "backend_preference": config.get("wallpaper_backend", "auto"),
        "backend_fallback": bool(backend.get("fallback")),
        "session": session_label(),
        "session_type": "wayland" if _wayland() else "x11",
        "wallpaper": state.get("wallpaper"),
        "applied_mode": state.get("mode"),
        "configured_mode": config["mode"],
        "style": config["style"],
        "folder": config["folder"],
        "wallpaper_mode": config.get("wallpaper_mode", "fill"),
        "slideshow_order": config.get("slideshow_order", "shuffle"),
        "themes": OUR_THEMES,
        "terminal": terminal_targets(),
        "terminal_selected": selected_terminal_targets(config=config),
        "lock_screen": lock_screen_available(),
        "autostart": autostart_enabled(),
        "autostart_profile": config.get("autostart_profile"),
        "autostart_delay": autostart_delay(config),
        "custom_css": store.CUSTOM_CSS,
        "custom_css_exists": os.path.exists(store.CUSTOM_CSS),
        "config_dir": store.CONFIG_DIR,
        "cache_dir": store.CACHE_DIR,
        "goinfre": store.GOINFRE,
    }
