import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from wallpaper_studio import video_wallpaper as video


class VideoStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patches = {
            "CONFIG_DIR": self.root / "config",
            "CACHE_DIR": self.root / "cache",
            "STATE_FILE": self.root / "config" / "video.json",
            "RUNTIME_FILE": self.root / "config" / "video-runtime.json",
            "LOG_FILE": self.root / "cache" / "video.log",
            "AUTOSTART_FILE": self.root / "config" / "autostart" / "video.desktop",
            "EXTENSION_DIR": self.root / "extensions" / video.EXTENSION_UUID,
        }
        patcher = mock.patch.multiple(video, **patches)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_and_round_trip(self):
        state = video.load()
        self.assertFalse(state["enabled"])
        self.assertTrue(state["mute"])
        self.assertEqual(state["fit"], "cover")
        path = self.root / "clip.mp4"
        path.write_bytes(b"not really a video")
        saved = video.save(path=str(path), mute=False, fit="contain", monitor=2)
        self.assertEqual(saved["path"], str(path.resolve()))
        self.assertFalse(saved["mute"])
        loaded = video.load()
        self.assertEqual(loaded["monitor"], 2)
        self.assertEqual(loaded["fit"], "contain")

    def test_invalid_values_are_clamped(self):
        video.save(fit="nonsense", monitor=-4)
        state = video.load()
        self.assertEqual(state["fit"], "cover")
        self.assertEqual(state["monitor"], 0)

    def test_video_extensions(self):
        self.assertTrue(video.is_video("movie.MP4"))
        self.assertTrue(video.is_video("clip.webm"))
        self.assertFalse(video.is_video("picture.png"))
        self.assertFalse(video.is_video(None))

    def test_stop_is_a_no_op_when_nothing_is_running(self):
        self.assertFalse(video.stop()["running"])
        self.assertFalse(video.STATE_FILE.exists())


if __name__ == "__main__":
    unittest.main()
