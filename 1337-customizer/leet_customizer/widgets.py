"""Desktop widget catalog, card widgets and shared CSS."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import constants, palette
from .util import human_size, popen, read_json, run

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Pango", "1.0")
    from gi.repository import Gdk, GLib, Gtk, Pango
except Exception:  # pragma: no cover
    Gdk = GLib = Gtk = Pango = None


WIDGET_TYPES: dict[str, dict] = {
    "clock": {
        "name": "Clock", "icon": "alarm-symbolic",
        "description": "Time and date, with optional seconds and a custom format.",
        "default": (0.04, 0.05, 0.22, 0.15),
        "options": {"seconds": False, "24h": True, "show_date": True,
                    "format": "", "date_format": "%A, %d %B"},
    },
    "calendar": {
        "name": "Calendar", "icon": "x-office-calendar-symbolic",
        "description": "A monthly calendar that highlights today.",
        "default": (0.78, 0.05, 0.18, 0.29),
        "options": {"show_week_numbers": False, "show_heading": True},
    },
    "system": {
        "name": "System monitor", "icon": "utilities-system-monitor-symbolic",
        "description": "CPU, RAM and home disk usage at a glance.",
        "default": (0.04, 0.23, 0.23, 0.20),
        "options": {"cpu": True, "ram": True, "disk": True},
    },
    "note": {
        "name": "Sticky note", "icon": "accessories-text-editor-symbolic",
        "description": "A note that survives restarts. Edit it in the studio.",
        "default": (0.78, 0.37, 0.18, 0.24),
        "options": {"text": "Today’s focus:\n• one important thing\n• one kind thing"},
    },
    "media": {
        "name": "Now playing", "icon": "audio-x-generic-symbolic",
        "description": "Track, artist and transport controls for MPRIS players.",
        "default": (0.30, 0.05, 0.25, 0.13),
        "options": {"show_controls": True, "show_artist": True},
    },
    "timer": {
        "name": "Focus timer", "icon": "preferences-system-time-symbolic",
        "description": "A Pomodoro-style countdown with start, pause and reset.",
        "default": (0.31, 0.22, 0.18, 0.14),
        "options": {"minutes": 25, "auto_start": False},
    },
    "launcher": {
        "name": "Quick launcher", "icon": "view-app-grid-symbolic",
        "description": "Buttons for your terminal, browser, files or custom commands.",
        "default": (0.04, 0.48, 0.21, 0.17),
        "options": {"commands": [
            {"label": "Terminal", "command": "kitty"},
            {"label": "Files", "command": "nautilus"},
            {"label": "Browser", "command": "xdg-open https://"},
        ]},
    },
    "weather": {
        "name": "Weather", "icon": "weather-clear-symbolic",
        "description": "Current conditions from Open-Meteo. No account or API key.",
        "default": (0.54, 0.05, 0.18, 0.15),
        "options": {"latitude": 0.0, "longitude": 0.0, "city": "",
                    "units": "celsius"},
    },
    "battery": {
        "name": "Battery", "icon": "battery-good-symbolic",
        "description": "Charge level, state and time remaining.",
        "default": (0.54, 0.23, 0.18, 0.11),
        "options": {"show_state": True},
    },
    "worldclock": {
        "name": "World clock", "icon": "globe-symbolic",
        "description": "Times in up to four IANA time zones.",
        "default": (0.31, 0.38, 0.20, 0.17),
        "options": {"zones": ["UTC", "America/New_York", "Asia/Tokyo"], "24h": True},
    },
    "countdown": {
        "name": "Countdown", "icon": "alarm-symbolic",
        "description": "Days and hours until a date that matters.",
        "default": (0.54, 0.37, 0.18, 0.12),
        "options": {"date": "", "label": "Countdown"},
    },
    "network": {
        "name": "Network", "icon": "network-wireless-symbolic",
        "description": "Local IP and current down/up throughput.",
        "default": (0.31, 0.57, 0.20, 0.12),
        "options": {"interface": "", "show_ip": True},
    },
    "quote": {
        "name": "Quote", "icon": "format-text-italic-symbolic",
        "description": "A line of text that keeps you pointed in the right direction.",
        "default": (0.54, 0.52, 0.22, 0.12),
        "options": {"text": "Make something that makes the day better.", "author": ""},
    },
}


def default_items() -> list[dict]:
    items = []
    for kind, geometry in (
        ("clock", (0.035, 0.045, 0.23, 0.15)),
        ("system", (0.035, 0.225, 0.23, 0.19)),
        ("calendar", (0.785, 0.045, 0.18, 0.30)),
        ("note", (0.785, 0.375, 0.18, 0.23)),
    ):
        metadata = WIDGET_TYPES[kind]
        x, y, width, height = geometry
        items.append({
            "id": f"{kind}-{uuid.uuid4().hex[:6]}",
            "type": kind, "enabled": True,
            "x": x, "y": y, "w": width, "h": height,
            "opacity": 1.0, "scale": 1.0, "interactive": False,
            "options": json.loads(json.dumps(metadata["options"])),
        })
    return items


def item_type(item: dict) -> dict:
    return WIDGET_TYPES.get(item.get("type", ""), WIDGET_TYPES["clock"])


def normalise_item(item: dict) -> dict:
    metadata = item_type(item)
    options = json.loads(json.dumps(metadata["options"]))
    if isinstance(item.get("options"), dict):
        options.update(item["options"])
    x = max(0.0, min(0.94, float(item.get("x", metadata["default"][0]))))
    y = max(0.0, min(0.94, float(item.get("y", metadata["default"][1]))))
    width = max(0.06, min(0.9, float(item.get("w", metadata["default"][2]))))
    height = max(0.05, min(0.9, float(item.get("h", metadata["default"][3]))))
    if x + width > 1:
        width = max(0.06, 1 - x)
    if y + height > 1:
        height = max(0.05, 1 - y)
    theme_name = str(item.get("theme") or "")
    if theme_name not in ("",) + tuple(constants.WIDGET_THEMES):
        theme_name = ""
    accent = palette.normalise_hex(str(item.get("accent") or ""), "") if item.get("accent") else ""
    background = palette.normalise_hex(str(item.get("bg") or ""), "") if item.get("bg") else ""
    foreground = palette.normalise_hex(str(item.get("fg") or ""), "") if item.get("fg") else ""
    align = str(item.get("align") or "start")
    if align not in ("start", "center", "end"):
        align = "start"
    return {
        "id": str(item.get("id") or f"{item.get('type', 'clock')}-{uuid.uuid4().hex[:6]}"),
        "type": item.get("type", "clock"),
        "enabled": bool(item.get("enabled", True)),
        "x": round(x, 4), "y": round(y, 4), "w": round(width, 4), "h": round(height, 4),
        "opacity": max(0.2, min(1.0, float(item.get("opacity", 1.0)))),
        "scale": max(0.65, min(2.0, float(item.get("scale", 1.0)))),
        "interactive": bool(item.get("interactive", False)),
        # Per-widget appearance overrides.  Empty strings / -1 mean "follow
        # the global style".
        "theme": theme_name,
        "accent": accent,
        "bg": background,
        "fg": foreground,
        "radius": max(-1, min(40, int(item.get("radius", -1)))),
        "border_width": max(-1, min(8, int(item.get("border_width", -1)))),
        "padding": max(-1, min(56, int(item.get("padding", -1)))),
        "align": align,
        "monitor": str(item.get("monitor") or ""),
        "shadow": bool(item.get("shadow", True)),
        "options": options,
    }


def normalise_items(items: list | None) -> list[dict]:
    if not isinstance(items, list) or not items:
        return default_items()
    return [normalise_item(item) for item in items if isinstance(item, dict)]


def ensure_default_items(config) -> list[dict]:
    items = normalise_items(config.get("widgets.items", []))
    if not config.get("widgets.items"):
        config.set("widgets.items", items)
    return items


def new_item(kind: str, items: list[dict]) -> dict:
    metadata = WIDGET_TYPES.get(kind, WIDGET_TYPES["clock"])
    x, y, width, height = metadata["default"]
    # Offset new widgets so they do not stack exactly on top of each other.
    for index in range(12):
        offset = 0.018 * index
        candidate = normalise_item({
            "id": f"{kind}-{uuid.uuid4().hex[:6]}", "type": kind,
            "x": min(0.92, x + offset), "y": min(0.92, y + offset),
            "w": width, "h": height, "options": metadata["options"],
        })
        if not any(abs(candidate["x"] - item["x"]) < 0.02 and abs(candidate["y"] - item["y"]) < 0.02
                   for item in items):
            return candidate
    return normalise_item({"id": f"{kind}-{uuid.uuid4().hex[:6]}", "type": kind})


LAYOUT_PRESETS: dict[str, tuple[str, list[dict]]] = {
    "minimal": ("Minimal", [
        {"type": "clock", "x": 0.04, "y": 0.05, "w": 0.24, "h": 0.17},
        {"type": "calendar", "x": 0.74, "y": 0.05, "w": 0.22, "h": 0.34},
        {"type": "note", "x": 0.04, "y": 0.76, "w": 0.25, "h": 0.18},
    ]),
    "dashboard": ("Dashboard", [
        {"type": "clock", "x": 0.035, "y": 0.045, "w": 0.23, "h": 0.15},
        {"type": "system", "x": 0.035, "y": 0.225, "w": 0.23, "h": 0.19},
        {"type": "media", "x": 0.30, "y": 0.045, "w": 0.26, "h": 0.15},
        {"type": "weather", "x": 0.59, "y": 0.045, "w": 0.19, "h": 0.17},
        {"type": "battery", "x": 0.59, "y": 0.24, "w": 0.19, "h": 0.12},
        {"type": "calendar", "x": 0.79, "y": 0.045, "w": 0.18, "h": 0.30},
        {"type": "note", "x": 0.79, "y": 0.38, "w": 0.18, "h": 0.23},
    ]),
    "focus": ("Focus", [
        {"type": "clock", "x": 0.04, "y": 0.05, "w": 0.27, "h": 0.17},
        {"type": "timer", "x": 0.04, "y": 0.26, "w": 0.22, "h": 0.17},
        {"type": "note", "x": 0.04, "y": 0.48, "w": 0.27, "h": 0.25},
        {"type": "quote", "x": 0.69, "y": 0.05, "w": 0.27, "h": 0.15},
        {"type": "launcher", "x": 0.69, "y": 0.25, "w": 0.24, "h": 0.18},
        {"type": "calendar", "x": 0.69, "y": 0.48, "w": 0.22, "h": 0.32},
    ]),
    "ambient": ("Ambient", [
        {"type": "clock", "x": 0.06, "y": 0.07, "w": 0.30, "h": 0.19},
        {"type": "worldclock", "x": 0.70, "y": 0.07, "w": 0.24, "h": 0.20},
        {"type": "quote", "x": 0.32, "y": 0.72, "w": 0.36, "h": 0.16},
    ]),
}


def layout_preset(name: str) -> list[dict]:
    _label, definitions = LAYOUT_PRESETS.get(name, LAYOUT_PRESETS["minimal"])
    items: list[dict] = []
    for definition in definitions:
        metadata = WIDGET_TYPES[definition["type"]]
        item = normalise_item({
            "id": f"{definition['type']}-{uuid.uuid4().hex[:6]}",
            "type": definition["type"],
            "x": definition["x"], "y": definition["y"],
            "w": definition["w"], "h": definition["h"],
            "options": json.loads(json.dumps(metadata["options"])),
        })
        items.append(item)
    return items


def widget_theme_colors(config=None, theme=None) -> dict:
    if theme and isinstance(theme.get("colors"), dict):
        return theme["colors"]
    if config is not None:
        try:
            from . import themes
            appearance = config.get("appearance", {})
            resolved = themes.resolve_theme(
                appearance.get("theme", "midnight-aurora"),
                mode=appearance.get("mode", "dark"),
                schedule=appearance.get("dark_schedule"),
                wallpaper_path=themes.wallpaper_path_from_state(),
                overrides=appearance,
            )
            return resolved["colors"]
        except Exception:
            pass
    return palette.derive_tokens("#0b0d17", "#151829", "#7aa2ff", mode="dark")


def _effective_widget_colors(theme_name: str, colors: dict, accent: str) -> tuple[dict, str]:
    if theme_name == "terminal":
        colors = palette.derive_tokens("#030803", "#071208", "#45ff76", mode="dark")
        accent = "#45ff76"
    elif theme_name == "paper":
        colors = palette.derive_tokens("#f3eee3", "#fffaf0", "#9b5b2d", mode="light")
        accent = "#9b5b2d"
    return colors, accent


def _card_background_style(theme_name: str, colors: dict, alpha: float, accent: str) -> str:
    bg = colors["surface"]
    border = colors["border"]
    if theme_name == "outline":
        return (f"background-color: rgba({','.join(str(c) for c in palette.hex_to_rgb(colors['bg']))},{alpha:.2f}); "
                f"border: 1.5px solid {accent};")
    if theme_name == "neon":
        return (f"background-color: rgba(5,8,15,{max(0.7, alpha):.2f}); border: 1.5px solid {accent}; "
                f"box-shadow: 0 0 18px {palette.with_alpha(accent, 0.34)};")
    if theme_name == "pixel":
        return (f"background-color: rgba(10,10,16,{max(0.82, alpha):.2f}); border: 2px solid {accent}; "
                f"box-shadow: 5px 5px 0 {colors['surface3']};")
    if theme_name == "terminal":
        return (f"background-color: rgba(3,8,3,{max(0.82, alpha):.2f}); border: 1px solid {accent}; "
                f"box-shadow: 0 0 14px {palette.with_alpha(accent, 0.22)};")
    if theme_name == "paper":
        return ("background-color: rgba(255,250,240,0.94); border: 1px solid #3b2b20; "
                "box-shadow: 4px 4px 0 rgba(59,43,32,0.35);")
    if theme_name == "minimal":
        return (f"background-color: rgba({','.join(str(c) for c in palette.hex_to_rgb(colors['bg']))},{max(0.0, alpha - 0.18):.2f}); "
                f"border: 1px solid {palette.with_alpha(border, 0.45)};")
    if theme_name == "solid":
        return f"background-color: rgba({','.join(str(c) for c in palette.hex_to_rgb(bg))},{alpha:.2f}); border: 1px solid {border};"
    return (f"background-color: rgba({','.join(str(c) for c in palette.hex_to_rgb(bg))},{max(0.55, alpha - 0.05):.2f}); "
            f"border: 1px solid {palette.with_alpha(colors['text'], 0.15)}; box-shadow: 0 12px 30px rgba(0,0,0,0.22);")


def widget_css(config=None, theme: dict | None = None) -> str:
    colors = widget_theme_colors(config, theme)
    widgets = config.get("widgets", {}) if config else {}
    theme_name = widgets.get("theme", "glass")
    opacity = float(widgets.get("opacity", 0.88))
    accent = palette.normalise_hex(widgets.get("accent") or colors["accent"])
    accent = palette.visible_accent(accent, colors["surface"])
    font = widgets.get("font_family") or ""
    scale = float(widgets.get("font_scale", 1.0) or 1.0)
    radius = 18 if theme_name in ("glass", "rounded") else (4 if theme_name == "pixel" else 14)
    colors, accent = _effective_widget_colors(theme_name, colors, accent)
    bg = colors["surface"]
    text = colors["text"]
    muted = colors["text_dim"]
    border = colors["border"]
    alpha = max(0.45, min(1.0, opacity))
    font_rule = f'font-family: "{font}";' if font else ""
    base = _card_background_style(theme_name, colors, alpha, accent)

    return f"""
window, window.background, .background, window.hw-window, .hw-window {{
  background-color: rgba(0,0,0,0);
  background-image: none;
  box-shadow: none;
}}
.hw-card {{
  {base}
  border-radius: {radius}px;
  padding: {int(14 * scale)}px;
  color: {text};
  {font_rule}
}}
.hw-card.hw-paper, .hw-card.hw-paper label {{ color: #241a13; }}
.hw-card.hw-paper .hw-muted {{ color: #6b5848; }}
.hw-card.hw-terminal, .hw-card.hw-terminal label {{ color: #7dffa0; }}
.hw-card.hw-neon, .hw-card.hw-neon label {{ color: #eefcff; }}
.hw-card.hw-edit {{
  border: 2px dashed {accent};
  box-shadow: 0 0 0 1px {palette.with_alpha(accent, 0.20)}, 0 14px 34px rgba(0,0,0,0.34);
}}
.hw-title {{
  font-size: {int(12 * scale)}pt;
  font-weight: 700;
  color: {text};
}}
.hw-value {{
  font-size: {int(25 * scale)}pt;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: {text};
}}
.hw-time {{
  font-size: {int(29 * scale)}pt;
  font-weight: 800;
  letter-spacing: -1px;
  color: {text};
}}
.hw-muted {{
  font-size: {int(9.5 * scale)}pt;
  color: {muted};
}}
.hw-accent {{ color: {accent}; }}
.hw-pill {{
  background-color: {palette.with_alpha(accent, 0.17)};
  color: {text};
  border-radius: 999px;
  padding: 3px 9px;
  font-size: {int(8.5 * scale)}pt;
}}
.hw-bar {{
  min-height: 5px;
  border-radius: 999px;
  background-color: {palette.with_alpha(text, 0.10)};
}}
.hw-bar > trough {{ min-height: 5px; border-radius: 999px; background-color: {palette.with_alpha(text, 0.10)}; }}
.hw-bar > progress {{ min-height: 5px; border-radius: 999px; background-color: {accent}; }}
.hw-button {{
  background-color: {palette.with_alpha(accent, 0.16)};
  color: {text};
  border: 1px solid {palette.with_alpha(accent, 0.38)};
  border-radius: 8px;
  padding: 3px 8px;
  font-size: {int(9 * scale)}pt;
}}
.hw-button:hover {{ background-color: {palette.with_alpha(accent, 0.30)}; }}
.hw-note {{ font-size: {int(11 * scale)}pt; }}
.hw-note textview, .hw-note text {{ background: transparent; color: {text}; }}
.hw-sep {{ background-color: {palette.with_alpha(text, 0.14)}; min-height: 1px; }}
.hw-album {{
  border-radius: {max(4, radius - 7)}px;
  background: linear-gradient(135deg, {palette.with_alpha(accent, 0.55)}, {palette.with_alpha(colors['bg'], 0.9)});
}}
.hw-toolbar {{
  background-color: rgba({','.join(str(c) for c in palette.hex_to_rgb(colors['surface2']))},0.96);
  color: {text};
  border: 1px solid {accent};
  border-radius: 12px;
  padding: 8px 10px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.32);
}}
.hw-toolbar label {{ color: {text}; font-weight: 700; }}
"""


def style_class(item: dict) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", str(item.get("id", "widget")))
    return f"hw-style-{safe}"


def item_style_css(item: dict, config=None, theme: dict | None = None) -> str:
    """Per-widget overrides scoped to a unique class.

    The desktop host adds this CSS provider at a higher priority than the
    shared widget stylesheet, so one card can have its own colour, radius,
    padding or typography without affecting the rest.
    """
    global_colors = widget_theme_colors(config, theme)
    widgets = config.get("widgets", {}) if config else {}
    global_theme = widgets.get("theme", "glass")
    theme_name = item.get("theme") or global_theme
    global_accent = palette.normalise_hex(widgets.get("accent") or global_colors["accent"])
    accent = palette.normalise_hex(item.get("accent") or global_accent)
    colors, accent = _effective_widget_colors(theme_name, global_colors, accent)
    accent = palette.visible_accent(accent, colors["surface"])
    global_opacity = float(widgets.get("opacity", 0.88) or 0.88)
    alpha = max(0.12, min(1.0, global_opacity * float(item.get("opacity", 1.0) or 1.0)))
    global_scale = float(widgets.get("font_scale", 1.0) or 1.0)
    scale = max(0.5, min(2.5, global_scale * float(item.get("scale", 1.0) or 1.0)))
    radius = int(item.get("radius", -1))
    if radius < 0:
        radius = 18 if theme_name in ("glass", "rounded") else (4 if theme_name == "pixel" else 14)
    border_width = int(item.get("border_width", -1))
    padding = int(item.get("padding", -1))
    if padding < 0:
        padding = int(14 * scale)
    text = palette.normalise_hex(item.get("fg") or colors["text"])
    background = palette.normalise_hex(item.get("bg") or "", "")
    base = _card_background_style(theme_name, colors, alpha, accent)
    declarations = [base, f"border-radius: {radius}px;", f"padding: {padding}px;", f"color: {text};"]
    if background:
        declarations.append(
            f"background-color: rgba({','.join(str(c) for c in palette.hex_to_rgb(background))},{alpha:.2f});"
        )
    if border_width >= 0:
        declarations.append(f"border-width: {border_width}px;")
    if not bool(item.get("shadow", True)):
        declarations.append("box-shadow: none;")
    selector = style_class(item)
    css = [f".{selector} {{ {' '.join(declarations)} }}"]
    css.append(f".{selector} label, .{selector} .hw-title, .{selector} .hw-time, .{selector} .hw-value {{ color: {text}; }}")
    css.append(f".{selector} .hw-muted {{ color: {palette.mix(text, colors['bg'], 0.45)}; }}")
    css.append(f".{selector} .hw-time {{ font-size: {int(29 * scale)}pt; }}")
    css.append(f".{selector} .hw-value {{ font-size: {int(25 * scale)}pt; }}")
    css.append(f".{selector} .hw-title {{ font-size: {int(12 * scale)}pt; }}")
    css.append(f".{selector} .hw-muted {{ font-size: {int(9.5 * scale)}pt; }}")
    css.append(f".{selector} .hw-note {{ font-size: {int(11 * scale)}pt; }}")
    css.append(f".{selector} .hw-button {{ font-size: {int(9 * scale)}pt; color: {text}; "
               f"background-color: {palette.with_alpha(accent, 0.16)}; border: 1px solid {palette.with_alpha(accent, 0.38)}; }}")
    css.append(f".{selector} .hw-pill {{ font-size: {int(8.5 * scale)}pt; background-color: {palette.with_alpha(accent, 0.17)}; color: {text}; }}")
    css.append(f".{selector} .hw-accent {{ color: {accent}; }}")
    css.append(f".{selector} .hw-bar > progress {{ background-color: {accent}; }}")
    css.append(f".{selector} .hw-calendar:selected {{ background-color: {accent}; }}")
    # Editing/selection outlines must survive the per-item provider's higher
    # priority, otherwise the chosen card is impossible to see.
    css.append(f".{selector}.hw-edit {{ border: 2px dashed {accent}; "
               f"box-shadow: 0 0 0 1px {palette.with_alpha(accent, 0.20)}, 0 14px 34px rgba(0,0,0,0.34); }}")
    css.append(f".{selector}.hw-edit.hw-selected {{ border: 3px solid {accent}; "
               f"box-shadow: 0 0 0 3px {palette.with_alpha(accent, 0.26)}, 0 18px 38px rgba(0,0,0,0.42); }}")
    return "\n".join(css)


def format_clock(now: dt.datetime, options: dict) -> tuple[str, str]:
    custom = str(options.get("format") or "")
    if custom:
        try:
            value = now.strftime(custom)
        except Exception:
            value = now.strftime("%H:%M")
    elif options.get("24h", True):
        value = now.strftime("%H:%M:%S" if options.get("seconds") else "%H:%M")
    else:
        value = now.strftime("%I:%M:%S %p" if options.get("seconds") else "%I:%M %p")
    date_format = str(options.get("date_format") or "%A, %d %B")
    try:
        date = now.strftime(date_format)
    except Exception:
        date = now.strftime("%A, %d %B")
    return value, date


def _read_cpu() -> tuple[int, int] | None:
    try:
        fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total
    except (OSError, ValueError, IndexError):
        return None


def _cpu_percent(previous: tuple[int, int] | None) -> tuple[float | None, tuple[int, int] | None]:
    current = _read_cpu()
    if not current:
        return None, previous
    if not previous:
        return None, current
    idle_delta = current[0] - previous[0]
    total_delta = current[1] - previous[1]
    if total_delta <= 0:
        return 0.0, current
    return max(0.0, min(100.0, 100.0 * (1 - idle_delta / total_delta))), current


def _ram() -> tuple[float, int, int]:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, rest = line.split(":", 1)
            values[key] = int(rest.strip().split()[0])
        total = values.get("MemTotal", 1)
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = max(0, total - available)
        return used / total * 100, used * 1024, total * 1024
    except (OSError, ValueError):
        return 0.0, 0, 0


def _disk() -> tuple[float, int, int]:
    try:
        usage = os.statvfs(str(constants.HOME))
        total = usage.f_blocks * usage.f_frsize
        free = usage.f_bavail * usage.f_frsize
        used = total - free
        return used / total * 100 if total else 0.0, used, total
    except OSError:
        return 0.0, 0, 0


class WidgetCard(Gtk.Box if Gtk else object):
    """A live widget card used by the desktop host and the studio preview."""

    def __init__(self, item: dict, config=None, *, edit: bool = False,
                 theme: dict | None = None, on_note_changed: Callable[[str], None] | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.item = normalise_item(item)
        self.config = config
        self.edit = edit
        self.on_note_changed = on_note_changed
        self._theme = theme
        self._last: dict[str, float] = {}
        self._cpu_prev = None
        self._net_prev = None
        self._weather = None
        self._weather_loading = False
        self._note_buffer = None
        self._pulse = 0
        global_theme = config.get("widgets.theme", "glass") if config else "glass"
        theme_name = self.item.get("theme") or global_theme
        self._align = {"start": 0.0, "center": 0.5, "end": 1.0}.get(
            self.item.get("align", "start"), 0.0
        )
        self.add_css_class("hw-card")
        self.add_css_class(f"hw-{theme_name}")
        self.add_css_class(style_class(self.item))
        if edit:
            self.add_css_class("hw-edit")
        self.set_hexpand(False)
        self.set_vexpand(False)
        display = Gdk.Display.get_default()
        if display is not None:
            provider = Gtk.CssProvider()
            provider.load_from_data(item_style_css(self.item, config, theme).encode(), -1)
            Gtk.StyleContext.add_provider_for_display(display, provider, 850)
        self._build()
        self.tick(force=True)

    def _label(self, text: str = "", css: str = "") -> "Gtk.Label":
        label = Gtk.Label(label=text, xalign=self._align)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        if css:
            label.add_css_class(css)
        return label

    def _build(self) -> None:
        kind = self.item["type"]
        options = self.item.get("options", {})
        for child in list(self):
            self.remove(child)
        if kind == "clock":
            self.time_label = self._label("", "hw-time")
            self.date_label = self._label("", "hw-muted")
            self.append(self.time_label)
            if options.get("show_date", True):
                self.append(self.date_label)
        elif kind == "calendar":
            self.append(self._label("Calendar", "hw-muted"))
            calendar = Gtk.Calendar()
            calendar.set_hexpand(True)
            calendar.set_vexpand(True)
            calendar.add_css_class("hw-calendar")
            with __import__("contextlib").suppress(Exception):
                calendar.set_show_week_numbers(bool(options.get("show_week_numbers", False)))
            with __import__("contextlib").suppress(Exception):
                calendar.set_show_heading(bool(options.get("show_heading", True)))
            self.append(calendar)
        elif kind == "system":
            self.append(self._label("System", "hw-muted"))
            self.cpu_bar, self.cpu_label = self._metric("CPU", options.get("cpu", True))
            self.ram_bar, self.ram_label = self._metric("RAM", options.get("ram", True))
            self.disk_bar, self.disk_label = self._metric("Disk", options.get("disk", True))
        elif kind == "note":
            if self.edit:
                view = Gtk.TextView()
                view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
                view.get_buffer().set_text(str(options.get("text", "")))
                view.add_css_class("hw-note")
                view.set_vexpand(True)
                self._note_buffer = view.get_buffer()
                self._note_buffer.connect("changed", self._note_changed)
                self.append(view)
            else:
                self.note_label = self._label(str(options.get("text", "")), "hw-note")
                self.append(self.note_label)
        elif kind == "media":
            self.media_icon = self._label("♫", "hw-title")
            self.media_title = self._label("No media", "hw-title")
            self.media_artist = self._label("Start a player to see it here", "hw-muted")
            self.append(self.media_icon)
            self.append(self.media_title)
            if options.get("show_artist", True):
                self.append(self.media_artist)
            if options.get("show_controls", True):
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
                for symbol, command in (("⏮", "previous"), ("⏯", "play-pause"), ("⏭", "next")):
                    button = Gtk.Button(label=symbol)
                    button.add_css_class("hw-button")
                    button.set_tooltip_text(command.replace("-", " ").title())
                    button.connect("clicked", lambda _b, cmd=command: self._media_command(cmd))
                    row.append(button)
                self.append(row)
        elif kind == "timer":
            self.timer_label = self._label("25:00", "hw-value")
            self.append(self.timer_label)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.timer_toggle = Gtk.Button(label="Start")
            self.timer_toggle.add_css_class("hw-button")
            self.timer_toggle.connect("clicked", self._toggle_timer)
            reset = Gtk.Button(label="Reset")
            reset.add_css_class("hw-button")
            reset.connect("clicked", self._reset_timer)
            row.append(self.timer_toggle)
            row.append(reset)
            self.append(row)
            self._timer_remaining = max(1, int(options.get("minutes", 25))) * 60
            self._timer_running = False
            self._timer_deadline = 0.0
        elif kind == "launcher":
            self.append(self._label("Quick launch", "hw-muted"))
            commands = options.get("commands") or []
            if isinstance(commands, str):
                commands = [{"label": "Open", "command": commands}]
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            row.set_homogeneous(True)
            for entry in commands[:4]:
                if not isinstance(entry, dict):
                    continue
                button = Gtk.Button(label=str(entry.get("label", "Open"))[:14])
                button.add_css_class("hw-button")
                button.set_tooltip_text(str(entry.get("command", "")))
                button.connect("clicked", self._launch, str(entry.get("command", "")))
                row.append(button)
            self.append(row)
        elif kind == "weather":
            self.weather_icon = self._label("◒", "hw-value")
            self.weather_temp = self._label("—", "hw-value")
            self.weather_city = self._label(str(options.get("city") or "Weather"), "hw-muted")
            self.weather_detail = self._label("Add a location in the studio", "hw-muted")
            self.append(self.weather_icon)
            self.append(self.weather_temp)
            self.append(self.weather_city)
            self.append(self.weather_detail)
        elif kind == "battery":
            self.battery_label = self._label("—", "hw-value")
            self.battery_state = self._label("", "hw-muted")
            self.battery_bar = Gtk.ProgressBar()
            self.battery_bar.add_css_class("hw-bar")
            self.append(self._label("Battery", "hw-muted"))
            self.append(self.battery_label)
            self.append(self.battery_bar)
            if options.get("show_state", True):
                self.append(self.battery_state)
        elif kind == "worldclock":
            self.append(self._label("World clock", "hw-muted"))
            self.zones_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            self.append(self.zones_box)
            self.zone_labels = []
            zones = options.get("zones") or ["UTC"]
            if isinstance(zones, str):
                zones = [zones]
            for zone in zones[:4]:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                label = self._label(str(zone), "hw-muted")
                value = self._label("", "hw-title")
                value.set_xalign(1.0)
                value.set_hexpand(True)
                row.append(label)
                row.append(value)
                self.zone_labels.append((label, value, str(zone)))
                self.zones_box.append(row)
        elif kind == "countdown":
            self.countdown_label = self._label(str(options.get("label") or "Countdown"), "hw-muted")
            self.countdown_value = self._label("—", "hw-value")
            self.append(self.countdown_label)
            self.append(self.countdown_value)
        elif kind == "network":
            self.net_label = self._label("Network", "hw-muted")
            self.net_ip = self._label("—", "hw-title")
            self.net_speed = self._label("", "hw-muted")
            self.append(self.net_label)
            self.append(self.net_ip)
            self.append(self.net_speed)
        elif kind == "quote":
            self.append(self._label("“", "hw-value"))
            self.append(self._label(str(options.get("text", "")), "hw-note"))
            if options.get("author"):
                self.append(self._label(f"— {options['author']}", "hw-muted"))
        else:
            self.append(self._label(kind.title(), "hw-title"))

    def _metric(self, name: str, enabled: bool):
        label = self._label("", "hw-muted")
        bar = Gtk.ProgressBar()
        bar.add_css_class("hw-bar")
        if not enabled:
            bar.set_visible(False)
            label.set_visible(False)
        else:
            self.append(label)
            self.append(bar)
        return bar, label

    def _note_changed(self, buffer) -> None:
        if not self.on_note_changed:
            return
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.on_note_changed(text)

    def _media_command(self, command: str) -> None:
        executable = "playerctl"
        popen([executable, command])

    def _launch(self, _button, command: str) -> None:
        if not command:
            return
        popen(["sh", "-c", command])

    def _toggle_timer(self, _button=None) -> None:
        if self._timer_running:
            self._timer_remaining = max(0, int(self._timer_deadline - time.monotonic()))
            self._timer_running = False
            self.timer_toggle.set_label("Start")
        else:
            self._timer_deadline = time.monotonic() + self._timer_remaining
            self._timer_running = True
            self.timer_toggle.set_label("Pause")

    def _reset_timer(self, _button=None) -> None:
        self._timer_remaining = max(1, int(self.item.get("options", {}).get("minutes", 25))) * 60
        self._timer_running = False
        self._timer_deadline = 0.0
        if self.timer_toggle:
            self.timer_toggle.set_label("Start")
        self._update_timer()

    def _update_timer(self) -> None:
        remaining = max(0, int((self._timer_deadline - time.monotonic()) if self._timer_running else self._timer_remaining))
        self.timer_label.set_text(f"{remaining // 60:02d}:{remaining % 60:02d}")
        if self._timer_running and remaining <= 0:
            self._timer_running = False
            self.timer_toggle.set_label("Start")
            from .util import notify
            notify("Focus timer", "Time is up. Take a breath.")

    def _update_weather(self, now: float) -> None:
        options = self.item.get("options", {})
        lat = float(options.get("latitude") or 0)
        lon = float(options.get("longitude") or 0)
        if not (lat or lon) or self._weather_loading:
            return
        self._weather_loading = True
        units = str(options.get("units", "celsius"))

        def worker():
            query = urllib.parse.urlencode({
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
                "temperature_unit": "fahrenheit" if units == "fahrenheit" else "celsius",
                "wind_speed_unit": "mph" if units == "fahrenheit" else "kmh",
            })
            url = "https://api.open-meteo.com/v1/forecast?" + query
            try:
                with urllib.request.urlopen(url, timeout=8) as response:
                    payload = json.loads(response.read().decode())
                current = payload.get("current", {})
                temperature = current.get("temperature_2m")
                code = int(current.get("weather_code", -1))
                wind = current.get("wind_speed_10m")
                result = {"temperature": temperature, "code": code, "wind": wind}
            except Exception:
                result = None
            GLib.idle_add(self._weather_done, result)

        threading.Thread(target=worker, daemon=True).start()

    def _weather_done(self, result) -> bool:
        self._weather_loading = False
        if not result:
            self.weather_detail.set_text("Weather unavailable")
            return False
        self._weather = result
        self.weather_temp.set_text(f"{round(result['temperature'])}°")
        icon, label = weather_label(result.get("code", -1))
        self.weather_icon.set_text(icon)
        self.weather_detail.set_text(f"{label} · wind {round(result.get('wind') or 0)}")
        return False

    def _weather_due(self, now: float) -> bool:
        return now - self._last.get("weather", 0) > 600

    def tick(self, force: bool = False) -> None:
        now = time.monotonic()
        kind = self.item["type"]
        options = self.item.get("options", {})
        if kind == "clock":
            moment = dt.datetime.now()
            value, date = format_clock(moment, options)
            self.time_label.set_text(value)
            self.date_label.set_text(date if options.get("show_date", True) else "")
        elif kind == "system":
            if force or now - self._last.get("system", 0) >= 2:
                # On the first sample only a baseline exists; schedule the next
                # tick immediately so the card never sits on "—" for seconds.
                self._last["system"] = 0 if force else now
                cpu, self._cpu_prev = _cpu_percent(self._cpu_prev)
                ram, ram_used, ram_total = _ram()
                disk, disk_used, disk_total = _disk()
                if options.get("cpu", True):
                    self.cpu_bar.set_fraction((cpu or 0) / 100)
                    self.cpu_label.set_text(f"CPU  {cpu:.0f}%" if cpu is not None else "CPU  —")
                if options.get("ram", True):
                    self.ram_bar.set_fraction(ram / 100)
                    self.ram_label.set_text(f"RAM  {human_size(ram_used)} / {human_size(ram_total)}")
                if options.get("disk", True):
                    self.disk_bar.set_fraction(disk / 100)
                    self.disk_label.set_text(f"Disk  {human_size(disk_used)} / {human_size(disk_total)}")
        elif kind == "media":
            if force or now - self._last.get("media", 0) >= 2:
                self._last["media"] = now
                result = run(["playerctl", "metadata", "--format",
                              "{{status}}|{{title}}|{{artist}}|{{mpris:artUrl}}"], timeout=2)
                text = (result.stdout or "").strip()
                if result.returncode == 0 and text:
                    parts = text.split("|")
                    status = parts[0] if parts else ""
                    title = parts[1] if len(parts) > 1 else "Unknown"
                    artist = parts[2] if len(parts) > 2 else ""
                    self.media_icon.set_text("▶" if status.lower() == "playing" else "❚❚")
                    self.media_title.set_text(title[:50] or "Unknown")
                    self.media_artist.set_text(artist[:50] or "Unknown artist")
                else:
                    self.media_icon.set_text("♫")
                    self.media_title.set_text("No media")
                    self.media_artist.set_text("Start a player to see it here")
        elif kind == "timer":
            self._update_timer()
        elif kind == "weather":
            if self._weather_due(now):
                self._last["weather"] = now
                self._update_weather(now)
        elif kind == "battery":
            if force or now - self._last.get("battery", 0) >= 30:
                self._last["battery"] = now
                percent, status = battery_state()
                if percent is not None:
                    self.battery_label.set_text(f"{percent}%")
                    self.battery_bar.set_fraction(percent / 100)
                    self.battery_state.set_text(status)
                else:
                    self.battery_label.set_text("—")
                    self.battery_bar.set_fraction(0)
                    self.battery_state.set_text("No battery")
        elif kind == "worldclock":
            if force or now - self._last.get("world", 0) >= 1:
                self._last["world"] = now
                for label, value, zone in self.zone_labels:
                    try:
                        hour = dt.datetime.now(ZoneInfo(zone)).strftime(
                            "%H:%M" if options.get("24h", True) else "%I:%M %p"
                        )
                    except ZoneInfoNotFoundError:
                        hour = "—"
                    value.set_text(hour)
        elif kind == "countdown":
            if force or now - self._last.get("countdown", 0) >= 60:
                self._last["countdown"] = now
                target = str(options.get("date") or "")
                try:
                    date = dt.date.fromisoformat(target)
                    days = (date - dt.date.today()).days
                    self.countdown_value.set_text(f"{days} days" if days >= 0 else "Passed")
                except ValueError:
                    self.countdown_value.set_text("Set a date")
        elif kind == "network":
            if force or now - self._last.get("network", 0) >= 2:
                self._last["network"] = now
                current = network_counters()
                down = up = 0
                if self._net_prev and current:
                    seconds = max(0.1, now - self._net_prev[0])
                    down = max(0, current[1] - self._net_prev[1]) / seconds
                    up = max(0, current[2] - self._net_prev[2]) / seconds
                self._net_prev = current
                self.net_ip.set_text(local_ip())
                self.net_speed.set_text(f"↓ {human_size(down)}/s   ↑ {human_size(up)}/s")
        self._last.setdefault("clock", now)

    def note_text(self) -> str | None:
        if self._note_buffer is None:
            return None
        return self._note_buffer.get_text(self._note_buffer.get_start_iter(),
                                          self._note_buffer.get_end_iter(), True)


def battery_state() -> tuple[int | None, str]:
    root = Path("/sys/class/power_supply")
    if not root.is_dir():
        return None, ""
    for entry in root.iterdir():
        if not entry.name.startswith("BAT"):
            continue
        try:
            capacity = int((entry / "capacity").read_text().strip())
            status = (entry / "status").read_text().strip()
            return capacity, status
        except (OSError, ValueError):
            continue
    return None, ""


def network_counters() -> tuple[float, int, int] | None:
    try:
        lines = Path("/proc/net/dev").read_text().splitlines()[2:]
        down = up = 0
        for line in lines:
            if ":" not in line:
                continue
            _name, data = line.split(":", 1)
            fields = data.split()
            if len(fields) >= 9:
                down += int(fields[0])
                up += int(fields[8])
        return time.monotonic(), down, up
    except (OSError, ValueError):
        return None


def local_ip() -> str:
    try:
        result = run(["hostname", "-I"], timeout=2)
        value = result.stdout.strip().split()
        return value[0] if value else socket.gethostbyname(socket.gethostname())
    except Exception:
        return "—"


def weather_label(code: int) -> tuple[str, str]:
    mapping = {
        0: ("☀", "Clear"), 1: ("☀", "Mostly clear"), 2: ("⛅", "Partly cloudy"),
        3: ("☁", "Cloudy"), 45: ("🌫", "Fog"), 48: ("🌫", "Fog"),
        51: ("🌦", "Drizzle"), 53: ("🌦", "Drizzle"), 55: ("🌧", "Drizzle"),
        61: ("🌦", "Rain"), 63: ("🌧", "Rain"), 65: ("🌧", "Heavy rain"),
        71: ("🌨", "Snow"), 73: ("🌨", "Snow"), 75: ("❄", "Heavy snow"),
        80: ("🌦", "Showers"), 81: ("🌧", "Showers"), 82: ("⛈", "Heavy showers"),
        95: ("⛈", "Thunderstorm"), 96: ("⛈", "Thunderstorm"), 99: ("⛈", "Thunderstorm"),
    }
    return mapping.get(code, ("◒", "Weather"))


def items_summary(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        counts[item["type"]] = counts.get(item["type"], 0) + 1
    return " · ".join(f"{count}× {WIDGET_TYPES.get(kind, {}).get('name', kind)}"
                       for kind, count in counts.items()) or "No widgets yet"
