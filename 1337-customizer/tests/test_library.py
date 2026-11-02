"""Library database and scanner tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from leet_customizer.library import Library, probe_media


def make_image(path: Path, size=(40, 30), color=(80, 120, 200)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.folder = self.root / "wallpapers"
        self.folder.mkdir()
        make_image(self.folder / "one.png", (40, 30), (80, 120, 200))
        make_image(self.folder / "two.jpg", (30, 40), (220, 80, 90))
        self.db = self.root / "library.db"
        self.library = Library(self.db)

    def tearDown(self):
        self.temporary.cleanup()

    def test_scan_and_items(self):
        result = self.library.scan([self.folder], recursive=True)
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["total"], 2)
        items = self.library.items()
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item.width > 0 and item.height > 0 for item in items))
        self.assertTrue(all(item.favorite is False for item in items))
        # A second scan should not duplicate entries.
        again = self.library.scan([self.folder], recursive=True)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["unchanged"], 2)
        self.assertEqual(self.library.stats()["total"], 2)

    def test_nested_roots_are_deduplicated(self):
        nested = self.folder / "nested"
        nested.mkdir()
        make_image(nested / "three.png")
        result = self.library.scan([self.folder, nested], recursive=True)
        self.assertEqual(result["total"], 3)
        self.assertEqual(self.library.stats()["total"], 3)

    def test_removed_root_is_pruned(self):
        other = self.root / "other"
        other.mkdir()
        make_image(other / "other.png")
        self.library.scan([self.folder, other], recursive=True)
        self.assertEqual(self.library.stats()["total"], 3)
        result = self.library.scan([self.folder], recursive=True)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(self.library.stats()["total"], 2)

    def test_favorites_and_filters(self):
        self.library.scan([self.folder])
        item = self.library.items()[0]
        self.assertTrue(self.library.toggle_favorite(item.path))
        stats = self.library.stats()
        self.assertEqual(stats["favorites"], 1)
        self.assertFalse(self.library.toggle_favorite(item.path))
        self.assertFalse(self.library.toggle_favorite(str(self.folder / "missing.png")))

    def test_history_and_next(self):
        self.library.scan([self.folder])
        paths = [item.path for item in self.library.items()]
        self.library.add_history(paths[0], "image", "all", "crop")
        self.library.add_history(paths[1], "image", "eDP-1", "fit")
        recent = self.library.recent(10)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0]["path"], paths[1])
        previous = self.library.history_item(1)
        self.assertEqual(previous["path"], paths[0])
        next_path = self.library.next_path(order="shuffle", current=paths[0])
        self.assertIn(next_path, paths)
        self.library.clear_history()
        self.assertEqual(self.library.recent(), [])

    def test_probe_media(self):
        width, height, kind, _duration = probe_media(self.folder / "one.png")
        self.assertEqual((width, height, kind), (40, 30, "image"))


if __name__ == "__main__":
    unittest.main()
