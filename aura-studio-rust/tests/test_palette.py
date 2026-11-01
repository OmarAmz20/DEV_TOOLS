"""Palette maths and generated stylesheet tests."""
from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
import zlib

from aura_studio import color, palette


def _png_chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def write_png(path, pixels, width, height):
    rows = []
    stride = width * 3
    for y in range(height):
        rows.append(b"\x00" + bytes(pixels[y * stride:(y + 1) * stride]))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(_png_chunk(b"IHDR", header))
        handle.write(_png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9)))
        handle.write(_png_chunk(b"IEND", b""))


class ColourTest(unittest.TestCase):
    def test_hex_roundtrip(self):
        for value in ("#123456", "#FFFFFF", "#000000", "#E86A33", "#7BA7FF"):
            lightness, chroma, hue = color.hex_to_oklch(value)
            self.assertTrue(color.is_hex(color.oklch_hex(lightness, chroma, hue)))

    def test_contrast(self):
        self.assertGreater(color.contrast("#111111", "#EEEEEE"), 15)
        self.assertEqual(color.contrast("#777777", "#777777"), 1.0)

    def test_contrast_direction(self):
        value, _ = color.adjust_for_contrast(0.5, 0.12, 250, "#FFFFFF", 4.5, "darker")
        self.assertGreaterEqual(color.contrast(value, "#FFFFFF"), 4.5)


class PaletteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="aura-palette-test-")
        cls.image = os.path.join(cls.directory.name, "colour.png")
        width = height = 48
        pixels = []
        for y in range(height):
            for x in range(width):
                if x < width // 2 and y < height // 2:
                    pixels += (25, 75, 210)
                elif x >= width // 2 and y < height // 2:
                    pixels += (240, 175, 30)
                elif x < width // 2:
                    pixels += (25, 150, 80)
                else:
                    pixels += (205, 40, 95)
        write_png(cls.image, pixels, width, height)
        cls.mono = os.path.join(cls.directory.name, "mono.png")
        pixels = []
        for y in range(32):
            for x in range(32):
                value = 35 + (x + y) * 3
                pixels += (value, value, value)
        write_png(cls.mono, pixels, 32, 32)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_all_styles_are_accessible(self):
        for style in palette.STYLES:
            value = palette.from_image(self.image, style)
            for mode in ("light", "dark"):
                item = value[mode]
                for key in palette.PALETTE_KEYS:
                    if key == "ansi":
                        self.assertEqual(len(item[key]), 16)
                        self.assertTrue(all(color.is_hex(c) for c in item[key]))
                    else:
                        self.assertTrue(color.is_hex(item[key]), f"{style}/{mode}/{key}")
                self.assertGreaterEqual(color.contrast(item["ink"], item["paper"]), 7,
                                        f"body text too weak in {style}/{mode}")
                self.assertGreaterEqual(color.contrast(item["accent_text"], item["paper"]), 4.5,
                                        f"accent text too weak in {style}/{mode}")
                self.assertGreaterEqual(color.contrast(item["accent"], item["paper"]), 3.0)

    def test_light_and_dark_differ(self):
        value = palette.from_image(self.image)
        self.assertNotEqual(value["light"]["paper"], value["dark"]["paper"])
        self.assertLess(color.luminance(value["dark"]["paper"]),
                        color.luminance(value["light"]["paper"]))

    def test_mono_image_stays_mono(self):
        value = palette.from_image(self.mono, "vivid")
        self.assertTrue(value["meta"]["mono"])
        lightness, chroma, _hue = color.hex_to_oklch(value["dark"]["accent"])
        self.assertLess(chroma, 0.01)

    def test_custom_accent_is_used(self):
        value = palette.from_image(self.image, "balanced", "#FF8800")
        self.assertTrue(value["meta"]["custom_accent"])
        _l, _c, hue = color.hex_to_oklch(value["dark"]["accent"])
        self.assertLess(color.hue_distance(hue, 55), 35)

    def test_gtk_css_is_valid(self):
        import gi
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk

        value = palette.from_image(self.image)
        for mode in ("light", "dark"):
            for glass in (False, True):
                provider = Gtk.CssProvider()
                provider.load_from_data(palette.gtk_css(value[mode], mode == "dark", glass).encode())

    def test_glass_opacity_is_configurable(self):
        value = palette.from_image(self.image)
        css = palette.gtk_css(value["dark"], True, True, 0.35)
        self.assertIn("alpha(@window_bg_color, 0.35)", css)
        self.assertNotIn("alpha(@window_bg_color, 0.72)", css)

    def test_json_export_shape(self):
        value = palette.from_image(self.image, "muted")
        exported = palette.palette_json(value)
        text = json.dumps(exported)
        self.assertIn("light", text)
        self.assertIn("dark", text)
        self.assertIn("contrast", exported)

    def test_kitty_theme(self):
        value = palette.from_image(self.image)
        text = palette.kitty_theme(value["dark"])
        for number in range(16):
            self.assertIn(f"color{number} ", text)
        self.assertIn("background ", text)


if __name__ == "__main__":
    unittest.main()
