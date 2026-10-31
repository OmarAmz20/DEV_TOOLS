"""Theme generation and restore, run against a throwaway HOME and in-memory gsettings."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

_ROOT = tempfile.mkdtemp(prefix="aura-system-test-")
os.environ["HOME"] = _ROOT
os.environ["XDG_CONFIG_HOME"] = os.path.join(_ROOT, ".config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_ROOT, ".cache")
os.environ["XDG_DATA_HOME"] = os.path.join(_ROOT, ".local", "share")
os.environ["GSETTINGS_BACKEND"] = "memory"

from aura_studio import palette, store, system  # noqa: E402

system._dms_available = lambda: False
system._dms_current_wallpapers = lambda: {}
system._dconf = lambda *args: ""
system._gnome_terminal = lambda: False
system._apply_kitty = lambda p: False
system._sync = lambda: None
system._run_hooks = lambda p, mode: None


def write_ppm(path):
    width = height = 32
    pixels = []
    for y in range(height):
        for x in range(width):
            pixels += (40 + x * 4, 90 + y * 3, 180 - x * 2)
    with open(path, "wb") as handle:
        handle.write(f"P6\n{width} {height}\n255\n".encode())
        handle.write(bytes(pixels))


class SystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = os.path.join(_ROOT, "test.ppm")
        write_ppm(cls.image)
        cls.value = palette.from_image(cls.image)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_ROOT, ignore_errors=True)

    def test_apply_and_restore(self):
        config = store.load_config()
        options = {key: config.get(key) for key in
                   ("glass", "recolour_gtk", "terminal", "lock_screen", "icon_theme",
                    "cursor_theme", "font", "mono_font", "text_scale")}
        options.update({"terminal": False, "lock_screen": False, "glass": True})
        system.apply_theme(self.value["dark"], "dark", options, still=self.image)
        self.assertTrue(os.path.exists(store.THEME_CSS))
        self.assertTrue(os.path.isdir(os.path.join(system.THEMES_DIR, "Aura A")))
        with open(system.GTK3_CSS, encoding="utf-8") as handle:
            self.assertIn("aura-studio", handle.read())
        with open(system.GTK4_CSS, encoding="utf-8") as handle:
            self.assertIn("aura-studio", handle.read())
        with open(store.THEME_CSS, encoding="utf-8") as handle:
            self.assertIn("@define-color accent_bg_color", handle.read())

        system.restore()
        self.assertFalse(os.path.exists(store.THEME_CSS))
        self.assertFalse(os.path.exists(system.GTK3_CSS))
        self.assertFalse(os.path.exists(system.GTK4_CSS))
        self.assertFalse(os.path.exists(os.path.join(system.THEMES_DIR, "Aura A")))
        self.assertFalse(os.path.exists(store.ORIGINALS))
        self.assertEqual(store.load_state(), {})

    def test_apply_without_gtk_recolour(self):
        config = store.load_config()
        options = {key: config.get(key) for key in
                   ("glass", "recolour_gtk", "terminal", "lock_screen", "icon_theme",
                    "cursor_theme", "font", "mono_font", "text_scale")}
        options.update({"terminal": False, "recolour_gtk": False})
        system.apply_theme(self.value["light"], "light", options, still=self.image)
        self.assertFalse(os.path.exists(store.THEME_CSS))
        system.restore()


if __name__ == "__main__":
    unittest.main()
