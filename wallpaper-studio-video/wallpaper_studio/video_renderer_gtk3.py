"""GTK 3 / GStreamer renderer used for X11 desktop windows (and Wayland fallback)."""

import argparse
import json
import os
from pathlib import Path
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, GLib, Gst, Gtk  # noqa: E402

TITLE_PREFIX = "@wallpaper-studio-video!"
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi")


def session_type() -> str:
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "wayland"
    return "x11"


def pick_sink(fit: str):
    for name in ("gtksink", "gtkglsink"):
        sink = Gst.ElementFactory.make(name)
        if sink is not None:
            if fit == "contain" and sink.find_property("force-aspect-ratio"):
                sink.set_property("force-aspect-ratio", True)
            elif sink.find_property("force-aspect-ratio"):
                sink.set_property("force-aspect-ratio", False)
            return sink
    return None


class VideoWindow(Gtk.Window):
    def __init__(self, path: Path, *, mute: bool, fit: str, monitor: int):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.path = path
        self.mute = mute
        self.fit = fit
        self.monitor_index = max(0, monitor)
        self.pipeline = None
        self.bus = None
        self.sink = None
        self._watch_id = 0

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_keep_below(True)
        self.set_keep_above(False)
        self.set_can_focus(False)
        self.connect("destroy", self._destroyed)

        if session_type() == "x11":
            try:
                self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            except Exception:
                pass

        geometry = self._monitor_geometry()
        self.set_default_size(geometry.width, geometry.height)
        self.move(geometry.x, geometry.y)
        self.set_title(f"{TITLE_PREFIX}{json.dumps({'pid': os.getpid(), 'monitor': self.monitor_index})}")

        self._build_pipeline()
        self._watch_id = GLib.timeout_add_seconds(2, self._watch_monitor)
        self.show_all()
        if session_type() == "x11":
            window = self.get_window()
            if window is not None:
                window.lower()

    def _monitor_geometry(self):
        display = Gdk.Display.get_default()
        if display is None:
            return Gdk.Rectangle(x=0, y=0, width=1920, height=1080)
        monitors = display.get_n_monitors()
        if monitors <= 0:
            return Gdk.Rectangle(x=0, y=0, width=1920, height=1080)
        index = min(self.monitor_index, monitors - 1)
        return display.get_monitor(index).get_geometry()

    def _build_pipeline(self):
        self.sink = pick_sink(self.fit)
        if self.sink is None:
            raise RuntimeError(
                "GStreamer's gtk3 video sink is missing. "
                "Install gstreamer1.0-gtk3 and gstreamer1.0-plugins-good."
            )
        widget = self.sink.get_property("widget")
        if widget is None:
            raise RuntimeError("The GStreamer GTK sink did not expose a widget")
        self.add(widget)

        self.pipeline = Gst.ElementFactory.make("playbin", "wallpaper")
        if self.pipeline is None:
            raise RuntimeError("GStreamer playbin is unavailable")
        audio = Gst.ElementFactory.make("fakesink" if self.mute else "autoaudiosink")
        if audio is None:
            audio = Gst.ElementFactory.make("fakesink")
        self.pipeline.set_property("uri", self.path.as_uri())
        self.pipeline.set_property("video-sink", self.sink)
        self.pipeline.set_property("audio-sink", audio)
        if self.pipeline.find_property("mute"):
            self.pipeline.set_property("mute", self.mute)
        self.pipeline.set_property("flags", Gst.PlayFlags.VIDEO | Gst.PlayFlags.AUDIO | Gst.PlayFlags.SOFT_VOLUME)

        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message::eos", self._loop)
        self.bus.connect("message::error", self._error)
        self.pipeline.set_state(Gst.State.PLAYING)

    def _loop(self, *_args):
        if self.pipeline is not None:
            self.pipeline.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                0,
            )
        return True

    def _error(self, _bus, message):
        error, debug = message.parse_error()
        print(f"video renderer: {error.message}" + (f" ({debug})" if debug else ""), file=sys.stderr)
        Gtk.main_quit()
        return True

    def _watch_monitor(self):
        geometry = self._monitor_geometry()
        self.resize(geometry.width, geometry.height)
        self.move(geometry.x, geometry.y)
        return True

    def _destroyed(self, *_args):
        if self._watch_id:
            GLib.source_remove(self._watch_id)
            self._watch_id = 0
        if self.bus is not None:
            self.bus.remove_signal_watch()
            self.bus = None
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        Gtk.main_quit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Wallpaper Studio Video renderer")
    parser.add_argument("--path", required=True)
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--fit", choices=("cover", "contain"), default="cover")
    parser.add_argument("--monitor", type=int, default=0)
    args = parser.parse_args(argv)

    path = Path(args.path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
        print(f"video renderer: not a supported video: {path}", file=sys.stderr)
        return 2

    Gst.init(None)
    Gtk.init(None)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    try:
        VideoWindow(path, mute=args.mute, fit=args.fit, monitor=args.monitor)
    except Exception as error:
        print(f"video renderer: {error}", file=sys.stderr)
        return 1
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
