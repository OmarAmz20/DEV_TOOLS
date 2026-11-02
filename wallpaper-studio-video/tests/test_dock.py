"""Dock configuration and app-entry tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wallpaper_studio import dock


class DockConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.old = (dock.CONFIG, dock.PID, dock.STATE, dock.LOCK)
        dock.CONFIG = root / "dock.json"
        dock.PID = root / "dock.pid"
        dock.STATE = root / "dock-state.json"
        dock.LOCK = root / "dock.lock"

    def tearDown(self):
        dock.CONFIG, dock.PID, dock.STATE, dock.LOCK = self.old
        self.temporary.cleanup()

    def test_defaults(self):
        config = dock.normalise({})
        self.assertEqual(config["position"], "bottom")
        self.assertIn(config["style"], dock.STYLES)
        self.assertTrue(any(not app.get("separator") for app in config["apps"]))
        self.assertGreaterEqual(config["icon_size"], 20)

    def test_invalid_values_are_clamped(self):
        config = dock.normalise({
            "position": "middle", "alignment": "diagonal", "style": "invisible",
            "opacity": 99, "icon_size": 2, "spacing": -4, "radius": 500,
        })
        self.assertEqual(config["position"], "bottom")
        self.assertEqual(config["alignment"], "center")
        self.assertEqual(config["style"], "glass")
        self.assertLessEqual(config["opacity"], 1.0)
        self.assertGreaterEqual(config["icon_size"], 20)
        self.assertGreaterEqual(config["spacing"], 0)
        self.assertLessEqual(config["radius"], 40)

    def test_accent_colour_is_validated(self):
        self.assertEqual(dock.normalise({"accent": "#12abEF"})["accent"], "#12abEF")
        self.assertEqual(dock.normalise({"accent": "red"})["accent"], "")
        self.assertEqual(dock.normalise({"accent": "#GGGGGG"})["accent"], "")

    def test_separators_are_trimmed(self):
        apps = [
            {"separator": True},
            {"label": "One", "command": "one"},
            {"separator": True},
            {"separator": True},
            {"label": "Two", "command": "two"},
            {"separator": True},
        ]
        config = dock.normalise({"apps": apps})
        self.assertEqual([bool(app.get("separator")) for app in config["apps"]],
                         [False, True, False])

    def test_save_add_remove_and_move(self):
        saved = dock.save({"enabled": True, "position": "left", "apps": dock.default_apps()})
        self.assertEqual(saved["position"], "left")
        loaded = dock.load()
        self.assertTrue(loaded["enabled"])
        self.assertGreaterEqual(len(loaded["apps"]), 3)
        added = dock.add_app({"label": "Editor", "icon": "accessories-text-editor",
                              "command": "gedit"})
        editor = next(app for app in added["apps"] if app.get("label") == "Editor")
        self.assertTrue(editor["id"])
        moved = dock.move_app(editor["id"], -1)
        self.assertIn(editor["id"], [app.get("id") for app in moved["apps"]])
        removed = dock.remove_app(editor["id"])
        self.assertNotIn(editor["id"], [app.get("id") for app in removed["apps"]])

    def test_css_and_rgba(self):
        css = dock.css(dock.normalise({"style": "neon", "accent": "#ff3b8d"}))
        self.assertIn(".dock-card", css)
        self.assertIn(".dock-button", css)
        self.assertIn("#ff3b8d", css)
        self.assertRegex(dock._rgba("#102030", .5), r"^rgba\(16,32,48,0\.50\)$")

    def test_autostart_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            old_home = __import__("os").environ.get("XDG_CONFIG_HOME")
            __import__("os").environ["XDG_CONFIG_HOME"] = directory
            try:
                dock.set_autostart(True)
                path = Path(directory) / "autostart" / "wallpaper-studio-video-dock.desktop"
                self.assertTrue(path.is_file())
                self.assertIn("dock start", path.read_text(encoding="utf-8"))
                dock.set_autostart(False)
                self.assertFalse(path.exists())
            finally:
                if old_home is None:
                    __import__("os").environ.pop("XDG_CONFIG_HOME", None)
                else:
                    __import__("os").environ["XDG_CONFIG_HOME"] = old_home


if __name__ == "__main__":
    unittest.main()
