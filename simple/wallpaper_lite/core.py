"""The small core of Wallpaper Lite: paths, palette, colours, and the way back.

Everything this program writes lives in one config folder and one cache folder:

    ~/.config/wallpaper-lite/config.json   folder + light/dark choice
    ~/.config/wallpaper-lite/state.json    current picture + its two palettes
    ~/.config/wallpaper-lite/theme.css     generated GTK colours
    ~/.config/wallpaper-lite/originals.json  settings saved for Restore
    ~/.cache/wallpaper-lite/               thumbnails

There is no network access, no downloaded theme, no hooks, and no shell.
"""
import colorsys
import contextlib
import fcntl
import hashlib
import json
import math
import os
import random
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402

APP_ID = "io.github.WallpaperLite"
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")

CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")
CACHE_HOME = os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache")
CONFIG_DIR = os.path.join(CONFIG_HOME, "wallpaper-lite")
CACHE_DIR = os.path.join(CACHE_HOME, "wallpaper-lite")
CONFIG = os.path.join(CONFIG_DIR, "config.json")
STATE = os.path.join(CONFIG_DIR, "state.json")
ORIGINALS = os.path.join(CONFIG_DIR, "originals.json")
THEME_CSS = os.path.join(CONFIG_DIR, "theme.css")
LOCK = os.path.join(CONFIG_DIR, ".lock")
GTK3_CSS = os.path.join(CONFIG_HOME, "gtk-3.0", "gtk.css")
GTK4_CSS = os.path.join(CONFIG_HOME, "gtk-4.0", "gtk.css")
DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share")
THEMES_DIR = os.path.join(DATA_HOME, "themes")
OUR_THEMES = ("Wallpaper Lite A", "Wallpaper Lite B")

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")
MAX_FILE_BYTES = 96 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_ASPECT = 16.0
MAX_THUMBS = 500
HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")

TOUCHED = (
    ("org.gnome.desktop.background", "picture-uri"),
    ("org.gnome.desktop.background", "picture-uri-dark"),
    ("org.gnome.desktop.background", "picture-options"),
    ("org.gnome.desktop.interface", "gtk-theme"),
    ("org.gnome.desktop.interface", "color-scheme"),
)
ALLOWED_ORIGINALS = {f"{schema} {key}" for schema, key in TOUCHED}


# --- private files -----------------------------------------------------------------

def ensure_dir(path, mode=0o700):
    """Create a directory if needed, without changing an existing folder's mode."""
    os.makedirs(path, mode=mode, exist_ok=True)


def private_dir(path):
    """Create one of our own directories and keep it at 0700."""
    ensure_dir(path)
    try:
        st = os.stat(path)
        if stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode) & 0o077:
            os.chmod(path, 0o700)
    except OSError:
        pass


def runtime_dir():
    """A private place for the helper's PID and lock, never a shared /tmp path."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base or not os.path.isdir(base):
        private_dir(CACHE_DIR)
        base = os.path.join(CACHE_DIR, "run")
    path = os.path.join(base, "wallpaper-lite")
    private_dir(path)
    return path


def _read_json(path, default):
    try:
        st = os.stat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 4 * 1024 * 1024:
            return default
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, TypeError):
        return default
    return data if isinstance(data, dict) else default


def _write(path, text, mode=0o600):
    """Write a file atomically with a private mode; never follow a destination symlink."""
    folder = os.path.dirname(path) or "."
    ensure_dir(folder)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _write_like(path, text):
    """Write text but keep the permissions the file already had (for the user's gtk.css)."""
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        mode = 0o644
    _write(path, text, mode=mode)


@contextlib.contextmanager
def locked():
    """One writer at a time (window and command line can overlap)."""
    private_dir(CONFIG_DIR)
    flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(LOCK, flags, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# --- settings ----------------------------------------------------------------------

def _settings(schema):
    try:
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(schema, True) is None:
            return None
        return Gio.Settings.new(schema)
    except (GLib.Error, TypeError):
        return None


def _get(schema, key):
    s = _settings(schema)
    if s is None or key not in s.list_keys():
        return None
    try:
        return s.get_value(key)
    except GLib.Error:
        return None


def _set(schema, key, value):
    """Set a key only when it exists and the administrator allows it."""
    s = _settings(schema)
    if s is None or key not in s.list_keys() or not s.is_writable(key):
        return False
    try:
        s.set_value(key, value)
        return True
    except GLib.Error:
        return False


def gnome_background_writable():
    """True when GNOME's own wallpaper setting can be changed (not locked at 42)."""
    s = _settings("org.gnome.desktop.background")
    if s is None or "picture-uri" not in s.list_keys():
        return False
    try:
        return s.is_writable("picture-uri")
    except GLib.Error:
        return False


def _save_originals():
    """Remember each setting once, before the first change, so Restore is exact."""
    if os.path.exists(ORIGINALS):
        return
    saved = {}
    for schema, key in TOUCHED:
        value = _get(schema, key)
        if value is not None:
            saved[f"{schema} {key}"] = value.print_(True)
    if saved:
        _write(ORIGINALS, json.dumps(saved, indent=2) + "\n")


def _set_background(still):
    """Use GNOME's normal wallpaper when its keys are writable."""
    uri = Gio.File.new_for_path(still).get_uri()
    changed = False
    for key in ("picture-uri", "picture-uri-dark"):
        changed = _set("org.gnome.desktop.background", key, GLib.Variant("s", uri)) or changed
    _set("org.gnome.desktop.background", "picture-options", GLib.Variant("s", "zoom"))
    return changed


# --- config and state ---------------------------------------------------------------

def default_folder():
    # From a checkout, use the sample wallpapers that sit next to simple/.
    sample = os.path.join(os.path.dirname(APP_DIR), "wallpapers")
    if os.path.isdir(sample):
        return sample
    for name in ("Pictures", "Downloads", "Desktop"):
        path = os.path.join(HOME, name)
        if os.path.isdir(path):
            return path
    return HOME


def default_mode():
    value = _get("org.gnome.desktop.interface", "color-scheme")
    try:
        if value is not None and value.unpack() == "prefer-dark":
            return "dark"
    except (TypeError, GLib.Error):
        pass
    return "light"


def load_config():
    raw = _read_json(CONFIG, {})
    folder = raw.get("folder")
    if not isinstance(folder, str) or not os.path.isdir(folder):
        folder = default_folder()
    mode = raw.get("mode")
    if mode not in ("light", "dark"):
        mode = default_mode()
    return {"folder": folder, "mode": mode}


def save_config(**changes):
    config = {**load_config(), **changes}
    if config.get("mode") not in ("light", "dark"):
        config["mode"] = "light"
    folder = config.get("folder")
    if not isinstance(folder, str) or not os.path.isdir(folder):
        config["folder"] = default_folder()
    private_dir(CONFIG_DIR)
    _write(CONFIG, json.dumps(config, indent=2) + "\n")
    return config


def _palette_ok(palette):
    if not isinstance(palette, dict):
        return False
    for mode in ("light", "dark"):
        p = palette.get(mode)
        if not isinstance(p, dict):
            return False
        for key in ("paper", "paper2", "sheet", "ink", "muted", "accent", "accent_text", "on_accent", "shadow"):
            value = p.get(key)
            if not isinstance(value, str) or not HEX_COLOUR.match(value):
                return False
    return True


def load_state():
    raw = _read_json(STATE, {})
    state = {}
    if isinstance(raw.get("wallpaper"), str) and raw["wallpaper"]:
        state["wallpaper"] = raw["wallpaper"]
    if _palette_ok(raw.get("palette")):
        state["palette"] = raw["palette"]
    for key in ("mtime_ns", "size"):
        value = raw.get(key)
        if isinstance(value, int):
            state[key] = value
    if isinstance(raw.get("changed"), (int, float)):
        state["changed"] = raw["changed"]
    if isinstance(raw.get("mode"), str) and raw["mode"] in ("light", "dark"):
        state["mode"] = raw["mode"]
    return state


def _save_state(state):
    private_dir(CONFIG_DIR)
    _write(STATE, json.dumps(state, indent=2) + "\n")


def effective_mode(config=None):
    config = config or load_config()
    mode = config.get("mode")
    return mode if mode in ("light", "dark") else "light"


# --- pictures -----------------------------------------------------------------------

def is_image(path):
    return isinstance(path, str) and path.lower().endswith(IMAGE_EXT)


def validate_image(path):
    """Reject unusual files and decompression/amplification bombs before decoding."""
    if not isinstance(path, str) or not path:
        raise ValueError("not a picture")
    path = os.path.realpath(os.path.expanduser(path))
    if not is_image(path):
        raise ValueError("not a supported picture (use JPG, PNG, WebP, GIF, BMP or TIFF)")
    try:
        st = os.stat(path)
    except OSError:
        raise ValueError("picture not found")
    if not stat.S_ISREG(st.st_mode):
        raise ValueError("not a regular file")
    if st.st_size > MAX_FILE_BYTES:
        raise ValueError(f"picture is too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB)")
    try:
        fmt, width, height = GdkPixbuf.Pixbuf.get_file_info(path)
    except GLib.Error:
        raise ValueError("cannot read this picture")
    if not fmt or not width or not height:
        raise ValueError("cannot read this picture")
    if width * height > MAX_PIXELS:
        raise ValueError("picture is too large (max 40 megapixels)")
    if max(width, height) / min(width, height) > MAX_ASPECT:
        raise ValueError("picture is too wide or too tall")
    return path


def image_size(path):
    try:
        fmt, width, height = GdkPixbuf.Pixbuf.get_file_info(path)
        return (width, height, fmt.get_name() if fmt else "")
    except GLib.Error:
        return (0, 0, "")


def wallpapers(folder=None):
    folder = folder or load_config()["folder"]
    try:
        with os.scandir(folder) as entries:
            names = sorted((e for e in entries if not e.name.startswith(".") and is_image(e.name)),
                           key=lambda e: e.name.lower())
    except OSError:
        return []
    found = []
    for entry in names:
        try:
            if entry.is_file(follow_symlinks=True):
                found.append(entry.path)
        except OSError:
            pass
    return found


# --- palette ------------------------------------------------------------------------

def _rgb_to_hex(rgb):
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _hsl(hue, saturation, lightness):
    return _rgb_to_hex(colorsys.hls_to_rgb((hue % 360) / 360.0,
                                           max(0.0, min(1.0, lightness)),
                                           max(0.0, min(1.0, saturation))))


def _luminance(colour):
    def linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    values = [int(colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    r, g, b = (linear(c) for c in values)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _reach_contrast(hue, saturation, lightness, against, target, step):
    for _ in range(200):
        colour = _hsl(hue, saturation, lightness)
        if contrast(colour, against) >= target or not 0.02 < lightness < 0.98:
            return colour
        lightness += step
    return _hsl(hue, saturation, lightness)


def _samples(path, size=64):
    """A small, fixed-size sample; at most 64x64 pixels reach the Python loop."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
    data = pixbuf.get_pixels()
    stride = pixbuf.get_rowstride()
    channels = pixbuf.get_n_channels()
    samples = []
    for y in range(pixbuf.get_height()):
        row = y * stride
        for x in range(pixbuf.get_width()):
            i = row + x * channels
            if channels >= 3:
                r, g, b = data[i] / 255.0, data[i + 1] / 255.0, data[i + 2] / 255.0
            else:
                r = g = b = data[i] / 255.0
            h, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
            samples.append((h * 360.0, saturation, lightness))
    return samples


BINS = 24


def build_palette(samples):
    """One pass over the samples: dominant tint + the most vivid common accent."""
    cast_count = [0] * BINS
    cast_weight = [0.0] * BINS
    cast_sx = [0.0] * BINS
    cast_sy = [0.0] * BINS
    cast_sat = [0.0] * BINS

    vivid_mass = [0.0] * BINS
    vivid_sx = [0.0] * BINS
    vivid_sy = [0.0] * BINS
    vivid_sat = [0.0] * BINS

    for hue, saturation, lightness in samples:
        if saturation <= 0.08 or not 0.05 < lightness < 0.95:
            continue
        b = int(hue / 360.0 * BINS) % BINS
        cast_count[b] += 1
        cast_weight[b] += saturation
        cast_sx[b] += math.cos(math.radians(hue)) * saturation
        cast_sy[b] += math.sin(math.radians(hue)) * saturation
        cast_sat[b] += saturation * saturation

        # Vivid colours near the middle of the lightness range make better accents.
        weight = saturation * max(0.0, 1.0 - abs(lightness - 0.5) * 1.2)
        if weight > 0:
            vivid_mass[b] += weight
            vivid_sx[b] += math.cos(math.radians(hue)) * weight
            vivid_sy[b] += math.sin(math.radians(hue)) * weight
            vivid_sat[b] += saturation * weight

    total = max(1, len(samples))
    mono = sum(cast_count) / total < 0.06 or sum(vivid_mass) < 0.01

    if mono:
        tint_hue, tint_saturation = 210.0, 0.03
        accent_hue, accent_saturation = tint_hue, 0.0
    else:
        def score(b):
            # Count and saturation both matter; 0.5 of a neighbour smooths noisy hues.
            near = vivid_mass[b] + 0.5 * (vivid_mass[b - 1] + vivid_mass[(b + 1) % BINS])
            sat = vivid_sat[b] / vivid_mass[b] if vivid_mass[b] else 0.0
            return near * (0.5 + sat)

        top = max(range(BINS), key=lambda b: cast_weight[b] + 0.5 * (
            cast_weight[b - 1] + cast_weight[(b + 1) % BINS]))
        tint_hue = math.degrees(math.atan2(cast_sy[top], cast_sx[top])) % 360.0
        tint_saturation = min((cast_sat[top] / cast_weight[top]) ** 0.5 * 0.45, 0.18)

        best = max(range(BINS), key=score)
        accent_hue = math.degrees(math.atan2(vivid_sy[best], vivid_sx[best])) % 360.0
        accent_saturation = min(max(vivid_sat[best] / vivid_mass[best] if vivid_mass[best] else 0.0,
                                    0.55), 0.92)
        # Yellow and green look muddy when darkened; keep them strong.
        if 40 <= accent_hue <= 170:
            accent_saturation = max(accent_saturation, 0.75)

    light_paper = _hsl(tint_hue, tint_saturation, 0.94)
    light_ink = _hsl(tint_hue, min(tint_saturation, 0.10), 0.12)
    if mono:
        light_accent = _hsl(tint_hue, 0.04, 0.30)
        light_accent_text = _hsl(tint_hue, 0.04, 0.24)
    else:
        light_accent = _reach_contrast(accent_hue, accent_saturation, 0.46, light_paper, 3.0, -0.015)
        light_accent_text = _reach_contrast(accent_hue, max(accent_saturation, 0.60),
                                            0.40, light_paper, 4.5, -0.015)
    light_on = "#FFFFFF" if contrast("#FFFFFF", light_accent) >= contrast(light_ink, light_accent) else light_ink

    dark_paper = _hsl(tint_hue, tint_saturation * 0.7, 0.09)
    dark_ink = _hsl(tint_hue, min(tint_saturation * 0.4, 0.08), 0.93)
    if mono:
        dark_accent = _hsl(tint_hue, 0.04, 0.78)
        dark_accent_text = _hsl(tint_hue, 0.04, 0.86)
    else:
        dark_accent = _reach_contrast(accent_hue, max(accent_saturation, 0.55),
                                      0.58, dark_paper, 4.5, 0.015)
        dark_accent_text = _reach_contrast(accent_hue, max(accent_saturation, 0.55),
                                           0.66, dark_paper, 6.0, 0.015)
    dark_on = dark_paper if contrast(dark_paper, dark_accent) >= 4.5 else "#FFFFFF"

    return {
        "light": {
            "paper": light_paper,
            "paper2": _hsl(tint_hue, tint_saturation, 0.88),
            "sheet": _hsl(tint_hue, tint_saturation * 0.7, 0.985),
            "ink": light_ink,
            "muted": _hsl(tint_hue, tint_saturation * 0.7, 0.42),
            "accent": light_accent,
            "accent_text": light_accent_text,
            "on_accent": light_on,
            "shadow": light_ink,
        },
        "dark": {
            "paper": dark_paper,
            "paper2": _hsl(tint_hue, tint_saturation * 0.7, 0.13),
            "sheet": _hsl(tint_hue, tint_saturation * 0.7, 0.16),
            "ink": dark_ink,
            "muted": _hsl(tint_hue, tint_saturation * 0.5, 0.65),
            "accent": dark_accent,
            "accent_text": dark_accent_text,
            "on_accent": dark_on,
            "shadow": "#000000",
        },
    }


def palette_from_image(path):
    path = validate_image(path)
    try:
        palette = build_palette(_samples(path))
    except GLib.Error:
        raise ValueError("cannot read this picture")
    if not _palette_ok(palette):
        raise ValueError("could not make colours from this picture")
    return palette


def preview_pixbuf(path, width, height):
    """Fit the picture inside a box (letterboxed), never enlarge it to a huge size."""
    path = validate_image(path)
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, True)
    except GLib.Error:
        raise ValueError("cannot read this picture")


def thumbnail(path, width, height):
    """A cached, fitted thumbnail; cache keys include size and modification time."""
    path = validate_image(path)
    st = os.stat(path)
    key = f"{path}:{st.st_size}:{st.st_mtime_ns}:{width}x{height}:v1"
    name = hashlib.sha256(key.encode()).hexdigest()[:24] + ".png"
    folder = os.path.join(CACHE_DIR, "thumbs")
    out = os.path.join(folder, name)
    if os.path.isfile(out):
        try:
            return GdkPixbuf.Pixbuf.new_from_file(out)
        except GLib.Error:
            pass
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, True)
    except GLib.Error:
        raise ValueError("cannot read this picture")
    private_dir(CACHE_DIR)
    private_dir(folder)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".png")
    os.close(fd)
    try:
        pixbuf.savev(tmp, "png", [], [])
        os.replace(tmp, out)
    except (GLib.Error, OSError):
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return pixbuf


# --- GTK stylesheet ------------------------------------------------------------------

def css_for(palette, dark):
    """Named colours for GTK 3 and GTK 4, plus a few gentle widget rules."""
    return f"""/* wallpaper-lite — generated from your picture; changes are overwritten */
@define-color ws_paper {palette['paper']};
@define-color ws_paper2 {palette['paper2']};
@define-color ws_sheet {palette['sheet']};
@define-color ws_ink {palette['ink']};
@define-color ws_muted {palette['muted']};
@define-color ws_accent {palette['accent']};
@define-color ws_accent_text {palette['accent_text']};
@define-color ws_on_accent {palette['on_accent']};
@define-color ws_shadow {palette['shadow']};

/* GTK 3 names */
@define-color theme_bg_color @ws_paper;
@define-color theme_fg_color @ws_ink;
@define-color theme_base_color @ws_sheet;
@define-color theme_text_color @ws_ink;
@define-color theme_selected_bg_color @ws_accent;
@define-color theme_selected_fg_color @ws_on_accent;
@define-color theme_unfocused_bg_color @ws_paper;
@define-color theme_unfocused_fg_color @ws_ink;
@define-color theme_unfocused_base_color @ws_sheet;
@define-color theme_unfocused_text_color @ws_ink;
@define-color theme_unfocused_selected_bg_color @ws_accent;
@define-color theme_unfocused_selected_fg_color @ws_on_accent;
@define-color insensitive_bg_color @ws_paper2;
@define-color insensitive_fg_color @ws_muted;
@define-color insensitive_base_color @ws_sheet;
@define-color borders @ws_muted;
@define-color unfocused_borders @ws_muted;
@define-color wm_title @ws_ink;
@define-color wm_unfocused_title @ws_muted;

/* GTK 4 / libadwaita names */
@define-color window_bg_color @ws_paper;
@define-color window_fg_color @ws_ink;
@define-color view_bg_color @ws_sheet;
@define-color view_fg_color @ws_ink;
@define-color headerbar_bg_color @ws_paper2;
@define-color headerbar_fg_color @ws_ink;
@define-color headerbar_border_color @ws_muted;
@define-color headerbar_backdrop_color @ws_paper;
@define-color headerbar_shade_color rgba(0, 0, 0, 0.25);
@define-color card_bg_color @ws_sheet;
@define-color card_fg_color @ws_ink;
@define-color card_shade_color rgba(0, 0, 0, 0.20);
@define-color dialog_bg_color @ws_sheet;
@define-color dialog_fg_color @ws_ink;
@define-color popover_bg_color @ws_sheet;
@define-color popover_fg_color @ws_ink;
@define-color sidebar_bg_color @ws_paper2;
@define-color sidebar_fg_color @ws_ink;
@define-color accent_color @ws_accent_text;
@define-color accent_bg_color @ws_accent;
@define-color accent_fg_color @ws_on_accent;
@define-color destructive_bg_color #c01c28;
@define-color destructive_fg_color #ffffff;
@define-color success_bg_color #2ec27e;
@define-color warning_bg_color #e5a50a;
@define-color error_bg_color #c01c28;

window, .background {{ background-color: @theme_bg_color; color: @theme_fg_color; }}
headerbar, .titlebar {{ background-color: @ws_paper2; color: @ws_ink; }}
.view, iconview, textview text, treeview.view {{
  background-color: @theme_base_color; color: @theme_text_color;
}}
selection, *:selected {{ background-color: @theme_selected_bg_color; color: @theme_selected_fg_color; }}
"""


def _write_themes(dark):
    """Two identical GTK 3 themes; switching the name makes open apps re-read them."""
    base = "resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained{}.css".format(
        "-dark" if dark else "")
    colours = Gio.File.new_for_path(THEME_CSS).get_uri()
    css = f'@import url("{base}");\n@import url("{colours}");\n'
    for name in OUR_THEMES:
        folder = os.path.join(THEMES_DIR, name)
        _write(os.path.join(folder, "index.theme"),
               f"[X-GNOME-Metatheme]\nName={name}\nType=X-GNOME-Metatheme\n"
               "Comment=Made by Wallpaper Lite\n")
        for filename in ("gtk.css", "gtk-dark.css"):
            _write(os.path.join(folder, "gtk-3.0", filename), css)


def _switch_theme():
    value = _get("org.gnome.desktop.interface", "gtk-theme")
    try:
        current = value.unpack() if value is not None else ""
    except (TypeError, GLib.Error):
        current = ""
    target = OUR_THEMES[1] if current == OUR_THEMES[0] else OUR_THEMES[0]
    _set("org.gnome.desktop.interface", "gtk-theme", GLib.Variant("s", target))


def _import_line():
    uri = Gio.File.new_for_path(THEME_CSS).get_uri()
    return f'@import url("{uri}"); /* wallpaper-lite */\n'


def _strip_imports(text):
    # Only remove lines that really are our import. A user line that merely mentions
    # the marker is kept, so we never delete somebody else's CSS.
    return "".join(line for line in text.splitlines(True)
                   if not (line.lstrip().startswith("@import url(") and "/* wallpaper-lite */" in line))


def _css_target(path):
    # Respect a user's symlinked dotfiles: change the file the link points at, not the link.
    try:
        if os.path.islink(path):
            return os.path.realpath(path)
    except OSError:
        pass
    return path


def add_import(path):
    path = _css_target(path)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    line = _import_line()
    if line in text:
        return
    _write_like(path, line + _strip_imports(text))


def remove_import(path):
    path = _css_target(path)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return
    kept = _strip_imports(text)
    if kept.strip():
        _write_like(path, kept)
    else:
        with contextlib.suppress(OSError):
            os.unlink(path)


# --- desktop helper -----------------------------------------------------------------

def write_helper_pid():
    _write(os.path.join(runtime_dir(), "desktop.pid"), f"{os.getpid()}\n")


def remove_helper_pid():
    with contextlib.suppress(OSError):
        os.unlink(os.path.join(runtime_dir(), "desktop.pid"))


def _pid_is_helper(pid):
    if pid <= 1:
        return False
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            parts = f.read().split(b"\0")
    except OSError:
        return False
    text = b" ".join(parts)
    return b"wallpaper_lite" in text and b"desktop" in text


def helper_pid():
    try:
        with open(os.path.join(runtime_dir(), "desktop.pid"), encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return None
    if not _pid_is_helper(pid):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def _start_helper(force=False):
    if helper_pid() is not None:
        return True
    # A DESKTOP-type X11 window only makes sense in an X11 session. On Wayland,
    # GNOME's own setting is the only supported route.
    if (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or os.environ.get("WAYLAND_DISPLAY")
            or not os.environ.get("DISPLAY")):
        return False
    env = {**os.environ}
    if force:
        # apply_theme already knows GNOME did not take the picture; show it anyway.
        env["WALLPAPER_LITE_FORCE"] = "1"
    try:
        subprocess.Popen(
            [sys.executable, "-m", "wallpaper_lite", "desktop"],
            cwd=APP_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True, env=env,
        )
    except OSError:
        return False
    return True


def _stop_helper():
    pid = helper_pid()
    if pid is None:
        remove_helper_pid()
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        remove_helper_pid()
        return
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    else:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGKILL)
    remove_helper_pid()


def start_helper():
    """Start the fallback only when GNOME's wallpaper is locked and X11 is present."""
    if gnome_background_writable():
        return False
    with locked():
        return _start_helper()


def stop_helper():
    with locked():
        _stop_helper()


# --- apply and restore ---------------------------------------------------------------

def _apply_theme_locked():
    state, config = load_state(), load_config()
    palette = state.get("palette")
    if not palette:
        return None
    mode = effective_mode(config)
    p = palette.get(mode) or palette.get("dark" if mode == "light" else "light")
    if not p:
        return None

    _save_originals()
    _write(THEME_CSS, css_for(p, mode == "dark"))
    _write_themes(mode == "dark")
    _switch_theme()
    _set("org.gnome.desktop.interface", "color-scheme",
         GLib.Variant("s", "prefer-dark" if mode == "dark" else "default"))
    add_import(GTK3_CSS)
    add_import(GTK4_CSS)
    Gio.Settings.sync()

    used_gnome = False
    still = state.get("wallpaper")
    if still and os.path.isfile(still):
        used_gnome = _set_background(still)
    if used_gnome:
        _stop_helper()
        message = "Wallpaper and colours applied."
    elif _start_helper(force=True):
        message = "Wallpaper and colours applied (desktop helper)."
    else:
        message = "Colours applied, but the wallpaper is locked in this session."

    state["mode"] = mode
    _save_state(state)
    return message


def apply_theme():
    with locked():
        return _apply_theme_locked()


def set_wallpaper(path):
    """Use one picture, make its palettes, and apply everything."""
    path = validate_image(path)
    st = os.stat(path)
    old = load_state()
    if (old.get("wallpaper") == path and old.get("mtime_ns") == st.st_mtime_ns
            and old.get("size") == st.st_size and _palette_ok(old.get("palette"))):
        palette = old["palette"]
    else:
        palette = palette_from_image(path)

    # Make the mode the user actually got explicit, so the window and later runs agree.
    save_config(mode=effective_mode())

    with locked():
        state = {
            "wallpaper": path,
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
            "palette": palette,
            "changed": time.time(),
        }
        _save_state(state)
    return apply_theme()


def set_mode(mode):
    if mode not in ("light", "dark"):
        raise ValueError("mode must be light or dark")
    save_config(mode=mode)
    return apply_theme()


def next_wallpaper():
    current = load_state().get("wallpaper")
    choices = [p for p in wallpapers() if os.path.realpath(p) != current]
    if not choices:
        return None
    pick = random.choice(choices)
    set_wallpaper(pick)
    return pick


def restore():
    """Put every setting back and remove only the files this app added."""
    with locked():
        _stop_helper()
        # Remove our user-CSS import before changing the theme, so running apps do
        # not reload our colours after the original theme comes back.
        remove_import(GTK3_CSS)
        remove_import(GTK4_CSS)

        saved = _read_json(ORIGINALS, {})
        for name, value in saved.items():
            if name not in ALLOWED_ORIGINALS or not isinstance(value, str):
                continue
            schema, key = name.split(" ", 1)
            try:
                variant = GLib.Variant.parse(None, value, None, None)
            except GLib.Error:
                continue
            _set(schema, key, variant)

        # If nothing was saved, or restoring the theme was blocked, at least get
        # off our generated theme before removing its files.
        current = _get("org.gnome.desktop.interface", "gtk-theme")
        try:
            current = current.unpack() if current is not None else ""
        except (TypeError, GLib.Error):
            current = ""
        if current in OUR_THEMES:
            _set("org.gnome.desktop.interface", "gtk-theme", GLib.Variant("s", "Adwaita"))
        Gio.Settings.sync()

        current = _get("org.gnome.desktop.interface", "gtk-theme")
        try:
            current = current.unpack() if current is not None else ""
        except (TypeError, GLib.Error):
            current = ""
        if current in OUR_THEMES:
            raise ValueError("could not restore the theme (it is locked by the administrator)")

        with contextlib.suppress(OSError):
            os.unlink(THEME_CSS)
        for name in OUR_THEMES:
            shutil.rmtree(os.path.join(THEMES_DIR, name), ignore_errors=True)
        _save_state({})
        with contextlib.suppress(OSError):
            os.unlink(ORIGINALS)
