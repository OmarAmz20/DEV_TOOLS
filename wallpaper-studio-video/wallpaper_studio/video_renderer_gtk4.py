"""GTK 4 / GStreamer renderer used on GNOME Wayland.

GNOME does not implement wlr-layer-shell.  The renderer is a normal toplevel;
the bundled Shell extension clones its actor into the background and hides the
original window.  ``gtk4paintablesink`` is provided by Ubuntu's
``libgtk-4-media-gstreamer`` / ``gstreamer1.0-gtk4`` packages.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, Gio, GLib, Gst, Gtk  # noqa: E402

TITLE_PREFIX = "@wallpaper-studio-video!"
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi")


def _monitor_geometry(index: int):
    display = Gdk.Display.get_default()
    if display is None:
        return Gdk.Rectangle(x=0, y=0, width=1920, height=1080)
    monitors = display.get_monitors()
    count = monitors.get_n_items()
    if count <= 0:
        return Gdk.Rectangle(x=0, y=0, width=1920, height=1080)
    monitor = monitors.get_item(min(max(index, 0), count - 1))
    return monitor.get_geometry()


class RendererWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, path: Path, *, mute: bool,
                 fit: str, monitor: int):
        super().__init__(application=app)
        self.path = path
        self.mute = mute
        self.fit = fit
        self.monitor_index = max(0, monitor)
        self.pipeline = None
        self.bus = None
        self._watch_id = 0

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_title(f"{TITLE_PREFIX}{json.dumps({'pid': os.getpid(), 'monitor': self.monitor_index})}")

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(False)
        self.picture.set_content_fit(Gtk.ContentFit.FILL if fit == "cover" else Gtk.ContentFit.CONTAIN)
        self.set_child(self.picture)

        geometry = _monitor_geometry(self.monitor_index)
        self.set_default_size(geometry.width, geometry.height)
        self._build_pipeline()
        self._watch_id = GLib.timeout_add_seconds(2, self._watch_monitor)
        self.present()

    def _build_pipeline(self) -> None:
        sink = Gst.ElementFactory.make("gtk4paintablesink")
        if sink is None:
            raise RuntimeError("gtk4paintablesink is missing")
        paintable = sink.get_property("paintable")
        if paintable is None:
            raise RuntimeError("gtk4paintablesink did not expose a paintable")
        self.picture.set_paintable(paintable)

        self.pipeline = Gst.ElementFactory.make("playbin", "wallpaper")
        if self.pipeline is None:
            raise RuntimeError("GStreamer playbin is unavailable")
        audio = Gst.ElementFactory.make("fakesink" if self.mute else "autoaudiosink")
        if audio is None:
            audio = Gst.ElementFactory.make("fakesink")
        self.pipeline.set_property("uri", self.path.as_uri())
        self.pipeline.set_property("video-sink", sink)
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
        self.get_application().quit()
        return True

    def _watch_monitor(self):
        geometry = _monitor_geometry(self.monitor_index)
        self.set_default_size(geometry.width, geometry.height)
        return True

    def stop_pipeline(self) -> None:
        if self._watch_id:
            GLib.source_remove(self._watch_id)
            self._watch_id = 0
        if self.bus is not None:
            self.bus.remove_signal_watch()
            self.bus = None
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None


class RendererApp(Gtk.Application):
    def __init__(self, path: Path, *, mute: bool, fit: str, monitor: int):
        super().__init__(application_id="io.github.WallpaperStudioVideo.Renderer",
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path = path
        self.mute = mute
        self.fit = fit
        self.monitor = monitor
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = RendererWindow(self, self.path, mute=self.mute,
                                        fit=self.fit, monitor=self.monitor)
            self.window.connect("destroy", self._destroyed)

    def _destroyed(self, window):
        window.stop_pipeline()
        self.window = None
        self.quit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Wallpaper Studio Video GTK4 renderer")
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
    app = RendererApp(path, mute=args.mute, fit=args.fit, monitor=args.monitor)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    try:
        return app.run([])
    except Exception as error:
        print(f"video renderer: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
