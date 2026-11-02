"""The existing personal dconf profile + normal GNOME login, without a desktop overlay.

This module is deliberately standard-library-only. Entry points prepare the
environment before importing Gio so every app process reads the same profile.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


class BackendError(RuntimeError):
    pass


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".studio-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_environment() -> Path:
    """Reuse the working profile byte-for-byte; create one only when absent."""
    home = Path.home()
    profile = home / ".config/dconf/wallpaper-profile"
    if not profile.exists():
        current = os.environ.get("DCONF_PROFILE", "user")
        source = Path(current) if current.startswith("/") else Path("/etc/dconf/profile") / current
        storage = "user-db:user"
        try:
            for line in source.read_text(encoding="utf-8").splitlines():
                if re.match(r"^\s*(user-db:|service-db:)", line):
                    storage = line.strip()
                    break
        except OSError:
            pass
        atomic_write(profile, storage + "\n")
    if not profile.is_file():
        raise BackendError(f"The personal GNOME profile is not a readable file: {profile}")
    os.environ["DCONF_PROFILE"] = str(profile)
    os.environ["GSETTINGS_BACKEND"] = "dconf"
    return profile


@dataclass
class Status:
    profile: str
    service: str | None
    loaded: bool | None
    writable: bool
    warning: str = ""

    @property
    def summary(self):
        if not self.writable:
            return "Wallpaper settings are unavailable in this session"
        if self.loaded is True:
            return "Your existing GNOME wallpaper setup is ready"
        if self.loaded is False:
            return "A normal logout/login is needed once"
        return "Personal GNOME settings selected"


class NativeBackend:
    SCHEMA = "org.gnome.desktop.background"
    FITS = {"zoom", "scaled", "stretched", "centered", "wallpaper", "spanned"}

    def __init__(self, runner=None):
        self.profile = Path.home() / ".config/dconf/wallpaper-profile"
        self.config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.runner = runner or subprocess.run

    def _run(self, args, *, allow_failure=False):
        try:
            result = self.runner(args, capture_output=True, text=True, timeout=6,
                                 env={**os.environ, "DCONF_PROFILE": str(self.profile),
                                      "GSETTINGS_BACKEND": "dconf"})
        except (OSError, subprocess.TimeoutExpired) as error:
            if allow_failure:
                return None
            raise BackendError(f"Could not access GNOME settings: {error}") from error
        if not allow_failure and (result.returncode or result.stderr.strip()):
            raise BackendError(result.stderr.strip() or result.stdout.strip() or "GNOME rejected the change")
        return result

    def get(self, key):
        result = self._run(["gsettings", "get", self.SCHEMA, key])
        return result.stdout.strip()

    def writable(self, key):
        result = self._run(["gsettings", "writable", self.SCHEMA, key], allow_failure=True)
        return bool(result and result.returncode == 0 and not result.stderr.strip()
                    and result.stdout.strip() == "true")

    def service(self):
        kinds = [os.environ.get("XDG_SESSION_TYPE", "x11"), "x11", "wayland"]
        for kind in dict.fromkeys(kinds):
            if kind not in ("x11", "wayland"):
                continue
            unit = f"org.gnome.Shell@{kind}.service"
            result = self._run(["systemctl", "--user", "is-active", "--quiet", unit], allow_failure=True)
            if result and result.returncode == 0:
                return unit
        return None

    def _loaded(self, unit):
        if not unit:
            return None
        result = self._run(["systemctl", "--user", "show", unit, "--property=MainPID", "--value"],
                           allow_failure=True)
        if not result or not result.stdout.strip().isdigit() or int(result.stdout.strip()) <= 0:
            return None
        try:
            data = Path(f"/proc/{int(result.stdout.strip())}/environ").read_bytes().split(b"\0")
            return b"DCONF_PROFILE=" + str(self.profile).encode() in data
        except OSError:
            return None

    def status(self):
        unit = self.service()
        return Status(str(self.profile), unit, self._loaded(unit), self.writable("picture-uri"))

    def ensure_setup(self):
        """Keep the known working override unchanged. No Shell start/stop/restart."""
        if os.geteuid() == 0:
            raise BackendError("Open Wallpaper Studio Video as your normal desktop user, without sudo.")
        prepare_environment()
        if not self.writable("picture-uri"):
            raise BackendError("GNOME could not write your personal wallpaper settings. Open the app in your normal Ubuntu desktop session.")
        unit = self.service()
        if not unit:
            raise BackendError("No active GNOME Shell user service was found. Your existing login configuration was left unchanged.")
        override = self.config_root / "systemd/user" / (unit + ".d") / "wallpaper-profile.conf"
        created = False
        if override.exists():
            # It is the file used by Hatim's already-working setup. Do not
            # rewrite it, change its permissions, or replace it on app updates.
            text = override.read_text(encoding="utf-8")
            found = []
            for line in text.splitlines():
                if line.strip().startswith("Environment="):
                    try:
                        found.extend(shlex.split(line.strip().partition("=")[2]))
                    except ValueError:
                        continue
            expected = "DCONF_PROFILE=" + str(self.profile)
            if expected not in [value.replace("%%", "%") for value in found]:
                if self._loaded(unit) is not True:
                    raise BackendError("A different GNOME startup override already exists. Plus left it unchanged; check Preferences → Native wallpaper setup.")
        else:
            value = str(self.profile).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
            atomic_write(override, f'[Service]\nEnvironment="DCONF_PROFILE={value}"\nEnvironment=GSETTINGS_BACKEND=dconf\n')
            self._run(["systemctl", "--user", "daemon-reload"])
            created = True
        loaded = self._loaded(unit)
        return Status(str(self.profile), unit, False if created and loaded is None else loaded, True)

    def apply_image(self, path, target="both", fit="zoom"):
        if target not in {"both", "light", "dark"} or fit not in self.FITS:
            raise BackendError("Choose a valid wallpaper target and fit.")
        image = Path(path).resolve(strict=True)
        if not image.is_file():
            raise BackendError("Choose a readable image file.")
        status = self.ensure_setup()
        changes = []
        if target in {"both", "light"}:
            changes.append(("picture-uri", repr(image.as_uri())))
        if target in {"both", "dark"}:
            changes.append(("picture-uri-dark", repr(image.as_uri())))
        changes.append(("picture-options", repr(fit)))
        previous = {}
        for key, value in changes:
            if not self.writable(key):
                raise BackendError(f"GNOME will not change {key}. No wallpaper settings were changed.")
            previous[key] = self.get(key)
        completed = []
        try:
            for key, value in changes:
                completed.append(key)
                self._run(["gsettings", "set", self.SCHEMA, key, value])
                if ast.literal_eval(self.get(key)) != ast.literal_eval(value):
                    raise BackendError("The wallpaper value could not be saved to the GNOME database.")
        except (BackendError, ValueError, SyntaxError):
            for key in reversed(completed):
                self._run(["gsettings", "set", self.SCHEMA, key, previous[key]], allow_failure=True)
            raise
        return status

    def current_image(self, dark=False):
        try:
            from urllib.parse import unquote, urlparse
            uri = ast.literal_eval(self.get("picture-uri-dark" if dark else "picture-uri"))
            parsed = urlparse(uri)
            if parsed.scheme == "file":
                path = Path(unquote(parsed.path))
                if path.is_file():
                    return str(path)
        except (BackendError, SyntaxError, ValueError):
            pass
        return None
