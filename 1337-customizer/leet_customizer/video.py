"""Video wallpaper control through mpvpaper (bundled or system)."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path

from . import constants, desktop
from .util import (
    atomic_write_text,
    notify,
    pid_alive,
    popen,
    read_json,
    run,
    which,
    write_json,
)


class VideoEngineMissing(RuntimeError):
    pass


def engine_path(preference: str = "auto") -> str | None:
    if preference not in ("auto", "", None):
        if Path(preference).exists():
            return str(preference)
    system = which("mpvpaper")
    if system:
        return system
    bundled = constants.BUNDLED_MPVPAPER
    if bundled.exists() and os.access(bundled, os.X_OK):
        return str(bundled)
    return None


def engine_available() -> bool:
    return engine_path() is not None and which("mpv") is not None


def engine_source() -> str:
    if which("mpvpaper"):
        return "system mpvpaper"
    if constants.BUNDLED_MPVPAPER.exists():
        return "bundled mpvpaper engine"
    return "not installed"


def state() -> dict:
    raw = read_json(constants.VIDEO_STATE, {})
    if not isinstance(raw, dict):
        return {}
    raw["processes"] = [item for item in raw.get("processes", []) if pid_alive(item.get("pid"))]
    raw["running"] = bool(raw["processes"])
    return raw


def running() -> bool:
    return bool(state().get("running"))


def _monitors(target: str) -> list[str]:
    if target and target != "all":
        return [target]
    names = [entry["name"] for entry in desktop.monitors() if entry.get("name") not in (None, "", "all")]
    return names or ["all"]


def _mpv_options(config: dict) -> str:
    video = config.get("video", {})
    fit = str(video.get("fit", "crop"))
    options = [
        "keep-open=yes",
        "osc=no",
        "osd-level=0",
        "really-quiet",
        "no-input-default-bindings",
        "no-border",
    ]
    if float(video.get("speed", 1.0) or 1.0) != 1.0:
        options.append(f"speed={max(0.25, min(4.0, float(video.get('speed', 1.0)))):.2f}")
    if video.get("loop", True):
        options.append("loop-file=inf")
    else:
        options.append("loop-file=no")
    if video.get("muted", True):
        options.append("no-audio")
    options.append(f"hwdec={video.get('hwdec', 'auto-safe')}")
    if fit in ("fit", "center"):
        options.append("panscan=0.0")
        options.append("video-unscaled=no")
    else:
        options.append("panscan=1.0")
    return " ".join(options)


def start(path: str | Path, config, *, monitor: str | None = None) -> dict:
    """Start one mpvpaper process per target output."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() not in constants.VIDEO_EXTENSIONS:
        raise ValueError("not a video file")
    engine = engine_path(config.get("video", {}).get("engine", "auto") if config else "auto")
    if not engine:
        raise VideoEngineMissing(
            "mpvpaper is not installed. Use “Build video engine”, or install mpvpaper."
        )
    if not desktop.has_layer_shell() and desktop.is_wayland():
        raise VideoEngineMissing(
            "This compositor does not expose wlr-layer-shell. Use a static fallback or a wlroots compositor."
        )
    stop()
    video = config.get("video", {}) if config else {}
    target = monitor or video.get("monitor", "all")
    outputs = _monitors(target)
    options = _mpv_options(config)
    layer = video.get("layer", "background")
    command_base = [engine, "-l", layer]
    if video.get("auto_pause", True):
        command_base.append("-p")
    if video.get("auto_stop_fullscreen", False):
        command_base += ["-s", "-a", "full"]
    command_base += ["-o", options]
    constants.LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = constants.VIDEO_LOG
    processes = []
    for output in outputs:
        command = command_base + [output, str(path)]
        try:
            with open(log_path, "ab") as log:
                log.write(f"\n[{time.strftime('%F %T')}] {shlex.join(command)}\n".encode())
                log.flush()
                process = popen(command, stdout=log, stderr=log)
        except OSError as error:
            raise VideoEngineMissing(f"Could not start mpvpaper: {error}") from error
        processes.append({"pid": process.pid, "monitor": output, "command": command})
    time.sleep(0.65)
    alive = []
    for item in processes:
        if pid_alive(item["pid"]):
            alive.append(item)
        else:
            _terminate(item["pid"])
    if not alive:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
        except OSError:
            pass
        raise VideoEngineMissing(f"mpvpaper exited immediately.\n{tail}")
    payload = {
        "running": True,
        "path": str(path),
        "monitor": target,
        "fit": video.get("fit", "crop"),
        "options": options,
        "processes": alive,
        "started": time.time(),
    }
    write_json(constants.VIDEO_STATE, payload)
    try:
        config.set("video.path", str(path), save=True)
    except Exception:
        pass
    from .util import set_notifications

    set_notifications(bool(config.get("notifications", True)) if config else True)
    notify("Video wallpaper started", f"{path.name} · {', '.join(item['monitor'] for item in alive)}")
    return payload


def _terminate(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.04)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def stop(*, notify_user: bool = False) -> int:
    current = state()
    stopped = 0
    for item in current.get("processes", []):
        pid = item.get("pid")
        if pid and pid_alive(pid):
            _terminate(pid)
            stopped += 1
    try:
        constants.VIDEO_STATE.unlink()
    except OSError:
        pass
    if notify_user and stopped:
        notify("Video wallpaper stopped", "Your static wallpaper is visible again.")
    return stopped


def restart_from_config(config) -> dict | None:
    video = config.get("video", {})
    if not video.get("restore_on_login", True):
        return None
    path = video.get("path")
    if not path or not Path(path).exists():
        return None
    try:
        return start(path, config, monitor=video.get("monitor", "all"))
    except Exception:
        return None


def build_engine() -> dict:
    script = constants.ENGINE_ROOT / "build-mpvpaper.sh"
    if not script.exists():
        return {"ok": False, "output": "build-mpvpaper.sh is missing"}
    result = run([str(script)], timeout=600)
    ok = result.returncode == 0 and constants.BUNDLED_MPVPAPER.exists()
    return {"ok": ok, "output": (result.stdout + result.stderr)[-4000:]}


def log_tail(lines: int = 20) -> str:
    try:
        return "\n".join(constants.VIDEO_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""
