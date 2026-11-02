"""JSON configuration with atomic writes and safe defaults."""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any

from . import constants
from .util import read_json, write_json


DEFAULTS: dict[str, Any] = {
    "version": 1,
    "first_run": True,
    "notifications": True,
    "autostart": False,
    "library": {
        "folders": constants.DEFAULT_FOLDERS,
        "recursive": True,
        "scan_on_start": True,
        "sort": "name",
        "filter": "all",
        "favorites_first": False,
        "preview_width": 360,
        "show_hidden": False,
        "remember_search": False,
        "search": "",
    },
    "wallpaper": {
        "fit": "crop",
        "monitor": "all",
        "apply_target": "both",
        "transition": "simple",
        "transition_duration": 0.8,
        "transition_fps": 60,
        "apply_theme": True,
        "copy_applied": True,
        "restore_on_login": True,
        "target": "auto",
        "slideshow": {
            "enabled": False,
            "minutes": 30,
            "order": "shuffle",
            "favorites_only": False,
            "skip_videos": True,
            "apply_on_start": False,
        },
    },
    "video": {
        "path": "",
        "monitor": "all",
        "fit": "crop",
        "muted": True,
        "loop": True,
        "speed": 1.0,
        "hwdec": "auto-safe",
        "auto_pause": True,
        "auto_stop_fullscreen": False,
        "layer": "background",
        "restore_on_login": True,
        "engine": "auto",
    },
    "appearance": {
        "theme": "midnight-aurora",
        "mode": "auto",
        "variant": "dark",
        "structure": "rounded",
        "radius": 14,
        "border_width": 1,
        "shadow": True,
        "transparency": 0.0,
        "density": "comfortable",
        "accent_override": "",
        "apply_theme": True,
        "apply_terminal": True,
        "terminal": "auto",
        "apply_icons": False,
        "icon_theme": "",
        "apply_cursor": False,
        "cursor_theme": "",
        "cursor_size": 24,
        "apply_fonts": False,
        "ui_font": "",
        "mono_font": "",
        "doc_font": "",
        "text_scale": 1.0,
        "match_wallpaper": True,
        "save_applied_copy": True,
        "dark_schedule": {
            "enabled": False,
            "light_start": "07:00",
            "dark_start": "19:00",
        },
        "button_layout": "",
        "animations": True,
        "overlay_scrolling": True,
        "primary_paste": True,
    },
    "widgets": {
        "enabled": False,
        "monitor": "all",
        "layer": "bottom",
        "opacity": 0.88,
        "theme": "glass",
        "accent": "",
        "font_family": "",
        "font_scale": 1.0,
        "click_through": True,
        "snap_grid": True,
        "grid_size": 2,
        "show_on_all_workspaces": True,
        "layout": "default",
        "restore_on_login": True,
        "items": [],
    },
    "performance": {
        "profile": "balanced",
        "thumb_threads": 4,
        "thumb_size": 360,
        "cache_mb": 512,
        "preview_max": 1600,
        "scan_batch": 32,
        "animations": True,
        "preload_thumbs": False,
        "thumbnail_format": "jpeg",
    },
    "desktop": {
        "ui_font": "",
        "mono_font": "",
        "doc_font": "",
        "text_scale": 1.0,
        "icon_theme": "",
        "cursor_theme": "",
        "cursor_size": 24,
        "button_layout": "",
        "animations": True,
        "overlay_scrolling": True,
        "primary_paste": True,
    },
    "ui": {
        "last_page": "library",
        "window_width": 1420,
        "window_height": 900,
        "sidebar_width": 226,
        "show_preview": True,
        "welcome_seen": False,
    },
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _dot_get(payload: dict[str, Any], key: str, default: Any = None) -> Any:
    part: Any = payload
    for piece in key.split("."):
        if not isinstance(part, dict) or piece not in part:
            return default
        part = part[piece]
    return part


class Config:
    """A small mutable configuration object shared by the app and helpers."""

    def __init__(self, path: Path | str = constants.CONFIG_FILE) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        constants.ensure_dirs()
        raw = read_json(self.path, {})
        if isinstance(raw, dict):
            self.data = deep_merge(DEFAULTS, raw)
        else:
            self.data = copy.deepcopy(DEFAULTS)
        self._normalise()

    def _normalise(self) -> None:
        folders = self.data.get("library", {}).get("folders")
        if not isinstance(folders, list) or not folders:
            self.data["library"]["folders"] = list(constants.DEFAULT_FOLDERS)
        if self.data["appearance"].get("theme") not in (None, ""):
            self.data["appearance"]["theme"] = str(self.data["appearance"]["theme"])
        for key in ("thumb_threads", "thumb_size", "cache_mb", "preview_max"):
            try:
                self.data["performance"][key] = int(self.data["performance"][key])
            except (TypeError, ValueError):
                self.data["performance"][key] = DEFAULTS["performance"][key]
        self.data["performance"]["thumb_threads"] = max(1, min(16, self.data["performance"]["thumb_threads"]))
        self.data["performance"]["thumb_size"] = max(180, min(800, self.data["performance"]["thumb_size"]))
        self.data["performance"]["cache_mb"] = max(64, min(8192, self.data["performance"]["cache_mb"]))
        self.data["performance"]["preview_max"] = max(800, min(4096, self.data["performance"]["preview_max"]))

    def save(self) -> None:
        with self._lock:
            write_json(self.path, self.data)

    def reload(self) -> None:
        with self._lock:
            self.load()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return _dot_get(self.data, key, default)

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        with self._lock:
            pieces = key.split(".")
            node = self.data
            for piece in pieces[:-1]:
                if not isinstance(node.get(piece), dict):
                    node[piece] = {}
                node = node[piece]
            node[pieces[-1]] = value
            if key == "first_run":
                self.data["first_run"] = bool(value)
            if save:
                self.save()

    def update(self, values: dict[str, Any], *, save: bool = True) -> None:
        with self._lock:
            self.data = deep_merge(self.data, values)
            self._normalise()
            if save:
                self.save()

    def reset(self, *, save: bool = True) -> None:
        with self._lock:
            self.data = copy.deepcopy(DEFAULTS)
            if save:
                self.save()

    @property
    def folders(self) -> list[str]:
        return list(self.get("library.folders", []))

    def add_folder(self, folder: str | Path) -> bool:
        folder = str(Path(folder).expanduser().resolve())
        folders = self.folders
        if folder in folders:
            return False
        folders.append(folder)
        self.set("library.folders", folders)
        return True

    def remove_folder(self, folder: str | Path) -> bool:
        folder = str(Path(folder).expanduser().resolve())
        folders = [item for item in self.folders if item != folder]
        if folders == self.folders:
            return False
        self.set("library.folders", folders)
        return True
