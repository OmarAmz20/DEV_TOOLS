"""Virtualised-friendly thumbnail and preview cache.

Workers only touch files; Gdk.Texture objects are always created on the GTK
main thread.  The grid model asks for a thumbnail when a cell is bound, so a
10,000-picture library only decodes what is actually visible.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from . import constants
from .util import atomic_write_bytes, run

try:
    from gi.repository import Gdk, GLib
except Exception:  # pragma: no cover
    Gdk = None
    GLib = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None


def _cache_key(path: str, mtime: float, size: int, kind: str, width: int) -> str:
    raw = f"{path}|{int(mtime * 1000)}|{size}|{kind}|{width}|v2"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _video_frame(path: Path, at: float = 1.0) -> bytes | None:
    for seek in (at, 0.0, 0.2):
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(seek),
            "-i", str(path), "-frames:v", "1", "-f", "image2pipe",
            "-vcodec", "png", "pipe:1",
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=22, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout:
            return result.stdout
    return None


def _make_thumb(source: Path, width: int, kind: str) -> bytes | None:
    if Image is None:
        return None
    if kind == "video":
        data = _video_frame(source)
        if not data:
            return None
        try:
            image = Image.open(io.BytesIO(data))
        except Exception:
            return None
    else:
        try:
            image = Image.open(source)
            image.load()
            if getattr(image, "is_animated", False):
                image.seek(0)
        except Exception:
            data = _video_frame(source)
            if not data:
                return None
            image = Image.open(io.BytesIO(data))
    if ImageOps is not None:
        image = ImageOps.exif_transpose(image)
    height = max(1, round(width * 9 / 16))
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (17, 17, 22))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")
    if ImageOps is not None:
        image = ImageOps.fit(image, (width, height), Image.Resampling.LANCZOS,
                             centering=(0.5, 0.5))
    else:
        image.thumbnail((width, height))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=82, optimize=True, progressive=True)
    return output.getvalue()


def _make_preview(source: Path, max_side: int, kind: str) -> bytes | None:
    if Image is None:
        return None
    if kind == "video":
        data = _video_frame(source)
        if not data:
            return None
        try:
            image = Image.open(io.BytesIO(data))
        except Exception:
            return None
    else:
        try:
            image = Image.open(source)
            image.load()
            if getattr(image, "is_animated", False):
                image.seek(0)
        except Exception:
            data = _video_frame(source)
            if not data:
                return None
            image = Image.open(io.BytesIO(data))
    if ImageOps is not None:
        image = ImageOps.exif_transpose(image)
    if image.mode != "RGB":
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            background = Image.new("RGB", image.size, (17, 17, 22))
            rgba = image.convert("RGBA")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=87, optimize=True, progressive=True)
    return output.getvalue()


class ThumbCache:
    def __init__(self, *, width: int = 360, workers: int = 4, max_mb: int = 512,
                 preview_max: int = 1600) -> None:
        self.width = max(160, int(width))
        self.max_mb = max(64, int(max_mb))
        self.preview_max = max(800, int(preview_max))
        self.threads = max(1, int(workers))
        self.executor = ThreadPoolExecutor(max_workers=self.threads)
        self.memory: OrderedDict[str, object] = OrderedDict()
        self.previews: OrderedDict[str, object] = OrderedDict()
        self.pending: dict[str, list[Callable]] = {}
        self.preview_pending: dict[str, list[Callable]] = {}
        self.hits = 0
        self.misses = 0
        self.generated = 0
        constants.THUMB_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _disk_path(self, key: str) -> Path:
        return constants.THUMB_DIR / key[:2] / f"{key}.jpg"

    def _remember(self, key: str, texture) -> None:
        self.memory[key] = texture
        self.memory.move_to_end(key)
        while len(self.memory) > 180:
            self.memory.popitem(last=False)

    def get_texture(self, path: str, mtime: float, size: int, kind: str, callback: Callable) -> None:
        key = _cache_key(path, mtime, size, kind, self.width)
        if key in self.memory:
            self.hits += 1
            callback(self.memory[key])
            return
        disk = self._disk_path(key)
        if disk.exists():
            try:
                texture = Gdk.Texture.new_from_filename(str(disk))
            except Exception:
                texture = None
            if texture is not None:
                self.hits += 1
                self._remember(key, texture)
                callback(texture)
                return
        self.misses += 1
        if key in self.pending:
            self.pending[key].append(callback)
            return
        self.pending[key] = [callback]
        source = Path(path)

        def work():
            if disk.exists():
                try:
                    data = disk.read_bytes()
                    if data:
                        return key, data
                except OSError:
                    pass
            data = _make_thumb(source, self.width, kind)
            if data:
                atomic_write_bytes(disk, data, mode=0o600)
            return key, data

        def finish(future):
            try:
                key_value, data = future.result()
            except Exception:
                key_value, data = key, None
            if GLib is not None:
                GLib.idle_add(self._finish_thumb, key_value, data)
            else:
                self._finish_thumb(key_value, data)

        self.executor.submit(work).add_done_callback(finish)

    def _finish_thumb(self, key: str, data: bytes | None) -> bool:
        texture = None
        if data:
            try:
                texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
            except Exception:
                texture = None
        callbacks = self.pending.pop(key, [])
        if texture is not None:
            self.generated += 1
            self._remember(key, texture)
        for callback in callbacks:
            try:
                callback(texture)
            except Exception:
                pass
        return False

    def get_preview(self, path: str, mtime: float, size: int, kind: str, callback: Callable) -> None:
        key = _cache_key(path, mtime, size, kind, self.preview_max)
        if key in self.previews:
            self.previews.move_to_end(key)
            callback(self.previews[key])
            return
        if key in self.preview_pending:
            self.preview_pending[key].append(callback)
            return
        self.preview_pending[key] = [callback]
        source = Path(path)

        def work():
            return key, _make_preview(source, self.preview_max, kind)

        def finish(future):
            try:
                key_value, data = future.result()
            except Exception:
                key_value, data = key, None
            if GLib is not None:
                GLib.idle_add(self._finish_preview, key_value, data)
            else:
                self._finish_preview(key_value, data)

        self.executor.submit(work).add_done_callback(finish)

    def _finish_preview(self, key: str, data: bytes | None) -> bool:
        texture = None
        if data:
            try:
                texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
            except Exception:
                texture = None
        callbacks = self.preview_pending.pop(key, [])
        if texture is not None:
            self.previews[key] = texture
            self.previews.move_to_end(key)
            while len(self.previews) > 24:
                self.previews.popitem(last=False)
        for callback in callbacks:
            try:
                callback(texture)
            except Exception:
                pass
        return False

    def cleanup(self) -> int:
        files = []
        for path in constants.THUMB_DIR.glob("*/*.jpg"):
            try:
                files.append((path.stat().st_mtime, path.stat().st_size, path))
            except OSError:
                pass
        files.sort()
        total = sum(size for _mtime, size, _path in files)
        removed = 0
        limit = self.max_mb * 1024 * 1024
        for _mtime, size, path in files:
            if total <= limit:
                break
            try:
                path.unlink()
                total -= size
                removed += 1
            except OSError:
                pass
        return removed

    def clear(self) -> int:
        removed = 0
        for path in constants.THUMB_DIR.glob("*/*.jpg"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        self.memory.clear()
        self.previews.clear()
        return removed

    def cache_stats(self) -> dict:
        total = 0
        count = 0
        for path in constants.THUMB_DIR.glob("*/*.jpg"):
            try:
                total += path.stat().st_size
                count += 1
            except OSError:
                pass
        return {
            "files": count, "bytes": total, "memory": len(self.memory),
            "previews": len(self.previews), "hits": self.hits, "misses": self.misses,
            "generated": self.generated, "pending": len(self.pending),
        }
