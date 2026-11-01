"""Perceptual colour maths, backed by the Rust core when it is built.

The pure-Python implementation in ``_color_py`` is kept as a fallback so the
app still runs before Rust has been compiled (and with ``AURA_FORCE_PYTHON=1``).
"""
from __future__ import annotations

import os

try:
    if os.environ.get("AURA_FORCE_PYTHON") == "1":
        raise ImportError
    import aura_core as _rust
except ImportError:
    _rust = None

RUST_BACKEND = _rust is not None

if _rust is not None:

    def parse_hex(value, default=None):
        if not isinstance(value, str):
            return default
        result = _rust.parse_hex(value)
        return result if result is not None else default

    def rgb_hex(rgb):
        return _rust.rgb_hex(tuple(rgb))

    def rgba_hex(rgb, alpha: float = 1.0):
        return _rust.rgba_hex(tuple(rgb), float(alpha))

    def rgba_css(hexcolor: str, alpha: float):
        return _rust.rgba_css(hexcolor, float(alpha))

    def rgb_to_oklab(rgb):
        return _rust.rgb_to_oklab(tuple(rgb))

    def oklab_to_rgb(lab, clamp: bool = True):
        return _rust.oklab_to_rgb(tuple(lab), clamp)

    def oklab_to_oklch(lab):
        return _rust.oklab_to_oklch(tuple(lab))

    def oklch_to_oklab(L, C, h):
        return _rust.oklch_to_oklab((L, C, h))

    def rgb_to_oklch(rgb):
        return _rust.rgb_to_oklch(tuple(rgb))

    def hex_to_oklch(hexcolor):
        if not isinstance(hexcolor, str):
            return None
        return _rust.hex_to_oklch(hexcolor)

    def oklch_rgb(L: float, C: float, h: float):
        return _rust.oklch_rgb(L, C, h)

    def oklch_hex(L: float, C: float, h: float) -> str:
        return _rust.oklch_hex(L, C, h)

    def hex_to_lch(hexcolor: str):
        return _rust.hex_to_lch(hexcolor)

    def luminance(hexcolor: str) -> float:
        return _rust.luminance(hexcolor)

    def contrast(one: str, two: str) -> float:
        return _rust.contrast(one, two)

    def best_on(background: str, candidates=("#101014", "#FFFFFF")) -> str:
        return _rust.best_on(background, list(candidates))

    def contrast_label(value: float) -> str:
        return _rust.contrast_label(value)

    def adjust_for_contrast(L: float, C: float, h: float, against: str,
                            target: float, prefer: str | None = None):
        return _rust.adjust_for_contrast(L, C, h, against, target, prefer)

    def tint(lightness: float, chroma: float, hue: float) -> str:
        return _rust.tint(lightness, chroma, hue)

    def hue_distance(one: float, two: float) -> float:
        return _rust.hue_distance(one, two)

    def circular_mean(hues, weights=None) -> float:
        return _rust.circular_mean(list(hues),
                                   None if weights is None else list(weights))

    def is_hex(value) -> bool:
        return isinstance(value, str) and _rust.is_hex(value)

else:
    from ._color_py import (  # noqa: F401
        adjust_for_contrast,
        best_on,
        circular_mean,
        contrast,
        contrast_label,
        hex_to_lch,
        hex_to_oklch,
        hue_distance,
        is_hex,
        luminance,
        oklab_to_oklch,
        oklab_to_rgb,
        oklch_hex,
        oklch_rgb,
        oklch_to_oklab,
        parse_hex,
        rgb_hex,
        rgb_to_oklab,
        rgb_to_oklch,
        rgba_css,
        rgba_hex,
        tint,
    )


__all__ = [
    "RUST_BACKEND", "parse_hex", "is_hex", "rgb_hex", "rgba_hex", "rgba_css",
    "rgb_to_oklab", "oklab_to_rgb", "oklab_to_oklch", "oklch_to_oklab",
    "rgb_to_oklch", "hex_to_oklch", "oklch_rgb", "oklch_hex", "hex_to_lch",
    "luminance", "contrast", "best_on", "contrast_label",
    "adjust_for_contrast", "tint", "hue_distance", "circular_mean",
]
