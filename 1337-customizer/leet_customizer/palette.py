"""Fast, deterministic colour extraction and accessible palette generation."""

from __future__ import annotations

import colorsys
import io
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from . import constants
from .util import which

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - Pillow is a hard runtime dependency
    Image = None
    ImageOps = None


# --- colour primitives ------------------------------------------------------------

def normalise_hex(value: str, fallback: str = "#808080") -> str:
    value = str(value or "").strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    if len(value) == 8:
        value = value[:6]
    if len(value) != 6:
        return fallback
    try:
        int(value, 16)
    except ValueError:
        return fallback
    return "#" + value.lower()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = normalise_hex(value)
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def rgb_to_hex(value: Iterable[int | float]) -> str:
    parts = []
    for channel in value:
        parts.append(max(0, min(255, int(round(channel)))))
    return "#" + "".join(f"{channel:02x}" for channel in parts)


def mix(first: str, second: str, amount: float) -> str:
    """Mix first toward second. amount=0 is first, amount=1 is second."""
    amount = max(0.0, min(1.0, float(amount)))
    left = hex_to_rgb(first)
    right = hex_to_rgb(second)
    return rgb_to_hex(left[index] + (right[index] - left[index]) * amount for index in range(3))


def lighten(color: str, amount: float = 0.1) -> str:
    return mix(color, "#ffffff", amount)


def darken(color: str, amount: float = 0.1) -> str:
    return mix(color, "#000000", amount)


def with_alpha(color: str, alpha: float) -> str:
    red, green, blue = hex_to_rgb(color)
    return f"rgba({red},{green},{blue},{max(0.0, min(1.0, alpha)):.3f})"


def relative_luminance(color: str) -> float:
    def channel(value: int) -> float:
        value = value / 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = hex_to_rgb(color)
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(first: str, second: str) -> float:
    luminance_a = relative_luminance(first)
    luminance_b = relative_luminance(second)
    lighter = max(luminance_a, luminance_b)
    darker = min(luminance_a, luminance_b)
    return (lighter + 0.05) / (darker + 0.05)


def best_text(background: str, light: str = "#f7f7fb", dark: str = "#111116") -> str:
    return light if contrast_ratio(light, background) >= contrast_ratio(dark, background) else dark


def ensure_contrast(foreground: str, background: str, target: float = 4.5) -> str:
    """Nudge a foreground toward white or black until it is readable."""
    if contrast_ratio(foreground, background) >= target:
        return foreground
    direction = "#ffffff" if relative_luminance(background) < 0.45 else "#000000"
    best = foreground
    best_ratio = contrast_ratio(foreground, background)
    for step in range(1, 21):
        candidate = mix(foreground, direction, step / 20)
        ratio = contrast_ratio(candidate, background)
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
        if ratio >= target:
            return candidate
    return best


def saturation(color: str) -> float:
    red, green, blue = (channel / 255 for channel in hex_to_rgb(color))
    _hue, sat, _value = colorsys.rgb_to_hsv(red, green, blue)
    return sat


def rotate_hue(color: str, turns: float) -> str:
    red, green, blue = (channel / 255 for channel in hex_to_rgb(color))
    hue, sat, value = colorsys.rgb_to_hsv(red, green, blue)
    hue = (hue + turns) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, sat, value)
    return rgb_to_hex((red * 255, green * 255, blue * 255))


def visible_accent(candidate: str, background: str, target: float = 4.0) -> str:
    """Keep an accent colourful but make it legible on a background."""
    if contrast_ratio(candidate, background) >= target:
        return candidate
    direction = "#ffffff" if relative_luminance(background) < 0.45 else "#000000"
    best = candidate
    best_ratio = contrast_ratio(candidate, background)
    for step in range(1, 25):
        value = mix(candidate, direction, step / 25)
        ratio = contrast_ratio(value, background)
        if ratio > best_ratio:
            best, best_ratio = value, ratio
        if ratio >= target:
            return value
    return best


ANSI_BASE = {
    "red": "#e06c75",
    "green": "#98c379",
    "yellow": "#e5c07b",
    "blue": "#61afef",
    "magenta": "#c678dd",
    "cyan": "#56b6c2",
    "red_bright": "#ef7a85",
    "green_bright": "#a9d68a",
    "yellow_bright": "#f2d18d",
    "blue_bright": "#7fc4f7",
    "magenta_bright": "#d79ae8",
    "cyan_bright": "#6dcbd6",
}


def _ansi_palette(theme_bg: str, theme_fg: str, theme_accent: str, is_dark: bool) -> list[str]:
    blend_target = "#000000" if is_dark else "#ffffff"
    amount = 0.22 if is_dark else 0.16
    normal = [
        ensure_contrast(mix(ANSI_BASE[key], blend_target, amount), theme_bg, 3.0)
        for key in ("red", "green", "yellow", "blue", "magenta", "cyan")
    ]
    bright = [
        ensure_contrast(mix(ANSI_BASE[key], blend_target, amount * 0.35), theme_bg, 3.0)
        for key in ("red_bright", "green_bright", "yellow_bright", "blue_bright",
                    "magenta_bright", "cyan_bright")
    ]
    # 16 terminal slots: black, red, green, yellow, blue, magenta, cyan, white,
    # then the bright variants; the final slots reuse the theme foreground and accent.
    return [
        theme_bg, *normal, theme_fg,
        mix(theme_bg, theme_fg, 0.32), *bright, theme_accent,
    ]


def derive_tokens(
    background: str,
    surface: str,
    accent: str,
    *,
    mode: str = "dark",
    text: str | None = None,
    structure: str = "rounded",
) -> dict:
    """Create a complete, contrast-checked token set from four seed colours."""
    background = normalise_hex(background, "#111116")
    surface = normalise_hex(surface, mix(background, "#ffffff", 0.06 if mode == "dark" else 0.55))
    accent = normalise_hex(accent, "#7aa2ff")
    is_dark = mode == "dark" or relative_luminance(background) < 0.35

    if is_dark:
        surface = mix(surface, "#ffffff", 0.015) if surface == background else surface
        surface_2 = mix(surface, "#ffffff", 0.07)
        surface_3 = mix(surface, "#ffffff", 0.12)
        border = mix(background, text or "#f5f5fa", 0.19)
        hover = mix(surface, "#ffffff", 0.10)
        shadow = "#000000"
    else:
        surface_2 = mix(surface, "#000000", 0.045)
        surface_3 = mix(surface, "#000000", 0.085)
        border = mix(background, text or "#17171c", 0.16)
        hover = mix(surface, "#000000", 0.035)
        shadow = "#6b6b78"

    if text:
        foreground = ensure_contrast(normalise_hex(text), background, 7.0)
    else:
        foreground = ensure_contrast(best_text(background), background, 7.0)
    muted = ensure_contrast(mix(foreground, background, 0.42), background, 4.5)
    accent = visible_accent(accent, surface, 4.2)
    accent_text = best_text(accent)
    if contrast_ratio(accent_text, accent) < 4.5:
        accent_text = "#ffffff" if relative_luminance(accent) < 0.4 else "#101014"

    danger = visible_accent("#e05665" if is_dark else "#b42338", background, 4.0)
    warning = visible_accent("#e6b450" if is_dark else "#966000", background, 4.0)
    success = visible_accent("#69c78a" if is_dark else "#19733b", background, 4.0)
    info = visible_accent("#62aee8" if is_dark else "#136b9d", background, 4.0)

    selection = mix(surface, accent, 0.30 if is_dark else 0.22)
    tokens = {
        "mode": "dark" if is_dark else "light",
        "bg": background,
        "surface": surface,
        "surface2": surface_2,
        "surface3": surface_3,
        "text": foreground,
        "text_dim": muted,
        "text_faint": ensure_contrast(mix(foreground, background, 0.62), background, 3.0),
        "accent": accent,
        "accent_text": accent_text,
        "accent_soft": mix(surface, accent, 0.18 if is_dark else 0.12),
        "border": border,
        "border_strong": mix(border, foreground, 0.35),
        "hover": hover,
        "selection": selection,
        "shadow": shadow,
        "danger": danger,
        "warning": warning,
        "success": success,
        "info": info,
        "structure": structure,
    }
    tokens["ansi"] = _ansi_palette(background, foreground, accent, is_dark)
    return tokens


# --- image sampling ---------------------------------------------------------------

def _ffmpeg_frame(path: Path, at: float = 1.0) -> bytes | None:
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        return None
    commands = [
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(at), "-i", str(path),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
    ]
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout:
            return result.stdout
    return None


def load_image(source: str | Path | bytes, *, max_side: int = 128):
    """Load an image into a small RGB Pillow object, including video stills."""
    if Image is None:
        raise RuntimeError("Pillow is required for colour extraction")
    data: bytes | None = None
    if isinstance(source, bytes):
        data = source
    else:
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix in constants.VIDEO_EXTENSIONS or suffix in {".heic", ".heif", ".avif"}:
            data = _ffmpeg_frame(path)
        if data is None:
            try:
                image = Image.open(path)
                image.load()
            except Exception:
                data = _ffmpeg_frame(path)
                if data is None:
                    raise
            else:
                return _prepare_image(image, max_side)
        image = Image.open(io.BytesIO(data))
        return _prepare_image(image, max_side)
    image = Image.open(io.BytesIO(data))
    return _prepare_image(image, max_side)


def _prepare_image(image, max_side: int):
    if ImageOps is not None:
        image = ImageOps.exif_transpose(image)
    if getattr(image, "is_animated", False):
        image.seek(0)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (17, 17, 22))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((max_side, max_side))
    return image


def extract_swatches(source: str | Path | bytes, limit: int = 10) -> list[tuple[str, int]]:
    """Return [(hex, population)] ordered by frequency."""
    image = load_image(source)
    quantized = image.quantize(colors=max(2, min(32, limit)), method=Image.Quantize.MEDIANCUT)
    counts = quantized.getcolors(maxcolors=1 << 24) or []
    palette = quantized.getpalette() or []
    swatches: list[tuple[str, int]] = []
    for population, index in sorted(counts, reverse=True):
        offset = index * 3
        if offset + 2 >= len(palette):
            continue
        red, green, blue = palette[offset:offset + 3]
        color = rgb_to_hex((red, green, blue))
        swatches.append((color, int(population)))
    return swatches[:limit]


def pick_accent(swatches: list[tuple[str, int]]) -> str:
    if not swatches:
        return "#7aa2ff"
    total = sum(count for _color, count in swatches) or 1
    scored: list[tuple[float, str]] = []
    for color, count in swatches:
        lightness = relative_luminance(color)
        if lightness < 0.015 or lightness > 0.97:
            continue
        score = saturation(color) * (0.35 + 0.65 * (count / total) ** 0.32)
        # Prefer accents that are neither pure grey nor almost white.
        score *= 0.55 + 0.45 * min(1.0, abs(lightness - 0.5) * 2.0)
        scored.append((score, color))
    if not scored:
        return swatches[0][0]
    scored.sort(reverse=True)
    return scored[0][1]


def wallpaper_palette(source: str | Path | bytes, mode: str = "dark", structure: str = "rounded") -> dict:
    """Build a full theme token set from a picture or video still."""
    swatches = extract_swatches(source, limit=12)
    colors = [color for color, _count in swatches]
    dominant = colors[0] if colors else "#1d1f2b"
    accent = pick_accent(swatches)
    if mode == "light":
        background = mix(dominant, "#ffffff", 0.90)
        surface = mix(dominant, "#ffffff", 0.82)
    else:
        background = mix(dominant, "#08080d", 0.86)
        surface = mix(dominant, "#111119", 0.72)
    tokens = derive_tokens(background, surface, accent, mode=mode, structure=structure)
    tokens["swatches"] = colors[:8]
    return tokens
