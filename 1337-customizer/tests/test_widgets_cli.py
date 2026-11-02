"""Widget model and CLI parser tests."""

from __future__ import annotations

import datetime as dt
import unittest

from leet_customizer import widgets
from leet_customizer.cli import _parser


class WidgetModelTests(unittest.TestCase):
    def test_catalog_size(self):
        self.assertGreaterEqual(len(widgets.WIDGET_TYPES), 13)
        for kind, metadata in widgets.WIDGET_TYPES.items():
            self.assertTrue(metadata["name"])
            self.assertEqual(len(metadata["default"]), 4)

    def test_default_items(self):
        items = widgets.default_items()
        self.assertGreaterEqual(len(items), 4)
        identifiers = [item["id"] for item in items]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for item in items:
            self.assertTrue(0 <= item["x"] <= 1)
            self.assertTrue(0 <= item["y"] <= 1)
            self.assertLessEqual(item["x"] + item["w"], 1.0)
            self.assertLessEqual(item["y"] + item["h"], 1.0)

    def test_normalise_clamps_and_merges_options(self):
        item = widgets.normalise_item({
            "type": "clock", "x": -4, "y": 2, "w": 0.99, "h": 0.01,
            "opacity": 5, "scale": 0.1, "options": {"seconds": True},
        })
        self.assertEqual(item["x"], 0.0)
        self.assertLessEqual(item["y"], 0.94)
        self.assertLessEqual(item["x"] + item["w"], 1.0)
        self.assertLessEqual(item["h"], 0.9)
        self.assertEqual(item["opacity"], 1.0)
        self.assertEqual(item["scale"], 0.65)
        self.assertTrue(item["options"]["seconds"])

    def test_new_item_avoids_exact_stack(self):
        items = widgets.default_items()
        added = widgets.new_item("quote", items)
        self.assertNotEqual((added["x"], added["y"]), (0.0, 0.0))
        self.assertEqual(added["type"], "quote")

    def test_widget_css(self):
        css = widgets.widget_css(None)
        self.assertIn(".hw-card", css)
        self.assertIn(".hw-card.hw-paper", css)
        self.assertIn("background-color", css)
        self.assertIn(".hw-bar", css)

    def test_per_widget_style_fields_and_css(self):
        item = widgets.normalise_item({
            "id": "style-test", "type": "clock", "theme": "neon",
            "accent": "#ff3b8d", "bg": "#080b12", "fg": "#7df9ff",
            "radius": 4, "border_width": 3, "padding": 18,
            "scale": 1.3, "align": "center", "shadow": False,
        })
        self.assertEqual(item["theme"], "neon")
        self.assertEqual(item["radius"], 4)
        self.assertEqual(item["align"], "center")
        css = widgets.item_style_css(item, None)
        self.assertIn(".hw-style-style-test", css)
        self.assertIn("#ff3b8d", css)
        self.assertIn("border-radius: 4px", css)
        self.assertIn("border-width: 3px", css)
        self.assertIn("box-shadow: none", css)

    def test_layout_presets(self):
        self.assertGreaterEqual(len(widgets.LAYOUT_PRESETS), 4)
        for name, (_label, _items) in widgets.LAYOUT_PRESETS.items():
            items = widgets.layout_preset(name)
            self.assertTrue(items)
            for item in items:
                self.assertLessEqual(item["x"] + item["w"], 1.0)
                self.assertLessEqual(item["y"] + item["h"], 1.0)

    def test_clock_format(self):
        now = dt.datetime(2026, 11, 1, 17, 5, 9)
        value, date = widgets.format_clock(now, {"seconds": True, "date_format": "%Y-%m-%d"})
        self.assertEqual(value, "17:05:09")
        self.assertEqual(date, "2026-11-01")
        value, _date = widgets.format_clock(now, {"format": "%H.%M"})
        self.assertEqual(value, "17.05")

    def test_weather_labels(self):
        self.assertEqual(widgets.weather_label(0)[1], "Clear")
        self.assertEqual(widgets.weather_label(95)[1], "Thunderstorm")
        self.assertEqual(widgets.weather_label(999)[1], "Weather")


class CliParserTests(unittest.TestCase):
    def test_set_arguments(self):
        args = _parser().parse_args(["set", "/tmp/wall.png", "--fit", "crop", "--no-theme"])
        self.assertEqual(args.command, "set")
        self.assertEqual(args.path, "/tmp/wall.png")
        self.assertEqual(args.fit, "crop")
        self.assertTrue(args.no_theme)

    def test_video_and_widgets(self):
        args = _parser().parse_args(["video", "start", "/tmp/movie.mp4", "--monitor", "eDP-1"])
        self.assertEqual(args.command, "video")
        self.assertEqual(args.action, "start")
        args = _parser().parse_args(["widgets", "edit"])
        self.assertEqual(args.action, "edit")

    def test_restore_scope(self):
        args = _parser().parse_args(["restore", "--scope", "all"])
        self.assertEqual(args.scope, "all")


if __name__ == "__main__":
    unittest.main()
