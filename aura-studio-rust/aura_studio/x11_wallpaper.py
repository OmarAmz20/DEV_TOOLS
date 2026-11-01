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

    /usr/bin/python3 aura_studio/x11_wallpaper.py /path/to/picture.jpg fill
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
    def __init__(self, path, mode="fill"):
        self.path = os.path.realpath(path)
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.path)
        self.mode = mode if mode in (
            "fill", "fit", "stretch", "center", "tile", "span") else "fill"
        self.scaled = None
        self.scaled_size = (0, 0)
        self._x11 = None
        self._display = None
        self._workspace = None
        self._ticks = 0

        self.window = Gtk.Window(title="Aura Studio wallpaper")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.window.set_keep_below(True)
        self.window.set_accept_focus(False)
        self.window.set_focus_on_map(False)
        self.window.move(0, 0)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("map-event", self._on_map)
        self.window.connect("screen-changed", self._screen_changed)
        self._connect_workspace_signal()

        self.area = Gtk.DrawingArea()
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        self.area.connect("draw", self._draw)
        self.window.add(self.area)

        self._resize_to_screen()
        self.window.show_all()
        # GNOME Shell 42 only honours sticky for an already-mapped window.
        GLib.timeout_add(300, self._stick)
        GLib.timeout_add(800, self._stick)
        GLib.timeout_add(1500, self._stick)
        # Poll a few times a second so a workspace switch is followed quickly;
        # lowering is throttled separately to avoid needless X traffic.
        GLib.timeout_add(250, self._maintain)

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

    def _connect_workspace_signal(self):
        screen = self._screen()
        if screen is None:
            return
        try:
            screen.connect("workspace-changed", self._on_workspace_changed)
        except (TypeError, AttributeError):
            pass

    def _screen_changed(self, _window, _old_screen):
        self._resize_to_screen()
        self._connect_workspace_signal()
        GLib.timeout_add(300, self._stick)
        GLib.timeout_add(300, self._lower)
        return False

    def _on_map(self, *_args):
        self._stick()
        return False

    def _on_workspace_changed(self, *_args):
        self._stick()
        return False

    def _maintain(self):
        """Keep the window on every workspace while the session is alive."""
        screen = self._screen()
        workspace = None
        if screen is not None:
            try:
                workspace = screen.get_active_workspace().get_number()
            except AttributeError:
                workspace = None
        if workspace != self._workspace:
            self._workspace = workspace
            self._ticks = 0
            self._stick()
        else:
            self._ticks += 1
            if self._ticks % 8 == 0:
                self._lower()
        return True

    def _stick(self):
        gdk_window = self.window.get_window()
        if gdk_window is None:
            return False
        self.window.stick()
        self._set_all_desktops(gdk_window)
        self._lower()
        return False

    def _init_x11(self):
        if self._x11 is not None:
            return bool(self._display)
        try:
            x11 = ctypes.CDLL("libX11.so.6")
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XInternAtom.restype = ctypes.c_ulong
            x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            x11.XChangeProperty.restype = ctypes.c_int
            x11.XChangeProperty.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
            x11.XLowerWindow.restype = ctypes.c_int
            x11.XLowerWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            x11.XFlush.restype = ctypes.c_int
            x11.XFlush.argtypes = [ctypes.c_void_p]
            self._x11 = x11
            self._display = x11.XOpenDisplay(None)
        except Exception:
            self._x11 = None
            self._display = None
        return bool(self._display)

    def _set_all_desktops(self, gdk_window):
        """Also ask the WM directly; stick() alone is unreliable on GNOME 42."""
        if not self._init_x11():
            return
        display = self._display
        xid = gdk_window.get_xid()
        try:
            # _NET_WM_DESKTOP = 0xFFFFFFFF means "all workspaces".
            desktop_atom = self._x11.XInternAtom(display, b"_NET_WM_DESKTOP", False)
            value = ctypes.c_ulong(0xFFFFFFFF)
            self._x11.XChangeProperty(
                display, xid, desktop_atom, 6, 32, 0,  # XA_CARDINAL
                ctypes.byref(value), 1)
            names = (b"_NET_WM_STATE_STICKY", b"_NET_WM_STATE_BELOW",
                     b"_NET_WM_STATE_SKIP_TASKBAR", b"_NET_WM_STATE_SKIP_PAGER")
            atoms = (ctypes.c_ulong * len(names))(
                *[self._x11.XInternAtom(display, name, False) for name in names])
            state_atom = self._x11.XInternAtom(display, b"_NET_WM_STATE", False)
            self._x11.XChangeProperty(
                display, xid, state_atom, 4, 32, 0,  # XA_ATOM
                atoms, len(names))
            self._x11.XFlush(display)
        except Exception:
            pass

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

    def _fit(self, width, height):
        if width <= 0 or height <= 0:
            return None
        if self.scaled is not None and self.scaled_size == (width, height):
            return self.scaled
        source_width, source_height = self.pixbuf.get_width(), self.pixbuf.get_height()
        if source_width <= 0 or source_height <= 0:
            return None
        scale = min(width / source_width, height / source_height)
        target_width = max(1, int(round(source_width * scale)))
        target_height = max(1, int(round(source_height * scale)))
        self.scaled = self.pixbuf.scale_simple(
            target_width, target_height, GdkPixbuf.InterpType.BILINEAR)
        self.scaled_size = (width, height)
        return self.scaled

    def _stretch(self, width, height):
        if width <= 0 or height <= 0:
            return None
        if self.scaled is not None and self.scaled_size == (width, height):
            return self.scaled
        self.scaled = self.pixbuf.scale_simple(
            width, height, GdkPixbuf.InterpType.BILINEAR)
        self.scaled_size = (width, height)
        return self.scaled

    def _tile(self, cr, width, height):
        pixbuf = self.pixbuf
        tile_width, tile_height = pixbuf.get_width(), pixbuf.get_height()
        if tile_width <= 0 or tile_height <= 0:
            return
        if tile_width < 64 or tile_height < 64:
            scale = max(64 / tile_width, 64 / tile_height)
            target_width = max(1, int(round(tile_width * scale)))
            target_height = max(1, int(round(tile_height * scale)))
            scaled = pixbuf.scale_simple(
                target_width, target_height, GdkPixbuf.InterpType.BILINEAR)
            if scaled is not None:
                pixbuf = scaled
                tile_width, tile_height = target_width, target_height
        for y in range(0, height, tile_height):
            for x in range(0, width, tile_width):
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, x, y)
                cr.paint()

    def _draw(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        mode = "fill" if self.mode == "span" else self.mode
        if mode == "tile":
            cr.save()
            cr.rectangle(0, 0, width, height)
            cr.clip()
            self._tile(cr, width, height)
            cr.restore()
            return False
        if mode == "center":
            pixbuf = self.pixbuf
            x = (width - pixbuf.get_width()) // 2
            y = (height - pixbuf.get_height()) // 2
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, x, y)
            cr.paint()
            return False
        if mode == "fit":
            scaled = self._fit(width, height)
            if scaled is not None:
                Gdk.cairo_set_source_pixbuf(
                    cr, scaled, (width - scaled.get_width()) // 2,
                    (height - scaled.get_height()) // 2)
                cr.paint()
            return False
        if mode == "stretch":
            scaled = self._stretch(width, height)
        else:
            scaled = self._cover(width, height)
        if scaled is not None:
            Gdk.cairo_set_source_pixbuf(cr, scaled, 0, 0)
            cr.paint()
        return False

    def _lower(self):
        gdk_window = self.window.get_window()
        if gdk_window is None or not self._init_x11():
            return True
        try:
            self._x11.XLowerWindow(self._display, gdk_window.get_xid())
            self._x11.XFlush(self._display)
        except Exception:
            pass
        return True


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) not in (1, 2):
        print("usage: x11_wallpaper.py PICTURE [fill|fit|stretch|center|tile|span]",
              file=sys.stderr)
        return 2
    if not os.path.isfile(argv[0]):
        print(f"not a file: {argv[0]}", file=sys.stderr)
        return 2
    mode = argv[1] if len(argv) > 1 else "fill"
    if mode not in ("fill", "fit", "stretch", "center", "tile", "span"):
        print(f"unknown wallpaper mode: {mode}", file=sys.stderr)
        return 2
    try:
        WallpaperWindow(argv[0], mode)
    except Exception as error:
        print(f"could not start the wallpaper window: {error}", file=sys.stderr)
        return 1

    for signum in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
