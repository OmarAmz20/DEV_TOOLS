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


CONFIG_DIR = os.environ.get("AURA_CONFIG_DIR") or os.path.join(
    _xdg("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "aura-studio")
CACHE_DIR = os.environ.get("AURA_CACHE_DIR") or os.path.join(
    _xdg("XDG_CACHE_HOME", os.path.join(HOME, ".cache")), "aura-studio")
CONFIG = os.path.join(CONFIG_DIR, "config.json")
STATE = os.path.join(CONFIG_DIR, "state.json")
ORIGINALS = os.path.join(CONFIG_DIR, "originals.json")
THEME_CSS = os.path.join(CONFIG_DIR, "theme.css")
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


DEFAULT_CONFIG = {
    "folder": _default_folder(),
    "mode": "auto",                 # light | dark | auto
    "light_from": 7,
    "dark_from": 19,
    "style": "balanced",            # vivid | balanced | muted | mono
    "accent": None,                 # custom #RRGGBB, or None for the picture's accent
    "match_colors": True,           # recolour when a wallpaper is applied
    "slide_minutes": 0,             # 0 = no slideshow
    "glass": False,
    "recolour_gtk": True,
    "terminal": True,
    "lock_screen": False,
    "icon_theme": None,             # None = leave the system value alone
    "cursor_theme": None,
    "font": None,
    "mono_font": None,
    "text_scale": None,
    "favorites": [],
}

PROFILE_KEYS = (
    "mode", "light_from", "dark_from", "style", "accent", "glass",
    "recolour_gtk", "terminal", "lock_screen", "icon_theme", "cursor_theme",
    "font", "mono_font", "text_scale",
)


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


def load_config():
    config = {**DEFAULT_CONFIG, **_read_json(CONFIG, {})}
    if not isinstance(config.get("folder"), str):
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
    try:
        config["slide_minutes"] = max(0, int(config.get("slide_minutes", 0)))
    except (TypeError, ValueError):
        config["slide_minutes"] = 0
    for key in ("icon_theme", "cursor_theme", "font", "mono_font"):
        if config.get(key) is not None and not isinstance(config.get(key), str):
            config[key] = None
    if config.get("text_scale") is not None:
        try:
            config["text_scale"] = max(0.5, min(3.0, float(config["text_scale"])))
        except (TypeError, ValueError):
            config["text_scale"] = None
    config["favorites"] = [path for path in config.get("favorites", [])
                           if isinstance(path, str)]
    return config


def save_config(**changes):
    config = {**load_config(), **changes}
    write_json(CONFIG, config)
    return config


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
