"""The Rust extension mirrors the pure-Python colour engine."""
from __future__ import annotations

import math
import os
import unittest

from aura_studio import _color_py, color, palette

try:
    import aura_core
except ImportError:
    aura_core = None


@unittest.skipIf(aura_core is None, "Rust core is not built")
class RustColourTest(unittest.TestCase):
    def test_hex_and_contrast_are_close_to_python(self):
        for value in ("#000000", "#FFFFFF", "#E86A33", "#7BA7FF", "#123456"):
            self.assertAlmostEqual(
                color.contrast(value, "#FFFFFF"),
                _color_py.contrast(value, "#FFFFFF"), places=6)
            self.assertAlmostEqual(
                color.luminance(value), _color_py.luminance(value), places=9)

    def test_oklab_roundtrip_is_close_to_python(self):
        for value in ("#123456", "#E86A33", "#FFFFFF", "#000000"):
            rust = color.rgb_to_oklab(_color_py.parse_hex(value))
            py = _color_py.rgb_to_oklab(_color_py.parse_hex(value))
            for one, two in zip(rust, py):
                self.assertTrue(math.isclose(one, two, rel_tol=1e-12, abs_tol=1e-12))

    def test_contrast_adjustment_still_passes(self):
        value, _lightness = color.adjust_for_contrast(
            0.5, 0.12, 250, "#FFFFFF", 4.5, "darker")
        self.assertGreaterEqual(color.contrast(value, "#FFFFFF"), 4.5)


@unittest.skipIf(aura_core is None, "Rust core is not built")
class RustPaletteTest(unittest.TestCase):
    image = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "docs", "library.png")

    def test_palette_has_the_same_shape(self):
        value = palette.from_image(self.image)
        self.assertEqual(set(value), {"light", "dark", "meta"})
        self.assertEqual(set(value["dark"]), set(palette.PALETTE_KEYS))
        self.assertTrue(palette.valid_palette(value))
        for mode in ("light", "dark"):
            self.assertGreaterEqual(
                color.contrast(value[mode]["ink"], value[mode]["paper"]), 7)
            self.assertGreaterEqual(
                color.contrast(value[mode]["accent_text"], value[mode]["paper"]), 4.5)

    def test_css_and_json_exports(self):
        value = palette.from_image(self.image)
        css = palette.gtk_css(value["dark"], True, True)
        self.assertIn("@define-color accent_bg_color", css)
        self.assertIn("window.desktopwindow", css)
        report = palette.palette_json(value)
        self.assertEqual(set(report), {"generator", "meta", "light", "dark", "contrast"})
        self.assertIn("body", report["contrast"]["dark"])
        self.assertTrue(palette.kitty_theme(value["dark"]).startswith("# Generated"))

    def test_rust_backend_is_active(self):
        if os.environ.get("AURA_FORCE_PYTHON") == "1":
            self.skipTest("fallback requested")
        self.assertTrue(color.RUST_BACKEND)
        self.assertTrue(palette.RUST_BACKEND)


if __name__ == "__main__":
    unittest.main()
