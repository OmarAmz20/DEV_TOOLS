"""GTK4 layer-shell dock host for Wallpaper Studio Video."""

from __future__ import annotations

import contextlib
import fcntl
import os
import sys
import time
from pathlib import Path

from . import dock

# GTK4 layer-shell must be loaded before libwayland on PyGObject.  The manager
# sets this in the environment; re-exec when the module is started directly.
if __name__ == "__main__" and not os.environ.get("LD_PRELOAD"):
    lib = next((p for p in (
        "/usr/lib/libgtk4-layer-shell.so",
        "/usr/lib64/libgtk4-layer-shell.so",
        "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so",
    ) if Path(p).exists()), None)
    if lib:
        env = dock._gi_environment()
        env["LD_PRELOAD"] = lib + ((":" + env["LD_PRELOAD"]) if env.get("LD_PRELOAD") else "")
        os.execvpe(sys.executable,
                   [sys.executable, "-m", "wallpaper_studio.dock_daemon", *sys.argv[1:]],
                   env)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell  # type: ignore
except Exception:  # pragma: no cover
    Gtk4LayerShell = None

try:
    import cairo  # type: ignore
except Exception:  # pragma: no cover
    cairo = None


def _monitors() -> list[Gdk.Monitor]:
    display = Gdk.Display.get_default()
    if display is None:
        return []
    model = display.get_monitors()
    return [model.get_item(i) for i in range(model.get_n_items())
            if isinstance(model.get_item(i), Gdk.Monitor)]


def _app_image(entry: dict, size: int) -> Gtk.Widget:
    if entry.get("desktop_file"):
        try:
            info = Gio.DesktopAppInfo.new_from_filename(entry["desktop_file"])
            icon = info.get_icon() if info else None
            if icon is not None:
                image = Gtk.Image.new_from_gicon(icon)
                image.set_pixel_size(size)
                return image
        except Exception:
            pass
    icon = entry.get("icon") or "application-x-executable"
    if os.path.isfile(icon):
        image = Gtk.Image.new_from_file(icon)
        image.set_pixel_size(size)
        return image
    image = Gtk.Image.new_from_icon_name(icon)
    image.set_pixel_size(size)
    return image


class DockWindow:
    def __init__(self, app: Gtk.Application, config: dict, monitor: Gdk.Monitor):
        self.app = app
        self.config = config
        self.monitor = monitor
        geometry = monitor.get_geometry()
        self.monitor_width = geometry.width
        self.monitor_height = geometry.height
        horizontal = config["position"] in ("bottom", "top")
        icon = int(config["icon_size"])
        padding = int(config["padding"])
        button_pad = 4
        label_height = 20 if config.get("show_labels") else 0
        cross = icon + button_pad * 2 + label_height + padding * 2 + 2
        self.window = Gtk.Window(application=app)
        self.window.add_css_class("dock-window")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.layer_ready = False
        if Gtk4LayerShell is not None:
            try:
                Gtk4LayerShell.init_for_window(self.window)
                Gtk4LayerShell.set_monitor(self.window, monitor)
                Gtk4LayerShell.set_layer(self.window, Gtk4LayerShell.Layer.TOP)
                edge = config["position"]
                anchors = {
                    "bottom": (Gtk4LayerShell.Edge.BOTTOM, Gtk4LayerShell.Edge.LEFT,
                               Gtk4LayerShell.Edge.RIGHT),
                    "top": (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.LEFT,
                            Gtk4LayerShell.Edge.RIGHT),
                    "left": (Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.TOP,
                             Gtk4LayerShell.Edge.BOTTOM),
                    "right": (Gtk4LayerShell.Edge.RIGHT, Gtk4LayerShell.Edge.TOP,
                              Gtk4LayerShell.Edge.BOTTOM),
                }[edge]
                for item in anchors:
                    Gtk4LayerShell.set_anchor(self.window, item, True)
                Gtk4LayerShell.set_exclusive_zone(
                    self.window, cross if config.get("reserve_space") else 0
                )
                Gtk4LayerShell.set_keyboard_mode(self.window, Gtk4LayerShell.KeyboardMode.NONE)
                Gtk4LayerShell.set_namespace(self.window, "wallpaper-studio-video-dock")
                if horizontal:
                    self.window.set_default_size(self.monitor_width, cross)
                else:
                    self.window.set_default_size(cross, self.monitor_height)
                self.layer_ready = True
            except Exception:
                self.layer_ready = False
        if not self.layer_ready:
            self.window.set_default_size(
                self.monitor_width if horizontal else cross,
                cross if horizontal else self.monitor_height,
            )
            with contextlib.suppress(Exception):
                self.window.fullscreen()

        card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL if horizontal else Gtk.Orientation.VERTICAL,
            spacing=int(config["spacing"]),
        )
        card.add_css_class("dock-card")
        self.card = card
        for entry in config.get("apps", []):
            if entry.get("separator"):
                sep = Gtk.Separator(
                    orientation=Gtk.Orientation.VERTICAL if horizontal else Gtk.Orientation.HORIZONTAL
                )
                sep.add_css_class("dock-separator")
                card.append(sep)
                continue
            button = Gtk.Button()
            button.add_css_class("dock-button")
            button.set_tooltip_text(f"{entry.get('label', 'Open')}\nClick to launch")
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            content.append(_app_image(entry, int(config["icon_size"])))
            if config.get("show_labels"):
                label = Gtk.Label(label=str(entry.get("label", ""))[:16])
                label.add_css_class("dock-label")
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.set_max_width_chars(16 if horizontal else 10)
                label.set_tooltip_text(str(entry.get("label", "")))
                content.append(label)
            button.set_child(content)
            button.connect("clicked", lambda _b, app_entry=entry: dock.launch_app(app_entry))
            card.append(button)
        if not config.get("apps"):
            card.append(Gtk.Label(label="No dock apps"))
        alignment = {
            "start": Gtk.Align.START, "center": Gtk.Align.CENTER, "end": Gtk.Align.END,
        }[config["alignment"]]
        if horizontal:
            self.card.set_halign(alignment)
            self.card.set_valign(
                Gtk.Align.START if config["position"] == "top" else Gtk.Align.END
            )
        else:
            self.card.set_halign(Gtk.Align.CENTER)
            self.card.set_valign(alignment)
        self.window.set_child(card)
        self.window.connect("map", self._mapped)
        self.window.connect("realize", self._mapped)
        self.window.present()

    def _mapped(self, *_args) -> bool:
        surface = self.window.get_surface()
        if surface is None:
            GLib.idle_add(self._mapped)
            return False
        if getattr(self, "_input_pending", False):
            return False
        self._input_pending = True
        self._input_attempts = 0
        GLib.timeout_add(30, self._set_input_region)
        return False

    def _set_input_region(self) -> bool:
        surface = self.window.get_surface()
        if surface is None:
            self._input_pending = False
            return False
        try:
            success, bounds = self.card.compute_bounds(self.window)
        except (TypeError, ValueError):
            success, bounds = False, None
        if success and bounds is not None and \
                bounds.get_width() > 1 and bounds.get_height() > 1:
            if cairo is not None:
                region = cairo.Region(cairo.RectangleInt(
                    int(bounds.get_x()), int(bounds.get_y()),
                    max(1, int(bounds.get_width())), max(1, int(bounds.get_height())),
                ))
                surface.set_input_region(region)
            self._input_pending = False
            return False
        self._input_attempts += 1
        if self._input_attempts >= 30:
            self._input_pending = False
            return False
        return True


class DockHost:
    def __init__(self, app: Gtk.Application):
        self.app = app
        self.config = dock.load()
        self.windows: list[DockWindow] = []

    def build(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(dock.css(self.config).encode(), -1)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, 800)
        monitors = _monitors()
        target = self.config.get("monitor", "all")
        if target != "all":
            try:
                target = int(target)
            except (TypeError, ValueError):
                target = 0
            monitors = monitors[target:target + 1] or monitors[:1]
        for monitor in monitors:
            try:
                self.windows.append(DockWindow(self.app, self.config, monitor))
            except Exception as error:
                print(f"dock window skipped: {error}", file=sys.stderr, flush=True)
        dock.PID.write_text(str(os.getpid()) + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(dock.PID, 0o600)
        dock.STATE.write_text(
            f'{{"running": true, "pid": {os.getpid()}, "windows": {len(self.windows)}}}\n',
            encoding="utf-8",
        )


def main() -> int:
    dock.CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = open(dock.LOCK, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another dock is already running", file=sys.stderr, flush=True)
        return 1
    application = Gtk.Application(
        application_id="io.github.WallpaperStudioVideo.Dock",
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )

    def activate(app):
        host = DockHost(app)
        app._host = host
        host.build()

    def shutdown(_app):
        with contextlib.suppress(OSError):
            if dock.PID.exists() and dock.PID.read_text().strip() == str(os.getpid()):
                dock.PID.unlink()
        with contextlib.suppress(OSError):
            dock.STATE.unlink()

    application.connect("activate", activate)
    application.connect("shutdown", shutdown)
    return application.run([])


if __name__ == "__main__":
    raise SystemExit(main())
