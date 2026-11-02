"""Shared names, paths and small constants for 1337-Customizer."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_ID = "io.github.LeetCustomizer"
APP_NAME = "1337-Customizer"
APP_SLUG = "1337-customizer"
ICON_NAME = "1337-customizer"
APP_SUBTITLE = "Wallpapers, looks, widgets and motion"
VERSION = "1.0.0"
PROJECT_URL = "https://github.com/"

HOME = Path(os.path.expanduser("~")).resolve()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state")
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache")


def _goinfre_root() -> Path | None:
    """The 42-school goinfre mount, when this machine has a writable one."""
    candidates = []
    override = os.environ.get("LEET_GOINFRE")
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(HOME / "goinfre")
    for candidate in candidates:
        try:
            if candidate.is_dir() and os.access(candidate, os.W_OK):
                return candidate.resolve()
        except OSError:
            continue
    return None


GOINFRE_ROOT = _goinfre_root()
GOINFRE_DIR = GOINFRE_ROOT / APP_SLUG if GOINFRE_ROOT else None

CONFIG_DIR = CONFIG_HOME / APP_SLUG
DATA_DIR = DATA_HOME / APP_SLUG
STATE_DIR = STATE_HOME / APP_SLUG
CACHE_DIR = Path(
    os.environ.get("LEET_CACHE_DIR")
    or (GOINFRE_DIR / "cache" if GOINFRE_DIR else CACHE_HOME / APP_SLUG)
)

CONFIG_FILE = CONFIG_DIR / "config.json"
LIBRARY_DB = DATA_DIR / "library.db"
THUMB_DIR = CACHE_DIR / "thumbs"
PREVIEW_DIR = CACHE_DIR / "previews"
LOG_DIR = STATE_DIR / "logs"
APPLIED_DIR = DATA_DIR / "applied"
THEMES_DIR = DATA_HOME / "themes"
LAYOUT_DIR = DATA_DIR / "layouts"
FONT_DIR = DATA_HOME / "fonts" / "1337-Customizer"
THEME_STATE = STATE_DIR / "theme.json"
WALLPAPER_STATE = STATE_DIR / "wallpaper.json"
VIDEO_STATE = STATE_DIR / "video.json"
WIDGET_STATE = STATE_DIR / "widgets.json"
SESSION_PID = STATE_DIR / "sessiond.pid"
WIDGET_PID = STATE_DIR / "widgetd.pid"
SESSION_LOG = LOG_DIR / "sessiond.log"
WIDGET_LOG = LOG_DIR / "widgetd.log"
VIDEO_LOG = LOG_DIR / "video.log"

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = APP_ROOT / "data"
ENGINE_ROOT = APP_ROOT / "engine"
BUNDLED_MPVPAPER = ENGINE_ROOT / "bin" / "mpvpaper"

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff",
    ".heic", ".heif", ".avif",
}
ANIMATED_EXTENSIONS = {".gif", ".webp", ".apng"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".wmv"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | ANIMATED_EXTENSIONS | VIDEO_EXTENSIONS

GTK3_CSS = CONFIG_HOME / "gtk-3.0" / "gtk.css"
GTK4_CSS = CONFIG_HOME / "gtk-4.0" / "gtk.css"
GTK3_SETTINGS = CONFIG_HOME / "gtk-3.0" / "settings.ini"
GTK4_SETTINGS = CONFIG_HOME / "gtk-4.0" / "settings.ini"
KITTY_CONF = CONFIG_HOME / "kitty" / "kitty.conf"
KITTY_THEME = CONFIG_HOME / "kitty" / "1337-theme.conf"
FOOT_CONF = CONFIG_HOME / "foot" / "foot.ini"
FOOT_THEME = CONFIG_HOME / "foot" / "1337-theme.ini"
GHOSTTY_CONF = CONFIG_HOME / "ghostty" / "config"
GHOSTTY_THEME = CONFIG_HOME / "ghostty" / "1337-theme"
ALACRITTY_CONF = CONFIG_HOME / "alacritty" / "alacritty.toml"
ALACRITTY_THEME = CONFIG_HOME / "alacritty" / "1337-theme.toml"

# New markers use the leet brand.  Legacy Hamiid markers are cleaned up so an
# upgrade cannot leave a duplicated terminal/GTK include behind.
THEME_MARKER_BEGIN = "/* 1337-customizer:begin */"
THEME_MARKER_END = "/* 1337-customizer:end */"
HASH_MARKER_BEGIN = "# 1337-customizer:begin"
HASH_MARKER_END = "# 1337-customizer:end"
GTK_IMPORT_MARKER_BEGIN = "/* 1337-customizer:import:begin */"
GTK_IMPORT_MARKER_END = "/* 1337-customizer:import:end */"

APP_CSS = DATA_ROOT / "app.css"
PRESETS_FILE = DATA_ROOT / "presets.json"
WIDGET_PRESETS_FILE = DATA_ROOT / "widget-presets.json"
DESKTOP_FILE = DATA_ROOT / "1337-customizer.desktop"
ICON_FILE = DATA_ROOT / "1337-customizer.svg"

DEFAULT_PICTURES = HOME / "Pictures" / "Wallpapers"


def _default_folders() -> list[str]:
    # Prefer dedicated wallpaper folders.  Case-sensitive filesystems often
    # have both "wallpapers" and "Wallpapers"; they are siblings, not nested,
    # so including both is safe and gives the collection a useful head start.
    candidates = [
        HOME / "Pictures" / "wallpapers",
        DEFAULT_PICTURES,
        HOME / "Pictures",
        HOME / "Downloads",
    ]
    found = [str(path) for path in candidates if path.is_dir()]
    if found:
        # Stop before the generic ~/Pictures folder when a dedicated one exists.
        dedicated = [path for path in found if Path(path).name.lower() == "wallpapers"]
        return dedicated if dedicated else found[:1]
    return [str(HOME / "Pictures")]


DEFAULT_FOLDERS = _default_folders()

# Search locations for GTK's typelib files.  Some distributions install
# gtk4-layer-shell outside the directory Pango/GI searches by default.
TYPE_LIB_PATHS = (
    "/usr/lib/girepository-1.0",
    "/usr/lib64/girepository-1.0",
    "/usr/lib/x86_64-linux-gnu/girepository-1.0",
    "/usr/local/lib/girepository-1.0",
)

LAYER_SHELL_LIBRARY_PATHS = (
    "/usr/lib/libgtk4-layer-shell.so",
    "/usr/lib64/libgtk4-layer-shell.so",
    "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
    "/usr/local/lib/libgtk4-layer-shell.so",
)

FIT_MODES = ("crop", "fit", "stretch", "center")
WALLPAPER_TRANSITIONS = (
    "none", "simple", "fade", "left", "right", "top", "bottom",
    "wipe", "wave", "grow", "center", "outer", "random",
)
STRUCTURES = (
    "rounded", "sharp", "glass", "neon", "paper", "pixel",
    "minimal", "retro",
)
WIDGET_THEMES = (
    "glass", "solid", "outline", "neon", "paper", "pixel",
    "terminal", "minimal",
)
TERMINALS = ("auto", "kitty", "foot", "ghostty", "wezterm", "alacritty")

# Paths from the previous name.  They are copied into the new tree once, so
# existing libraries, saved looks and backups survive the rename.
LEGACY_SLUG = "hamiid-studio"
LEGACY_FONT_DIR = DATA_HOME / "fonts" / "Hamiid Studio"
LEGACY_THEME_SLOTS = ("Hamiid-A", "Hamiid-B")
LEGACY_KITTY_THEME = CONFIG_HOME / "kitty" / "hamiid-theme.conf"
LEGACY_FOOT_THEME = CONFIG_HOME / "foot" / "hamiid-theme.ini"
LEGACY_GHOSTTY_THEME = CONFIG_HOME / "ghostty" / "hamiid-theme"
LEGACY_ALACRITTY_THEME = CONFIG_HOME / "alacritty" / "hamiid-theme.toml"
LEGACY_WEZTERM_THEME = CONFIG_HOME / "wezterm" / "hamiid-theme.lua"
LEGACY_AUTOSTART = CONFIG_HOME / "autostart" / "io.github.HamiidStudio.desktop"


def _migrate_legacy() -> None:
    """Copy old Hamiid Studio user data into the 1337 tree once."""
    pairs = (
        (CONFIG_HOME / LEGACY_SLUG, CONFIG_DIR),
        (DATA_HOME / LEGACY_SLUG, DATA_DIR),
        (STATE_HOME / LEGACY_SLUG, STATE_DIR),
        (CACHE_HOME / LEGACY_SLUG, CACHE_DIR),
    )
    for old, new in pairs:
        if old.is_dir() and not new.exists():
            try:
                shutil.copytree(old, new, dirs_exist_ok=True)
            except OSError:
                pass
    if LEGACY_FONT_DIR.is_dir() and not FONT_DIR.exists():
        try:
            shutil.copytree(LEGACY_FONT_DIR, FONT_DIR, dirs_exist_ok=True)
        except OSError:
            pass


def ensure_dirs() -> None:
    _migrate_legacy()
    for directory in (
        CONFIG_DIR, DATA_DIR, STATE_DIR, CACHE_DIR, THUMB_DIR, PREVIEW_DIR,
        LOG_DIR, APPLIED_DIR, THEMES_DIR, LAYOUT_DIR, FONT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
