#!/usr/bin/env python3
"""Supervise the video renderer and keep the runtime PID file in sync."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

try:
    from . import video_wallpaper as vw
except ImportError:  # run as a plain script from the installed app
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from wallpaper_studio import video_wallpaper as vw  # type: ignore

STOP = False


def _stop(*_args):
    global STOP
    STOP = True


def _state_mtime() -> float:
    try:
        return vw.STATE_FILE.stat().st_mtime
    except OSError:
        return 0.0


def _renderer_command(state: dict) -> list[str]:
    command = [
        sys.executable, str(vw.renderer_script()),
        "--path", state["path"],
        "--fit", state.get("fit", "cover"),
        "--monitor", str(state.get("monitor", 0)),
    ]
    if state.get("mute", True):
        command.append("--mute")
    return command


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    state = vw.load()
    if not state.get("enabled") or not state.get("path"):
        vw._write_runtime(renderer_pid=0, supervisor_pid=os.getpid(), error="")
        return 0

    vw.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(vw.LOG_FILE, "ab", buffering=0)
    last_mtime = _state_mtime()
    delay = 0.4
    child = None
    child_started = 0.0
    ready = False
    failures = 0
    final_error = ""
    try:
        while not STOP:
            state = vw.load()
            if not state.get("enabled") or not state.get("path"):
                break

            if child is not None and child.poll() is not None:
                lived = time.monotonic() - child_started
                failures = failures + 1 if lived < 2.0 else 0
                child = None
                ready = False
                vw._write_runtime(
                    renderer_pid=0, ready=False, failures=failures,
                    error="The video renderer exited; see the log.",
                )
                if failures >= 5:
                    final_error = "The video renderer failed five times. Check the log and the GStreamer packages."
                    vw._write_runtime(
                        renderer_pid=0, supervisor_pid=0, ready=False,
                        failures=failures, error=final_error,
                    )
                    break
                time.sleep(delay)
                delay = min(5.0, delay * 1.7)

            if child is None:
                try:
                    child = subprocess.Popen(
                        _renderer_command(state),
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=True, close_fds=True,
                    )
                except OSError as error:
                    vw._write_runtime(renderer_pid=0, supervisor_pid=os.getpid(),
                                      ready=False, error=str(error))
                    time.sleep(delay)
                    delay = min(5.0, delay * 1.7)
                    continue
                child_started = time.monotonic()
                ready = False
                vw._write_runtime(
                    renderer_pid=child.pid, supervisor_pid=os.getpid(),
                    started=time.time(), session=vw.session_type(),
                    error="", ready=False, failures=failures,
                )
            elif not ready and time.monotonic() - child_started >= 1.0:
                ready = True
                failures = 0
                delay = 0.4
                vw._write_runtime(ready=True, failures=0, error="")

            mtime = _state_mtime()
            if mtime != last_mtime:
                last_mtime = mtime
                current = vw.load()
                if current != state:
                    if child is not None and child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            child.kill()
                    child = None
                    ready = False
                    failures = 0
                    vw._write_runtime(renderer_pid=0, supervisor_pid=os.getpid(),
                                      ready=False, failures=0, error="")
            time.sleep(0.25)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
        vw._write_runtime(renderer_pid=0, supervisor_pid=0, started=0,
                          error=final_error, ready=False,
                          failures=failures if final_error else 0)
        log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
