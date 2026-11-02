"""User-owned application dock: configuration, styling and process control.

The dock is independent from the GNOME dash.  It can be placed on any edge,
on all monitors or a chosen one, and started without enabling a Shell
extension.  The GTK4 helper uses wlr-layer-shell when available and falls back
to a normal window elsewhere.
"""

from __future__ import annotations

import ctypes.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import core, recipes

NAME = "Wallpaper Studio Video Dock"
CONFIG = Path(core.CONFIG_DIR) / "dock.json"
PID = Path(core.CONFIG_DIR) / "dock.pid"
STATE = Path(core.CONFIG_DIR) / "dock-state.json"
LOCK = Path(core.CONFIG_DIR) / "dock.lock"
LOG = Path(core.CACHE_DIR) / "dock.log"

POSITIONS = ("bottom", "top", "left", "right")
ALIGNMENTS = ("start", "center", "end")
STYLES = ("glass", "solid", "outline", "neon", "midnight", "minimal")


def default_apps() -> list[dict]:
    terminal = shutil.which("kitty") or shutil.which("gnome-terminal") or shutil.which("x-terminal-emulator")
    files = shutil.which("nautilus") or shutil.which("dolphin") or shutil.which("thunar")
    browser = next((shutil.which(name) for name in (
        "firefox", "chromium", "chromium-browser", "google-chrome",
        "brave-browser", "microsoft-edge",
    ) if shutil.which(name)), None)
    return [
        {
            "id": f"terminal-{uuid.uuid4().hex[:6]}",
            "label": "Terminal",
            "icon": "utilities-terminal",
            "command": terminal or "x-terminal-emulator",
            "desktop_file": "",
        },
        {
            "id": f"files-{uuid.uuid4().hex[:6]}",
            "label": "Files",
            "icon": "system-file-manager",
            "command": files or "xdg-open .",
            "desktop_file": "",
        },
        {
            "id": f"browser-{uuid.uuid4().hex[:6]}",
            "label": "Browser",
            "icon": "web-browser",
            "command": browser or "xdg-open https://example.com",
            "desktop_file": "",
        },
    ]


def normalise_app(app: dict) -> dict | None:
    if not isinstance(app, dict):
        return None
    if app.get("separator"):
        return {"id": str(app.get("id") or f"sep-{uuid.uuid4().hex[:6]}"),
                "separator": True}
    label = str(app.get("label") or "").strip()[:48]
    command = str(app.get("command") or "").strip()
    desktop_file = str(app.get("desktop_file") or "").strip()
    if not label or (not command and not desktop_file):
        return None
    icon = str(app.get("icon") or "application-x-executable").strip()[:160]
    return {
        "id": str(app.get("id") or f"{label.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"),
        "label": label,
        "icon": icon,
        "command": command,
        "desktop_file": desktop_file,
        "separator": False,
    }


def normalise(raw: dict | None = None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    apps = [normalise_app(app) for app in (raw.get("apps") or [])]
    apps = [app for app in apps if app]
    cleaned = []
    for app in apps:
        if app.get("separator"):
            if cleaned and not cleaned[-1].get("separator"):
                cleaned.append(app)
        else:
            cleaned.append(app)
    while cleaned and cleaned[-1].get("separator"):
        cleaned.pop()
    apps = cleaned
    if not any(not app.get("separator") for app in apps):
        apps = default_apps()
    try:
        monitor = raw.get("monitor", "all")
        monitor = "all" if monitor in ("all", "", None) else int(monitor)
    except (TypeError, ValueError):
        monitor = "all"
    try:
        opacity = max(.25, min(1.0, float(raw.get("opacity", .86))))
    except (TypeError, ValueError):
        opacity = .86
    def bounded(key, default, low, high):
        try:
            return max(low, min(high, int(raw.get(key, default))))
        except (TypeError, ValueError):
            return default
    return {
        "enabled": bool(raw.get("enabled", False)),
        "monitor": monitor,
        "position": raw.get("position") if raw.get("position") in POSITIONS else "bottom",
        "alignment": raw.get("alignment") if raw.get("alignment") in ALIGNMENTS else "center",
        "style": raw.get("style") if raw.get("style") in STYLES else "glass",
        "opacity": opacity,
        "icon_size": bounded("icon_size", 42, 20, 96),
        "spacing": bounded("spacing", 8, 0, 32),
        "padding": bounded("padding", 8, 2, 40),
        "radius": bounded("radius", 18, 0, 40),
        "accent": str(raw.get("accent") or "").strip() if recipes.valid_hex(str(raw.get("accent") or "").strip()) else "",
        "show_labels": bool(raw.get("show_labels", False)),
        "reserve_space": bool(raw.get("reserve_space", False)),
        "autostart": bool(raw.get("autostart", False)),
        "apps": apps,
    }


def load() -> dict:
    try:
        with open(CONFIG, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        raw = {}
    return normalise(raw)


def save(payload: dict | None = None, **changes) -> dict:
    current = load()
    if payload:
        current.update(payload)
    current.update(changes)
    current = normalise(current)
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = CONFIG.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.chmod(temp, 0o600)
    os.replace(temp, CONFIG)
    return current


def add_app(app: dict) -> dict:
    current = load()
    item = normalise_app(app)
    if item:
        current["apps"].append(item)
        save(current)
    return current


def remove_app(identifier: str) -> dict:
    current = load()
    current["apps"] = [app for app in current["apps"] if app.get("id") != identifier]
    if not any(not app.get("separator") for app in current["apps"]):
        current["apps"] = default_apps()
    return save(current)


def move_app(identifier: str, offset: int) -> dict:
    current = load()
    index = next((i for i, app in enumerate(current["apps"]) if app.get("id") == identifier), None)
    if index is not None:
        target = max(0, min(len(current["apps"]) - 1, index + offset))
        current["apps"].insert(target, current["apps"].pop(index))
        save(current)
    return current


def palette(mode: str | None = None) -> dict:
    try:
        config = core.load_config()
        modes = core.preview_palette(None, config)
        return modes[mode or core.effective_mode(config)]
    except Exception:
        return recipes.resolve(recipes.sample_base(), core.load_config()).get("dark", {})


def _rgb(value: str) -> str:
    r, g, b = core.palette.hex_to_rgb(value)
    return f"{round(r * 255)},{round(g * 255)},{round(b * 255)}"


def _rgba(value: str, alpha: float) -> str:
    return f"rgba({_rgb(value)},{max(0.0, min(1.0, alpha)):.2f})"


def css(config: dict | None = None) -> str:
    config = config or load()
    mode = "dark" if core.effective_mode() == "dark" else "light"
    p = palette(mode)
    sheet = p.get("sheet", "#20242b")
    paper = p.get("paper", "#161a20")
    ink = p.get("ink", "#f5f6f8")
    accent = config.get("accent") or p.get("accent", "#7aa2ff")
    alpha = float(config.get("opacity", .86))
    radius = int(config.get("radius", 18))
    padding = int(config.get("padding", 8))
    style = config.get("style", "glass")
    if style == "solid":
        bg = _rgba(sheet, alpha)
        border, shadow = f"1px solid rgba(255,255,255,.10)", "0 12px 30px rgba(0,0,0,.30)"
    elif style == "outline":
        bg = "rgba(8,10,15,.35)"
        border, shadow = f"1.5px solid {accent}", "0 0 16px rgba(0,0,0,.22)"
    elif style == "neon":
        bg = "rgba(4,6,12,.86)"
        border, shadow = f"1.5px solid {accent}", f"0 0 20px {accent}55"
    elif style == "midnight":
        bg = _rgba(paper, max(.6, alpha))
        border, shadow = "1px solid rgba(255,255,255,.10)", "0 14px 34px rgba(0,0,0,.45)"
    elif style == "minimal":
        bg = _rgba(sheet, max(.35, alpha - .18))
        border, shadow = "1px solid rgba(255,255,255,.06)", "none"
    else:  # glass
        bg = _rgba(sheet, max(.55, alpha - .04))
        border, shadow = "1px solid rgba(255,255,255,.16)", "0 14px 36px rgba(0,0,0,.32)"
    return f"""
window.dock-window, .dock-window {{
  background-color: transparent;
  background-image: none;
}}
.dock-card {{
  background-color: {bg};
  border: {border};
  border-radius: {radius}px;
  padding: {padding}px;
  box-shadow: {shadow};
}}
.dock-button {{
  background-color: transparent;
  background-image: none;
  border: 0;
  border-radius: {max(4, radius - 6)}px;
  padding: 4px;
  color: {ink};
  min-width: 0;
  min-height: 0;
}}
.dock-button:hover {{
  background-color: {accent}38;
}}
.dock-button:active {{
  background-color: {accent}68;
}}
.dock-label {{
  color: {ink};
  font-size: 9pt;
  font-weight: 600;
}}
.dock-dot {{
  background-color: {accent};
  border-radius: 999px;
  min-width: 5px;
  min-height: 5px;
}}
.dock-separator {{
  background-color: rgba(255,255,255,.18);
  min-width: 1px;
  min-height: 1px;
  margin: 4px 2px;
}}
.dock-preview-stage {{
  border-radius: 16px;
  padding: 24px;
  background:
    radial-gradient(circle at 20% 0%, {accent}30, transparent 55%),
    {paper};
  border: 1px solid rgba(255,255,255,.08);
}}
"""


def launch_app(app: dict) -> bool:
    """Launch a desktop entry or a custom command from the dock."""
    try:
        desktop_file = app.get("desktop_file")
        if desktop_file and Path(desktop_file).exists():
            from gi.repository import Gio
            info = Gio.DesktopAppInfo.new_from_filename(desktop_file)
            if info:
                info.launch([], None)
                return True
        command = app.get("command")
        if command:
            subprocess.Popen(["sh", "-c", command], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return True
    except Exception:
        pass
    return False


def _gi_environment() -> dict[str, str]:
    env = os.environ.copy()
    typelibs = [p for p in (
        "/usr/lib/girepository-1.0",
        "/usr/lib64/girepository-1.0",
        "/usr/lib/x86_64-linux-gnu/girepository-1.0",
        "/usr/local/lib/girepository-1.0",
    ) if Path(p).is_dir()]
    current = [p for p in env.get("GI_TYPELIB_PATH", "").split(":") if p]
    env["GI_TYPELIB_PATH"] = ":".join(dict.fromkeys(current + typelibs))
    library = None
    for candidate in (
        "/usr/lib/libgtk4-layer-shell.so",
        "/usr/lib64/libgtk4-layer-shell.so",
        "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
        "/usr/local/lib/libgtk4-layer-shell.so",
    ):
        if Path(candidate).exists():
            library = candidate
            break
    library = library or ctypes.util.find_library("gtk4-layer-shell")
    if library:
        preload = [p for p in env.get("LD_PRELOAD", "").split(":") if p]
        if library not in preload:
            preload.insert(0, library)
        env["LD_PRELOAD"] = ":".join(preload)
    root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = root + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    return env


def _daemon_pids() -> list[int]:
    pids = []
    current = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == current:
            continue
        try:
            parts = [part.decode("utf-8", "replace")
                     for part in (entry / "cmdline").read_bytes().split(b"\0") if part]
        except OSError:
            continue
        if len(parts) > 2 and Path(parts[0]).name.startswith("python") and \
                parts[1] == "-m" and parts[2] == "wallpaper_studio.dock_daemon":
            pids.append(int(entry.name))
    return pids


def running() -> bool:
    return bool(_read_pid() or _daemon_pids())


def _read_pid() -> int | None:
    try:
        value = int(PID.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(value, 0)
    except OSError:
        return None
    return value


def status() -> dict:
    pid = _read_pid()
    pids = _daemon_pids()
    state = {}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {**state, "running": bool(pid or pids),
            "pid": pid or (pids[0] if pids else None), "processes": pids}


def start() -> dict:
    stop()
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = _gi_environment()
    LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [sys.executable, "-m", "wallpaper_studio.dock_daemon"]
    try:
        with open(LOG, "ab") as log:
            log.write(f"\n[{time.strftime('%F %T')}] starting dock\n".encode())
            log.flush()
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, env=env,
                                       start_new_session=True)
    except OSError as error:
        raise RuntimeError(f"Could not start the dock: {error}") from error
    for _ in range(30):
        time.sleep(.1)
        if running():
            return status()
        if process.poll() is not None:
            break
    tail = ""
    try:
        tail = "\n".join(LOG.read_text(errors="replace").splitlines()[-18:])
    except OSError:
        pass
    raise RuntimeError("Dock exited at startup. " + tail)


def stop() -> bool:
    pids = set(_daemon_pids())
    pid = _read_pid()
    if pid:
        pids.add(pid)
    stopped = False
    for value in pids:
        try:
            os.kill(value, signal.SIGTERM)
            stopped = True
        except OSError:
            pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and any(_alive(value) for value in pids):
        time.sleep(.05)
    for value in pids:
        if _alive(value):
            try:
                os.kill(value, signal.SIGKILL)
            except OSError:
                pass
    for path in (PID, STATE):
        try:
            path.unlink()
        except OSError:
            pass
    return stopped


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def autostart_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "wallpaper-studio-video-dock.desktop"


def _desktop_exec(path: str) -> str:
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
    escaped = escaped.replace("$", "\\$").replace("%", "%%")
    return f'"{escaped}"'


def set_autostart(enabled: bool) -> None:
    path = autostart_file()
    if not enabled:
        try:
            path.unlink()
        except OSError:
            pass
        return
    launcher = shutil.which("wallpaper-studio-video") or str(
        Path(__file__).resolve().parent.parent / "wallpaper-studio-video"
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Wallpaper Studio Video Dock\n"
        "Comment=Start the Wallpaper Studio Video dock\n"
        f"Exec={_desktop_exec(launcher)} dock start\n"
        "Icon=io.github.WallpaperStudioVideo\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o644)
