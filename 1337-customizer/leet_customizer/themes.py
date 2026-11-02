"""Theme presets, custom themes and CSS generation."""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any

from . import constants, palette
from .util import read_json, slugify, write_json

WALLPAPER_PRESET = "__wallpaper__"


def load_presets() -> list[dict]:
    raw = read_json(constants.PRESETS_FILE, [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("id")]


def custom_theme_dir() -> Path:
    directory = constants.CONFIG_DIR / "themes"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def load_custom_themes() -> list[dict]:
    themes = []
    for path in sorted(custom_theme_dir().glob("*.json")):
        raw = read_json(path)
        if isinstance(raw, dict) and raw.get("id"):
            raw["custom"] = True
            themes.append(raw)
    return themes


def all_presets() -> list[dict]:
    presets = load_presets()
    custom = load_custom_themes()
    for preset in custom:
        preset.setdefault("description", "Your saved theme")
        preset.setdefault("structure", "rounded")
    return presets + custom


def find_preset(preset_id: str) -> dict | None:
    for preset in all_presets():
        if preset.get("id") == preset_id:
            return preset
    return None


def desired_variant(mode: str, schedule: dict | None = None) -> str:
    mode = (mode or "auto").lower()
    if mode in ("light", "dark"):
        return mode
    schedule = schedule or {}
    if not schedule.get("enabled"):
        return "dark"
    now = datetime.now().time()
    try:
        light_start = dtime.fromisoformat(str(schedule.get("light_start", "07:00")))
        dark_start = dtime.fromisoformat(str(schedule.get("dark_start", "19:00")))
    except ValueError:
        return "dark"
    if light_start <= dark_start:
        return "light" if light_start <= now < dark_start else "dark"
    # The light window crosses midnight.
    return "light" if now >= light_start or now < dark_start else "dark"


def wallpaper_path_from_state() -> str | None:
    raw = read_json(constants.WALLPAPER_STATE, {})
    path = raw.get("applied") or raw.get("path")
    return str(path) if path and Path(path).exists() else None


def resolve_theme(
    preset_id: str,
    *,
    mode: str = "dark",
    schedule: dict | None = None,
    wallpaper_path: str | None = None,
    overrides: dict | None = None,
) -> dict:
    """Return a fully resolved theme dictionary for the requested variant."""
    overrides = overrides or {}
    variant = desired_variant(mode, schedule)
    preset = None if preset_id == WALLPAPER_PRESET else find_preset(preset_id)

    if preset and preset.get("colors"):
        # An imported/exported full theme.
        raw = preset["colors"].get(variant) or preset["colors"].get("dark") or {}
        tokens = palette.derive_tokens(
            raw.get("bg", "#111116"),
            raw.get("surface", "#1b1b24"),
            raw.get("accent", "#7aa2ff"),
            mode=variant,
            text=raw.get("text"),
            structure=preset.get("structure", "rounded"),
        )
        tokens.update({key: value for key, value in raw.items() if isinstance(value, str)})
        name = preset.get("name", "Custom theme")
        structure = preset.get("structure", "rounded")
        style_data = preset.get("style", {})
    elif preset_id == WALLPAPER_PRESET:
        path = wallpaper_path or wallpaper_path_from_state()
        if path:
            tokens = palette.wallpaper_palette(path, variant, "rounded")
            name = "Wallpaper"
        else:
            fallback = find_preset("midnight-aurora") or {}
            seed = fallback.get(variant, {})
            tokens = palette.derive_tokens(
                seed.get("bg", "#0b0d17"), seed.get("surface", "#151829"),
                seed.get("accent", "#7aa2ff"), mode=variant,
            )
            name = "Wallpaper (no picture)"
        structure = "rounded"
        style_data = {}
    else:
        if not preset:
            preset = find_preset("midnight-aurora") or (load_presets() or [{}])[0]
        seed = preset.get(variant) or preset.get("dark") or {}
        tokens = palette.derive_tokens(
            seed.get("bg", "#0b0d17"),
            seed.get("surface", "#151829"),
            seed.get("accent", "#7aa2ff"),
            mode=variant,
            text=seed.get("text"),
            structure=preset.get("structure", "rounded"),
        )
        name = preset.get("name", "1337-Customizer theme")
        structure = preset.get("structure", "rounded")
        style_data = preset.get("style", {})

    accent_override = overrides.get("accent_override") or ""
    if accent_override:
        tokens["accent"] = palette.visible_accent(accent_override, tokens["surface"])
        tokens["accent_text"] = palette.best_text(tokens["accent"])
        tokens["accent_soft"] = palette.mix(tokens["surface"], tokens["accent"], 0.18)
    if overrides.get("text_override"):
        tokens["text"] = palette.ensure_contrast(overrides["text_override"], tokens["bg"], 7.0)

    style = {
        "structure": overrides.get("structure") or structure,
        "radius": int(overrides.get("radius", style_data.get("radius", 14))),
        "border_width": int(overrides.get("border_width", style_data.get("border_width", 1))),
        "shadow": bool(overrides.get("shadow", style_data.get("shadow", True))),
        "transparency": float(overrides.get("transparency", style_data.get("transparency", 0.0))),
        "density": overrides.get("density", style_data.get("density", "comfortable")),
    }
    style["radius"] = max(0, min(28, style["radius"]))
    style["border_width"] = max(0, min(4, style["border_width"]))
    style["transparency"] = max(0.0, min(0.45, style["transparency"]))
    return {
        "id": preset_id,
        "name": name,
        "variant": variant,
        "colors": tokens,
        "style": style,
        "wallpaper": wallpaper_path or (wallpaper_path_from_state() if preset_id == WALLPAPER_PRESET else None),
    }


def _rgba(color: str, alpha: float) -> str:
    red, green, blue = palette.hex_to_rgb(color)
    return f"rgba({red},{green},{blue},{max(0.0, min(1.0, alpha)):.3f})"


def _structure_css(theme: dict) -> str:
    colors = theme["colors"]
    style = theme["style"]
    structure = style.get("structure", "rounded")
    radius = style.get("radius", 14)
    border = style.get("border_width", 1)
    accent = colors["accent"]
    text = colors["text"]
    shadow = colors.get("shadow", "#000000")
    pieces = []

    if structure == "sharp":
        radius = 0
        border = max(1, border)
        pieces.append("""
button, entry, spinbutton, searchentry, menuitem, popover > contents,
row, .card, frame, notebook, tab, headerbar, .navigation-sidebar, tooltip {
  border-radius: 0;
}
""")
    elif structure == "glass":
        radius = max(10, radius)
        alpha = max(0.62, 0.94 - style.get("transparency", 0.0))
        pieces.append(f"""
window, .background {{ background-color: {_rgba(colors['bg'], alpha)}; }}
headerbar, .titlebar, .navigation-sidebar, popover > contents, .card, row, frame {{
  background-color: {_rgba(colors['surface'], min(1.0, alpha + 0.03))};
  border-color: {_rgba(colors['border'], 0.72)};
}}
button {{ background-color: {_rgba(colors['surface2'], 0.86)}; }}
button:hover {{ background-color: {_rgba(colors['surface3'], 0.96)}; }}
""")
    elif structure == "neon":
        radius = min(radius, 7)
        pieces.append(f"""
window, .background {{ background-color: {colors['bg']}; }}
button, entry, spinbutton, searchentry, row, .card, frame, headerbar {{
  border: {max(1, border)}px solid {accent};
  box-shadow: 0 0 10px {_rgba(accent, 0.26)}, inset 0 0 8px {_rgba(accent, 0.10)};
}}
button:hover, entry:focus, row:hover {{
  box-shadow: 0 0 18px {_rgba(accent, 0.46)}, inset 0 0 10px {_rgba(accent, 0.16)};
}}
""")
    elif structure == "paper":
        radius = min(radius, 3)
        pieces.append(f"""
window, .background {{ background-color: {colors['bg']}; }}
button, .card, frame, row, entry, popover > contents {{
  border: {max(1, border)}px solid {colors['border_strong']};
  box-shadow: 3px 3px 0 {_rgba(shadow, 0.35)};
}}
button:active {{ box-shadow: 1px 1px 0 {_rgba(shadow, 0.35)}; }}
""")
    elif structure == "pixel":
        radius = 0
        pieces.append(f"""
* {{ border-radius: 0; }}
button, entry, spinbutton, searchentry, row, .card, frame, headerbar, popover > contents {{
  border: {max(2, border)}px solid {text};
  box-shadow: 4px 4px 0 {colors['surface3']};
}}
button:hover, row:hover {{ background-color: {colors['accent_soft']}; }}
button:active {{ box-shadow: 1px 1px 0 {colors['surface3']}; }}
""")
    elif structure == "minimal":
        radius = min(radius, 9)
        pieces.append(f"""
button, entry, spinbutton, searchentry, row, .card, frame, headerbar {{
  box-shadow: none;
  border-color: {_rgba(colors['border'], 0.65)};
}}
button {{ border-color: transparent; }}
button:hover {{ border-color: {_rgba(colors['border'], 0.8)}; }}
""")
    elif structure == "retro":
        radius = min(radius, 4)
        pieces.append(f"""
button, entry, spinbutton, searchentry, row, .card, frame {{
  border: {max(1, border)}px solid {colors['border_strong']};
  box-shadow: inset 1px 1px 0 {_rgba('#ffffff', 0.18)}, inset -1px -1px 0 {_rgba('#000000', 0.28)};
}}
button:active {{ box-shadow: inset 1px 1px 3px {_rgba('#000000', 0.40)}; }}
""")
    else:  # rounded
        pieces.append(f"""
button, entry, spinbutton, searchentry, row, .card, frame, headerbar, popover > contents {{
  border-radius: {radius}px;
}}
""")

    if style.get("density") == "compact":
        pieces.append("""
button, entry, spinbutton, searchentry { padding-top: 4px; padding-bottom: 4px; }
row { min-height: 32px; }
""")
    elif style.get("density") == "spacious":
        pieces.append("""
button, entry, spinbutton, searchentry { padding-top: 9px; padding-bottom: 9px; }
row { min-height: 48px; }
""")
    return "\n".join(pieces)


def generate_gtk_css(theme: dict, *, gtk_version: int = 4) -> str:
    """Generate a complete GTK 3/4 stylesheet from a resolved theme."""
    colors = theme["colors"]
    style = theme["style"]
    name = theme.get("name", "1337-Customizer")
    alpha = max(0.55, 1.0 - style.get("transparency", 0.0))
    bg = _rgba(colors["bg"], alpha) if style.get("transparency") else colors["bg"]
    surface = _rgba(colors["surface"], alpha) if style.get("transparency") else colors["surface"]
    border_width = max(0, int(style.get("border_width", 1)))
    radius = int(style.get("radius", 14))
    accent = colors["accent"]
    text = colors["text"]
    muted = colors["text_dim"]
    shadow = colors.get("shadow", "#000000")

    definitions = {
        "theme_bg_color": colors["bg"],
        "theme_fg_color": colors["text"],
        "theme_base_color": colors["surface"],
        "theme_text_color": colors["text"],
        "theme_selected_bg_color": colors["accent"],
        "theme_selected_fg_color": colors["accent_text"],
        "insensitive_bg_color": colors["surface2"],
        "insensitive_fg_color": colors["text_faint"],
        "borders": colors["border"],
        "unfocused_borders": colors["border_strong"],
        "warning_color": colors["warning"],
        "error_color": colors["danger"],
        "success_color": colors["success"],
        "accent_color": colors["accent"],
        "accent_bg_color": colors["accent"],
        "accent_fg_color": colors["accent_text"],
        "window_bg_color": colors["bg"],
        "view_bg_color": colors["surface"],
        "headerbar_bg_color": colors["surface"],
        "popover_bg_color": colors["surface2"],
        "card_bg_color": colors["surface"],
        "dialog_bg_color": colors["surface"],
        "sidebar_bg_color": colors["bg"],
        "shade_color": _rgba(shadow, 0.35),
        "scrollbar_outline_color": colors["border_strong"],
    }
    header = [f"/* {name} — generated by 1337-Customizer */"]
    header += [f"@define-color {key} {value};" for key, value in definitions.items()]
    header += [
        f"@define-color leet_bg {colors['bg']};",
        f"@define-color leet_surface {colors['surface']};",
        f"@define-color leet_surface2 {colors['surface2']};",
        f"@define-color leet_text {colors['text']};",
        f"@define-color leet_muted {colors['text_dim']};",
        f"@define-color leet_accent {colors['accent']};",
        f"@define-color leet_border {colors['border']};",
    ]

    common = f"""
window, .background {{
  background-color: {bg};
  color: {text};
}}
window.csd {{
  box-shadow: 0 18px 50px {_rgba(shadow, 0.45 if colors['mode'] == 'dark' else 0.18)};
}}
headerbar, .titlebar {{
  background-color: {surface};
  background-image: none;
  color: {text};
  border-bottom: {border_width}px solid {colors['border']};
  box-shadow: none;
  min-height: 38px;
}}
headerbar:backdrop, .titlebar:backdrop {{
  background-color: {surface};
  color: {muted};
}}
headerbar .title, .titlebar .title {{
  font-weight: 700;
  color: {text};
}}
.navigation-sidebar {{
  background-color: {colors['bg']};
  border-right: 1px solid {colors['border']};
  padding: 8px;
}}
.navigation-sidebar row {{
  border-radius: {max(2, radius - 4)}px;
  padding: 7px 10px;
  color: {muted};
}}
.navigation-sidebar row:hover {{
  background-color: {colors['hover']};
  color: {text};
}}
.navigation-sidebar row:selected {{
  background-color: {colors['accent_soft']};
  color: {text};
  font-weight: 600;
}}
label {{ color: {text}; }}
label.dim-label, .dim-label, .subtitle, .caption {{
  color: {muted};
}}
.dim-label:disabled, label:disabled {{ color: {colors['text_faint']}; }}
link, .link {{
  color: {accent};
}}
button {{
  background-color: {colors['surface2']};
  background-image: none;
  color: {text};
  border: {border_width}px solid {colors['border']};
  border-radius: {radius}px;
  padding: 6px 12px;
  min-height: 18px;
  box-shadow: none;
  transition: background-color 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
}}
button:hover {{
  background-color: {colors['hover']};
  border-color: {colors['border_strong']};
}}
button:active, button:checked {{
  background-color: {colors['selection']};
  border-color: {accent};
}}
button:focus:focus-visible, button:focus, entry:focus, searchentry:focus-within {{
  outline: none;
  border-color: {accent};
  box-shadow: inset 0 0 0 1px {_rgba(accent, 0.65)};
}}
button:disabled {{
  background-color: {colors['surface2']};
  color: {colors['text_faint']};
  border-color: {colors['border']};
}}
button.flat {{
  background-color: transparent;
  border-color: transparent;
  box-shadow: none;
}}
button.flat:hover {{
  background-color: {colors['hover']};
}}
button.suggested-action {{
  background-color: {accent};
  border-color: {accent};
  color: {colors['accent_text']};
}}
button.suggested-action:hover {{
  background-color: {palette.mix(accent, '#ffffff', 0.14)};
}}
button.destructive-action {{
  background-color: {colors['danger']};
  border-color: {colors['danger']};
  color: {palette.best_text(colors['danger'])};
}}
button.circular {{ border-radius: 999px; padding: 6px; }}
entry, spinbutton, searchentry {{
  background-color: {colors['surface']};
  color: {text};
  border: {border_width}px solid {colors['border']};
  border-radius: {radius}px;
  padding: 6px 10px;
  box-shadow: none;
  caret-color: {accent};
  transition: border-color 120ms ease, box-shadow 120ms ease;
}}
entry:focus, spinbutton:focus-within, searchentry:focus-within {{
  border-color: {accent};
  box-shadow: inset 0 0 0 1px {_rgba(accent, 0.28)};
}}
entry:disabled, spinbutton:disabled {{
  color: {colors['text_faint']};
  background-color: {colors['surface2']};
}}
entry selection, textview selection, text selection {{
  background-color: {colors['accent']};
  color: {colors['accent_text']};
}}
popover > contents, popover.background, menu {{
  background-color: {colors['surface2']};
  color: {text};
  border: 1px solid {colors['border']};
  border-radius: {radius}px;
  box-shadow: 0 12px 32px {_rgba(shadow, 0.38)};
  padding: 5px;
}}
menuitem, modelbutton {{
  border-radius: {max(2, radius - 5)}px;
  padding: 6px 10px;
  color: {text};
}}
menuitem:hover, modelbutton:hover {{
  background-color: {colors['selection']};
  color: {text};
}}
menuitem:disabled, modelbutton:disabled {{ color: {colors['text_faint']}; }}
row, list > row {{
  background-color: transparent;
  color: {text};
  border-radius: {max(2, radius - 4)}px;
}}
row:hover, list > row:hover {{
  background-color: {colors['hover']};
}}
row:selected, list > row:selected, flowboxchild:selected, gridview child:selected {{
  background-color: {colors['selection']};
  color: {text};
}}
frame, .card, card, .boxed-list, .preferences-group {{
  background-color: {colors['surface']};
  border: {border_width}px solid {colors['border']};
  border-radius: {radius}px;
  box-shadow: {('0 8px 24px ' + _rgba(shadow, 0.20)) if style.get('shadow') else 'none'};
}}
frame > label, frame > box, .card > box {{ background-color: transparent; }}
list.boxed-list, .boxed-list {{
  background-color: {colors['surface']};
  border: {border_width}px solid {colors['border']};
  border-radius: {radius}px;
}}
list.boxed-list > row {{
  border-bottom: 1px solid {colors['border']};
  border-radius: 0;
  padding: 10px 12px;
}}
list.boxed-list > row:last-child {{ border-bottom: none; }}
list.boxed-list > row:first-child {{ border-top-left-radius: {radius}px; border-top-right-radius: {radius}px; }}
list.boxed-list > row:last-child {{ border-bottom-left-radius: {radius}px; border-bottom-right-radius: {radius}px; }}
switch {{
  background-color: {colors['surface3']};
  border: 1px solid {colors['border']};
  border-radius: 999px;
  min-width: 42px;
  min-height: 22px;
}}
switch:checked {{ background-color: {accent}; border-color: {accent}; }}
switch slider {{
  background-color: {colors['text']};
  border-radius: 999px;
  box-shadow: 0 1px 3px {_rgba(shadow, 0.35)};
  min-width: 18px;
  min-height: 18px;
}}
switch:checked slider {{ background-color: {colors['accent_text']}; }}
scale trough {{
  background-color: {colors['surface3']};
  border-radius: 999px;
  min-height: 5px;
}}
scale highlight {{ background-color: {accent}; border-radius: 999px; }}
scale slider {{
  background-color: {colors['surface']};
  border: 2px solid {accent};
  border-radius: 999px;
  min-width: 14px;
  min-height: 14px;
}}
progressbar trough {{ background-color: {colors['surface3']}; border-radius: 999px; }}
progressbar progress {{ background-color: {accent}; border-radius: 999px; }}
scrollbar {{ background-color: transparent; }}
scrollbar slider {{
  background-color: {colors['border_strong']};
  border-radius: 999px;
  min-width: 6px;
  min-height: 6px;
}}
scrollbar slider:hover {{ background-color: {accent}; }}
notebook {{ background-color: {colors['surface']}; border-radius: {radius}px; }}
notebook > header {{ background-color: {colors['bg']}; border-bottom: 1px solid {colors['border']}; }}
notebook > header > tabs > tab {{
  color: {muted};
  padding: 7px 12px;
  border-radius: {max(2, radius - 4)}px;
}}
notebook > header > tabs > tab:checked {{
  color: {text};
  background-color: {colors['surface2']};
  box-shadow: inset 0 -2px 0 {accent};
}}
tooltip, tooltip.background {{
  background-color: {colors['surface3']};
  color: {text};
  border: 1px solid {colors['border']};
  border-radius: {max(3, radius - 4)}px;
  padding: 4px 8px;
}}
.check, radio {{ border: 2px solid {colors['border_strong']}; background-color: {colors['surface']}; }}
.check:checked, radio:checked {{ background-color: {accent}; border-color: {accent}; color: {colors['accent_text']}; }}
separator {{ background-color: {colors['border']}; min-width: 1px; min-height: 1px; }}
paned > separator {{ background-color: {colors['border']}; }}
.sidebar, .sidebar-pane {{ background-color: {colors['bg']}; }}
.osd, .toolbar, .bottom-bar {{
  background-color: {_rgba(colors['surface2'], 0.96)};
  color: {text};
  border: 1px solid {colors['border']};
  border-radius: {radius}px;
}}
.title-1, .title-2, .title-3, .title-4 {{ color: {text}; }}
.subtitle {{ color: {muted}; }}
.accent {{ color: {accent}; }}
.success {{ color: {colors['success']}; }}
.warning {{ color: {colors['warning']}; }}
.error {{ color: {colors['danger']}; }}
"""+ _structure_css(theme)

    # A few widgets still use the old GTK3 names.
    if gtk_version == 3:
        common += f"""
.toolbar, .inline-toolbar {{ background-color: {surface}; border-color: {colors['border']}; }}
.entry:focus, .spinbutton:focus {{ border-color: {accent}; }}
treeview.view:selected, iconview:selected {{ background-color: {colors['accent']}; color: {colors['accent_text']}; }}
"""
    return "\n".join(header) + "\n" + common


def generate_preview_css(theme: dict) -> str:
    colors = theme["colors"]
    style = theme["style"]
    radius = int(style.get("radius", 14))
    border = max(1, int(style.get("border_width", 1)))
    accent = colors["accent"]
    return f"""
.hp-root {{
  background-color: {colors['bg']};
  color: {colors['text']};
  border: 1px solid {colors['border']};
  border-radius: {radius + 6}px;
  padding: 14px;
}}
.hp-card {{
  background-color: {colors['surface']};
  border: {border}px solid {colors['border']};
  border-radius: {radius}px;
  padding: 12px;
}}
.hp-title {{ color: {colors['text']}; font-weight: 700; font-size: 15px; }}
.hp-muted {{ color: {colors['text_dim']}; font-size: 11px; }}
.hp-accent {{ color: {accent}; }}
.hp-button {{
  background-color: {colors['surface2']};
  color: {colors['text']};
  border: {border}px solid {colors['border']};
  border-radius: {radius}px;
  padding: 5px 11px;
}}
.hp-button.primary {{
  background-color: {accent};
  color: {colors['accent_text']};
  border-color: {accent};
}}
.hp-button.danger {{
  background-color: {colors['danger']};
  color: {palette.best_text(colors['danger'])};
  border-color: {colors['danger']};
}}
.hp-entry {{
  background-color: {colors['surface']};
  color: {colors['text']};
  border: {border}px solid {colors['border']};
  border-radius: {radius}px;
  padding: 5px 9px;
}}
.hp-pill {{
  background-color: {colors['accent_soft']};
  color: {colors['text']};
  border-radius: 999px;
  padding: 3px 10px;
}}
.hp-sidebar {{
  background-color: {colors['bg']};
  border: 1px solid {colors['border']};
  border-radius: {radius}px;
  padding: 8px;
}}
.hp-swatch {{
  border-radius: 999px;
  min-width: 16px;
  min-height: 16px;
}}
.hp-progress {{
  background-color: {colors['surface3']};
  border-radius: 999px;
  min-height: 7px;
}}
.hp-progress > progress {{
  background-color: {accent};
  border-radius: 999px;
  min-height: 7px;
}}
"""


def terminal_theme(theme: dict, terminal: str) -> tuple[str, str] | None:
    """Return (filename suffix, content) for a terminal theme."""
    colors = theme["colors"]
    ansi = colors.get("ansi") or []
    if len(ansi) < 16:
        return None
    accent = colors["accent"]
    background = colors["bg"]
    foreground = colors["text"]
    cursor = colors["accent"]
    selection = colors["selection"]
    result: dict[str, str] = {
        "background": background,
        "foreground": foreground,
        "cursor": cursor,
        "selection_background": selection,
        "selection_foreground": colors["text"],
        "color0": ansi[0], "color1": ansi[1], "color2": ansi[2], "color3": ansi[3],
        "color4": ansi[4], "color5": ansi[5], "color6": ansi[6], "color7": ansi[7],
        "color8": ansi[8], "color9": ansi[9], "color10": ansi[10], "color11": ansi[11],
        "color12": ansi[12], "color13": ansi[13], "color14": ansi[14], "color15": ansi[15],
    }
    if terminal == "kitty":
        lines = ["# 1337-Customizer terminal theme"]
        for key in ("background", "foreground", "cursor", "selection_background",
                    "selection_foreground"):
            lines.append(f"{key} {result[key]}")
        for index in range(16):
            lines.append(f"color{index} {result[f'color{index}']}")
        lines += [
            "active_border_color " + accent,
            "inactive_border_color " + colors["border"],
            "tab_bar_style powerline",
            "tab_powerline_style slanted",
        ]
        return ".conf", "\n".join(lines) + "\n"
    if terminal == "foot":
        lines = ["[colors]", f"background={background}", f"foreground={foreground}",
                 f"selection-background={selection}", f"selection-foreground={colors['text']}"]
        names = ("regular0", "regular1", "regular2", "regular3",
                 "regular4", "regular5", "regular6", "regular7",
                 "bright0", "bright1", "bright2", "bright3",
                 "bright4", "bright5", "bright6", "bright7")
        for name, value in zip(names, ansi[:16]):
            lines.append(f"{name}={value}")
        return ".ini", "\n".join(lines) + "\n"
    if terminal == "ghostty":
        lines = ["# 1337-Customizer terminal theme", f"background = {background}",
                 f"foreground = {foreground}", f"cursor-color = {cursor}",
                 f"selection-background = {selection}", f"selection-foreground = {colors['text']}"]
        for index, value in enumerate(ansi[:16]):
            lines.append(f"palette = {index}={value}")
        return "", "\n".join(lines) + "\n"
    if terminal == "alacritty":
        lines = ["# 1337-Customizer terminal theme", "", "[colors.primary]",
                 f'background = "{background}"', f'foreground = "{foreground}"', "",
                 "[colors.cursor]", f'text = "{colors["accent_text"]}"', f'cursor = "{cursor}"', "",
                 "[colors.selection]", f'text = "{colors["text"]}"', f'background = "{selection}"', "",
                 "[colors.normal]", f'black = "{ansi[0]}"', f'red = "{ansi[1]}"',
                 f'green = "{ansi[2]}"', f'yellow = "{ansi[3]}"', f'blue = "{ansi[4]}"',
                 f'magenta = "{ansi[5]}"', f'cyan = "{ansi[6]}"', f'white = "{ansi[7]}"', "",
                 "[colors.bright]", f'black = "{ansi[8]}"', f'red = "{ansi[9]}"',
                 f'green = "{ansi[10]}"', f'yellow = "{ansi[11]}"', f'blue = "{ansi[12]}"',
                 f'magenta = "{ansi[13]}"', f'cyan = "{ansi[14]}"', f'white = "{ansi[15]}"']
        return ".toml", "\n".join(lines) + "\n"
    if terminal == "wezterm":
        lines = ["-- 1337-Customizer terminal theme", "return {", "  colors = {"]
        for index, value in enumerate(ansi[:16]):
            lines.append(f'    ansi = {{ {", ".join(chr(34) + item + chr(34) for item in ansi[:8])} }},')
            lines.append(f'    brights = {{ {", ".join(chr(34) + item + chr(34) for item in ansi[8:16])} }},')
            break
        lines += [f'    background = "{background}",', f'    foreground = "{foreground}",',
                  f'    cursor_bg = "{cursor}",', f'    selection_bg = "{selection}",',
                  f'    selection_fg = "{colors["text"]}",', "  },", "}"]
        return ".lua", "\n".join(lines) + "\n"
    return None


def export_theme(theme: dict) -> dict:
    return {
        "format": "1337-theme",
        "version": 1,
        "name": theme.get("name", "1337-Customizer theme"),
        "id": theme.get("id", "custom"),
        "variant": theme.get("variant", "dark"),
        "colors": {"dark" if theme.get("variant") == "dark" else "light": copy.deepcopy(theme["colors"])},
        "style": copy.deepcopy(theme["style"]),
    }


def import_theme(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        return None
    colors = payload.get("colors")
    if not isinstance(colors, dict):
        return None
    name = str(payload.get("name") or "Imported theme")
    theme_id = slugify(str(payload.get("id") or name))
    style = payload.get("style") if isinstance(payload.get("style"), dict) else {}
    seeds = {}
    for variant in ("light", "dark"):
        value = colors.get(variant)
        if isinstance(value, dict):
            seeds[variant] = {
                "bg": palette.normalise_hex(value.get("bg", "#111116")),
                "surface": palette.normalise_hex(value.get("surface", "#1b1b24")),
                "accent": palette.normalise_hex(value.get("accent", "#7aa2ff")),
                "text": value.get("text"),
            }
    if not seeds:
        return None
    return {
        "id": theme_id,
        "name": name,
        "description": str(payload.get("description") or "Imported theme"),
        "structure": style.get("structure", "rounded"),
        "light": seeds.get("light") or seeds.get("dark"),
        "dark": seeds.get("dark") or seeds.get("light"),
        "style": style,
        "custom": True,
    }


def save_custom_theme(preset: dict) -> str:
    preset = copy.deepcopy(preset)
    base = slugify(str(preset.get("id") or preset.get("name") or "custom"))
    builtin_ids = {item.get("id") for item in load_presets()}
    existing_ids = {item.get("id") for item in load_custom_themes()}
    candidate = base
    if candidate in builtin_ids:
        candidate = f"{base}-custom"
    if candidate in existing_ids and candidate != base:
        # Keep updating the same imported name, but never shadow a preset.
        pass
    elif candidate in builtin_ids:
        counter = 2
        while f"{base}-{counter}" in builtin_ids or f"{base}-{counter}" in existing_ids:
            counter += 1
        candidate = f"{base}-{counter}"
    preset["id"] = candidate
    preset["custom"] = True
    write_json(custom_theme_dir() / f"{candidate}.json", preset, mode=0o600)
    return candidate


def delete_custom_theme(theme_id: str) -> bool:
    path = custom_theme_dir() / f"{slugify(theme_id)}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def theme_from_seeds(
    name: str,
    *,
    light_bg: str,
    light_surface: str,
    light_accent: str,
    dark_bg: str,
    dark_surface: str,
    dark_accent: str,
    structure: str = "rounded",
    description: str = "",
) -> dict:
    return {
        "id": slugify(name),
        "name": name,
        "description": description or "A custom 1337-Customizer look",
        "structure": structure,
        "light": {"bg": light_bg, "surface": light_surface, "accent": light_accent},
        "dark": {"bg": dark_bg, "surface": dark_surface, "accent": dark_accent},
        "style": {"structure": structure, "radius": 14, "border_width": 1,
                  "shadow": True, "transparency": 0.0, "density": "comfortable"},
        "custom": True,
    }


def contrast_report(theme: dict) -> list[tuple[str, str, float]]:
    colors = theme["colors"]
    return [
        ("Body text", colors["bg"], palette.contrast_ratio(colors["text"], colors["bg"])),
        ("Muted text", colors["bg"], palette.contrast_ratio(colors["text_dim"], colors["bg"])),
        ("Accent text", colors["accent"], palette.contrast_ratio(colors["accent_text"], colors["accent"])),
    ]
