"""Small, boring, atomic persistence for Aura Studio.

Nothing here talks to the desktop; see system.py for that.  Set
AURA_CONFIG_DIR / AURA_CACHE_DIR to keep tests away from the real settings.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
import time

HOME = os.path.expanduser("~")


def _xdg(env, fallback):
    return os.environ.get(env) or fallback


def _goinfre_root():
    """The 42-school goinfre mount, when this machine has one.

    goinfre is big and survives between sessions on campus machines, while the
    home directory has a small quota.  Set AURA_GOINFRE to override it.
    """
    candidates = []
    if os.environ.get("AURA_GOINFRE"):
        candidates.append(os.environ["AURA_GOINFRE"])
    candidates.append(os.path.join(HOME, "goinfre"))
    for candidate in candidates:
        if candidate and os.path.isdir(candidate) and os.access(candidate, os.W_OK):
            return os.path.realpath(candidate)
    return None


GOINFRE = _goinfre_root()
GOINFRE_ROOT = os.path.join(GOINFRE, "aura-studio") if GOINFRE else None


def _cache_dir():
    override = os.environ.get("AURA_CACHE_DIR")
    if override:
        return override
    if GOINFRE_ROOT:
        return os.path.join(GOINFRE_ROOT, "cache")
    return os.path.join(_xdg("XDG_CACHE_HOME", os.path.join(HOME, ".cache")),
                        "aura-studio")


CONFIG_DIR = os.environ.get("AURA_CONFIG_DIR") or os.path.join(
    _xdg("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "aura-studio")
CACHE_DIR = _cache_dir()
CONFIG = os.path.join(CONFIG_DIR, "config.json")
STATE = os.path.join(CONFIG_DIR, "state.json")
ORIGINALS = os.path.join(CONFIG_DIR, "originals.json")
THEME_CSS = os.path.join(CONFIG_DIR, "theme.css")
CUSTOM_CSS = os.path.join(CONFIG_DIR, "custom.css")
HOOKS = os.path.join(CONFIG_DIR, "hooks")
PROFILES = os.path.join(CONFIG_DIR, "profiles")
LOCK = os.path.join(CONFIG_DIR, ".lock")
THUMBS = os.path.join(CACHE_DIR, "thumbs")
FRAMES = os.path.join(CACHE_DIR, "frames")
EXPORTS = os.path.join(CONFIG_DIR, "exports")


def _default_folder():
    candidates = (
        os.path.join(HOME, "Pictures", "wallpapers"),
        os.path.join(HOME, "Pictures", "Wallpapers"),
        os.path.join(HOME, "Pictures"),
        os.path.join(HOME, "Downloads"),
    )
    for path in candidates:
        if os.path.isdir(path):
            return path
    return HOME


WALLPAPER_MODES = ("fill", "fit", "stretch", "center", "tile", "span")
WALLPAPER_MODE_LABELS = {
    "fill": "Fill the screen",
    "fit": "Fit inside the screen",
    "stretch": "Stretch to the screen",
    "center": "Centre at original size",
    "tile": "Tile",
    "span": "Span across monitors",
}
SLIDESHOW_ORDERS = ("shuffle", "sequential")
SLIDESHOW_ORDER_LABELS = {
    "shuffle": "Shuffle",
    "sequential": "In order",
}

WALLPAPER_BACKENDS = (
    "auto", "gnome", "desktop", "feh", "dms", "hyprpaper", "awww", "swaybg",
)
WALLPAPER_BACKEND_LABELS = {
    "auto": "Detect automatically",
    "gnome": "GNOME desktop settings",
    "desktop": "X11 desktop window",
    "feh": "feh",
    "dms": "DankMaterialShell",
    "hyprpaper": "hyprpaper",
    "awww": "awww",
    "swaybg": "swaybg",
}

TERMINAL_TARGETS = ("kitty", "gnome-terminal")
TERMINAL_TARGET_LABELS = {
    "kitty": "Kitty",
    "gnome-terminal": "GNOME Terminal",
}

BOOLEAN_KEYS = (
    "match_colors", "glass", "recolour_gtk", "terminal", "lock_screen",
)

DEFAULT_CONFIG = {
    "folder": _default_folder(),
    "mode": "auto",                 # light | dark | auto
    "light_from": 7,
    "dark_from": 19,
    "style": "balanced",            # vivid | balanced | muted | mono
    "accent": None,                 # custom #RRGGBB, or None for the picture's accent
    "match_colors": True,           # recolour when a wallpaper is applied
    "wallpaper_mode": "fill",       # fill | fit | stretch | center | tile | span
    "wallpaper_backend": "auto",    # auto, or force one of WALLPAPER_BACKENDS
    "slide_minutes": 0,             # 0 = no slideshow
    "slideshow_order": "shuffle",   # shuffle | sequential
    "glass": False,
    "glass_opacity": 0.72,          # wallpaper visibility through app windows
    "recolour_gtk": True,
    "terminal": True,
    "terminal_targets": None,       # None = every detected terminal, or a list
    "lock_screen": False,
    "icon_theme": None,             # None = leave the system value alone
    "cursor_theme": None,
    "cursor_size": None,            # None = leave the system value alone
    "font": None,
    "mono_font": None,
    "text_scale": None,
    "autostart_profile": None,      # profile id, or None for the last applied look
    "autostart_delay": 8,           # seconds to wait after login
    "favorites": [],
}

PROFILE_KEYS = (
    "mode", "light_from", "dark_from", "style", "accent", "wallpaper_mode",
    "glass", "glass_opacity", "recolour_gtk", "terminal", "terminal_targets",
    "lock_screen", "icon_theme", "cursor_theme", "cursor_size", "font",
    "mono_font", "text_scale", "autostart_delay",
)
CONFIG_KEYS = tuple(DEFAULT_CONFIG)


# --- files ------------------------------------------------------------------------

def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def write_text(path, text):
    """Write *path* atomically, creating parents and keeping its mode."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = None
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def write_json(path, value):
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _bool(value, default=False):
    """Treat JSON true/false and the strings people type in a terminal alike."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off", ""):
            return False
    if value is None:
        return default
    return bool(value)


def _hex(value, fallback=None):
    if not isinstance(value, str):
        return fallback
    value = value.strip().upper()
    if len(value) == 7 and value.startswith("#") and \
            all(character in "0123456789ABCDEF" for character in value[1:]):
        return value
    return fallback


def load_config():
    config = {**DEFAULT_CONFIG, **_read_json(CONFIG, {})}
    if not isinstance(config.get("folder"), str) or not config["folder"]:
        config["folder"] = DEFAULT_CONFIG["folder"]
    if config.get("mode") not in ("light", "dark", "auto"):
        config["mode"] = "auto"
    if config.get("style") not in ("vivid", "balanced", "muted", "mono"):
        config["style"] = "balanced"
    for key in ("light_from", "dark_from"):
        try:
            config[key] = max(0, min(23, int(config[key])))
        except (TypeError, ValueError):
            config[key] = DEFAULT_CONFIG[key]
    for key, upper in (("slide_minutes", 10080), ("autostart_delay", 300)):
        try:
            config[key] = max(0, min(upper, int(config.get(key, 0))))
        except (TypeError, ValueError):
            config[key] = DEFAULT_CONFIG[key]
    if config.get("wallpaper_mode") not in WALLPAPER_MODES:
        config["wallpaper_mode"] = "fill"
    if config.get("wallpaper_backend") not in WALLPAPER_BACKENDS:
        config["wallpaper_backend"] = "auto"
    if config.get("slideshow_order") not in SLIDESHOW_ORDERS:
        config["slideshow_order"] = "shuffle"
    for key in BOOLEAN_KEYS:
        config[key] = _bool(config.get(key), DEFAULT_CONFIG[key])
    config["accent"] = _hex(config.get("accent"))
    for key in ("icon_theme", "cursor_theme", "font", "mono_font",
                "autostart_profile"):
        if config.get(key) is not None and not isinstance(config.get(key), str):
            config[key] = None
    if config.get("cursor_size") is not None:
        try:
            config["cursor_size"] = max(8, min(128, int(config["cursor_size"])))
        except (TypeError, ValueError):
            config["cursor_size"] = None
    if config.get("text_scale") is not None:
        try:
            config["text_scale"] = max(0.5, min(3.0, float(config["text_scale"])))
        except (TypeError, ValueError):
            config["text_scale"] = None
    try:
        config["glass_opacity"] = max(0.15, min(1.0, float(config["glass_opacity"])))
    except (TypeError, ValueError):
        config["glass_opacity"] = DEFAULT_CONFIG["glass_opacity"]
    targets = config.get("terminal_targets")
    if targets is None:
        config["terminal_targets"] = None
    elif isinstance(targets, (list, tuple)):
        seen = []
        for target in targets:
            if isinstance(target, str) and target in TERMINAL_TARGETS and target not in seen:
                seen.append(target)
        config["terminal_targets"] = seen
    else:
        config["terminal_targets"] = None
    config["favorites"] = [path for path in config.get("favorites", [])
                           if isinstance(path, str)]
    return config


def save_config(**changes):
    with locked():
        config = {**load_config(), **changes}
        write_json(CONFIG, config)
        return load_config()


def load_state():
    return _read_json(STATE, {})


def save_state(state):
    write_json(STATE, state)


def load_originals():
    return _read_json(ORIGINALS, {})


def save_originals(originals):
    write_json(ORIGINALS, originals)


def remove_originals():
    with contextlib.suppress(FileNotFoundError):
        os.remove(ORIGINALS)


@contextlib.contextmanager
def locked():
    """Serialise changes between the window, the CLI and auto-switchers."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(LOCK, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


# --- favorites --------------------------------------------------------------------

def toggle_favorite(path):
    path = os.path.realpath(path)
    config = load_config()
    favorites = [os.path.realpath(p) for p in config["favorites"]]
    if path in favorites:
        favorites.remove(path)
    else:
        favorites.append(path)
    save_config(favorites=favorites)
    return path in favorites


def is_favorite(path):
    normalized = os.path.realpath(path)
    return normalized in {os.path.realpath(p) for p in load_config()["favorites"]}


# --- cache ------------------------------------------------------------------------

def cache_name(path, width, height, extension):
    stat = os.stat(path)
    key = f"{os.path.realpath(path)}:{stat.st_size}:{stat.st_mtime_ns}:{width}x{height}"
    return hashlib.sha1(key.encode()).hexdigest()[:20] + extension


def thumbnail_path(path, width, height):
    return os.path.join(THUMBS, cache_name(path, width, height, ".jpg"))


def frame_path(path, width):
    return os.path.join(FRAMES, cache_name(path, width, 0, ".jpg"))


# --- profiles ---------------------------------------------------------------------

def _profile_path(profile_id):
    return os.path.join(PROFILES, f"{profile_id}.json")


def new_profile_id():
    return f"{int(time.time())}-{os.urandom(4).hex()}"


def save_profile(profile):
    profile = dict(profile)
    profile.setdefault("id", new_profile_id())
    profile.setdefault("created", time.time())
    profile["updated"] = time.time()
    write_json(_profile_path(profile["id"]), profile)
    return profile


def load_profiles():
    try:
        names = [n for n in os.listdir(PROFILES) if n.endswith(".json")]
    except OSError:
        return []
    profiles = []
    for name in names:
        profile = _read_json(os.path.join(PROFILES, name), {})
        if profile.get("id") and profile.get("palette"):
            profiles.append(profile)
    return sorted(profiles, key=lambda p: p.get("created", 0), reverse=True)


def delete_profile(profile_id):
    with contextlib.suppress(FileNotFoundError):
        os.remove(_profile_path(profile_id))


# --- misc -------------------------------------------------------------------------

def applied_mode(config):
    config = config or load_config()
    if config["mode"] in ("light", "dark"):
        return config["mode"]
    hour = time.localtime().tm_hour
    light_from, dark_from = int(config["light_from"]), int(config["dark_from"])
    if light_from == dark_from:
        return "light"
    if light_from < dark_from:
        return "light" if light_from <= hour < dark_from else "dark"
    return "light" if hour >= light_from or hour < dark_from else "dark"


def human_size(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""
