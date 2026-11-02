"""Colour and palette tests."""

from __future__ import annotations

import io
import unittest

from PIL import Image

from leet_customizer import palette


def image_bytes(colors, size=(64, 64)) -> bytes:
    image = Image.new("RGB", size, colors[0])
    width, height = size
    block = max(1, width // max(1, len(colors)))
    for index, color in enumerate(colors):
        for x in range(index * block, min(width, (index + 1) * block)):
            for y in range(height):
                image.putpixel((x, y), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ColourTests(unittest.TestCase):
    def test_hex_round_trip(self):
        self.assertEqual(palette.hex_to_rgb("#ff8800"), (255, 136, 0))
        self.assertEqual(palette.rgb_to_hex((255, 136, 0)), "#ff8800")
        self.assertEqual(palette.normalise_hex("#abc"), "#aabbcc")
        self.assertEqual(palette.normalise_hex("nope", "#123456"), "#123456")

    def test_mix(self):
        self.assertEqual(palette.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(palette.mix("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(palette.mix("#000000", "#ffffff", 1), "#ffffff")

    def test_contrast_and_ensure(self):
        self.assertGreater(palette.contrast_ratio("#ffffff", "#000000"), 20)
        adjusted = palette.ensure_contrast("#777777", "#111111", 7.0)
        self.assertGreaterEqual(palette.contrast_ratio(adjusted, "#111111"), 7.0)

    def test_derive_tokens(self):
        tokens = palette.derive_tokens("#101018", "#181824", "#ff5f87", mode="dark")
        self.assertEqual(tokens["mode"], "dark")
        self.assertEqual(len(tokens["ansi"]), 16)
        self.assertGreaterEqual(palette.contrast_ratio(tokens["text"], tokens["bg"]), 7.0)
        self.assertGreaterEqual(palette.contrast_ratio(tokens["accent_text"], tokens["accent"]), 4.5)
        for key in ("bg", "surface", "surface2", "text", "text_dim", "accent",
                    "accent_text", "border", "danger", "warning", "success"):
            self.assertTrue(tokens[key].startswith("#"), key)

    def test_extract_palette_from_bytes(self):
        data = image_bytes([(220, 40, 80), (20, 30, 70), (245, 245, 240), (30, 160, 120)])
        swatches = palette.extract_swatches(data, limit=8)
        self.assertGreaterEqual(len(swatches), 2)
        for color, count in swatches:
            self.assertRegex(color, r"^#[0-9a-f]{6}$")
            self.assertGreaterEqual(count, 0)
        accent = palette.pick_accent(swatches)
        self.assertRegex(accent, r"^#[0-9a-f]{6}$")

    def test_wallpaper_palette(self):
        data = image_bytes([(230, 80, 100), (10, 16, 30), (80, 200, 180), (250, 248, 240)])
        dark = palette.wallpaper_palette(data, "dark")
        light = palette.wallpaper_palette(data, "light")
        self.assertEqual(dark["mode"], "dark")
        self.assertEqual(light["mode"], "light")
        self.assertGreaterEqual(palette.contrast_ratio(light["text"], light["bg"]), 7.0)
        self.assertTrue(dark["swatches"])


if __name__ == "__main__":
    unittest.main()
