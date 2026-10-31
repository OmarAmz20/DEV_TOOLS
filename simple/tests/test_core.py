"""Small regression tests for the core; they never touch the real desktop settings."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

from wallpaper_lite import core  # noqa: E402


def make_png(path, width=64, height=64):
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height)
    pixbuf.fill(0x3366CCFF)
    # A red band gives the palette something vivid to choose.
    red = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, max(1, height // 4))
    red.fill(0xCC2200FF)
    red.copy_area(0, 0, width, red.get_height(), pixbuf, 0, 0)
    pixbuf.savev(path, "png", [], [])
    return path


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wallpaper-lite-test-")
        self.config = os.path.join(self.tmp, "config")
        self.cache = os.path.join(self.tmp, "cache")
        self.patches = [
            mock.patch.object(core, "CONFIG_DIR", self.config),
            mock.patch.object(core, "CONFIG", os.path.join(self.config, "config.json")),
            mock.patch.object(core, "STATE", os.path.join(self.config, "state.json")),
            mock.patch.object(core, "ORIGINALS", os.path.join(self.config, "originals.json")),
            mock.patch.object(core, "THEME_CSS", os.path.join(self.config, "theme.css")),
            mock.patch.object(core, "LOCK", os.path.join(self.config, ".lock")),
            mock.patch.object(core, "CACHE_DIR", self.cache),
            mock.patch.object(core, "GTK3_CSS", os.path.join(self.tmp, "gtk-3.0", "gtk.css")),
            mock.patch.object(core, "GTK4_CSS", os.path.join(self.tmp, "gtk-4.0", "gtk.css")),
            mock.patch.object(core, "THEMES_DIR", os.path.join(self.tmp, "themes")),
            mock.patch.object(core, "runtime_dir", lambda: os.path.join(self.tmp, "run")),
            mock.patch.object(core, "_get", lambda schema, key: None),
            mock.patch.object(core, "_set", lambda schema, key, value: True),
            mock.patch.object(core, "_set_background", lambda path: True),
            mock.patch.object(core, "_stop_helper", lambda: None),
            mock.patch.object(core, "_start_helper", lambda: False),
        ]
        for patch in self.patches:
            patch.start()
        os.makedirs(os.path.join(self.tmp, "run"), mode=0o700, exist_ok=True)
        self.wall = make_png(os.path.join(self.tmp, "wall.png"))

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_palette_is_valid_and_readable(self):
        palette = core.palette_from_image(self.wall)
        self.assertTrue(core._palette_ok(palette))
        self.assertGreaterEqual(core.contrast(palette["light"]["ink"], palette["light"]["paper"]), 4.0)
        self.assertGreaterEqual(core.contrast(palette["dark"]["ink"], palette["dark"]["paper"]), 4.0)
        self.assertGreaterEqual(core.contrast(palette["light"]["accent"], palette["light"]["paper"]), 3.0)
        self.assertGreaterEqual(core.contrast(palette["dark"]["accent"], palette["dark"]["paper"]), 4.5)

    def test_monochrome_palette(self):
        palette = core.build_palette([(0.0, 0.0, 0.5)] * 500)
        self.assertTrue(core._palette_ok(palette))
        self.assertGreaterEqual(core.contrast(palette["light"]["ink"], palette["light"]["paper"]), 4.0)

    def test_validate_rejects_bad_files(self):
        bad = os.path.join(self.tmp, "not-a-picture.jpg")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("hello")
        with self.assertRaises(ValueError):
            core.validate_image(bad)
        with self.assertRaises(ValueError):
            core.validate_image(self.wall + ".txt")

    def test_validate_rejects_pixel_bomb(self):
        class FakeFormat:
            @staticmethod
            def get_name():
                return "png"

        fake = (FakeFormat(), 20_000, 20_000)
        with mock.patch.object(core.GdkPixbuf.Pixbuf, "get_file_info", return_value=fake):
            with self.assertRaises(ValueError):
                core.validate_image(self.wall)

    def test_css_import_round_trip_preserves_user_css(self):
        os.makedirs(os.path.dirname(core.GTK4_CSS), exist_ok=True)
        original = ("/* this line mentions /* wallpaper-lite */ but is not an import */\n"
                    "window { color: red; }\n")
        with open(core.GTK4_CSS, "w", encoding="utf-8") as f:
            f.write(original)

        core.add_import(core.GTK4_CSS)
        with open(core.GTK4_CSS, encoding="utf-8") as f:
            after = f.read()
        self.assertTrue(after.startswith('@import url("file://'))
        self.assertIn("window { color: red; }", after)
        self.assertIn("this line mentions", after)

        core.remove_import(core.GTK4_CSS)
        with open(core.GTK4_CSS, encoding="utf-8") as f:
            self.assertEqual(f.read(), original)

    def test_apply_and_restore(self):
        message = core.set_wallpaper(self.wall)
        self.assertIn("applied", message.lower())
        state = core.load_state()
        self.assertEqual(state["wallpaper"], self.wall)
        self.assertTrue(core._palette_ok(state["palette"]))
        self.assertTrue(os.path.isfile(core.THEME_CSS))
        self.assertTrue(os.path.isfile(core.GTK3_CSS))
        self.assertTrue(os.path.isfile(core.GTK4_CSS))
        for name in core.OUR_THEMES:
            self.assertTrue(os.path.isfile(
                os.path.join(core.THEMES_DIR, name, "gtk-3.0", "gtk.css")))

        core.restore()
        self.assertEqual(core.load_state(), {})
        self.assertFalse(os.path.exists(core.THEME_CSS))
        self.assertFalse(os.path.exists(core.GTK3_CSS))
        self.assertFalse(os.path.exists(core.GTK4_CSS))
        for name in core.OUR_THEMES:
            self.assertFalse(os.path.exists(os.path.join(core.THEMES_DIR, name)))

    def test_thumbnail_cache(self):
        first = core.thumbnail(self.wall, 216, 122)
        self.assertLessEqual(first.get_width(), 216)
        self.assertLessEqual(first.get_height(), 122)
        files = os.listdir(os.path.join(self.cache, "thumbs"))
        self.assertEqual(len(files), 1)
        second = core.thumbnail(self.wall, 216, 122)
        self.assertEqual((second.get_width(), second.get_height()),
                         (first.get_width(), first.get_height()))
        self.assertEqual(len(os.listdir(os.path.join(self.cache, "thumbs"))), 1)


if __name__ == "__main__":
    unittest.main()
