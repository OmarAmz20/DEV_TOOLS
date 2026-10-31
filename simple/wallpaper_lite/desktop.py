"""A tiny fallback wallpaper window for X11 sessions where GNOME's picture is locked.

It is one GTK 3 window of type DESKTOP: no raw Xlib, no video player, no hooks. The
window is click-through-ish (it stays under everything) and reloads state.json once a
second, so applying a new picture from the main window updates it immediately.

On a normal GNOME session the background keys are writable, so this helper exits and
GNOME draws the picture itself.
"""
import fcntl
import os
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from . import core  # noqa: E402


class DesktopWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Wallpaper Lite")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_keep_below(True)
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.stick()

        self.pixbuf = None
        self.state_key = None
        self.background = (0.0, 0.0, 0.0)

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self.draw)
        self.add(self.area)

        screen = Gdk.Screen.get_default()
        if screen is not None:
            self.resize(max(1, screen.get_width()), max(1, screen.get_height()))
            screen.connect("size-changed", self.on_screen_changed)
        self.move(0, 0)

        # A desktop window should never be closed by the user.
        self.connect("delete-event", lambda *_: True)
        self.connect("map-event", self.on_map)
        self.load_state()
        GLib.timeout_add_seconds(1, self.poll)

    def on_map(self, *_):
        window = self.get_window()
        if window is not None:
            window.lower()
        return False

    def on_screen_changed(self, screen, *_):
        self.resize(max(1, screen.get_width()), max(1, screen.get_height()))
        self.state_key = None
        self.load_state()

    def poll(self):
        self.load_state()
        return True

    def load_state(self):
        state = core.load_state()
        path = state.get("wallpaper")
        key = None
        if isinstance(path, str) and os.path.isfile(path):
            try:
                st = os.stat(path)
                key = (path, st.st_mtime_ns, st.st_size)
            except OSError:
                key = None
        palette = state.get("palette")
        if isinstance(palette, dict):
            mode = state.get("mode") if state.get("mode") in ("light", "dark") else "dark"
            p = palette.get(mode) or {}
            value = p.get("paper")
            if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
                self.background = tuple(int(value[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

        if key == self.state_key:
            return
        self.state_key = key
        self.pixbuf = None
        if key is not None:
            screen = Gdk.Screen.get_default()
            width = max(1, screen.get_width()) if screen else 1920
            height = max(1, screen.get_height()) if screen else 1080
            try:
                core.validate_image(path)
                self.pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, width, height, True)
            except (ValueError, GLib.Error, OSError):
                self.pixbuf = None
        self.area.queue_draw()

    def draw(self, widget, cr):
        allocation = widget.get_allocation()
        width, height = max(1, allocation.width), max(1, allocation.height)

        cr.set_source_rgb(*self.background)
        cr.paint()

        pixbuf = self.pixbuf
        if pixbuf is None or not pixbuf.get_width() or not pixbuf.get_height():
            return False

        pw, ph = pixbuf.get_width(), pixbuf.get_height()
        scale = max(width / pw, height / ph)
        cr.save()
        cr.scale(scale, scale)
        cr.translate((width / scale - pw) / 2.0, (height / scale - ph) / 2.0)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
        cr.restore()
        return False


def _quit(*_):
    Gtk.main_quit()


def main():
    if (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or os.environ.get("WAYLAND_DISPLAY")):
        print("wallpaper-lite: the desktop helper needs an X11 session", file=sys.stderr)
        return 1

    result = Gtk.init_check(sys.argv)
    started = result[0] if isinstance(result, tuple) else result
    if not started:
        print("wallpaper-lite: no display", file=sys.stderr)
        return 1

    # On a normal session GNOME can draw the picture itself; do not cover it.
    if not os.environ.get("WALLPAPER_LITE_FORCE") and core.gnome_background_writable():
        return 0

    # The helper is only useful when there is a picture to show.
    saved = core.load_state().get("wallpaper")
    if not saved or not os.path.isfile(saved):
        return 0

    try:
        os.makedirs(core.runtime_dir(), mode=0o700, exist_ok=True)
        lock_path = os.path.join(core.runtime_dir(), "desktop.lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
        lock = os.fdopen(lock_fd, "r+", encoding="utf-8")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0

    core.write_helper_pid()
    signal.signal(signal.SIGTERM, _quit)
    signal.signal(signal.SIGINT, _quit)
    try:
        window = DesktopWindow()
        window.show_all()
        Gtk.main()
    finally:
        core.remove_helper_pid()
        try:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        except OSError:
            pass
    return 0
