"""Paint a wallpaper in an X11 desktop window.

This helper is deliberately separate from the GTK 4 application: it uses the
host's GTK 3 (which is already present on Ubuntu) so it can create a real
``_NET_WM_WINDOW_TYPE_DESKTOP`` window.  GNOME Shell draws its own background
above the X root pixmap, so nitrogen/feh cannot change a managed GNOME desktop.
A desktop window is stacked above the Shell background and below normal
windows, which gives us the same result without touching locked settings.

The window must be made sticky *after* it is mapped: GNOME Shell 42 ignores a
sticky hint set before the window is shown and ties the window to the workspace
where it first appeared.  Calling ``stick()`` after mapping makes it visible on
every workspace.

Run it with a system Python that has PyGObject + GTK 3, for example:

    /usr/bin/python3 aura_studio/x11_wallpaper.py /path/to/picture.jpg
"""
from __future__ import annotations

import ctypes
import os
import signal
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402


class WallpaperWindow:
    def __init__(self, path):
        self.path = os.path.realpath(path)
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.path)
        self.scaled = None
        self.scaled_size = (0, 0)
        self._x11 = None
        self._display = None

        self.window = Gtk.Window(title="Aura Studio wallpaper")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.window.set_accept_focus(False)
        self.window.set_focus_on_map(False)
        self.window.move(0, 0)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("screen-changed", self._screen_changed)

        self.area = Gtk.DrawingArea()
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        self.area.connect("draw", self._draw)
        self.window.add(self.area)

        self._resize_to_screen()
        self.window.show_all()
        # GNOME Shell 42 only honours sticky for an already-mapped window.
        GLib.timeout_add(500, self._stick)
        GLib.timeout_add(1000, self._lower)
        GLib.timeout_add(2000, self._lower)
        GLib.timeout_add_seconds(1, self._lower)

    def _screen(self):
        return self.window.get_screen() or Gdk.Screen.get_default()

    def _resize_to_screen(self):
        screen = self._screen()
        if screen is None:
            return
        width, height = screen.get_width(), screen.get_height()
        if width > 0 and height > 0:
            self.window.resize(width, height)
            self.window.move(0, 0)
            self.area.set_size_request(width, height)

    def _screen_changed(self, _window, _old_screen):
        self._resize_to_screen()
        GLib.timeout_add(300, self._stick)
        GLib.timeout_add(300, self._lower)
        return False

    def _stick(self):
        if self.window.get_window() is not None:
            self.window.stick()
            self._lower()
        return False

    def _cover(self, width, height):
        if width <= 0 or height <= 0:
            return None
        if self.scaled is not None and self.scaled_size == (width, height):
            return self.scaled
        source = self.pixbuf
        source_width, source_height = source.get_width(), source.get_height()
        if source_width <= 0 or source_height <= 0:
            return None
        target_aspect = width / height
        source_aspect = source_width / source_height
        if source_aspect > target_aspect:
            crop_width = max(1, int(round(source_height * target_aspect)))
            crop = source.new_subpixbuf((source_width - crop_width) // 2, 0,
                                        crop_width, source_height)
        else:
            crop_height = max(1, int(round(source_width / target_aspect)))
            crop = source.new_subpixbuf(0, (source_height - crop_height) // 2,
                                        source_width, crop_height)
        self.scaled = crop.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        self.scaled_size = (width, height)
        return self.scaled

    def _draw(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        scaled = self._cover(width, height)
        if scaled is not None:
            Gdk.cairo_set_source_pixbuf(cr, scaled, 0, 0)
            cr.paint()
        return False

    def _lower(self):
        gdk_window = self.window.get_window()
        if gdk_window is None:
            return True
        try:
            if self._x11 is None:
                self._x11 = ctypes.CDLL("libX11.so.6")
                self._x11.XOpenDisplay.restype = ctypes.c_void_p
                self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
                self._x11.XLowerWindow.restype = ctypes.c_int
                self._x11.XLowerWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                self._x11.XFlush.restype = ctypes.c_int
                self._x11.XFlush.argtypes = [ctypes.c_void_p]
                self._display = self._x11.XOpenDisplay(None)
            if self._display:
                self._x11.XLowerWindow(self._display, gdk_window.get_xid())
                self._x11.XFlush(self._display)
        except Exception:
            pass
        return True


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: x11_wallpaper.py PICTURE", file=sys.stderr)
        return 2
    if not os.path.isfile(argv[0]):
        print(f"not a file: {argv[0]}", file=sys.stderr)
        return 2
    try:
        WallpaperWindow(argv[0])
    except Exception as error:
        print(f"could not start the wallpaper window: {error}", file=sys.stderr)
        return 1

    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
