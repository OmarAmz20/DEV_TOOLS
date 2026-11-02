"""Background slideshow and auto light/dark schedule."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import sys
import time
from pathlib import Path

from . import constants, desktop, themes, wallpaper
from .config import Config
from .util import (
    pid_alive,
    popen,
    read_json,
    read_pid,
    stop_pid,
    write_pid,
)


def running() -> bool:
    return bool(read_pid(constants.SESSION_PID))


def status() -> dict:
    pid = read_pid(constants.SESSION_PID)
    return {"running": bool(pid), "pid": pid}


def start() -> dict:
    if running():
        return status()
    env = os.environ.copy()
    env.pop("LD_PRELOAD", None)
    env["PYTHONPATH"] = str(constants.APP_ROOT) + (
        ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    constants.LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [sys.executable, "-m", "leet_customizer.sessiond", "--config", str(constants.CONFIG_FILE)]
    try:
        with open(constants.SESSION_LOG, "ab") as log:
            log.write(f"\n[{time.strftime('%F %T')}] starting session helper\n".encode())
            log.flush()
            process = popen(command, env=env, stdout=log, stderr=log)
    except OSError as error:
        raise RuntimeError(f"Could not start session helper: {error}") from error
    for _ in range(20):
        time.sleep(0.1)
        if running():
            return status()
        if process.poll() is not None:
            break
    return status()


def stop() -> bool:
    return stop_pid(constants.SESSION_PID, grace=2.0)


def autostart_needed(config: Config) -> bool:
    slideshow = config.get("wallpaper.slideshow", {})
    schedule = config.get("appearance.dark_schedule", {})
    return bool(slideshow.get("enabled") or (config.get("appearance.mode") == "auto"
                                             and schedule.get("enabled")))


def start_if_needed(config: Config) -> dict:
    if autostart_needed(config):
        return start()
    return status()


class SessionLoop:
    def __init__(self, config: Config):
        self.config = config
        self.last_slide = 0.0
        self.last_variant = ""
        self.last_config_mtime = 0.0
        self.stop_requested = False

    def log(self, message: str) -> None:
        print(time.strftime("[%F %T] "), message, flush=True)

    def reload(self) -> None:
        try:
            mtime = constants.CONFIG_FILE.stat().st_mtime
        except OSError:
            return
        if mtime != self.last_config_mtime:
            self.last_config_mtime = mtime
            self.config.reload()
            self.log("configuration reloaded")

    def tick(self, now: float) -> None:
        self.reload()
        slideshow = self.config.get("wallpaper.slideshow", {})
        if slideshow.get("enabled"):
            interval = max(1, int(slideshow.get("minutes", 30))) * 60
            if not self.last_slide:
                self.last_slide = now - (interval if slideshow.get("apply_on_start") else 0)
            if now - self.last_slide >= interval:
                self.last_slide = now
                try:
                    result = wallpaper.next_wallpaper(self.config)
                    if result:
                        self.log(f"slideshow: {result.get('source')}")
                    else:
                        self.log("slideshow: no eligible wallpapers")
                except Exception as error:
                    self.log(f"slideshow error: {error}")
        else:
            self.last_slide = 0.0

        if self.config.get("appearance.mode") == "auto":
            schedule = self.config.get("appearance.dark_schedule", {})
            if schedule.get("enabled"):
                desired = themes.desired_variant("auto", schedule)
                state = read_json(constants.THEME_STATE, {})
                current = (state.get("theme") or {}).get("variant") if isinstance(state, dict) else None
                if desired != current:
                    try:
                        theme, result = desktop.apply_theme_from_config(self.config, variant=desired)
                        self.log(f"schedule: applied {desired} variant")
                    except Exception as error:
                        self.log(f"schedule error: {error}")

    def run(self) -> int:
        write_pid(constants.SESSION_PID, os.getpid())
        self.last_config_mtime = 0.0
        self.log("session helper ready")

        def handle_signal(_signum, _frame):
            self.stop_requested = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
        while not self.stop_requested:
            self.tick(time.monotonic())
            for _ in range(10):
                if self.stop_requested:
                    break
                time.sleep(0.5)
        with contextlib.suppress(OSError):
            if read_pid(constants.SESSION_PID) == os.getpid():
                constants.SESSION_PID.unlink()
        self.log("session helper stopped")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="1337-sessiond")
    parser.add_argument("--config", default=str(constants.CONFIG_FILE))
    args = parser.parse_args(argv)
    config = Config(args.config)
    return SessionLoop(config).run()


if __name__ == "__main__":
    raise SystemExit(main())
