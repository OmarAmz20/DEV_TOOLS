"""High-level actions shared by the window and the command line."""
from __future__ import annotations

import os
import time

from . import library, palette as palette_module, store, system

OPTION_KEYS = (
    "glass", "recolour_gtk", "terminal", "lock_screen", "icon_theme",
    "cursor_theme", "font", "mono_font", "text_scale",
)


def options_snapshot(config):
    return {key: config.get(key) for key in OPTION_KEYS}


def clock_mode(light_from, dark_from, hour=None):
    """Light/dark for the clock, including ranges that cross midnight."""
    hour = time.localtime().tm_hour if hour is None else hour
    light_from, dark_from = int(light_from), int(dark_from)
    if light_from == dark_from:
        return "light"
    if light_from < dark_from:
        return "light" if light_from <= hour < dark_from else "dark"
    return "light" if hour >= light_from or hour < dark_from else "dark"


def effective_mode(config):
    config = config or store.load_config()
    if config["mode"] in ("light", "dark"):
        return config["mode"]
    return clock_mode(config["light_from"], config["dark_from"])


def _state_for(source, result, palette_value, mode, config, options, profile_id=None):
    state = store.load_state()
    state.update({
        "wallpaper": source,
        "still": result["path"] if result else state.get("still"),
        "backend": result["backend"] if result else state.get("backend"),
        "changed": time.time(),
        "profile_id": None,
    })
    if palette_value:
        state.update({
            "palette": palette_value,
            "palette_source": state.get("palette_source") if profile_id else source,
            "mode": mode,
            "mode_setting": config["mode"],
            "style": config.get("style", "balanced"),
            "accent": config.get("accent"),
            "options": options,
            "applied": time.time(),
            "profile_id": profile_id,
        })
        if profile_id:
            state["palette_source"] = source
    return state


def apply_wallpaper(path, config=None, palette_value=None, match_colors=None):
    """Set a wallpaper, optionally recolour everything from it, and save state."""
    config = config or store.load_config()
    path = os.path.realpath(path)
    if not os.path.isfile(path) or not library.is_wallpaper(path):
        raise ValueError(f"not a picture or video: {path}")
    match = config.get("match_colors", True) if match_colors is None else match_colors
    mode = effective_mode(config)
    applied_palette = None
    if match:
        still = library.still_for(path, 1920) or path
        applied_palette = palette_value or palette_module.from_image(
            still, config.get("style", "balanced"), config.get("accent"))
    result = system.apply_wallpaper(path)
    if applied_palette:
        system.apply_theme(applied_palette, mode, config, still=result["path"] or path)
    options = options_snapshot(config)
    state = _state_for(path, result, applied_palette, mode, config, options)
    with store.locked():
        store.save_state(state)
    return {
        "result": result,
        "palette": applied_palette,
        "mode": mode,
        "matched": match,
    }


def apply_colours(palette_value, config=None, mode=None, options=None,
                  source=None, still=None, profile_id=None):
    """Apply palette + options without changing the wallpaper."""
    config = config or store.load_config()
    options = options or options_snapshot(config)
    mode = mode or effective_mode(config)
    state = store.load_state()
    still = still or state.get("still")
    system.apply_theme(palette_value, mode, options, still=still)
    state = _state_for(state.get("wallpaper") or "", None, palette_value,
                       mode, config, options, profile_id)
    state["palette_source"] = source or state.get("palette_source") or state.get("wallpaper")
    with store.locked():
        store.save_state(state)
    return mode


def apply_profile(profile):
    """Apply a saved profile, including its desktop details, in one step."""
    if not isinstance(profile, dict) or "palette" not in profile:
        raise ValueError("not an Aura profile")
    value = profile["palette"]
    if not palette_module.valid_palette(value):
        raise ValueError("profile has invalid light/dark colours")
    config = store.load_config()
    wallpaper = profile.get("wallpaper")
    result = None
    if wallpaper and os.path.isfile(wallpaper) and library.is_wallpaper(wallpaper):
        result = system.apply_wallpaper(os.path.realpath(wallpaper))
        wallpaper = os.path.realpath(wallpaper)

    mode_setting = profile.get("mode", "auto")
    if mode_setting in ("light", "dark"):
        mode = mode_setting
    else:
        mode = clock_mode(profile.get("light_from", config["light_from"]),
                          profile.get("dark_from", config["dark_from"]))

    options = {}
    for key in OPTION_KEYS:
        options[key] = profile.get(key, config.get(key))
    updates = {
        "mode": mode_setting,
        "light_from": int(profile.get("light_from", config["light_from"])),
        "dark_from": int(profile.get("dark_from", config["dark_from"])),
        "style": profile.get("style", config["style"]),
        "accent": profile.get("accent"),
        **options,
    }
    still = result["path"] if result else (wallpaper if wallpaper and os.path.isfile(wallpaper)
                                           else store.load_state().get("still"))
    system.apply_theme(value, mode, options, still=still)
    config = store.save_config(**updates)
    state = _state_for(wallpaper or store.load_state().get("wallpaper") or "",
                       result, value, mode, config, options, profile.get("id"))
    state["palette_source"] = profile.get("palette_source") or wallpaper or state.get("wallpaper")
    with store.locked():
        store.save_state(state)
    return {"wallpaper": wallpaper, "result": result, "mode": mode, "config": config}


def restore():
    return system.restore()


def next_wallpaper(folder=None, current=None):
    config = store.load_config()
    folder = folder or config["folder"]
    path = library.shuffle([entry["path"] for entry in library.scan(folder)],
                           current or store.load_state().get("wallpaper"))
    if not path:
        return None
    return apply_wallpaper(path, config)
