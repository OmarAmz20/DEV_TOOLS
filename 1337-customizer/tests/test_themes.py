"""Theme preset, CSS and import/export tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from leet_customizer import constants, palette, themes


class ThemeTests(unittest.TestCase):
    def test_presets_are_unique_and_complete(self):
        presets = themes.load_presets()
        self.assertGreaterEqual(len(presets), 20)
        identifiers = [preset["id"] for preset in presets]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for preset in presets:
            self.assertTrue(preset.get("name"))
            for variant in ("light", "dark"):
                seed = preset[variant]
                for key in ("bg", "surface", "accent"):
                    self.assertRegex(seed[key], r"^#[0-9a-fA-F]{6}$")

    def test_resolve_theme(self):
        theme = themes.resolve_theme("midnight-aurora", mode="dark")
        self.assertEqual(theme["variant"], "dark")
        self.assertEqual(len(theme["colors"]["ansi"]), 16)
        self.assertIn("structure", theme["style"])
        light = themes.resolve_theme("midnight-aurora", mode="light")
        self.assertEqual(light["variant"], "light")
        self.assertNotEqual(theme["colors"]["bg"], light["colors"]["bg"])

    def test_override_accent_and_radius(self):
        theme = themes.resolve_theme(
            "nord", mode="dark",
            overrides={"accent_override": "#ff2266", "radius": 4, "border_width": 2},
        )
        self.assertNotEqual(theme["colors"]["accent"], "#7aa2ff")
        self.assertGreaterEqual(
            __import__("leet_customizer.palette", fromlist=["contrast_ratio"]).contrast_ratio(
                theme["colors"]["accent"], theme["colors"]["surface"]
            ),
            4.0,
        )
        self.assertEqual(theme["style"]["radius"], 4)
        self.assertEqual(theme["style"]["border_width"], 2)

    def test_css_parses(self):
        for preset in themes.load_presets()[:5]:
            for mode in ("dark", "light"):
                theme = themes.resolve_theme(preset["id"], mode=mode)
                for version in (3, 4):
                    css = themes.generate_gtk_css(theme, gtk_version=version)
                    provider = Gtk.CssProvider()
                    errors = []
                    provider.connect(
                        "parsing-error",
                        lambda _provider, section, error, errors=errors: errors.append(
                            f"{section.to_string()}: {error.message}"
                        ),
                    )
                    provider.load_from_data(css.encode(), -1)
                    self.assertEqual(errors, [], preset["id"])

    def test_preview_css(self):
        theme = themes.resolve_theme("catppuccin", mode="dark", overrides={"radius": 20})
        css = themes.generate_preview_css(theme)
        self.assertIn(".hp-root", css)
        self.assertIn("border-radius: 26px", css)

    def test_terminal_themes(self):
        theme = themes.resolve_theme("gruvbox", mode="dark")
        for terminal in ("kitty", "foot", "ghostty", "alacritty", "wezterm"):
            generated = themes.terminal_theme(theme, terminal)
            self.assertIsNotNone(generated, terminal)
            self.assertIn(theme["colors"]["bg"], generated[1])

    def test_import_export_round_trip(self):
        theme = themes.resolve_theme("ocean-glass", mode="dark")
        payload = themes.export_theme(theme)
        imported = themes.import_theme(payload)
        self.assertIsNotNone(imported)
        self.assertEqual(imported["dark"]["accent"], theme["colors"]["accent"])
        resolved = themes.resolve_theme(imported["id"], mode="dark")
        self.assertTrue(resolved["colors"]["accent"])
        self.assertFalse(themes.import_theme({"no": "colours"}))

    def test_desired_variant_schedule(self):
        schedule = {"enabled": True, "light_start": "07:00", "dark_start": "19:00"}
        self.assertIn(themes.desired_variant("auto", schedule), ("light", "dark"))
        self.assertEqual(themes.desired_variant("dark", schedule), "dark")
        self.assertEqual(themes.desired_variant("light", schedule), "light")

    def test_custom_theme_save_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            original = constants.CONFIG_DIR
            try:
                # custom_theme_dir is derived lazily; patch constants for isolation.
                constants.CONFIG_DIR = Path(directory)
                preset = themes.theme_from_seeds(
                    "Test Look", light_bg="#ffffff", light_surface="#fafafa",
                    light_accent="#3366ff", dark_bg="#101018",
                    dark_surface="#181824", dark_accent="#7aa2ff",
                )
                themes.save_custom_theme(preset)
                found = [item for item in themes.load_custom_themes() if item["id"] == "test-look"]
                self.assertEqual(len(found), 1)
                self.assertTrue(themes.delete_custom_theme("test-look"))
            finally:
                constants.CONFIG_DIR = original


if __name__ == "__main__":
    unittest.main()
