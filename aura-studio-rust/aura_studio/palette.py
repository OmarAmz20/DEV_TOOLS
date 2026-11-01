"""Palette extraction and exports, backed by the Rust core when available.

The pure-Python implementation in ``_palette_py`` remains the fallback, so a
checkout without a compiled extension (or ``AURA_FORCE_PYTHON=1``) still works.
"""
from __future__ import annotations

import os

from . import color  # noqa: F401  (kept for code that imports palette.color)

try:
    if os.environ.get("AURA_FORCE_PYTHON") == "1":
        raise ImportError
    import aura_core as _rust
except ImportError:
    _rust = None

RUST_BACKEND = _rust is not None

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


if _rust is not None:

    def valid_mode(value):
        return _rust.valid_mode(value)

    def valid_palette(value):
        return _rust.valid_palette(value)

    def build(samples, style="balanced", accent_override=None):
        samples = list(samples)
        try:
            return _rust.palette_from_samples(samples, style, accent_override)
        except ValueError:
            from . import _palette_py
            return _palette_py.build(samples, style, accent_override)

    def from_image(path, style="balanced", accent_override=None):
        try:
            return _rust.palette_from_image(str(path), style, accent_override)
        except ValueError:
            # AVIF/JXL and other loaders that the Rust image crate does not
            # know about still work through GdkPixbuf in the Python fallback.
            from . import _palette_py
            return _palette_py.from_image(path, style, accent_override)

    def contrast_report(value):
        return _rust.contrast_report(value)

    def terminal_colours(value):
        return _rust.terminal_colours(value)

    def kitty_theme(value):
        return _rust.kitty_theme(value)

    def gtk_css(value, dark, glass=False):
        return _rust.gtk_css(value, dark, glass)

    def css_for_export(value, dark):
        return _rust.css_for_export(value, dark)

    def palette_json(value):
        return _rust.palette_json(value)

else:
    from ._palette_py import (  # noqa: F401
        build,
        contrast_report,
        css_for_export,
        from_image,
        gtk_css,
        kitty_theme,
        palette_json,
        terminal_colours,
        valid_mode,
        valid_palette,
    )


__all__ = [
    "RUST_BACKEND", "STYLES", "STYLE_LABELS", "STYLE_DESCRIPTIONS",
    "ANSI_HUES", "ANSI_NAMES", "SWATCH_KEYS", "PALETTE_KEYS",
    "valid_mode", "valid_palette", "build", "from_image", "contrast_report",
    "terminal_colours", "kitty_theme", "gtk_css", "css_for_export",
    "palette_json",
]
