#!/usr/bin/env python3
"""Choose the best GTK/GStreamer video sink and launch its renderer."""
from __future__ import annotations

import json
import os
import sys

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

try:
    from . import video_wallpaper as vw
except ImportError:  # run as a plain script
    import video_wallpaper as vw  # type: ignore


def session_type() -> str:
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "wayland"
    return "x11"


def available_sinks() -> list[str]:
    registry = Gst.Registry.get()
    found = []
    for name in ("gtk4paintablesink", "gtksink"):
        if registry.find_feature(name, Gst.ElementFactory):
            found.append(name)
    return found


def _implementation(name: str):
    module = "video_renderer_gtk4" if name == "gtk4paintablesink" else "video_renderer_gtk3"
    try:
        if __package__:
            return __import__(f"{__package__}.{module}", fromlist=[module])
        return __import__(module)
    except Exception:
        return None


def main(argv=None) -> int:
    Gst.init(None)
    sinks = available_sinks()
    order = ("gtksink", "gtk4paintablesink") if session_type() == "x11" \
        else ("gtk4paintablesink", "gtksink")
    for name in order:
        if name not in sinks:
            continue
        implementation = _implementation(name)
        if implementation is not None:
            try:
                vw.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                vw.SINK_FILE.write_text(
                    json.dumps({"sink": name, "pid": os.getpid()}) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                pass
            return implementation.main(argv)
    print(
        "video renderer: no GTK video sink is available. "
        "On Ubuntu install gstreamer1.0-gtk3 (X11/GTK3) and "
        "libgtk-4-media-gstreamer or gstreamer1.0-gtk4 (GNOME Wayland).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
