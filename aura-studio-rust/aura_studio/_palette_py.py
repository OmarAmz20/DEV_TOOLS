"""Turn a picture into two complete palettes (light and dark).

The approach is deliberately different from a simple "most common colour":
samples are clustered in OKLab, the accent is the most vivid cluster that
stands apart from the picture's overall cast, and every text/accent pair is
pushed until it passes a WCAG contrast target.  Four styles control how
loud the result is.
"""
from __future__ import annotations

import math
import random

from . import _color_py as color

STYLES = ("vivid", "balanced", "muted", "mono")
STYLE_LABELS = {
    "vivid": "Vivid",
    "balanced": "Balanced",
    "muted": "Muted",
    "mono": "Mono",
}
STYLE_DESCRIPTIONS = {
    "vivid": "More chroma in the accent and backgrounds",
    "balanced": "Readable colour taken straight from the picture",
    "muted": "Soft, paper-like colours with a quiet accent",
    "mono": "Graphite neutrals, no coloured accent",
}

ANSI_HUES = (28.0, 148.0, 92.0, 258.0, 330.0, 198.0)
ANSI_NAMES = ("red", "green", "yellow", "blue", "magenta", "cyan")
SWATCH_KEYS = ("paper", "paper2", "sheet", "ink", "muted", "accent")
PALETTE_KEYS = (
    "paper", "paper2", "sheet", "ink", "muted",
    "accent", "accent_text", "on_accent", "ansi",
)


def valid_mode(value):
    """True when a single light/dark palette has only safe colour values."""
    if not isinstance(value, dict):
        return False
    if not all(color.is_hex(value.get(key)) for key in (
            "paper", "paper2", "sheet", "ink", "muted",
            "accent", "accent_text", "on_accent")):
        return False
    ansi = value.get("ansi")
    return isinstance(ansi, list) and len(ansi) == 16 and all(color.is_hex(c) for c in ansi)


def valid_palette(value):
    return isinstance(value, dict) and all(valid_mode(value.get(mode))
                                           for mode in ("light", "dark"))


# --- extraction -------------------------------------------------------------------

def _load_samples(path, max_side=72):
    """Pixels of *path* as OKLab samples (alpha ignored below 50%)."""
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max_side, max_side, True)
    data, stride, channels = pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()
    width, height = pb.get_width(), pb.get_height()
    samples = []
    for y in range(height):
        row = y * stride
        for x in range(width):
            i = row + x * channels
            if channels == 4 and data[i + 3] < 128:
                continue
            samples.append(color.rgb_to_oklab((
                data[i] / 255, data[i + 1] / 255, data[i + 2] / 255)))
    return samples


def _cast(samples):
    """The picture's overall hue, how colourful it is, and how much colour it has."""
    hues, weights, chromas = [], [], []
    for L, a, b in samples:
        chroma = math.hypot(a, b)
        if chroma > 0.018 and 0.05 < L < 0.95:
            hues.append(math.degrees(math.atan2(b, a)) % 360)
            weights.append(chroma)
            chromas.append(chroma)
    if not hues:
        return 0.0, 0.0, 0.0
    hist = [0.0] * 36
    for hue, weight in zip(hues, weights):
        hist[int(hue / 10) % 36] += weight
    smooth = [hist[i] + 0.5 * (hist[i - 1] + hist[(i + 1) % 36]) for i in range(36)]
    peak_bin = max(range(36), key=lambda i: smooth[i])
    peak = peak_bin * 10 + 5
    picked_hues, picked_weights = [], []
    for hue, weight in zip(hues, weights):
        if color.hue_distance(hue, peak) <= 24:
            picked_hues.append(hue)
            picked_weights.append(weight)
    cast_hue = color.circular_mean(picked_hues or hues, picked_weights or weights)
    cast_chroma = sum(picked_weights) / len(picked_weights) if picked_weights else \
        sum(chromas) / len(chromas)
    share = len(hues) / max(1, len(samples))
    return cast_hue, cast_chroma, share


def _distance(one, two):
    return sum((a - b) ** 2 for a, b in zip(one, two))


def _kmeans(points, k=10, iterations=14):
    """Deterministic weighted-by-population k-means in OKLab."""
    if not points:
        return []
    step = max(1, math.ceil(len(points) / 3200))
    pts = points[::step]
    k = max(1, min(k, len(pts)))
    rng = random.Random(7)
    centres = [pts[rng.randrange(len(pts))]]
    while len(centres) < k:
        distances = [min(_distance(p, c) for c in centres) for p in pts]
        total = sum(distances)
        if total <= 1e-12:
            break
        target = rng.random() * total
        for point, distance in zip(pts, distances):
            target -= distance
            if target <= 0:
                centres.append(point)
                break
        else:
            centres.append(pts[-1])
    groups = [[] for _ in centres]
    for _ in range(iterations):
        groups = [[] for _ in centres]
        for point in pts:
            best = min(range(len(centres)), key=lambda i: _distance(point, centres[i]))
            groups[best].append(point)
        moved = False
        for i, group in enumerate(groups):
            if not group:
                continue
            centre = tuple(sum(p[j] for p in group) / len(group) for j in range(3))
            if _distance(centre, centres[i]) > 1e-10:
                moved = True
            centres[i] = centre
        if not moved:
            break
    total = len(pts)
    clusters = []
    for group, centre in zip(groups, centres):
        if group:
            clusters.append({"lab": centre, "weight": len(group) / total})
    clusters.sort(key=lambda c: c["weight"], reverse=True)
    return clusters


def _cluster_hue(cluster):
    L, a, b = cluster["lab"]
    return math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _pick_accent(clusters, cast_hue):
    """The most vivid cluster that is not simply the background colour."""
    best, best_score = None, 0.0
    for cluster in clusters:
        L, _a, _b = cluster["lab"]
        chroma, hue = _cluster_hue(cluster)
        if chroma < 0.024 or not 0.18 < L < 0.94:
            continue
        distinctness = 0.58 + 0.42 * min(color.hue_distance(hue, cast_hue), 120) / 120
        score = (cluster["weight"] ** 0.32) * min(chroma / 0.20, 1.0) * distinctness
        if score > best_score:
            best, best_score = (hue, chroma), score
    return best


def _style_accent(hue, chroma, style):
    if style == "mono":
        return hue, 0.0
    if style == "vivid":
        chroma *= 1.18
    elif style == "muted":
        chroma *= 0.68
    if chroma < 0.024:
        return hue, 0.0
    return hue, min(max(chroma, 0.078), 0.205)


def _tint_strength(cast_chroma, style):
    factor = {"vivid": 0.58, "balanced": 0.38, "muted": 0.20, "mono": 0.0}[style]
    return min(max(cast_chroma * factor, 0.0), 0.048)


# --- palette building -------------------------------------------------------------

def _ansi(light, paper, tint_hue, tint_chroma, accent_chroma):
    chroma = min(max(accent_chroma * 0.62, 0.085), 0.16)
    base_l, bright_l = (0.455, 0.60) if light else (0.685, 0.795)
    prefer = "darker" if light else "lighter"
    base = [
        color.adjust_for_contrast(base_l, chroma, hue, paper, 3.1, prefer)[0]
        for hue in ANSI_HUES
    ]
    bright = [
        color.adjust_for_contrast(bright_l, chroma, hue, paper, 3.8 if light else 4.0, prefer)[0]
        for hue in ANSI_HUES
    ]
    if light:
        black = color.tint(0.22, tint_chroma * 0.7, tint_hue)
        white = color.tint(0.46, tint_chroma * 0.6, tint_hue)
        bright_black = color.tint(0.36, tint_chroma * 0.6, tint_hue)
        bright_white = color.tint(0.20, tint_chroma * 0.7, tint_hue)
    else:
        black = color.tint(0.235, tint_chroma * 0.75, tint_hue)
        white = color.tint(0.86, tint_chroma * 0.5, tint_hue)
        bright_black = color.tint(0.62, tint_chroma * 0.5, tint_hue)
        bright_white = color.tint(0.955, tint_chroma * 0.3, tint_hue)
    return [black, *base[:6], white, bright_black, *bright[:6], bright_white]


def _mode(light, tint_hue, tint_chroma, accent_hue, accent_chroma):
    if light:
        paper = color.tint(0.966, tint_chroma * 0.48, tint_hue)
        paper2 = color.tint(0.925, tint_chroma * 0.72, tint_hue)
        sheet = color.tint(0.991, tint_chroma * 0.22, tint_hue)
        ink = color.tint(0.225, tint_chroma * 0.62, tint_hue)
        muted = color.tint(0.465, tint_chroma * 0.55, tint_hue)
        if accent_chroma == 0:
            accent = color.tint(0.335, 0.0, tint_hue)
            accent_text = color.tint(0.245, 0.0, tint_hue)
        else:
            accent = color.adjust_for_contrast(0.585, accent_chroma, accent_hue, paper, 3.2, "darker")[0]
            accent_text = color.adjust_for_contrast(0.46, accent_chroma, accent_hue, paper, 4.6, "darker")[0]
        on_accent = color.best_on(accent)
    else:
        paper = color.tint(0.158, tint_chroma * 0.78, tint_hue)
        paper2 = color.tint(0.128, tint_chroma * 0.95, tint_hue)
        sheet = color.tint(0.210, tint_chroma * 0.82, tint_hue)
        ink = color.tint(0.930, tint_chroma * 0.42, tint_hue)
        muted = color.tint(0.680, tint_chroma * 0.50, tint_hue)
        if accent_chroma == 0:
            accent = color.tint(0.805, 0.0, tint_hue)
            accent_text = color.tint(0.885, 0.0, tint_hue)
        else:
            accent = color.adjust_for_contrast(0.735, accent_chroma, accent_hue, paper, 4.6, "lighter")[0]
            accent_text = color.adjust_for_contrast(0.815, accent_chroma, accent_hue, paper, 7.0, "lighter")[0]
        on_accent = color.best_on(accent)
    return {
        "paper": paper,
        "paper2": paper2,
        "sheet": sheet,
        "ink": ink,
        "muted": muted,
        "accent": accent,
        "accent_text": accent_text,
        "on_accent": on_accent,
        "ansi": _ansi(light, paper, tint_hue, tint_chroma, accent_chroma),
    }


def build(samples, style="balanced", accent_override=None):
    """Build the light and dark palettes from OKLab samples."""
    style = style if style in STYLES else "balanced"
    samples = list(samples)
    if not samples:
        raise ValueError("the picture has no readable pixels")
    clusters = _kmeans(samples)
    cast_hue, cast_chroma, coloured_share = _cast(samples)
    mono_image = coloured_share < 0.035 or cast_chroma < 0.018

    tint_chroma = 0.0 if mono_image else _tint_strength(cast_chroma, style)
    custom = bool(accent_override)
    if custom:
        parsed = color.hex_to_oklch(accent_override)
        if parsed:
            accent_hue, accent_chroma = parsed[2], parsed[1]
        else:
            custom = False
    if not custom:
        accent_hue, accent_chroma = cast_hue, 0.0
        picked = None if mono_image else _pick_accent(clusters, cast_hue)
        if picked:
            accent_hue, accent_chroma = picked
        elif not mono_image:
            # The picture is colourful, but no single cluster is vivid enough:
            # use its overall cast so the accent is not needlessly grey.
            accent_hue, accent_chroma = cast_hue, cast_chroma
        accent_hue, accent_chroma = _style_accent(accent_hue, accent_chroma, style)
    else:
        # A custom accent keeps its hue/chroma; only mono discards colour, and even
        # then an explicit custom choice is respected.
        accent_hue, accent_chroma = _style_accent(accent_hue, accent_chroma, style if style != "mono" else "balanced")

    palette = {
        "light": _mode(True, cast_hue, tint_chroma, accent_hue, accent_chroma),
        "dark": _mode(False, cast_hue, tint_chroma, accent_hue, accent_chroma),
        "meta": {
            "cast_hue": round(cast_hue, 1),
            "cast_chroma": round(cast_chroma, 4),
            "coloured_share": round(coloured_share, 3),
            "accent_hue": round(accent_hue, 1),
            "accent_chroma": round(accent_chroma, 4),
            "mono": mono_image or style == "mono",
            "style": style,
            "custom_accent": custom,
            "clusters": len(clusters),
        },
    }
    return palette


def from_image(path, style="balanced", accent_override=None):
    """The light and dark palettes for a picture on disk."""
    return build(_load_samples(path), style, accent_override)


# --- preview / export helpers -----------------------------------------------------

def contrast_report(palette):
    light, dark = palette["light"], palette["dark"]
    return {
        "light": {
            "body": color.contrast(light["ink"], light["paper"]),
            "accent": color.contrast(light["accent_text"], light["paper"]),
        },
        "dark": {
            "body": color.contrast(dark["ink"], dark["paper"]),
            "accent": color.contrast(dark["accent_text"], dark["paper"]),
        },
    }


def terminal_colours(p):
    return {
        "background": p["paper"],
        "foreground": p["ink"],
        "cursor": p["accent"],
        "cursor_text": p["on_accent"],
        "selection_background": p["accent"],
        "selection_foreground": p["on_accent"],
        "palette": list(p["ansi"]),
    }


def kitty_theme(p):
    term = terminal_colours(p)
    lines = [
        "# Generated by Aura Studio. Changes are overwritten.",
        f"background {term['background']}",
        f"foreground {term['foreground']}",
        f"cursor {term['cursor']}",
        f"cursor_text_color {term['cursor_text']}",
        f"selection_background {term['selection_background']}",
        f"selection_foreground {term['selection_foreground']}",
    ]
    for i, value in enumerate(term["palette"]):
        lines.append(f"color{i} {value}")
    return "\n".join(lines) + "\n"


_GLASS_CSS = """
/* see-through windows: the wallpaper shows through, text stays solid */
window.background:not(.popup):not(tooltip):not(.solid-csd):not(.desktopwindow) {
  background-color: alpha(@window_bg_color, 0.72);
}
headerbar, .titlebar:not(headerbar) { background-color: alpha(@headerbar_bg_color, 0.48); }
headerbar:backdrop, .titlebar:not(headerbar):backdrop { background-color: alpha(@headerbar_backdrop_color, 0.42); }
.view, textview text, iconview, treeview.view, list, listview, columnview, .content-view,
.boxed-list, scrolledwindow > viewport > list, entry, spinbutton {
  background-color: alpha(@view_bg_color, 0.48);
}
.sidebar, placessidebar, stacksidebar, .navigation-sidebar, .sidebar-pane {
  background-color: alpha(@sidebar_bg_color, 0.42);
}
list row, listview row, .card, frame > border { background-color: transparent; }
popover > contents, popover.background > contents, menu, .menu, .context-menu, tooltip,
tooltip.background, messagedialog, dialog.background, window.dialog {
  background-color: @popover_bg_color;
}
"""


def gtk_css(p, dark, glass=False):
    """A GTK 3 + GTK 4 stylesheet with libadwaita's colour names."""
    if not valid_mode(p):
        raise ValueError("invalid palette colours")
    accent = p["accent"]
    colours = {
        "accent_color": p["accent_text"],
        "accent_bg_color": accent,
        "accent_fg_color": p["on_accent"],
        "destructive_color": p["ansi"][9] if dark else p["ansi"][1],
        "destructive_bg_color": p["ansi"][1],
        "destructive_fg_color": "#FFFFFF",
        "success_color": p["ansi"][2],
        "warning_color": p["ansi"][3],
        "error_color": p["ansi"][1],
        "window_bg_color": p["paper"],
        "window_fg_color": p["ink"],
        "view_bg_color": p["sheet"],
        "view_fg_color": p["ink"],
        "headerbar_bg_color": p["paper2"],
        "headerbar_fg_color": p["ink"],
        "headerbar_border_color": p["ink"],
        "headerbar_backdrop_color": p["paper"],
        "headerbar_shade_color": "rgba(0, 0, 0, 0.5)" if dark else color.rgba_css(p["ink"], 0.12),
        "card_bg_color": p["sheet"],
        "card_fg_color": p["ink"],
        "card_shade_color": "rgba(0, 0, 0, 0.4)" if dark else color.rgba_css(p["ink"], 0.10),
        "dialog_bg_color": p["sheet"] if dark else p["paper"],
        "dialog_fg_color": p["ink"],
        "popover_bg_color": p["sheet"],
        "popover_fg_color": p["ink"],
        "sidebar_bg_color": p["paper2"],
        "sidebar_fg_color": p["ink"],
        "shade_color": "rgba(0, 0, 0, 0.35)" if dark else color.rgba_css(p["ink"], 0.08),
        "scrollbar_outline_color": "rgba(0, 0, 0, 0.5)" if dark else "rgba(255, 255, 255, 0.5)",
        # older GTK 3 themes and apps look for these
        "theme_bg_color": p["paper"],
        "theme_fg_color": p["ink"],
        "theme_base_color": p["sheet"],
        "theme_text_color": p["ink"],
        "theme_selected_bg_color": accent,
        "theme_selected_fg_color": p["on_accent"],
        # stable names for hand-written gtk.css snippets
        "aura_paper": p["paper"],
        "aura_paper2": p["paper2"],
        "aura_sheet": p["sheet"],
        "aura_ink": p["ink"],
        "aura_muted": p["muted"],
        "aura_accent": accent,
        "aura_accent_text": p["accent_text"],
        "aura_on_accent": p["on_accent"],
        "aura_shadow": "#000000" if dark else p["ink"],
    }
    text = "/* Aura Studio — generated from your wallpaper; changes are overwritten */\n"
    text += "".join(f"@define-color {name} {value};\n" for name, value in colours.items())
    text += "\nwindow.desktopwindow { background-color: transparent; }\n"
    if glass:
        text += _GLASS_CSS
    return text


def css_for_export(palette, dark):
    return gtk_css(palette["dark" if dark else "light"], dark, False)


def palette_json(palette):
    """Both modes plus readable contrast numbers, ready for a file."""
    report = contrast_report(palette)
    out = {
        "generator": "Aura Studio",
        "meta": palette.get("meta", {}),
        "light": {k: v for k, v in palette["light"].items()},
        "dark": {k: v for k, v in palette["dark"].items()},
        "contrast": {mode: {k: round(v, 2) for k, v in values.items()}
                     for mode, values in report.items()},
    }
    return out
