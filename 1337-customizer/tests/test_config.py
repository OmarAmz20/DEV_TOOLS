"""Configuration and text helper tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from leet_customizer.config import Config, DEFAULTS, deep_merge
from leet_customizer import util


class ConfigTests(unittest.TestCase):
    def test_merge_preserves_defaults(self):
        merged = deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}})
        self.assertEqual(merged["a"], {"b": 3, "c": 2})

    def test_load_save_and_dot_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = Config(path)
            self.assertTrue(config.folders)
            config.set("appearance.radius", 22)
            config.save()
            again = Config(path)
            self.assertEqual(again.get("appearance.radius"), 22)
            self.assertEqual(again.get("missing.key", "fallback"), "fallback")

    def test_folders_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(Path(directory) / "config.json")
            folder = Path(directory) / "wallpapers"
            folder.mkdir()
            self.assertTrue(config.add_folder(folder))
            self.assertFalse(config.add_folder(folder))
            self.assertTrue(config.remove_folder(folder))
            self.assertFalse(config.remove_folder(folder))

    def test_normalisation_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(Path(directory) / "config.json")
            config.data["performance"]["thumb_threads"] = 999
            config.data["performance"]["thumb_size"] = 10
            config._normalise()
            self.assertLessEqual(config.get("performance.thumb_threads"), 16)
            self.assertGreaterEqual(config.get("performance.thumb_size"), 180)


class MarkedBlockTests(unittest.TestCase):
    def test_replace_and_strip(self):
        original = "user config\n"
        updated = util.replace_marked_block(original, "# begin", "# end", "include theme")
        self.assertIn("# begin", updated)
        self.assertIn("include theme", updated)
        stripped = util.strip_marked_block(updated, "# begin", "# end")
        self.assertEqual(stripped.strip(), "user config")

    def test_replace_is_idempotent(self):
        text = "a\n# begin\nold\n# end\nb\n"
        updated = util.replace_marked_block(text, "# begin", "# end", "new")
        self.assertEqual(updated.count("# begin"), 1)
        self.assertIn("new", updated)
        self.assertNotIn("old", updated)


if __name__ == "__main__":
    unittest.main()
