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

from aura_studio import core, library, palette, store, system  # noqa: E402

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

    def test_custom_css_is_appended_and_kept_on_restore(self):
        self.addCleanup(system.restore)
        self.addCleanup(lambda: os.path.exists(store.CUSTOM_CSS) and
                        os.remove(store.CUSTOM_CSS))
        store.write_text(store.CUSTOM_CSS, ".my-extra { border-radius: 3px; }")
        config = store.load_config()
        options = {key: config.get(key) for key in core.OPTION_KEYS}
        options.update({"terminal": False, "lock_screen": False, "glass": True})
        system.apply_theme(self.value["dark"], "dark", options, still=self.image)
        with open(store.THEME_CSS, encoding="utf-8") as handle:
            self.assertIn(".my-extra", handle.read())
        self.assertTrue(os.path.exists(store.CUSTOM_CSS))
        system.restore()
        self.assertTrue(os.path.exists(store.CUSTOM_CSS))

    def test_restore_does_not_clobber_a_later_theme_change(self):
        original = system._get_string("org.gnome.desktop.interface", "gtk-theme")
        try:
            config = store.load_config()
            options = {key: config.get(key) for key in core.OPTION_KEYS}
            options.update({"terminal": False, "lock_screen": False})
            system.apply_theme(self.value["dark"], "dark", options, still=self.image)
            applied = system._get_string("org.gnome.desktop.interface", "gtk-theme")
            self.assertIn(applied, system.OUR_THEMES)
            system._set_string("org.gnome.desktop.interface", "gtk-theme", "UserChosenTheme")
            system._sync()
            system.restore()
            self.assertEqual(
                system._get_string("org.gnome.desktop.interface", "gtk-theme", ""),
                "UserChosenTheme")
        finally:
            system._set_string("org.gnome.desktop.interface", "gtk-theme",
                               original or "Adwaita")
            system._sync()
            with __import__("contextlib").suppress(FileNotFoundError):
                os.remove(store.ORIGINALS)
            store.save_state({})

    def test_apply_without_gtk_recolour(self):
        config = store.load_config()
        options = {key: config.get(key) for key in
                   ("glass", "recolour_gtk", "terminal", "lock_screen", "icon_theme",
                    "cursor_theme", "font", "mono_font", "text_scale")}
        options.update({"terminal": False, "recolour_gtk": False})
        system.apply_theme(self.value["light"], "light", options, still=self.image)
        self.assertFalse(os.path.exists(store.THEME_CSS))
        system.restore()

    def test_cursor_size_is_applied_and_restored(self):
        self.addCleanup(system.restore)
        original = system._get_int("org.gnome.desktop.interface", "cursor-size", 24)
        config = store.load_config()
        options = {key: config.get(key) for key in
                   ("glass", "recolour_gtk", "terminal", "lock_screen", "icon_theme",
                    "cursor_theme", "font", "mono_font", "text_scale")}
        options.update({"terminal": False, "recolour_gtk": False, "cursor_size": 48})
        system.apply_theme(self.value["dark"], "dark", options, still=self.image)
        self.assertEqual(
            system._get_int("org.gnome.desktop.interface", "cursor-size"), 48)
        system.restore()
        self.assertEqual(
            system._get_int("org.gnome.desktop.interface", "cursor-size", 24),
            original)


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
                mock.patch.object(system, "_stop_desktop_window"), \
                mock.patch.object(system, "_run", side_effect=fake_run):
            result = system.apply_wallpaper(image)
        self.assertEqual(result["backend"], "feh")
        self.assertEqual(calls[-1][:3], ["feh", "--no-fehbg", "--bg-fill"])
        self.assertEqual(calls[-1][-1], image)

    def test_desktop_backend_starts_a_window(self):
        with tempfile.TemporaryDirectory(prefix="aura-desktop-test-") as directory:
            image = os.path.join(directory, "wall paper.png")
            write_png(image)
            with mock.patch.object(system, "detect_backend",
                                   return_value={"name": "desktop",
                                                 "label": "X11 desktop window"}), \
                    mock.patch.object(system, "_start_desktop_window") as start:
                result = system.apply_wallpaper(image)
        self.assertEqual(result["backend"], "desktop")
        start.assert_called_once_with(image, "fill")

    def test_feh_receives_the_scaling_mode(self):
        with tempfile.TemporaryDirectory(prefix="aura-feh-mode-test-") as directory:
            image = os.path.join(directory, "wall.png")
            write_png(image)
            calls = []

            def fake_run(command, timeout=12):
                calls.append(command)
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(system, "detect_backend",
                                   return_value={"name": "feh", "label": "feh"}), \
                    mock.patch.object(system, "_stop_desktop_window"), \
                    mock.patch.object(system, "_run", side_effect=fake_run):
                result = system.apply_wallpaper(image, mode="fit")
        self.assertEqual(result["mode"], "fit")
        self.assertEqual(calls[-1][:3], ["feh", "--no-fehbg", "--bg-max"])

    def test_gnome_receives_the_scaling_option(self):
        with tempfile.TemporaryDirectory(prefix="aura-gnome-mode-test-") as directory:
            image = os.path.join(directory, "wall.png")
            write_png(image)
            values = []

            def fake_set(schema, key, value):
                values.append((schema, key, value))
                return True

            with mock.patch.object(system, "detect_backend",
                                   return_value={"name": "gnome", "label": "GNOME"}), \
                    mock.patch.object(system, "_stop_desktop_window"), \
                    mock.patch.object(system, "_set_string", side_effect=fake_set):
                system.apply_wallpaper(image, mode="tile")
        self.assertIn(("org.gnome.desktop.background", "picture-options", "wallpaper"), values)


class AutostartTest(unittest.TestCase):
    def tearDown(self):
        system.set_autostart(False)

    def test_login_entry_uses_the_configured_delay(self):
        system.set_autostart(True, profile="my-profile", delay=23)
        with open(system.AUTOSTART_FILE, encoding="utf-8") as handle:
            entry = handle.read()
        self.assertIn("--delay 23", entry)
        system.set_autostart(False)

    def test_login_entry_reapplies_the_saved_look(self):
        system.set_autostart(True, profile="my-profile")
        self.assertTrue(system.autostart_enabled())
        self.assertTrue(os.path.exists(system.AUTOSTART_FILE))
        with open(system.AUTOSTART_FILE, encoding="utf-8") as handle:
            entry = handle.read()
        self.assertIn("Exec=", entry)
        self.assertIn("apply-saved", entry)
        self.assertIn("--profile my-profile", entry)
        self.assertIn("--delay 8", entry)
        self.assertIn("X-GNOME-Autostart-enabled=true", entry)

        system.set_autostart(False)
        self.assertFalse(system.autostart_enabled())
        self.assertFalse(os.path.exists(system.AUTOSTART_FILE))


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

    def test_a_pinned_backend_overrides_automatic_detection(self):
        with mock.patch.dict(os.environ, {
                "XDG_CURRENT_DESKTOP": "XFCE",
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": ""}, clear=False), \
                mock.patch.object(system, "_schema", return_value=FakeSettings(False)), \
                mock.patch.object(system, "_dms_available", return_value=False), \
                mock.patch.object(system, "_hyprland", return_value=False), \
                mock.patch.object(system, "_wayland", return_value=False), \
                mock.patch.object(system, "_desktop_window_available", return_value=True), \
                mock.patch.object(system.shutil, "which",
                                  side_effect=lambda name: "/usr/bin/feh" if name == "feh" else None):
            result = system.detect_backend(refresh=True, preferred="desktop")
        self.assertEqual(result["name"], "desktop")
        self.assertFalse(result["fallback"])

    def test_gnome_can_use_host_gsettings_when_gio_is_isolated(self):
        with mock.patch.dict(os.environ, {
                "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": ""}, clear=False), \
                mock.patch.object(system, "_schema", return_value=None), \
                mock.patch.object(system, "_host_gsettings_writable", return_value=True), \
                mock.patch.object(system, "_dms_available", return_value=False), \
                mock.patch.object(system, "_hyprland", return_value=False), \
                mock.patch.object(system, "_wayland", return_value=False):
            result = system.detect_backend(refresh=True)
        self.assertEqual(result["name"], "gnome")

    def test_gnome_strings_also_reach_the_host_backend(self):
        with mock.patch.object(system, "_set_string", return_value=False), \
                mock.patch.object(system, "_host_gsettings_enabled", return_value=True), \
                mock.patch.object(system, "_host_gsettings_set", return_value=True) as host_set:
            ok = system._gnome_set_string("org.gnome.desktop.background",
                                          "picture-uri", "file:///wall.png")
        self.assertTrue(ok)
        host_set.assert_called_once_with("org.gnome.desktop.background",
                                         "picture-uri", "file:///wall.png")

    def test_unavailable_pinned_backend_falls_back(self):
        with mock.patch.dict(os.environ, {
                "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": ""}, clear=False), \
                mock.patch.object(system, "_schema", return_value=FakeSettings(True)), \
                mock.patch.object(system, "_dms_available", return_value=False), \
                mock.patch.object(system, "_hyprland", return_value=False), \
                mock.patch.object(system, "_wayland", return_value=False):
            result = system.detect_backend(refresh=True, preferred="awww")
        self.assertEqual(result["name"], "gnome")
        self.assertTrue(result["fallback"])

    def test_locked_gnome_x11_uses_desktop_window(self):
        with mock.patch.dict(os.environ, {
                "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                "XDG_SESSION_TYPE": "x11",
                "DISPLAY": ":0",
                "WAYLAND_DISPLAY": ""}, clear=False), \
                mock.patch.object(system, "_schema", return_value=FakeSettings(False)), \
                mock.patch.object(system, "_dms_available", return_value=False), \
                mock.patch.object(system, "_hyprland", return_value=False), \
                mock.patch.object(system, "_wayland", return_value=False), \
                mock.patch.object(system, "_desktop_window_available", return_value=True):
            result = system.detect_backend(refresh=True)
        self.assertEqual(result["name"], "desktop")
        self.assertIn("desktop", result["label"].lower())


class SavedLookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = os.path.join(_ROOT, "saved.png")
        write_png(cls.image)
        cls.value = palette.from_image(cls.image)
        cls.config = {
            "autostart_profile": None,
            "wallpaper_mode": "fit",
            "slideshow_order": "shuffle",
            "mode": "dark",
            "light_from": 7,
            "dark_from": 19,
        }

    def test_apply_saved_prefers_a_profile(self):
        profile = {"id": "p1", "name": "Night", "palette": self.value}
        config = {**self.config, "autostart_profile": "p1"}
        with mock.patch.object(core.store, "load_config", return_value=config), \
                mock.patch.object(core.store, "load_profiles", return_value=[profile]), \
                mock.patch.object(core, "apply_profile", return_value={"profile": "p1"}) as apply:
            result = core.apply_saved()
        self.assertEqual(result, {"profile": "p1"})
        apply.assert_called_once_with(profile)

    def test_apply_saved_restores_wallpaper_and_palette(self):
        state = {"wallpaper": self.image, "palette": self.value}
        with mock.patch.object(core.store, "load_config", return_value=self.config), \
                mock.patch.object(core.store, "load_profiles", return_value=[]), \
                mock.patch.object(core.store, "load_state", return_value=state), \
                mock.patch.object(core, "apply_wallpaper", return_value="wallpaper") as apply:
            result = core.apply_saved()
        self.assertEqual(result, "wallpaper")
        apply.assert_called_once_with(self.image, self.config,
                                      palette_value=self.value, match_colors=True)

    def test_apply_saved_can_restore_only_colours(self):
        state = {"palette": self.value, "palette_source": self.image, "still": self.image}
        with mock.patch.object(core.store, "load_config", return_value=self.config), \
                mock.patch.object(core.store, "load_profiles", return_value=[]), \
                mock.patch.object(core.store, "load_state", return_value=state), \
                mock.patch.object(core, "apply_colours", return_value="dark") as apply:
            result = core.apply_saved()
        self.assertEqual(result["mode"], "dark")
        apply.assert_called_once()
        self.assertEqual(apply.call_args.kwargs["source"], self.image)

    def test_nothing_saved_returns_none(self):
        with mock.patch.object(core.store, "load_config", return_value=self.config), \
                mock.patch.object(core.store, "load_profiles", return_value=[]), \
                mock.patch.object(core.store, "load_state", return_value={}):
            self.assertIsNone(core.apply_saved())


class NextPathTest(unittest.TestCase):
    def test_sequential_walks_the_sorted_folder(self):
        paths = ["/p/b.png", "/p/a.png", "/p/c.png"]
        self.assertEqual(library.next_path(paths, "/p/a.png", "sequential"), "/p/b.png")
        self.assertEqual(library.next_path(paths, "/p/c.png", "sequential"), "/p/a.png")

    def test_sequential_starts_at_the_first_wallpaper(self):
        paths = ["/p/b.png", "/p/a.png"]
        self.assertEqual(library.next_path(paths, None, "sequential"), "/p/a.png")


class ConfigTest(unittest.TestCase):
    def test_invalid_values_are_normalised(self):
        original = store.load_config()
        try:
            store.write_json(store.CONFIG, {
                "glass": "false",
                "glass_opacity": 9,
                "wallpaper_backend": "magic",
                "terminal_targets": ["kitty", "unknown", "kitty"],
                "autostart_delay": -5,
                "slide_minutes": "many",
                "accent": "red",
            })
            config = store.load_config()
            self.assertFalse(config["glass"])
            self.assertEqual(config["glass_opacity"], 1.0)
            self.assertEqual(config["wallpaper_backend"], "auto")
            self.assertEqual(config["terminal_targets"], ["kitty"])
            self.assertEqual(config["autostart_delay"], 0)
            self.assertEqual(config["slide_minutes"], 0)
            self.assertIsNone(config["accent"])
        finally:
            store.write_json(store.CONFIG, original)

    def test_terminal_targets_can_be_limited(self):
        with mock.patch.object(system, "terminal_targets",
                               return_value=["kitty", "gnome-terminal"]):
            self.assertEqual(
                system.selected_terminal_targets({"terminal_targets": ["kitty"]}),
                ["kitty"])
            self.assertEqual(
                system.selected_terminal_targets({"terminal_targets": []}), [])
            self.assertEqual(
                system.selected_terminal_targets({"terminal_targets": None}),
                ["kitty", "gnome-terminal"])
            self.assertEqual(
                system.selected_terminal_targets({"terminal_targets": ["kitty"]},
                                                 config={}),
                ["kitty"])


if __name__ == "__main__":
    unittest.main()
