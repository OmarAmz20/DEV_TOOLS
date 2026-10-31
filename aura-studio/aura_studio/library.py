"""Finding wallpapers and making the thumbnails the window shows.

Pictures are read by GdkPixbuf; videos get one frame extracted with ffmpeg
and cached, so the library can show them without pulling in a video player.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess

from . import store

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".jxl", ".bmp", ".tif", ".tiff", ".avif")
ANIM_EXT = (".gif", ".webp")
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".mpeg", ".mpg")
ALL_EXT = IMAGE_EXT + ANIM_EXT + VIDEO_EXT


def is_video(path):
    return bool(path) and path.lower().endswith(VIDEO_EXT)


def is_animated(path):
    return bool(path) and path.lower().endswith(ANIM_EXT)


def is_wallpaper(path):
    return bool(path) and path.lower().endswith(ALL_EXT)


def kind(path):
    if is_video(path):
        return "Video"
    if path.lower().endswith(".gif"):
        return "GIF"
    return "Picture"


def scan(folder):
    """Wallpaper files in *folder*, with lightweight metadata."""
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    found = []
    for entry in entries:
        try:
            if entry.name.startswith(".") or not entry.is_file(follow_symlinks=True):
                continue
            if not is_wallpaper(entry.name):
                continue
            stat = entry.stat()
        except OSError:
            continue
        found.append({
            "path": entry.path,
            "name": entry.name,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "kind": kind(entry.name),
        })
    found.sort(key=lambda item: item["name"].lower())
    return found


def _extract_frame(path, width=1280):
    """One frame of a video, cached.  Returns None if ffmpeg cannot read it."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    out = store.frame_path(path, width)
    if os.path.exists(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    for seek in ("1", "0"):
        temporary = out + f".{seek}.tmp.jpg"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", seek, "-i", path, "-frames:v", "1",
            "-vf", f"scale={width}:-2:flags=lanczos", "-q:v", "2", temporary,
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if os.path.exists(temporary) and os.path.getsize(temporary) > 0:
            os.replace(temporary, out)
            return out
        try:
            os.remove(temporary)
        except OSError:
            pass
    return None


def still_for(path, width=1280):
    """A readable picture for *path* (videos become their first useful frame)."""
    if is_video(path):
        return _extract_frame(path, width)
    if os.path.isfile(path):
        return path
    return None


def _cover(path, width, height):
    """Scale and centre-crop *path* to exactly width x height."""
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    _fmt, source_w, source_h = GdkPixbuf.Pixbuf.get_file_info(path)
    if not source_w or not source_h:
        raise GLib.Error("unreadable picture")
    scale = max(width / source_w, height / source_h)
    load_w = max(width, int(math.ceil(source_w * scale)) + 2)
    load_h = max(height, int(math.ceil(source_h * scale)) + 2)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, load_w, load_h, False)
    x = max(0, (pixbuf.get_width() - width) // 2)
    y = max(0, (pixbuf.get_height() - height) // 2)
    return pixbuf.new_subpixbuf(x, y, min(width, pixbuf.get_width()), min(height, pixbuf.get_height()))


def thumbnail(path, width=384, height=216):
    """A cached 16:9 JPEG thumbnail, or None when the file cannot be read."""
    cached = store.thumbnail_path(path, width, height)
    if os.path.exists(cached):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        try:
            return GdkPixbuf.Pixbuf.new_from_file(cached)
        except Exception:
            pass
    still = still_for(path, 1280)
    if not still:
        return None
    try:
        pixbuf = _cover(still, width, height)
    except Exception:
        return None
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    temporary = cached + ".tmp.jpg"
    try:
        pixbuf.savev(temporary, "jpeg", ["quality"], ["90"])
        os.replace(temporary, cached)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
    return pixbuf


def preview(path, width=820, height=460):
    """A larger cached crop for the hero panel."""
    cached = store.thumbnail_path(path, width, height)
    if os.path.exists(cached):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        try:
            return GdkPixbuf.Pixbuf.new_from_file(cached)
        except Exception:
            pass
    still = still_for(path, 1920)
    if not still:
        return None
    try:
        pixbuf = _cover(still, width, height)
    except Exception:
        return None
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    temporary = cached + ".tmp.jpg"
    try:
        pixbuf.savev(temporary, "jpeg", ["quality"], ["91"])
        os.replace(temporary, cached)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
    return pixbuf


def dimensions(path):
    """(width, height) for a picture or video, or None."""
    if is_video(path):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path],
                capture_output=True, text=True, timeout=8, check=False)
            width, height = result.stdout.strip().split("x")[:2]
            return int(width), int(height)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
        _fmt, width, height = GdkPixbuf.Pixbuf.get_file_info(path)
        return (width, height) if width and height else None
    except Exception:
        return None


def shuffle(paths, current=None):
    """A random path different from *current*, or None when there is no choice."""
    import random
    current = os.path.realpath(current) if current else None
    choices = [p for p in paths if os.path.realpath(p) != current]
    return random.choice(choices) if choices else None
