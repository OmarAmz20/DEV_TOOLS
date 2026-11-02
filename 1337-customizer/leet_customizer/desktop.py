"""Desktop integration: GNOME/GTK settings, themes, terminals and monitors."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from . import constants, palette, themes
from .util import (
    atomic_write_text,
    file_uri,
    human_size,
    notify,
    read_json,
    read_text,
    run,
    strip_marked_block,
    which,
    write_json,
)

try:
    from gi.repository import Gio, GLib
except Exception:  # pragma: no cover
    Gio = None
    GLib = None


INTERFACE = "org.gnome.desktop.interface"
BACKGROUND = "org.gnome.desktop.background"
SCREENSAVER = "org.gnome.desktop.screensaver"
WM = "org.gnome.desktop.wm.preferences"

TOUCHED_KEYS = [
    (INTERFACE, "gtk-theme"),
    (INTERFACE, "color-scheme"),
    (INTERFACE, "icon-theme"),
    (INTERFACE, "cursor-theme"),
    (INTERFACE, "cursor-size"),
    (INTERFACE, "font-name"),
    (INTERFACE, "document-font-name"),
    (INTERFACE, "monospace-font-name"),
    (INTERFACE, "text-scaling-factor"),
    (INTERFACE, "gtk-enable-animations"),
    (INTERFACE, "gtk-overlay-scrolling"),
    (INTERFACE, "gtk-enable-primary-paste"),
    (INTERFACE, "accent-color"),
    (WM, "button-layout"),
]

BACKUP_DIR = constants.STATE_DIR / "backups"
DESKTOP_BACKUP = BACKUP_DIR / "desktop.json"
THEME_DIR = constants.THEMES_DIR
THEME_SLOTS = ("L33T-A", "L33T-B")

_SCHEMA_CACHE: dict[str, Any] = {}
_FONTS_CACHE: tuple[float, list[str]] = (0.0, [])


def _schema(name: str):
    if Gio is None:
        return None
    if name in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[name]
    source = Gio.SettingsSchemaSource.get_default()
    if source is None:
        return None
    schema = source.lookup(name, True)
    _SCHEMA_CACHE[name] = schema
    return schema


def _settings(name: str):
    schema = _schema(name)
    if schema is None:
        return None
    return Gio.Settings.new_full(schema, None, None)


def has_key(schema_name: str, key: str) -> bool:
    schema = _schema(schema_name)
    return bool(schema is not None and schema.has_key(key))


def get_value(schema_name: str, key: str, default: Any = None) -> Any:
    settings = _settings(schema_name)
    if settings is None or not has_key(schema_name, key):
        return default
    try:
        value = settings.get_value(key)
        return value.unpack()
    except Exception:
        return default


def backup_payload() -> dict:
    raw = read_json(DESKTOP_BACKUP, {})
    return raw if isinstance(raw, dict) else {}


def _capture(schema_name: str, key: str) -> None:
    settings = _settings(schema_name)
    if settings is None or not has_key(schema_name, key):
        return
    full = f"{schema_name}:{key}"
    backup = backup_payload()
    if full in backup:
        return
    try:
        value = settings.get_value(key)
        key_object = _schema(schema_name).get_key(key)
        backup[full] = {
            "schema": schema_name,
            "key": key,
            "type": key_object.get_value_type().dup_string(),
            "value": value.print_(True),
        }
        BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_json(DESKTOP_BACKUP, backup)
    except Exception:
        pass


def set_value(schema_name: str, key: str, value: Any, *, capture: bool = True) -> bool:
    settings = _settings(schema_name)
    if settings is None or not has_key(schema_name, key):
        return False
    try:
        if not settings.is_writable(key):
            return False
    except Exception:
        return False
    if capture:
        _capture(schema_name, key)
    try:
        key_object = _schema(schema_name).get_key(key)
        variant_type = key_object.get_value_type().dup_string()
        variant = GLib.Variant(variant_type, value)
        settings.set_value(key, variant)
        Gio.Settings.sync()
        return True
    except Exception:
        return False


def set_string(schema: str, key: str, value: str, *, capture: bool = True) -> bool:
    return set_value(schema, key, str(value), capture=capture)


def set_int(schema: str, key: str, value: int, *, capture: bool = True) -> bool:
    return set_value(schema, key, int(value), capture=capture)


def set_double(schema: str, key: str, value: float, *, capture: bool = True) -> bool:
    return set_value(schema, key, float(value), capture=capture)


def set_bool(schema: str, key: str, value: bool, *, capture: bool = True) -> bool:
    return set_value(schema, key, bool(value), capture=capture)


def restore_desktop_backup(keys: set[str] | None = None) -> int:
    backup = backup_payload()
    restored = 0
    for full_key, entry in backup.items():
        if keys is not None and entry.get("key") not in keys:
            continue
        schema_name = entry.get("schema")
        key = entry.get("key")
        value = entry.get("value")
        if not schema_name or not key or value is None:
            continue
        settings = _settings(schema_name)
        if settings is None or not has_key(schema_name, key):
            continue
        try:
            variant = GLib.Variant.parse(None, str(value), None, None)
            settings.set_value(key, variant)
            restored += 1
        except Exception:
            pass
    if Gio is not None:
        with contextlib.suppress(Exception):
            Gio.Settings.sync()
    return restored


# --- appearance / theme -----------------------------------------------------------

def _theme_dir(slot: str) -> Path:
    return THEME_DIR / slot


def _index_theme(slot: str, theme: dict) -> str:
    layout = get_value(WM, "button-layout", "appmenu:minimize,maximize,close")
    if not isinstance(layout, str):
        layout = "appmenu:minimize,maximize,close"
    return f"""[Desktop Entry]
Type=X-GNOME-Metatheme
Name={slot}
Comment=Generated by 1337-Customizer
Encoding=UTF-8

[X-GNOME-Metatheme]
GtkTheme={slot}
MetacityTheme=Adwaita
IconTheme=Adwaita
CursorTheme=Adwaita
ButtonLayout={layout}
"""


def write_gtk_theme(theme: dict, slot: str) -> Path:
    directory = _theme_dir(slot)
    for version in (3, 4):
        css_dir = directory / f"gtk-{version}.0"
        css_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        css = themes.generate_gtk_css(theme, gtk_version=version)
        atomic_write_text(css_dir / "gtk.css", css, mode=0o644)
    atomic_write_text(directory / "index.theme", _index_theme(slot, theme), mode=0o644)
    return directory


def _strip_legacy_imports(text: str) -> str:
    text = strip_marked_block(text, "/* hamiid-studio:import:begin */",
                              "/* hamiid-studio:import:end */")
    return strip_marked_block(text, "/* hamiid-studio:begin */", "/* hamiid-studio:end */")


def _prepend_managed_import(path: Path, import_path: Path) -> None:
    begin = constants.GTK_IMPORT_MARKER_BEGIN
    end = constants.GTK_IMPORT_MARKER_END
    original = read_text(path)
    original = _strip_legacy_imports(original)
    original = strip_marked_block(original, begin, end)
    block = f'{begin}\n@import url("{file_uri(import_path)}");\n{end}\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, block + original.lstrip(), mode=0o644)


def _remove_managed_import(path: Path) -> None:
    if not path.exists():
        return
    original = _strip_legacy_imports(read_text(path))
    updated = strip_marked_block(original, constants.GTK_IMPORT_MARKER_BEGIN,
                                 constants.GTK_IMPORT_MARKER_END)
    if updated != original:
        atomic_write_text(path, updated, mode=0o644)


def _clean_theme_state() -> dict:
    state = read_json(constants.THEME_STATE, {})
    return state if isinstance(state, dict) else {}


def apply_theme(config, theme: dict) -> dict:
    """Write CSS, set GTK/desktop options and return a result report."""
    report = {"ok": True, "warnings": [], "terminal": "", "gtk": "", "variant": theme.get("variant")}
    appearance = config.get("appearance", {}) if config else {}
    slot = THEME_SLOTS[0]
    previous = _clean_theme_state().get("slot")
    if previous in THEME_SLOTS:
        slot = THEME_SLOTS[(THEME_SLOTS.index(previous) + 1) % len(THEME_SLOTS)]
    try:
        directory = write_gtk_theme(theme, slot)
        report["gtk"] = slot
    except Exception as error:
        report["ok"] = False
        report["warnings"].append(f"Could not write GTK theme: {error}")
        directory = _theme_dir(slot)

    if appearance.get("apply_theme", True):
        if set_string(INTERFACE, "gtk-theme", slot):
            report["gtk"] = slot
        else:
            report["warnings"].append("GTK theme setting is not writable")
        # Direct imports keep the change visible even when an app ignores the
        # GTK theme name (common with some GTK4/libadwaita applications).
        with contextlib.suppress(Exception):
            _prepend_managed_import(constants.GTK4_CSS, directory / "gtk-4.0" / "gtk.css")
        with contextlib.suppress(Exception):
            _prepend_managed_import(constants.GTK3_CSS, directory / "gtk-3.0" / "gtk.css")
        scheme = "prefer-dark" if theme.get("variant") == "dark" else "prefer-light"
        set_string(INTERFACE, "color-scheme", scheme)
        if appearance.get("accent_override"):
            set_string(INTERFACE, "accent-color", appearance["accent_override"])
        if "apply_icons" in appearance:
            if appearance.get("apply_icons") and appearance.get("icon_theme"):
                set_string(INTERFACE, "icon-theme", appearance["icon_theme"])
        if "apply_cursor" in appearance:
            if appearance.get("apply_cursor") and appearance.get("cursor_theme"):
                set_string(INTERFACE, "cursor-theme", appearance["cursor_theme"])
            if appearance.get("apply_cursor"):
                set_int(INTERFACE, "cursor-size", int(appearance.get("cursor_size", 24)))
        if appearance.get("apply_fonts"):
            apply_fonts(config)
        set_bool(INTERFACE, "gtk-enable-animations", bool(appearance.get("animations", True)))
        set_bool(INTERFACE, "gtk-overlay-scrolling", bool(appearance.get("overlay_scrolling", True)))
        set_bool(INTERFACE, "gtk-enable-primary-paste", bool(appearance.get("primary_paste", True)))
        if appearance.get("button_layout"):
            set_string(WM, "button-layout", appearance["button_layout"])

    if appearance.get("apply_terminal", True):
        try:
            terminal_result = apply_terminal(theme, appearance.get("terminal", "auto"))
            report["terminal"] = terminal_result
            if terminal_result.startswith("alacritty:") or terminal_result.startswith("wezterm:"):
                report["warnings"].append(terminal_result)
        except Exception as error:
            report["warnings"].append(f"Terminal theme: {error}")

    state = {
        "version": 1,
        "applied": True,
        "slot": slot,
        "at": time.time(),
        "theme": theme,
    }
    write_json(constants.THEME_STATE, state)
    return report


def apply_fonts(config) -> dict:
    appearance = config.get("appearance", {})
    changed = {}
    if appearance.get("ui_font"):
        changed["font-name"] = set_string(INTERFACE, "font-name", appearance["ui_font"])
    if appearance.get("mono_font"):
        changed["monospace-font-name"] = set_string(INTERFACE, "monospace-font-name", appearance["mono_font"])
    if appearance.get("doc_font"):
        changed["document-font-name"] = set_string(INTERFACE, "document-font-name", appearance["doc_font"])
    try:
        scale = float(appearance.get("text_scale", 1.0))
        if 0.75 <= scale <= 2.5:
            changed["text-scaling-factor"] = set_double(INTERFACE, "text-scaling-factor", scale)
    except (TypeError, ValueError):
        pass
    return changed


def apply_desktop_controls(config) -> dict:
    appearance = config.get("appearance", {})
    result = {}
    if appearance.get("ui_font") or appearance.get("mono_font") or appearance.get("doc_font"):
        result.update(apply_fonts(config))
    if appearance.get("apply_icons") and appearance.get("icon_theme"):
        result["icon-theme"] = set_string(INTERFACE, "icon-theme", appearance["icon_theme"])
    if appearance.get("apply_cursor"):
        if appearance.get("cursor_theme"):
            result["cursor-theme"] = set_string(INTERFACE, "cursor-theme", appearance["cursor_theme"])
        result["cursor-size"] = set_int(INTERFACE, "cursor-size", int(appearance.get("cursor_size", 24)))
    result["animations"] = set_bool(INTERFACE, "gtk-enable-animations",
                                    bool(appearance.get("animations", True)))
    result["overlay-scrolling"] = set_bool(INTERFACE, "gtk-overlay-scrolling",
                                           bool(appearance.get("overlay_scrolling", True)))
    result["primary-paste"] = set_bool(INTERFACE, "gtk-enable-primary-paste",
                                       bool(appearance.get("primary_paste", True)))
    if appearance.get("button_layout"):
        result["button-layout"] = set_string(WM, "button-layout", appearance["button_layout"])
    return result


def restore_theme() -> dict:
    _remove_managed_import(constants.GTK3_CSS)
    _remove_managed_import(constants.GTK4_CSS)
    restore_terminal()
    restored = restore_desktop_backup()
    with contextlib.suppress(OSError):
        constants.THEME_STATE.unlink()
    for slot in THEME_SLOTS + constants.LEGACY_THEME_SLOTS:
        for directory in (constants.THEMES_DIR / slot,
                          constants.DATA_DIR / "themes" / slot):
            with contextlib.suppress(OSError):
                shutil.rmtree(directory)
    return {"desktop_keys": restored}


def load_applied_theme() -> dict | None:
    state = _clean_theme_state()
    if state.get("applied") and isinstance(state.get("theme"), dict):
        return state["theme"]
    return None


def apply_theme_from_config(config, *, preset_id: str | None = None, variant: str | None = None):
    appearance = config.get("appearance", {})
    theme = themes.resolve_theme(
        preset_id or appearance.get("theme", "midnight-aurora"),
        mode=variant or appearance.get("mode", "auto"),
        schedule=appearance.get("dark_schedule"),
        wallpaper_path=themes.wallpaper_path_from_state(),
        overrides=appearance,
    )
    return theme, apply_theme(config, theme)


# --- terminal themes --------------------------------------------------------------

def _terminal_include(target: str) -> tuple[Path, Path, str, str, str] | None:
    if target == "kitty":
        theme_path = constants.KITTY_THEME
        config_path = constants.KITTY_CONF
        body = "include 1337-theme.conf"
        return theme_path, config_path, constants.HASH_MARKER_BEGIN, constants.HASH_MARKER_END, body
    if target == "foot":
        theme_path = constants.FOOT_THEME
        config_path = constants.FOOT_CONF
        body = f"include={theme_path}"
        return theme_path, config_path, constants.HASH_MARKER_BEGIN, constants.HASH_MARKER_END, body
    if target == "ghostty":
        theme_path = constants.GHOSTTY_THEME
        config_path = constants.GHOSTTY_CONF
        body = f"config-file = {theme_path}"
        return theme_path, config_path, constants.HASH_MARKER_BEGIN, constants.HASH_MARKER_END, body
    if target == "alacritty":
        return constants.ALACRITTY_THEME, constants.ALACRITTY_CONF, "", "", ""
    if target == "wezterm":
        return constants.CONFIG_HOME / "wezterm" / "1337-theme.lua", constants.CONFIG_HOME / "wezterm" / "wezterm.lua", "", "", ""
    return None


def terminal_available(target: str) -> bool:
    if target in ("kitty", "foot", "ghostty", "wezterm", "alacritty"):
        if which(target):
            return True
        include = _terminal_include(target)
        return bool(include and (include[0].parent.exists() or include[1].exists()))
    return False


def detected_terminals() -> list[str]:
    return [name for name in constants.TERMINALS if name != "auto" and terminal_available(name)]


def _choose_terminal(preference: str) -> str | None:
    if preference and preference != "auto":
        return preference if terminal_available(preference) else None
    current = os.environ.get("TERM_PROGRAM", "").lower()
    for name in ("kitty", "ghostty", "wezterm", "foot", "alacritty"):
        if name in current and terminal_available(name):
            return name
    for name in detected_terminals():
        return name
    return None


def apply_terminal(theme: dict, preference: str = "auto") -> str:
    target = _choose_terminal(preference)
    if not target:
        return "no supported terminal found"
    generated = themes.terminal_theme(theme, target)
    if not generated:
        return f"{target}: theme generation unavailable"
    suffix, content = generated
    include = _terminal_include(target)
    if not include:
        return f"{target}: unsupported"
    theme_path, config_path, begin, end, body = include
    if target == "alacritty":
        atomic_write_text(theme_path, content, mode=0o600)
        return f"alacritty: theme written to {theme_path}; add this file to your config"
    if target == "wezterm":
        atomic_write_text(theme_path, content, mode=0o600)
        return f"wezterm: theme written to {theme_path}; load it from wezterm.lua"
    atomic_write_text(theme_path, content, mode=0o600)
    for legacy in (constants.LEGACY_KITTY_THEME, constants.LEGACY_FOOT_THEME,
                   constants.LEGACY_GHOSTTY_THEME, constants.LEGACY_ALACRITTY_THEME,
                   constants.LEGACY_WEZTERM_THEME):
        with contextlib.suppress(OSError):
            legacy.unlink()
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    original = strip_marked_block(read_text(config_path), "# hamiid-studio:begin",
                                  "# hamiid-studio:end")
    updated = strip_marked_block(original, begin, end).rstrip()
    updated = updated + f"\n\n{begin}\n{body}\n{end}\n" if updated else f"{begin}\n{body}\n{end}\n"
    atomic_write_text(config_path, updated, mode=0o600)
    return f"{target}: {theme_path.name}"


def restore_terminal() -> None:
    for path, begin, end in (
        (constants.KITTY_CONF, constants.HASH_MARKER_BEGIN, constants.HASH_MARKER_END),
        (constants.FOOT_CONF, constants.HASH_MARKER_BEGIN, constants.HASH_MARKER_END),
        (constants.GHOSTTY_CONF, constants.HASH_MARKER_BEGIN, constants.HASH_MARKER_END),
    ):
        if path.exists():
            original = read_text(path)
            updated = strip_marked_block(original, "# hamiid-studio:begin", "# hamiid-studio:end")
            updated = strip_marked_block(updated, begin, end)
            if updated != original:
                atomic_write_text(path, updated, mode=0o600)
    for path in (constants.KITTY_THEME, constants.FOOT_THEME, constants.GHOSTTY_THEME,
                 constants.ALACRITTY_THEME, constants.CONFIG_HOME / "wezterm" / "1337-theme.lua",
                 constants.LEGACY_KITTY_THEME, constants.LEGACY_FOOT_THEME,
                 constants.LEGACY_GHOSTTY_THEME, constants.LEGACY_ALACRITTY_THEME,
                 constants.LEGACY_WEZTERM_THEME):
        with contextlib.suppress(OSError):
            path.unlink()


# --- icons, cursors, fonts --------------------------------------------------------

def _theme_dirs() -> list[Path]:
    return [
        constants.HOME / ".local/share/icons",
        constants.HOME / ".icons",
        Path("/usr/share/icons"),
        Path("/usr/local/share/icons"),
    ]


def list_icon_themes() -> list[str]:
    found = set()
    for root in _theme_dirs():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and (child / "index.theme").exists():
                found.add(child.name)
    return sorted(found, key=str.casefold)


def list_cursor_themes() -> list[str]:
    found = set()
    for root in _theme_dirs():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir() and (child / "cursors").is_dir():
                found.add(child.name)
    return sorted(found, key=str.casefold)


def list_font_families() -> list[str]:
    global _FONTS_CACHE
    now = time.monotonic()
    if _FONTS_CACHE[0] > now and _FONTS_CACHE[1]:
        return _FONTS_CACHE[1]
    result = run(["fc-list", ":", "family"], timeout=8)
    families = set()
    for line in result.stdout.splitlines():
        first = line.split(",")[0].strip()
        if first and not first.startswith("."):
            families.add(first)
    for fallback in ("Adwaita Sans", "Adwaita Mono", "Cantarell", "DejaVu Sans", "Fira Code"):
        families.add(fallback)
    values = sorted(families, key=str.casefold)
    _FONTS_CACHE = (now + 60, values)
    return values


def install_font_files(paths: list[str | Path]) -> dict:
    copied = []
    errors = []
    constants.FONT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    for source in paths:
        source = Path(source)
        if source.suffix.lower() not in (".ttf", ".otf", ".ttc", ".woff", ".woff2"):
            errors.append(f"{source.name}: unsupported")
            continue
        try:
            destination = constants.FONT_DIR / source.name
            shutil.copy2(source, destination)
            copied.append(destination.name)
        except OSError as error:
            errors.append(f"{source.name}: {error}")
    if copied:
        run(["fc-cache", "-f", str(constants.FONT_DIR)], timeout=60)
        global _FONTS_CACHE
        _FONTS_CACHE = (0.0, [])
    return {"copied": copied, "errors": errors}


# --- monitors ---------------------------------------------------------------------

def monitors() -> list[dict]:
    if which("hyprctl"):
        result = run(["hyprctl", "monitors", "-j"], timeout=5)
        try:
            raw = json.loads(result.stdout)
            values = []
            for item in raw:
                values.append({
                    "name": str(item.get("name", "monitor")),
                    "width": int(item.get("width", 1920)),
                    "height": int(item.get("height", 1080)),
                    "scale": float(item.get("scale", 1.0) or 1.0),
                    "x": int(item.get("x", 0)),
                    "y": int(item.get("y", 0)),
                    "primary": bool(item.get("focused")),
                    "refresh": float(item.get("refreshRate", 60) or 60),
                    "description": str(item.get("description", "")),
                })
            if values:
                return values
        except (ValueError, TypeError, AttributeError):
            pass
    if which("awww"):
        result = run(["awww", "query"], timeout=5)
        values = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            name, rest = line.split(":", 1)
            import re
            match = re.search(r"(\d+)x(\d+)", rest)
            scale_match = re.search(r"scale:\s*([0-9.]+)", rest)
            width, height = (int(match.group(1)), int(match.group(2))) if match else (1920, 1080)
            values.append({
                "name": name.strip(), "width": width, "height": height,
                "scale": float(scale_match.group(1)) if scale_match else 1.0,
                "x": 0, "y": 0, "primary": not values, "refresh": 60, "description": "",
            })
        if values:
            return values
    return [{"name": "all", "width": 1920, "height": 1080, "scale": 1.0,
             "x": 0, "y": 0, "primary": True, "refresh": 60, "description": ""}]


def monitor_names() -> list[str]:
    return [item["name"] for item in monitors()]


def primary_monitor() -> dict:
    for monitor in monitors():
        if monitor.get("primary"):
            return monitor
    return monitors()[0]


def monitor_choices() -> list[tuple[str, str]]:
    choices = [("all", "All monitors")]
    for monitor in monitors():
        label = monitor["name"]
        if monitor.get("description"):
            label += f"  ·  {monitor['width']}×{monitor['height']}"
        choices.append((monitor["name"], label))
    return choices


# --- environment report -----------------------------------------------------------

def environment_report() -> dict:
    report = {
        "session": os.environ.get("XDG_SESSION_TYPE", "unknown"),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown"),
        "wayland": bool(os.environ.get("WAYLAND_DISPLAY")),
        "hyprland": bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")),
        "monitors": monitors(),
        "backends": {},
        "tools": {},
        "gtk": {},
    }
    for name in ("awww", "awww-daemon", "hyprpaper", "swaybg", "dms", "mpvpaper",
                 "mpv", "ffmpeg", "ffprobe", "kitty", "foot", "ghostty", "wezterm",
                 "alacritty", "playerctl", "notify-send", "hyprctl", "gsettings",
                 "fc-list", "fc-cache"):
        report["tools"][name] = which(name) or ""
    report["backends"] = {
        "awww": bool(which("awww")),
        "hyprpaper": bool(which("hyprpaper")),
        "swaybg": bool(which("swaybg")),
        "dms": bool(which("dms")),
        "mpvpaper": bool(which("mpvpaper") or constants.BUNDLED_MPVPAPER.exists()),
        "gnome": "gnome" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower(),
        "layer_shell": has_layer_shell(),
    }
    if Gio is not None:
        for schema_name, key in ((INTERFACE, "gtk-theme"), (INTERFACE, "icon-theme"),
                                 (INTERFACE, "cursor-theme"), (INTERFACE, "font-name"),
                                 (INTERFACE, "color-scheme")):
            report["gtk"][key] = get_value(schema_name, key)
    return report


def has_layer_shell() -> bool:
    from .util import has_layer_shell as probe

    return probe()


def version_string() -> str:
    return f"{constants.APP_NAME} {constants.VERSION}"
