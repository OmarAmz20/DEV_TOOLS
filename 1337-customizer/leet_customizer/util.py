"""Small, dependency-free helpers used by both the GUI and the CLI."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from . import constants


def _clean_environment(env: dict[str, str] | None) -> dict[str, str]:
    if env is not None:
        return env
    cleaned = os.environ.copy()
    # A widget host preloads gtk4-layer-shell into itself; child utilities such
    # as playerctl and ffmpeg must not inherit that preload.
    cleaned.pop("LD_PRELOAD", None)
    return cleaned


def run(
    command: Iterable[str] | str,
    *,
    timeout: float = 15,
    env: dict[str, str] | None = None,
    stdin: Any = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command and always return a CompletedProcess (never raises OSError)."""
    if isinstance(command, str):
        command = shlex.split(command)
    command = [str(part) for part in command]
    env = _clean_environment(env)
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            input=stdin,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        process = subprocess.CompletedProcess(command, 1, "", str(error))
    if check and process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or f"command failed: {command}")
    return process


def popen(
    command: Iterable[str] | str,
    *,
    env: dict[str, str] | None = None,
    stdout: Any = subprocess.DEVNULL,
    stderr: Any = subprocess.DEVNULL,
    cwd: str | None = None,
) -> subprocess.Popen:
    if isinstance(command, str):
        command = shlex.split(command)
    env = _clean_environment(env)
    return subprocess.Popen(
        [str(part) for part in command],
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        env=env,
        cwd=cwd,
        start_new_session=True,
        close_fds=True,
    )


def which(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def read_json(path: Path | str, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def atomic_write_text(path: Path | str, text: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def atomic_write_bytes(path: Path | str, data: bytes, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def write_json(path: Path | str, payload: Any, mode: int = 0o600) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n", mode)


def human_size(value: int | float) -> str:
    value = float(value or 0)
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or suffix == "TB":
            return f"{value:.0f} {suffix}" if suffix == "B" else f"{value:.1f} {suffix}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: float | int | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "theme"


def pretty_name(path: str | Path) -> str:
    return Path(path).stem.replace("_", " ").replace("-", " ").strip() or Path(path).name


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def file_uri(path: str | Path) -> str:
    from urllib.parse import quote

    return "file://" + quote(str(Path(path).resolve()))


_NOTIFICATIONS_ENABLED = True


def set_notifications(enabled: bool) -> None:
    global _NOTIFICATIONS_ENABLED
    _NOTIFICATIONS_ENABLED = bool(enabled)


def notify(title: str, body: str = "", *, urgent: bool = False) -> None:
    """Best-effort desktop notification without importing GLib."""
    if not _NOTIFICATIONS_ENABLED:
        return
    notifier = which("notify-send")
    if not notifier:
        return
    command = [notifier, "-a", constants.APP_NAME, "-t", "4500"]
    if urgent:
        command += ["-u", "critical"]
    command += [str(title), str(body)]
    with contextlib.suppress(OSError):
        popen(command)


def open_path(path: str | Path) -> None:
    opener = which("xdg-open")
    if opener:
        popen([opener, str(path)])


def open_uri(uri: str) -> None:
    opener = which("xdg-open")
    if opener:
        popen([opener, uri])


def ensure_gi_paths() -> None:
    """Make gtk4-layer-shell's typelib discoverable without changing the system."""
    existing = [part for part in os.environ.get("GI_TYPELIB_PATH", "").split(":") if part]
    candidates = [str(path) for path in constants.TYPE_LIB_PATHS if Path(path).is_dir()]
    merged = []
    for path in existing + candidates:
        if path not in merged:
            merged.append(path)
    if merged:
        os.environ["GI_TYPELIB_PATH"] = ":".join(merged)


def find_layer_shell_library() -> str | None:
    for candidate in constants.LAYER_SHELL_LIBRARY_PATHS:
        if Path(candidate).exists():
            return candidate
    try:
        import ctypes.util

        return ctypes.util.find_library("gtk4-layer-shell")
    except Exception:
        return None


def layer_shell_environment() -> dict[str, str]:
    """Environment for subprocesses that create layer-shell windows.

    GTK4 layer shell must be preloaded before libwayland-client on the PyGObject
    stack, otherwise the protocol object cannot be initialised.
    """
    env = os.environ.copy()
    ensure_gi_paths()
    env.update({key: value for key, value in os.environ.items() if key in ("GI_TYPELIB_PATH",)})
    library = find_layer_shell_library()
    if library:
        preload = env.get("LD_PRELOAD", "")
        parts = [part for part in preload.split(":") if part]
        if library not in parts:
            parts.insert(0, library)
        env["LD_PRELOAD"] = ":".join(parts)
    return env


def has_layer_shell() -> bool:
    """Whether GTK4 layer shell is importable in a disposable interpreter."""
    if not find_layer_shell_library():
        return False
    probe = (
        "import gi; gi.require_version('Gtk4LayerShell','1.0'); "
        "from gi.repository import Gtk4LayerShell; print('yes')"
    )
    result = run(["python3", "-c", probe], timeout=8, env=layer_shell_environment())
    return result.returncode == 0 and "yes" in result.stdout


def is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def is_hyprland() -> bool:
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) or \
        "hyprland" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def desktop_name() -> str:
    value = os.environ.get("XDG_CURRENT_DESKTOP", "").strip()
    return value or ("Hyprland" if is_hyprland() else "Linux")


def now() -> float:
    return time.time()


def strip_marked_block(text: str, begin: str, end: str) -> str:
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    return pattern.sub("", text)


def replace_marked_block(text: str, begin: str, end: str, body: str) -> str:
    text = strip_marked_block(text, begin, end).rstrip() + "\n"
    return text + f"{begin}\n{body.rstrip()}\n{end}\n"


def read_text(path: Path | str, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return default


def write_text_managed(path: Path | str, begin: str, end: str, body: str) -> None:
    path = Path(path)
    original = read_text(path)
    atomic_write_text(path, replace_marked_block(original, begin, end, body), mode=0o644)


def remove_text_managed(path: Path | str, begin: str, end: str) -> None:
    path = Path(path)
    if not path.exists():
        return
    original = read_text(path)
    updated = strip_marked_block(original, begin, end)
    if updated != original:
        atomic_write_text(path, updated, mode=0o644)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


def read_pid(path: Path | str) -> int | None:
    try:
        value = int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return value if pid_alive(value) else None


def write_pid(path: Path | str, pid: int) -> None:
    atomic_write_text(path, f"{pid}\n")


def stop_pid(path: Path | str, *, grace: float = 2.0) -> bool:
    pid = read_pid(path)
    if not pid:
        with contextlib.suppress(OSError):
            Path(path).unlink()
        return False
    try:
        os.kill(pid, 15)
    except OSError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            break
        time.sleep(0.05)
    if pid_alive(pid):
        with contextlib.suppress(OSError):
            os.kill(pid, 9)
    with contextlib.suppress(OSError):
        Path(path).unlink()
    return True
