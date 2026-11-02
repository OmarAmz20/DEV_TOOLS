"""SQLite-backed wallpaper library with fast metadata probing."""

from __future__ import annotations

import contextlib
import json
import os
import random
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable

from . import constants
from .util import human_size, read_json, run

try:
    from gi.repository import GObject
except Exception:  # pragma: no cover
    GObject = None

try:
    from PIL import Image
except Exception:
    Image = None


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    name TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'image',
    duration REAL NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]',
    last_seen REAL NOT NULL DEFAULT 0,
    added REAL NOT NULL DEFAULT 0,
    updated REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS files_root_idx ON files(root);
CREATE INDEX IF NOT EXISTS files_kind_idx ON files(kind);
CREATE INDEX IF NOT EXISTS files_favorite_idx ON files(favorite);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    monitor TEXT NOT NULL DEFAULT 'all',
    fit TEXT NOT NULL DEFAULT 'crop',
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS history_at_idx ON history(at DESC);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class WallpaperItem(GObject.Object if GObject else object):
    """A GObject wrapper so Gtk.GridView can virtualise the library."""

    if GObject:
        __gtype_name__ = "LeetWallpaperItem"

        path = GObject.Property(type=str, default="")
        root = GObject.Property(type=str, default="")
        name = GObject.Property(type=str, default="")
        kind = GObject.Property(type=str, default="image")
        width = GObject.Property(type=int, default=0)
        height = GObject.Property(type=int, default=0)
        size = GObject.Property(type=int, default=0)
        mtime = GObject.Property(type=float, default=0.0)
        duration = GObject.Property(type=float, default=0.0)
        favorite = GObject.Property(type=bool, default=False)
        tags = GObject.Property(type=str, default="[]")
        folder = GObject.Property(type=str, default="")

    def __init__(self, **values):
        super().__init__()
        for key, value in values.items():
            if hasattr(type(self), key) or key in getattr(self, "__dict__", {}):
                try:
                    setattr(self, key, value)
                except Exception:
                    pass

    @property
    def directory(self) -> str:
        return str(Path(self.path).parent)

    @property
    def size_text(self) -> str:
        return human_size(self.size)

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}" if self.width and self.height else "Unknown"

    @property
    def is_video(self) -> bool:
        return self.kind == "video"

    @property
    def is_animated(self) -> bool:
        return self.kind == "animated"

    @property
    def kind_label(self) -> str:
        return {"video": "Video", "animated": "Animated", "image": "Image"}.get(self.kind, "Image")


def _probe_image(path: Path) -> tuple[int, int, str, float]:
    if Image is None:
        return 0, 0, "image", 0.0
    try:
        with Image.open(path) as image:
            width, height = image.size
            animated = bool(getattr(image, "is_animated", False) and getattr(image, "n_frames", 1) > 1)
            duration = 0.0
            if animated:
                frame_duration = image.info.get("duration", 0) or 0
                duration = (frame_duration * max(1, getattr(image, "n_frames", 1))) / 1000.0
            return width, height, "animated" if animated else "image", duration
    except Exception:
        return 0, 0, "image", 0.0


def _probe_video(path: Path) -> tuple[int, int, str, float]:
    result = run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration:format=duration",
            "-of", "json", str(path),
        ],
        timeout=18,
    )
    width = height = 0
    duration = 0.0
    try:
        payload = json.loads(result.stdout)
        stream = (payload.get("streams") or [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        duration = float(stream.get("duration") or payload.get("format", {}).get("duration") or 0)
    except (ValueError, TypeError, IndexError):
        pass
    return width, height, "video", duration


def probe_media(path: str | Path) -> tuple[int, int, str, float]:
    path = Path(path)
    if path.suffix.lower() in constants.VIDEO_EXTENSIONS:
        return _probe_video(path)
    if path.suffix.lower() in constants.ANIMATED_EXTENSIONS:
        width, height, kind, duration = _probe_image(path)
        return width, height, ("animated" if kind == "image" else kind), duration
    return _probe_image(path)


def _write_tags(value: str) -> str:
    try:
        tags = json.loads(value)
        if isinstance(tags, list):
            return json.dumps([str(tag) for tag in tags[:20]])
    except (ValueError, TypeError):
        pass
    return "[]"


class Library:
    def __init__(self, db_path: str | Path = constants.LIBRARY_DB) -> None:
        constants.ensure_dirs()
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA temp_store=MEMORY")
        return connection

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.closing(self._connect()) as connection:
            connection.executescript(SCHEMA)

    # --- scanning -----------------------------------------------------------------

    def _iter_files(self, folders: Iterable[str], recursive: bool) -> Iterable[tuple[Path, Path]]:
        for folder in folders:
            root = Path(folder).expanduser()
            if not root.is_dir():
                continue
            if recursive:
                for current, directories, files in os.walk(root, followlinks=False):
                    directories[:] = [
                        name for name in directories
                        if not name.startswith(".")
                        and name not in {"node_modules", "__pycache__", ".git", ".cache"}
                    ]
                    for name in files:
                        if name.startswith("."):
                            continue
                        path = Path(current) / name
                        if path.suffix.lower() in constants.ALL_EXTENSIONS:
                            yield root, path
            else:
                try:
                    entries = list(os.scandir(root))
                except OSError:
                    continue
                for entry in entries:
                    if entry.is_file(follow_symlinks=False):
                        path = Path(entry.path)
                        if path.suffix.lower() in constants.ALL_EXTENSIONS:
                            yield root, path

    def scan(
        self,
        folders: Iterable[str],
        *,
        recursive: bool = True,
        progress: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict:
        started = time.monotonic()
        folders = [str(Path(folder).expanduser().resolve()) for folder in folders if Path(folder).expanduser().is_dir()]
        token = time.time()
        rows: dict[str, sqlite3.Row] = {}
        with contextlib.closing(self._connect()) as connection:
            for row in connection.execute("SELECT * FROM files"):
                rows[row["path"]] = row

        discovered_raw: list[tuple[Path, Path]] = list(self._iter_files(folders, recursive))
        discovered: list[tuple[Path, Path]] = []
        discovered_seen = set()
        for root, path in discovered_raw:
            key = str(path)
            if key in discovered_seen:
                continue
            discovered_seen.add(key)
            discovered.append((root, path))
        total = len(discovered)
        added = updated = unchanged = removed = 0
        aborted = False
        probes: list[tuple[Path, Path, os.stat_result]] = []
        seen_paths = set()
        for index, (root, path) in enumerate(discovered):
            if should_stop and should_stop():
                aborted = True
                break
            try:
                stat = path.stat()
            except OSError:
                continue
            seen_paths.add(str(path))
            existing = rows.get(str(path))
            if existing and int(existing["mtime"] * 1000) == int(stat.st_mtime * 1000) and existing["size"] == stat.st_size:
                unchanged += 1
            else:
                probes.append((root, path, stat))
            if progress and (index < 8 or index % max(1, min(40, max(1, total // 5))) == 0):
                progress(index + 1, total, path.name)

        def probe_entry(entry: tuple[Path, Path, os.stat_result]):
            root, path, stat = entry
            width, height, kind, duration = probe_media(path)
            return root, path, stat, width, height, kind, duration

        results = []
        if probes:
            workers = min(4, max(1, os.cpu_count() or 4))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for counter, result in enumerate(executor.map(probe_entry, probes), 1):
                    if should_stop and should_stop():
                        aborted = True
                        break
                    results.append(result)
                    if progress and (counter % 20 == 0 or counter == len(probes)):
                        progress(counter, len(probes), result[1].name)

        now = time.time()
        with contextlib.closing(self._connect()) as connection:
            for root, path, stat, width, height, kind, duration in results:
                key = str(path)
                if key in rows:
                    updated += 1
                    connection.execute(
                        """UPDATE files SET root=?, name=?, mtime=?, size=?, width=?, height=?,
                           kind=?, duration=?, last_seen=?, updated=? WHERE path=?""",
                        (str(root), path.name, stat.st_mtime, stat.st_size, width, height,
                         kind, duration, token, now, key),
                    )
                else:
                    added += 1
                    connection.execute(
                        """INSERT INTO files
                           (path, root, name, mtime, size, width, height, kind, duration,
                            favorite, tags, last_seen, added, updated)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', ?, ?, ?)""",
                        (key, str(root), path.name, stat.st_mtime, stat.st_size,
                         width, height, kind, duration, token, now, now),
                    )
            # Existing unchanged rows still need a fresh last_seen stamp.
            if seen_paths:
                for path in seen_paths:
                    if path in rows:
                        connection.execute("UPDATE files SET last_seen=? WHERE path=?", (token, path))
            if not aborted and folders:
                placeholders = ",".join("?" for _ in folders)
                stale = connection.execute(
                    f"SELECT path FROM files WHERE root NOT IN ({placeholders})", folders
                ).fetchall()
                for row in stale:
                    connection.execute("DELETE FROM files WHERE path=?", (row["path"],))
                    removed += 1
                for root in folders:
                    stale = connection.execute(
                        "SELECT path FROM files WHERE root=? AND last_seen<>?", (root, token)
                    ).fetchall()
                    for row in stale:
                        connection.execute("DELETE FROM files WHERE path=?", (row["path"],))
                        removed += 1
            connection.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('last_scan',?)", (str(now),)
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('last_scan_seconds',?)",
                (str(round(time.monotonic() - started, 3)),),
            )
            connection.commit()

        return {
            "added": added, "updated": updated, "unchanged": unchanged,
            "removed": removed, "total": len(seen_paths),
            "seconds": round(time.monotonic() - started, 3),
        }

    # --- queries ------------------------------------------------------------------

    def rows(self) -> list[sqlite3.Row]:
        with contextlib.closing(self._connect()) as connection:
            return connection.execute(
                "SELECT * FROM files ORDER BY name COLLATE NOCASE ASC"
            ).fetchall()

    def items(self) -> list[WallpaperItem]:
        return [self._item(row) for row in self.rows()]

    def item(self, path: str) -> WallpaperItem | None:
        with contextlib.closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM files WHERE path=?", (str(path),)).fetchone()
        return self._item(row) if row else None

    def _item(self, row: sqlite3.Row) -> WallpaperItem:
        return WallpaperItem(
            path=row["path"], root=row["root"], name=row["name"], kind=row["kind"],
            width=row["width"], height=row["height"], size=row["size"],
            mtime=row["mtime"], duration=row["duration"],
            favorite=bool(row["favorite"]), tags=row["tags"],
            folder=str(Path(row["path"]).parent),
        )

    def toggle_favorite(self, path: str) -> bool:
        with contextlib.closing(self._connect()) as connection:
            row = connection.execute("SELECT favorite FROM files WHERE path=?", (str(path),)).fetchone()
            if not row:
                return False
            value = 0 if row["favorite"] else 1
            connection.execute("UPDATE files SET favorite=? WHERE path=?", (value, str(path)))
            connection.commit()
            return bool(value)

    def set_tags(self, path: str, tags: list[str]) -> None:
        with contextlib.closing(self._connect()) as connection:
            connection.execute("UPDATE files SET tags=? WHERE path=?", (_write_tags(json.dumps(tags)), str(path)))
            connection.commit()

    def stats(self) -> dict:
        with contextlib.closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS total,
                          COALESCE(SUM(favorite),0) AS favorites,
                          COALESCE(SUM(size),0) AS bytes,
                          COALESCE(SUM(kind='video'),0) AS videos,
                          COALESCE(SUM(kind='animated'),0) AS animated,
                          COALESCE(SUM(kind='image'),0) AS images
                   FROM files"""
            ).fetchone()
            history = connection.execute("SELECT COUNT(*) AS count FROM history").fetchone()
            meta = {item["key"]: item["value"] for item in connection.execute("SELECT * FROM meta")}
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "total": row["total"], "favorites": row["favorites"], "bytes": row["bytes"],
            "images": row["images"], "videos": row["videos"], "animated": row["animated"],
            "db_bytes": size, "history": history["count"],
            "last_scan": float(meta.get("last_scan", 0) or 0),
            "last_scan_seconds": float(meta.get("last_scan_seconds", 0) or 0),
        }

    def vacuum(self) -> None:
        with contextlib.closing(self._connect()) as connection:
            connection.execute("VACUUM")
            connection.execute("PRAGMA optimize")

    # --- history ------------------------------------------------------------------

    def add_history(self, path: str, kind: str, monitor: str = "all", fit: str = "crop") -> None:
        with contextlib.closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO history(path,kind,monitor,fit,at) VALUES(?,?,?,?,?)",
                (str(path), kind, monitor, fit, time.time()),
            )
            connection.execute(
                "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY at DESC LIMIT 60)"
            )
            connection.commit()

    def recent(self, limit: int = 30) -> list[dict]:
        with contextlib.closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM history ORDER BY at DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def history_item(self, offset: int = 1) -> dict | None:
        recent = self.recent(offset + 1)
        return recent[offset] if len(recent) > offset else None

    def next_path(
        self,
        *,
        favorites_only: bool = False,
        skip_videos: bool = True,
        order: str = "shuffle",
        current: str | None = None,
    ) -> str | None:
        clauses = []
        params: list = []
        if favorites_only:
            clauses.append("favorite=1")
        if skip_videos:
            clauses.append("kind<>'video'")
        query = "SELECT path FROM files" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        if order == "name":
            query += " ORDER BY name COLLATE NOCASE"
        else:
            query += " ORDER BY RANDOM()"
        with contextlib.closing(self._connect()) as connection:
            paths = [row["path"] for row in connection.execute(query, params)]
        if not paths:
            return None
        if current in paths and len(paths) > 1:
            paths = [path for path in paths if path != current]
        return paths[0] if order != "shuffle" else random.choice(paths)

    def clear_history(self) -> None:
        with contextlib.closing(self._connect()) as connection:
            connection.execute("DELETE FROM history")
            connection.commit()
