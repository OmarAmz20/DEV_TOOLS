"""Theme generation and restore, run against a throwaway HOME and in-memory gsettings."""
from __future__ import annotations

import os
import shutil
import struct
import tempfile
import unittest
import zlib
from unittest import mock

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


def _png_chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def write_png(path):
    width = height = 32
    pixels = []
    for y in range(height):
        for x in range(width):
            pixels += (40 + x * 4, 90 + y * 3, 180 - x * 2)
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


class SystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = os.path.join(_ROOT, "test.png")
        write_png(cls.image)
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


class FakeSettings:
    def __init__(self, writable):
        self.writable = writable

    def is_writable(self, _key):
        return self.writable


class WallpaperBackendTest(unittest.TestCase):
    def test_feh_command_keeps_spaces_in_the_path(self):
        with tempfile.TemporaryDirectory(prefix="aura-feh-test-") as directory:
            image = os.path.join(directory, "wall paper.png")
            write_png(image)
            self._assert_feh(image)

    def _assert_feh(self, image):
        calls = []

        def fake_run(command, timeout=12):
            calls.append(command)
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(system, "detect_backend",
                               return_value={"name": "feh", "label": "feh"}), \
                mock.patch.object(system, "_run", side_effect=fake_run):
            result = system.apply_wallpaper(image)
        self.assertEqual(result["backend"], "feh")
        self.assertEqual(calls[-1][:3], ["feh", "--no-fehbg", "--bg-fill"])
        self.assertEqual(calls[-1][-1], image)


class BackendTest(unittest.TestCase):
    def setUp(self):
        system._BACKEND = None

    def tearDown(self):
        system._BACKEND = None

    def test_ubuntu_gnome_x11_uses_gsettings(self):
        with mock.patch.dict(os.environ, {
                "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": ""}, clear=False), \
                mock.patch.object(system, "_schema", return_value=FakeSettings(True)):
            result = system.detect_backend(refresh=True)
            session = system.session_label()
        self.assertEqual(result["name"], "gnome")
        self.assertIn("X11", session)

    def test_plain_x11_uses_feh(self):
        with mock.patch.dict(os.environ, {
                "XDG_CURRENT_DESKTOP": "XFCE",
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": ""}, clear=False), \
                mock.patch.object(system, "_schema", return_value=FakeSettings(False)), \
                mock.patch.object(system, "_dms_available", return_value=False), \
                mock.patch.object(system, "_hyprland", return_value=False), \
                mock.patch.object(system, "_wayland", return_value=False), \
                mock.patch.object(system.shutil, "which",
                                  side_effect=lambda name: "/usr/bin/feh" if name == "feh" else None):
            result = system.detect_backend(refresh=True)
            session = system.session_label()
        self.assertEqual(result["name"], "feh")
        self.assertIn("X11", session)


if __name__ == "__main__":
    unittest.main()
