"""Backend helpers that can be tested without touching the desktop."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leet_customizer import constants, desktop, video, wallpaper
from leet_customizer.config import Config


class WallpaperBackendTests(unittest.TestCase):
    def test_fit_maps(self):
        self.assertEqual(wallpaper.FIT_TO_AWWW["crop"], "crop")
        self.assertEqual(wallpaper.FIT_TO_AWWW["center"], "no")
        self.assertEqual(wallpaper.FIT_TO_GNOME["fit"], "scaled")
        self.assertEqual(wallpaper.FIT_TO_GNOME["stretch"], "stretched")
        self.assertEqual(wallpaper.FIT_TO_HYPRPAPER["crop"], "cover")
        self.assertEqual(wallpaper.FIT_TO_SWAYBG["fit"], "fit")

    def test_copy_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "picture.png"
            source.write_bytes(b"fake image for copy")
            old = constants.APPLIED_DIR
            try:
                constants.APPLIED_DIR = root / "applied"
                copied = wallpaper._copy_applied(source)
                self.assertTrue(copied.exists())
                self.assertTrue(copied.read_bytes().startswith(b"fake image"))
                self.assertEqual(wallpaper._copy_applied(source), copied)
            finally:
                constants.APPLIED_DIR = old

    def test_state_default(self):
        state = wallpaper.state()
        self.assertIsInstance(state, dict)
        self.assertIn("running", video.state())


class VideoOptionsTests(unittest.TestCase):
    def test_mpv_options(self):
        config = Config("/tmp/1337-video-test.json")
        config.data["video"].update({"fit": "crop", "muted": True, "loop": True,
                                     "speed": 1.25, "hwdec": "auto-safe"})
        options = video._mpv_options(config)
        self.assertIn("loop-file=inf", options)
        self.assertIn("no-audio", options)
        self.assertIn("speed=1.25", options)
        self.assertIn("hwdec=auto-safe", options)
        self.assertIn("panscan=1.0", options)
        config.data["video"]["fit"] = "fit"
        self.assertIn("panscan=0.0", video._mpv_options(config))

    def test_engine_status_is_boolean(self):
        self.assertIsInstance(video.engine_available(), bool)
        self.assertIsInstance(video.engine_source(), str)


class DesktopHelpersTests(unittest.TestCase):
    def test_monitor_shape(self):
        monitors = desktop.monitors()
        self.assertTrue(monitors)
        for monitor in monitors:
            self.assertIn("name", monitor)
            self.assertGreater(monitor["width"], 0)
            self.assertGreater(monitor["height"], 0)
            self.assertGreater(monitor["scale"], 0)

    def test_environment_report(self):
        report = desktop.environment_report()
        self.assertIn("backends", report)
        self.assertIn("tools", report)
        self.assertIn("monitors", report)

    def test_theme_slots_are_named(self):
        self.assertEqual(len(desktop.THEME_SLOTS), 2)
        self.assertTrue(all(slot.startswith("L33T-") for slot in desktop.THEME_SLOTS))


if __name__ == "__main__":
    unittest.main()
