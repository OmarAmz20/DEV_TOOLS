"""Wallpaper backends for Hyprland, wlroots, GNOME, KDE and X11."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import constants, desktop, video
from .util import (
    file_uri,
    notify,
    pid_alive,
    popen,
    read_json,
    run,
    which,
    write_json,
)


class WallpaperError(RuntimeError):
    pass


BACKUP_DIR = constants.STATE_DIR / "backups"
WALLPAPER_BACKUP = BACKUP_DIR / "wallpaper.json"
SWAYBG_PIDS = constants.STATE_DIR / "swaybg.json"

FIT_TO_AWWW = {"crop": "crop", "fit": "fit", "stretch": "stretch", "center": "no"}
FIT_TO_GNOME = {"crop": "zoom", "fit": "scaled", "stretch": "stretched", "center": "centered"}
FIT_TO_HYPRPAPER = {"crop": "cover", "fit": "contain", "stretch": "stretch", "center": "contain"}
FIT_TO_SWAYBG = {"crop": "fill", "fit": "fit", "stretch": "stretch", "center": "center"}


def state() -> dict:
    raw = read_json(constants.WALLPAPER_STATE, {})
    return raw if isinstance(raw, dict) else {}


def current_path() -> str | None:
    raw = state()
    path = raw.get("applied") or raw.get("source")
    if path and Path(path).exists():
        return str(path)
    if _dms_available():
        result = run(["dms", "ipc", "call", "wallpaper", "getFor", desktop.primary_monitor()["name"]], timeout=6)
        candidate = (result.stdout or "").strip()
        if result.returncode == 0 and candidate.startswith("/") and Path(candidate).exists():
            return candidate
    value = desktop.get_value(desktop.BACKGROUND, "picture-uri", "")
    if isinstance(value, str) and value.startswith("file://"):
        from urllib.parse import unquote
        candidate = unquote(value[7:])
        if Path(candidate).exists():
            return candidate
    return None


def _dms_available() -> bool:
    if not which("dms"):
        return False
    result = run(["dms", "ipc", "call", "outputs", "current"], timeout=5)
    return result.returncode == 0 and result.stdout.strip().startswith("[")


def _dms_current(monitor: str) -> str | None:
    result = run(["dms", "ipc", "call", "wallpaper", "getFor", monitor], timeout=6)
    value = (result.stdout or "").strip()
    return value if result.returncode == 0 and value.startswith("/") else None


def _apply_dms(path: Path, monitor: str, fit: str, config) -> str:
    targets = [monitor] if monitor and monitor != "all" else [
        item["name"] for item in desktop.monitors() if item.get("name") not in (None, "", "all")
    ]
    fill_mode = {"crop": "Fill", "fit": "Fit", "stretch": "Stretch", "center": "Center"}.get(fit, "Fill")
    run(["dms", "ipc", "call", "settings", "set", "wallpaperFillMode", fill_mode], timeout=8)
    errors = []
    for target in targets:
        result = run(["dms", "ipc", "call", "wallpaper", "setFor", target, str(path)], timeout=20)
        if result.returncode != 0:
            # Per-monitor mode is off: try the global setter.
            result = run(["dms", "ipc", "call", "wallpaper", "set", str(path)], timeout=20)
        if result.returncode != 0:
            errors.append(f"{target}: {(result.stderr or result.stdout).strip()[:180]}")
    if errors and len(errors) == len(targets):
        raise WallpaperError("; ".join(errors))
    return "dms"


def _capture_previous() -> None:
    if WALLPAPER_BACKUP.exists():
        return
    payload = {"gnome": {}, "dms": {}, "awww": "", "at": time.time()}
    for key in ("picture-uri", "picture-uri-dark", "picture-options"):
        value = desktop.get_value(desktop.BACKGROUND, key)
        if value is not None:
            payload["gnome"][key] = value
    for key in ("picture-uri", "picture-options"):
        value = desktop.get_value(desktop.SCREENSAVER, key)
        if value is not None:
            payload["gnome"][f"screensaver:{key}"] = value
    if _dms_available():
        for monitor in desktop.monitors():
            name = monitor.get("name")
            if name and name != "all":
                current = _dms_current(name)
                if current:
                    payload["dms"][name] = current
        fill = run(["dms", "ipc", "call", "settings", "get", "wallpaperFillMode"], timeout=5)
        value = (fill.stdout or "").strip().strip('"')
        if fill.returncode == 0 and value:
            payload["dms_fill"] = value
    BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_json(WALLPAPER_BACKUP, payload)


def _copy_applied(path: Path) -> Path:
    constants.APPLIED_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        stat = path.stat()
    except OSError:
        return path
    digest = hashlib.sha1(f"{path}|{stat.st_mtime_ns}|{stat.st_size}".encode()).hexdigest()[:14]
    destination = constants.APPLIED_DIR / f"{path.stem}-{digest}{path.suffix}"
    if not destination.exists():
        try:
            shutil.copy2(path, destination)
        except OSError:
            return path
    return destination


def _still_frame(path: Path) -> Path | None:
    constants.APPLIED_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha1(str(path).encode()).hexdigest()[:12]
    destination = constants.APPLIED_DIR / f"video-still-{digest}.jpg"
    if destination.exists():
        return destination
    commands = [
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1",
         "-i", str(path), "-frames:v", "1", "-vf", "scale=2560:-2", str(destination)],
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(path), "-frames:v", "1", "-vf", "scale=2560:-2", str(destination)],
    ]
    for command in commands:
        result = run(command, timeout=30)
        if result.returncode == 0 and destination.exists():
            return destination
    return None


def _awww_ready() -> bool:
    if not which("awww"):
        return False
    result = run(["awww", "query"], timeout=5)
    if result.returncode == 0 and result.stdout.strip():
        return True
    daemon = which("awww-daemon")
    if not daemon:
        return False
    try:
        popen([daemon])
    except OSError:
        return False
    for _ in range(20):
        time.sleep(0.08)
        result = run(["awww", "query"], timeout=3)
        if result.returncode == 0 and result.stdout.strip():
            return True
    return False


def _apply_awww(path: Path, monitor: str, fit: str, config) -> str:
    if not _awww_ready():
        raise WallpaperError("awww daemon is not running")
    wallpaper = config.get("wallpaper", {}) if config else {}
    command = [
        "awww", "img", str(path),
        "--resize", FIT_TO_AWWW.get(fit, "crop"),
        "--filter", "Lanczos3",
        "--transition-type", str(wallpaper.get("transition", "simple")),
        "--transition-duration", str(float(wallpaper.get("transition_duration", 0.8) or 0.8)),
        "--transition-fps", str(int(wallpaper.get("transition_fps", 60) or 60)),
    ]
    if monitor and monitor != "all":
        command += ["--outputs", monitor]
    result = run(command, timeout=25)
    if result.returncode != 0:
        raise WallpaperError((result.stderr or result.stdout).strip()[:500])
    return "awww"


def _hyprpaper_running() -> bool:
    if not which("hyprctl"):
        return False
    result = run(["hyprctl", "hyprpaper", "listloaded"], timeout=4)
    return result.returncode == 0 and "error" not in result.stdout.lower()


def _apply_hyprpaper(path: Path, monitor: str, fit: str, config) -> str:
    run(["hyprctl", "hyprpaper", "preload", str(path)], timeout=15)
    targets = [monitor] if monitor and monitor != "all" else [item["name"] for item in desktop.monitors()]
    for target in targets:
        mode = FIT_TO_HYPRPAPER.get(fit, "cover")
        result = run(["hyprctl", "hyprpaper", "wallpaper", f"{target},{path},{mode}"], timeout=15)
        if result.returncode != 0:
            raise WallpaperError((result.stderr or result.stdout).strip()[:500])
    return "hyprpaper"


def _stop_swaybg() -> None:
    raw = read_json(SWAYBG_PIDS, [])
    if isinstance(raw, list):
        for pid in raw:
            if pid_alive(pid):
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGTERM)
    with contextlib.suppress(OSError):
        SWAYBG_PIDS.unlink()


def _apply_swaybg(path: Path, monitor: str, fit: str, config) -> str:
    if not which("swaybg"):
        raise WallpaperError("swaybg is not installed")
    _stop_swaybg()
    targets = [monitor] if monitor and monitor != "all" else [item["name"] for item in desktop.monitors()]
    pids = []
    for target in targets:
        command = ["swaybg", "-i", str(path), "-m", FIT_TO_SWAYBG.get(fit, "fill")]
        if target and target != "all":
            command += ["-o", target]
        try:
            process = popen(command)
            pids.append(process.pid)
        except OSError as error:
            raise WallpaperError(f"swaybg: {error}") from error
    write_json(SWAYBG_PIDS, pids)
    time.sleep(0.3)
    if not any(pid_alive(pid) for pid in pids):
        raise WallpaperError("swaybg exited immediately")
    return "swaybg"


def _apply_gnome(path: Path, monitor: str, fit: str, config) -> str:
    _capture_previous()
    wallpaper = config.get("wallpaper", {}) if config else {}
    target = wallpaper.get("apply_target", "both")
    uri = file_uri(path)
    options = FIT_TO_GNOME.get(fit, "zoom")
    if target in ("both", "light"):
        desktop.set_string(desktop.BACKGROUND, "picture-uri", uri, capture=False)
        desktop.set_string(desktop.BACKGROUND, "picture-options", options, capture=False)
    if target in ("both", "dark"):
        desktop.set_string(desktop.BACKGROUND, "picture-uri-dark", uri, capture=False)
        desktop.set_string(desktop.BACKGROUND, "picture-options", options, capture=False)
    desktop.set_string(desktop.SCREENSAVER, "picture-uri", uri, capture=False)
    desktop.set_string(desktop.SCREENSAVER, "picture-options", options, capture=False)
    return "gnome"


def _apply_plasma(path: Path, monitor: str, fit: str, config) -> str:
    if not which("plasma-apply-wallpaperimage"):
        raise WallpaperError("plasma-apply-wallpaperimage is not installed")
    result = run(["plasma-apply-wallpaperimage", str(path)], timeout=30)
    if result.returncode != 0:
        raise WallpaperError((result.stderr or result.stdout).strip()[:500])
    return "plasma"


def _apply_feh(path: Path, monitor: str, fit: str, config) -> str:
    if not which("feh"):
        raise WallpaperError("feh is not installed")
    mode = {"crop": "--bg-fill", "fit": "--bg-max", "stretch": "--bg-scale",
            "center": "--bg-center"}.get(fit, "--bg-fill")
    result = run(["feh", mode, str(path)], timeout=20)
    if result.returncode != 0:
        raise WallpaperError((result.stderr or result.stdout).strip()[:500])
    return "feh"


def backend_priority() -> list[str]:
    desktop_name = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if _dms_available():
        return ["dms", "awww", "hyprpaper", "swaybg", "feh", "gnome"]
    if "gnome" in desktop_name or "ubuntu" in desktop_name:
        return ["gnome", "awww", "hyprpaper", "swaybg", "feh"]
    if "kde" in desktop_name or "plasma" in desktop_name:
        return ["plasma", "awww", "swaybg", "feh"]
    values = []
    if _awww_ready() if which("awww") else False:
        values.append("awww")
    if _hyprpaper_running():
        values.append("hyprpaper")
    if which("awww"):
        values.append("awww")
    if which("swaybg"):
        values.append("swaybg")
    if which("feh"):
        values.append("feh")
    if desktop.has_key(desktop.BACKGROUND, "picture-uri"):
        values.append("gnome")
    if which("plasma-apply-wallpaperimage"):
        values.append("plasma")
    return values


def backend_status() -> list[tuple[str, bool, str]]:
    values = []
    awww = which("awww")
    values.append(("awww", bool(awww), "Animated GIF + images, per-monitor, transitions" if awww else "not installed"))
    hyprpaper = which("hyprpaper")
    values.append(("hyprpaper", bool(hyprpaper), "Hyprland native images" if hyprpaper else "not installed"))
    swaybg = which("swaybg")
    values.append(("swaybg", bool(swaybg), "wlroots fallback" if swaybg else "not installed"))
    values.append(("gnome", desktop.has_key(desktop.BACKGROUND, "picture-uri"), "GNOME image settings"))
    plasma = which("plasma-apply-wallpaperimage")
    values.append(("plasma", bool(plasma), "KDE Plasma image settings" if plasma else "not installed"))
    feh = which("feh")
    values.append(("feh", bool(feh), "X11 root pixmap" if feh else "not installed"))
    values.append(("dms", _dms_available(), "DankMaterialShell wallpaper state"))
    values.append(("mpvpaper", video.engine_available(), video.engine_source()))
    return values


def _apply_static(path: Path, monitor: str, fit: str, config, *, animated: bool = False) -> str:
    errors = []
    for backend in backend_priority():
        try:
            if backend == "dms":
                return _apply_dms(path, monitor, fit, config)
            if backend == "awww":
                if animated or path.suffix.lower() in constants.ANIMATED_EXTENSIONS:
                    return _apply_awww(path, monitor, fit, config)
                return _apply_awww(path, monitor, fit, config)
            if backend == "hyprpaper":
                return _apply_hyprpaper(path, monitor, fit, config)
            if backend == "swaybg":
                return _apply_swaybg(path, monitor, fit, config)
            if backend == "gnome":
                return _apply_gnome(path, monitor, fit, config)
            if backend == "plasma":
                return _apply_plasma(path, monitor, fit, config)
            if backend == "feh":
                return _apply_feh(path, monitor, fit, config)
        except Exception as error:
            errors.append(f"{backend}: {error}")
    raise WallpaperError("; ".join(errors) or "No wallpaper backend is available")


def apply(
    path: str | Path,
    config,
    *,
    monitor: str | None = None,
    fit: str | None = None,
    allow_video: bool = True,
    apply_theme: bool | None = None,
) -> dict:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise WallpaperError(f"File not found: {path}")
    wallpaper = config.get("wallpaper", {}) if config else {}
    monitor = monitor or wallpaper.get("monitor", "all")
    fit = fit or wallpaper.get("fit", "crop")
    kind = "video" if path.suffix.lower() in constants.VIDEO_EXTENSIONS else (
        "animated" if path.suffix.lower() in constants.ANIMATED_EXTENSIONS else "image"
    )
    result = {"ok": False, "source": str(path), "monitor": monitor, "fit": fit,
              "kind": kind, "warning": "", "backend": ""}
    _capture_previous()

    if kind == "video" and allow_video:
        try:
            payload = video.start(path, config, monitor=monitor)
            result.update({"ok": True, "backend": "mpvpaper", "applied": str(path),
                           "processes": payload.get("processes", [])})
            _record(path, kind, monitor, fit, backend="mpvpaper")
            _maybe_theme(config, apply_theme, path)
            return result
        except Exception as error:
            frame = _still_frame(path)
            if frame is None:
                raise WallpaperError(str(error))
            result["warning"] = f"Video engine unavailable; applied a still frame. {error}"
            path = frame
            kind = "image"

    applied_path = _copy_applied(path) if wallpaper.get("copy_applied", True) else path
    try:
        backend = _apply_static(applied_path, monitor, fit, config, animated=kind == "animated")
    except Exception:
        if applied_path != path:
            backend = _apply_static(path, monitor, fit, config, animated=kind == "animated")
            applied_path = path
        else:
            raise
    result.update({"ok": True, "backend": backend, "applied": str(applied_path)})
    _record(path, kind, monitor, fit, backend=backend, applied=str(applied_path))
    _maybe_theme(config, apply_theme, applied_path)
    from .util import set_notifications

    set_notifications(bool(config.get("notifications", True)) if config else True)
    notify("Wallpaper applied", f"{path.name} · {backend}")
    return result


def _maybe_theme(config, override: bool | None, path: Path) -> None:
    if override is False:
        return
    wallpaper = config.get("wallpaper", {}) if config else {}
    if not wallpaper.get("apply_theme", True):
        return
    appearance = config.get("appearance", {}) if config else {}
    if not appearance.get("apply_theme", True):
        return
    try:
        theme, report = desktop.apply_theme_from_config(config)
        if not report.get("ok"):
            notify("Theme warning", "; ".join(report.get("warnings", []))[:300])
    except Exception as error:
        notify("Theme warning", str(error))


def _record(source: Path, kind: str, monitor: str, fit: str, *, backend: str,
            applied: str | None = None) -> None:
    payload = {
        "version": 1,
        "source": str(source),
        "applied": applied or str(source),
        "kind": kind,
        "monitor": monitor,
        "fit": fit,
        "backend": backend,
        "at": time.time(),
        "video": bool(kind == "video" and backend == "mpvpaper"),
    }
    write_json(constants.WALLPAPER_STATE, payload)
    try:
        from .library import Library

        library = Library()
        library.add_history(str(source), kind, monitor, fit)
    except Exception:
        pass


def _restore_previous() -> bool:
    backup = read_json(WALLPAPER_BACKUP, {})
    dms_values = backup.get("dms", {}) if isinstance(backup, dict) else {}
    if dms_values and _dms_available():
        for monitor, path in dms_values.items():
            run(["dms", "ipc", "call", "wallpaper", "setFor", monitor, str(path)], timeout=20)
        fill = backup.get("dms_fill") if isinstance(backup, dict) else None
        if fill:
            run(["dms", "ipc", "call", "settings", "set", "wallpaperFillMode", str(fill)], timeout=8)
        return True
    values = backup.get("gnome", {}) if isinstance(backup, dict) else {}
    if not values:
        return False
    for key, value in values.items():
        if key.startswith("screensaver:"):
            desktop.set_string(desktop.SCREENSAVER, key.split(":", 1)[1], str(value), capture=False)
        else:
            desktop.set_string(desktop.BACKGROUND, key, str(value), capture=False)
    return True


def restore() -> dict:
    stopped = video.stop()
    _stop_swaybg()
    result = {"stopped_video": stopped, "restored": False}
    try:
        from .library import Library

        previous = Library().history_item(1)
    except Exception:
        previous = None
    if previous:
        try:
            apply(previous["path"], _config_for_restore(), monitor=previous.get("monitor", "all"),
                  fit=previous.get("fit", "crop"))
            result["restored"] = True
            result["path"] = previous["path"]
            return result
        except Exception:
            pass
    if _restore_previous():
        result["restored"] = True
        result["path"] = "previous wallpaper"
    with contextlib.suppress(OSError):
        constants.WALLPAPER_STATE.unlink()
    return result


def _config_for_restore():
    from .config import Config

    return Config()


def stop_video() -> int:
    return video.stop(notify_user=True)


def next_wallpaper(config) -> dict | None:
    from .library import Library

    library = Library()
    slideshow = config.get("wallpaper.slideshow", {})
    current = state().get("source")
    path = library.next_path(
        favorites_only=bool(slideshow.get("favorites_only")),
        skip_videos=bool(slideshow.get("skip_videos", True)),
        order=str(slideshow.get("order", "shuffle")),
        current=current,
    )
    if not path:
        return None
    return apply(path, config)
