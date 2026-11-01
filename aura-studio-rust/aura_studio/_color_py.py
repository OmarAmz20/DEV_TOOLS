"""Perceptual colour maths for Aura Studio.

Everything here is plain Python (no GTK), so it can be tested and used from
the command line.  Colours are sRGB hex strings; blending and lightness
adjustments happen in OKLab/OKLCH, which keeps hues stable and avoids the
muddy greys that HSL produces.
"""
from __future__ import annotations

import math
import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


# --- sRGB <-> linear --------------------------------------------------------------

def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def parse_hex(value, default=None):
    """'#abc' or 'A1B2C3' -> (r, g, b) floats in 0..1, or *default*."""
    if not isinstance(value, str):
        return default
    match = _HEX.match(value.strip())
    if not match:
        return default
    text = match.group(1)
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return tuple(int(text[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def rgba_hex(rgb, alpha: float = 1.0) -> str:
    r, g, b = (round(max(0.0, min(1.0, c)) * 255) for c in rgb)
    return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, alpha)):.3g})"


def rgba_css(hexcolor: str, alpha: float) -> str:
    rgb = parse_hex(hexcolor, (0, 0, 0))
    return rgba_hex(rgb, alpha)


# --- OKLab / OKLCH ----------------------------------------------------------------

def rgb_to_oklab(rgb):
    r, g, b = (_to_linear(c) for c in rgb)
    lr = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    mg = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    sb = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (lr, mg, sb))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(lab, clamp: bool = True):
    L, a, b = lab
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    out = (_to_srgb(r), _to_srgb(g), _to_srgb(bb))
    if clamp:
        out = tuple(max(0.0, min(1.0, c)) for c in out)
    return out


def oklab_to_oklch(lab):
    L, a, b = lab
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def oklch_to_oklab(L, C, h):
    rad = math.radians(h)
    return L, C * math.cos(rad), C * math.sin(rad)


def rgb_to_oklch(rgb):
    return oklab_to_oklch(rgb_to_oklab(rgb))


def hex_to_oklch(hexcolor):
    rgb = parse_hex(hexcolor)
    return rgb_to_oklch(rgb) if rgb else None


def _in_gamut(lab) -> bool:
    rgb = oklab_to_rgb(lab, clamp=False)
    return all(-1e-5 <= c <= 1 + 1e-5 for c in rgb)


def _fit_chroma(L: float, C: float, h: float) -> float:
    """The largest chroma <= C that still fits in sRGB at this lightness/hue."""
    L = max(0.0, min(1.0, L))
    if C <= 0 or _in_gamut(oklch_to_oklab(L, C, h)):
        return max(0.0, C)
    lo, hi = 0.0, C
    for _ in range(18):
        mid = (lo + hi) / 2
        if _in_gamut(oklch_to_oklab(L, mid, h)):
            lo = mid
        else:
            hi = mid
    return lo


def oklch_rgb(L: float, C: float, h: float):
    L = max(0.0, min(1.0, L))
    C = max(0.0, _fit_chroma(L, C, h))
    return oklab_to_rgb(oklch_to_oklab(L, C, h))


def oklch_hex(L: float, C: float, h: float) -> str:
    return rgb_hex(oklch_rgb(L, C, h))


def hex_to_lch(hexcolor: str):
    lab = rgb_to_oklab(parse_hex(hexcolor, (0, 0, 0)))
    return oklab_to_oklch(lab)


# --- contrast ---------------------------------------------------------------------

def luminance(hexcolor: str) -> float:
    r, g, b = (max(0.0, min(1.0, c)) for c in parse_hex(hexcolor, (0, 0, 0)))
    r, g, b = _to_linear(r), _to_linear(g), _to_linear(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one: str, two: str) -> float:
    a, b = sorted((luminance(one), luminance(two)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def best_on(background: str, candidates=("#101014", "#FFFFFF")) -> str:
    return max(candidates, key=lambda c: contrast(c, background))


def contrast_label(value: float) -> str:
    if value >= 7:
        return "AAA"
    if value >= 4.5:
        return "AA"
    if value >= 3:
        return "AA large"
    return "low"


def adjust_for_contrast(L: float, C: float, h: float, against: str, target: float,
                        prefer: str | None = None) -> tuple[str, float]:
    """Move lightness until the colour reads on *against*.

    *prefer* can be 'darker' or 'lighter'.  When omitted the direction with
    the most headroom is tried first.
    """
    directions = (-1, 1) if prefer != "lighter" else (1, -1)
    if prefer == "darker":
        directions = (-1, 1)
    for direction in directions:
        value = L
        for _ in range(160):
            candidate = oklch_hex(value, C, h)
            if contrast(candidate, against) >= target:
                return candidate, value
            value += direction * 0.004
            if value < 0 or value > 1:
                break
    # Nothing reached the target: return the most contrasting end.
    dark = oklch_hex(0.08, C * 0.6, h)
    light = oklch_hex(0.97, C * 0.4, h)
    return (dark if contrast(dark, against) >= contrast(light, against) else light), L


# --- mixing, tinting and helpers --------------------------------------------------

def tint(lightness: float, chroma: float, hue: float) -> str:
    return oklch_hex(lightness, chroma, hue)


def hue_distance(one: float, two: float) -> float:
    d = abs(one - two) % 360
    return min(d, 360 - d)


def circular_mean(hues, weights=None) -> float:
    x = y = 0.0
    for i, hue in enumerate(hues):
        weight = 1.0 if weights is None else weights[i]
        x += math.cos(math.radians(hue)) * weight
        y += math.sin(math.radians(hue)) * weight
    return math.degrees(math.atan2(y, x)) % 360 if x or y else 0.0


def is_hex(value) -> bool:
    return bool(isinstance(value, str) and _HEX.match(value.strip()))
