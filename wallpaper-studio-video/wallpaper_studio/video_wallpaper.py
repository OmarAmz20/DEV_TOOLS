"""Video-wallpaper state, process control and GNOME Shell extension helpers.

The video engine is deliberately separate from the static GNOME wallpaper
backend.  A still frame is still applied as the GNOME wallpaper (so the desktop
looks right everywhere), while the renderer plays the moving version above it.
On X11 the renderer owns a desktop-type window.  On GNOME Wayland the bundled
Shell extension clones the renderer window into the background actor.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

APP_SLUG = "wallpaper-studio-video"
APP_ID = "io.github.WallpaperStudioVideo"
EXTENSION_UUID = "wallpaper-studio-video@local"
TITLE_PREFIX = "@wallpaper-studio-video!"
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi")

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache")


def _cache_dir() -> Path:
    override = os.environ.get("WALLPAPER_STUDIO_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    goinfre = Path(os.environ.get("WALLPAPER_STUDIO_GOINFRE") or HOME / "goinfre")
    try:
        if goinfre.is_dir() and os.access(goinfre, os.W_OK):
            return goinfre.resolve() / APP_SLUG / "cache"
    except OSError:
        pass
    return CACHE_HOME / APP_SLUG


CONFIG_DIR = CONFIG_HOME / APP_SLUG
CACHE_DIR = _cache_dir()
STATE_FILE = CONFIG_DIR / "video.json"
RUNTIME_FILE = CONFIG_DIR / "video-runtime.json"
SINK_FILE = CONFIG_DIR / "video-sink.json"
LOG_FILE = CACHE_DIR / "video.log"
AUTOSTART_FILE = CONFIG_HOME / "autostart" / f"{APP_SLUG}-video.desktop"
EXTENSION_DIR = DATA_HOME / "gnome-shell" / "extensions" / EXTENSION_UUID

DEFAULT_STATE = {
    "enabled": False,
    "path": "",
    "mute": True,
    "fit": "cover",
    "monitor": 0,
}
DEFAULT_RUNTIME = {
    "renderer_pid": 0,
    "supervisor_pid": 0,
    "started": 0,
    "session": "",
    "error": "",
    "ready": False,
    "failures": 0,
}


def is_video(path: str | os.PathLike | None) -> bool:
    return bool(path) and str(path).lower().endswith(VIDEO_EXT)


def _read_json(path: Path, default):
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".video-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load() -> dict:
    value = {**DEFAULT_STATE, **_read_json(STATE_FILE, {})}
    if value.get("fit") not in ("cover", "contain"):
        value["fit"] = "cover"
    try:
        value["monitor"] = max(0, int(value.get("monitor", 0)))
    except (TypeError, ValueError):
        value["monitor"] = 0
    value["mute"] = bool(value.get("mute", True))
    value["enabled"] = bool(value.get("enabled", False))
    return value


def save(**changes) -> dict:
    value = {**load(), **changes}
    if "path" in value:
        value["path"] = str(Path(value["path"]).expanduser().resolve()) if value["path"] else ""
    _write_json(STATE_FILE, value)
    return value


def runtime() -> dict:
    return {**DEFAULT_RUNTIME, **_read_json(RUNTIME_FILE, {})}


def _write_runtime(**changes) -> dict:
    value = {**runtime(), **changes}
    _write_json(RUNTIME_FILE, value)
    return value


def session_type() -> str:
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11":
        return "x11"
    return "unknown"


def is_gnome() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "gnome" in desktop or "ubuntu" in desktop


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_command(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return " ".join(part.decode("utf-8", "replace") for part in raw.split(b"\0") if part)
    except OSError:
        return ""


def _pid_is_ours(pid: int) -> bool:
    command = _pid_command(pid)
    if not command:
        return False
    markers = {"video_renderer.py", "video_engine.py", renderer_script().name}
    return any(marker and marker in command for marker in markers)


def extension_status() -> dict:
    installed = (EXTENSION_DIR / "metadata.json").is_file()
    enabled = False
    if installed and shutil.which("gnome-extensions"):
        try:
            result = subprocess.run(
                ["gnome-extensions", "list", "--enabled"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            enabled = EXTENSION_UUID in result.stdout.split()
        except (OSError, subprocess.SubprocessError):
            pass
    return {"installed": installed, "enabled": enabled, "path": str(EXTENSION_DIR)}


def enable_extension() -> bool:
    if not shutil.which("gnome-extensions"):
        return False
    try:
        subprocess.run(
            ["gnome-extensions", "enable", EXTENSION_UUID],
            capture_output=True, text=True, timeout=8, check=False,
        )
        return extension_status()["enabled"]
    except (OSError, subprocess.SubprocessError):
        return False


def install_extension(source: Path | None = None) -> Path:
    """Copy the bundled Shell extension into the user's extension directory."""
    source = source or (Path(__file__).resolve().parent / "video_extension")
    if not source.is_dir():
        raise FileNotFoundError(f"Video extension source not found: {source}")
    EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = EXTENSION_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    schemas = EXTENSION_DIR / "schemas"
    if schemas.is_dir() and shutil.which("glib-compile-schemas"):
        subprocess.run(
            ["glib-compile-schemas", str(schemas)],
            capture_output=True, text=True, timeout=15, check=False,
        )
    return EXTENSION_DIR


def renderer_script() -> Path:
    override = os.environ.get("WALLPAPER_STUDIO_VIDEO_RENDERER")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().with_name("video_renderer.py")


def engine_script() -> Path:
    return Path(__file__).resolve().with_name("video_engine.py")


def _launcher() -> str:
    local = Path(__file__).resolve().parent.parent / "wallpaper-studio-video"
    if local.is_file():
        return str(local)
    found = shutil.which("wallpaper-studio-video")
    return found or "wallpaper-studio-video"


def write_autostart() -> None:
    """Install a no-op-unless-enabled login entry for the video engine."""
    AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
    command = _launcher()
    quoted = '"' + command.replace("\\", "\\\\").replace('"', '\\"') + '"'
    AUTOSTART_FILE.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Wallpaper Studio Video\n"
        "Comment=Restore the video desktop wallpaper\n"
        f"Exec={quoted} video start\n"
        "NoDisplay=true\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


def remove_autostart() -> None:
    AUTOSTART_FILE.unlink(missing_ok=True)


def start(path: str | None = None, *, mute: bool | None = None,
          fit: str | None = None, monitor: int | None = None,
          wait: bool = True) -> dict:
    current = load()
    if path is None and not current.get("enabled"):
        return status()
    if path:
        current["path"] = str(Path(path).expanduser().resolve())
    if not current["path"] or not Path(current["path"]).is_file():
        raise ValueError("Choose an existing video file first.")
    if not is_video(current["path"]):
        raise ValueError("The video wallpaper accepts MP4, WebM, MKV, MOV, M4V or AVI files.")
    changes = {"enabled": True, **{key: value for key, value in {
        "mute": mute, "fit": fit, "monitor": monitor,
    }.items() if value is not None}}
    if session_type() == "wayland" and is_gnome() and not extension_status()["enabled"]:
        try:
            install_extension()
            enable_extension()
        except (OSError, RuntimeError, FileNotFoundError):
            pass
        if not extension_status()["enabled"]:
            raise ValueError(
                "The GNOME video extension is not enabled yet. Open Video wallpaper, "
                "press Install / enable, then log out and back in once."
            )
    current = save(path=current["path"], **changes)
    write_autostart()

    running = runtime()
    if running.get("supervisor_pid") and _pid_alive(int(running["supervisor_pid"])) \
            and _pid_is_ours(int(running["supervisor_pid"])):
        # The engine watches the state file and restarts the renderer.
        return status()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "ab", buffering=0)
    try:
        process = subprocess.Popen(
            [sys.executable, str(engine_script())],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )
    finally:
        log.close()
    _write_runtime(
        supervisor_pid=process.pid, renderer_pid=0, started=time.time(),
        session=session_type(), error="", ready=False, failures=0,
    )
    if wait:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            info = runtime()
            if info.get("renderer_pid") and info.get("ready") and _pid_alive(int(info["renderer_pid"])):
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
    return status()


def stop() -> dict:
    info = runtime()
    state = load()
    if not state.get("enabled") and not info.get("renderer_pid") and not info.get("supervisor_pid"):
        return status()
    for key in ("renderer_pid", "supervisor_pid"):
        pid = info.get(key) or 0
        if not isinstance(pid, int) or pid <= 0 or not _pid_alive(pid):
            continue
        if not _pid_is_ours(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not any(_pid_alive(int(info.get(key) or 0)) for key in ("renderer_pid", "supervisor_pid")):
            break
        time.sleep(0.1)
    for key in ("renderer_pid", "supervisor_pid"):
        pid = info.get(key) or 0
        if isinstance(pid, int) and pid > 0 and _pid_alive(pid) and _pid_is_ours(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    _write_runtime(renderer_pid=0, supervisor_pid=0, started=0, error="", ready=False, failures=0)
    SINK_FILE.unlink(missing_ok=True)
    save(enabled=False)
    return status()


def status() -> dict:
    state = load()
    info = runtime()
    renderer_pid = int(info.get("renderer_pid") or 0)
    supervisor_pid = int(info.get("supervisor_pid") or 0)
    renderer_alive = bool(renderer_pid and _pid_alive(renderer_pid) and _pid_is_ours(renderer_pid))
    supervisor_alive = bool(supervisor_pid and _pid_alive(supervisor_pid) and _pid_is_ours(supervisor_pid))
    return {
        **state,
        **info,
        "renderer_pid": renderer_pid,
        "supervisor_pid": supervisor_pid,
        "renderer_alive": renderer_alive,
        "supervisor_alive": supervisor_alive,
        "ready": bool(info.get("ready")),
        "running": renderer_alive and bool(info.get("ready")),
        "session": session_type(),
        "extension": extension_status(),
        "log": str(LOG_FILE),
    }


def status_text() -> str:
    info = status()
    if info["running"]:
        return f"Video wallpaper running (PID {info['renderer_pid']})"
    if info.get("error"):
        return f"Video wallpaper failed: {info['error']}"
    if info["enabled"]:
        return "Video wallpaper is enabled but the renderer is not running"
    return "Video wallpaper is off"
