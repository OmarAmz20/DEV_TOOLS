"""The Wallpaper Lite window: a grid of pictures, one click to apply, two colours."""
import concurrent.futures
import contextlib
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import core  # noqa: E402

APP_ID = core.APP_ID
THUMB_W, THUMB_H = 216, 122
PREVIEW_W, PREVIEW_H = 480, 270
MAX_LIBRARY = core.MAX_THUMBS

# Fallback colours for the very first start, before theme.css exists. The real
# theme provider loads at USER priority and overrides these at APPLICATION priority.
CSS = b"""
@define-color ws_paper #f6f5f4;
@define-color ws_paper2 #ecebe9;
@define-color ws_sheet #fdfdfc;
@define-color ws_ink #1d1d1d;
@define-color ws_muted #77767b;
@define-color ws_accent #3584e4;
@define-color ws_accent_text #1a5fb4;
@define-color ws_on_accent #ffffff;
@define-color ws_shadow #1d1d1d;

.ws-title { font-size: 1.35em; font-weight: bold; }
.ws-subtitle { color: @ws_muted; }
.ws-heading { font-weight: bold; }
.ws-status { padding: 8px 16px; color: @ws_muted; }
.ws-status.error { color: #c01c28; }
.ws-status.ok { color: @ws_ink; }

.preview {
  border-radius: 12px;
  border: 1px solid alpha(@ws_ink, 0.14);
  background-color: alpha(@ws_ink, 0.06);
}
.thumb {
  padding: 4px;
  border: 2px solid transparent;
  border-radius: 10px;
  background-color: transparent;
  box-shadow: none;
}
.thumb:hover { background-color: alpha(@ws_ink, 0.06); }
.thumb.current { border-color: @ws_accent; }
.thumb image {
  border-radius: 6px;
  background-color: alpha(@ws_ink, 0.08);
}
.swatch { border-radius: 5px; }
.mode button { padding: 4px 16px; }
.dim { color: @ws_muted; }
"""


def swatch(colour):
    area = Gtk.DrawingArea()
    area.set_size_request(24, 24)
    area.set_tooltip_text(colour)
    area.get_style_context().add_class("swatch")
    rgba = Gdk.RGBA()
    rgba.parse(colour)

    def draw(widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1.0)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.28)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, max(0, width - 1), max(0, height - 1))
        cr.stroke()
        return False

    area.connect("draw", draw)
    return area


def clear(box):
    for child in box.get_children():
        box.remove(child)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Wallpaper Lite")
        self.set_default_size(1000, 780)
        self.set_icon_name("preferences-desktop-wallpaper")
        self.set_position(Gtk.WindowPosition.CENTER)

        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.busy = False
        self.closed = False
        self.library_token = 0
        self.preview_token = 0
        self.preview_key = None
        self.buttons = {}
        self.mode_buttons = {}
        self._syncing_mode = False
        self.config = core.load_config()

        self.theme_provider = Gtk.CssProvider()
        self.app_provider = Gtk.CssProvider()
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, self.theme_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
            Gtk.StyleContext.add_provider_for_screen(
                screen, self.app_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.reload_theme()

        # Follow changes made by the command line or another window.
        self.state_monitor = Gio.File.new_for_path(core.STATE).monitor_file(
            Gio.FileMonitorFlags.NONE, None)
        self.state_monitor.connect("changed", self.on_state_changed)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.pack_start(self.build_hero(), False, False, 0)
        outer.pack_start(self.build_library(), True, True, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.get_style_context().add_class("ws-status")
        outer.pack_end(self.status, False, False, 0)
        self.add(outer)

        self.connect("destroy", self.on_destroy)
        self.load_library()
        self.set_focus(self.first_button)

    # --- layout -------------------------------------------------------------------------

    def build_hero(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Wallpaper Lite")
        header.set_subtitle("Your picture's colours, everywhere")
        self.set_titlebar(header)

        self.spinner = Gtk.Spinner()
        self.spinner.set_no_show_all(True)
        header.pack_start(self.spinner)

        folder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        folder.set_tooltip_text("Choose wallpaper folder")
        folder.connect("clicked", self.choose_folder)
        header.pack_start(folder)

        file_button = Gtk.Button.new_from_icon_name("document-open-symbolic", Gtk.IconSize.BUTTON)
        file_button.set_tooltip_text("Open one picture")
        file_button.connect("clicked", self.choose_file)
        header.pack_start(file_button)

        restore = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
        restore.set_tooltip_text("Restore original look")
        restore.connect("clicked", self.ask_restore)
        header.pack_end(restore)

        box = Gtk.Box(spacing=22, margin=18)
        self.preview_box = Gtk.EventBox()
        self.preview_box.get_style_context().add_class("preview")
        self.preview_box.set_size_request(PREVIEW_W, PREVIEW_H)
        self.preview = Gtk.Image()
        self.preview.set_size_request(PREVIEW_W, PREVIEW_H)
        self.preview.set_from_icon_name("preferences-desktop-wallpaper-symbolic", Gtk.IconSize.DIALOG)
        self.preview_box.add(self.preview)
        box.pack_start(self.preview_box, False, False, 0)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        side.set_valign(Gtk.Align.CENTER)
        side.set_hexpand(True)
        side.set_size_request(240, -1)
        self.title = Gtk.Label(xalign=0)
        self.title.get_style_context().add_class("ws-title")
        self.title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.get_style_context().add_class("ws-subtitle")
        self.subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        side.pack_start(self.title, False, False, 0)
        side.pack_start(self.subtitle, False, False, 0)

        self.palette_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        side.pack_start(self.palette_box, False, False, 4)

        mode_row = Gtk.Box(spacing=10)
        label = Gtk.Label(label="Colours", xalign=0)
        label.get_style_context().add_class("dim")
        mode_row.pack_start(label, False, False, 0)
        modes = Gtk.Box(spacing=0)
        modes.get_style_context().add_class("linked")
        modes.get_style_context().add_class("mode")
        for mode, text in (("light", "Light"), ("dark", "Dark")):
            button = Gtk.ToggleButton(label=text)
            button.connect("toggled", self.on_mode, mode)
            self.mode_buttons[mode] = button
            modes.pack_start(button, False, False, 0)
        mode_row.pack_start(modes, False, False, 0)
        side.pack_start(mode_row, False, False, 4)

        actions = Gtk.Box(spacing=8)
        self.first_button = Gtk.Button(label="Random picture")
        self.first_button.get_style_context().add_class("suggested-action")
        self.first_button.connect("clicked", self.on_random)
        actions.pack_start(self.first_button, False, False, 0)
        side.pack_start(actions, False, False, 4)

        hint = Gtk.Label(label="Click any picture below to use it.", xalign=0)
        hint.get_style_context().add_class("dim")
        side.pack_start(hint, False, False, 0)

        box.pack_start(side, True, True, 0)
        return box

    def build_library(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=18, margin_end=18)
        self.library_label = Gtk.Label(xalign=0)
        self.library_label.get_style_context().add_class("ws-heading")
        box.pack_start(self.library_label, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_shadow_type(Gtk.ShadowType.NONE)

        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_homogeneous(True)
        self.flow.set_min_children_per_line(1)
        self.flow.set_max_children_per_line(4)
        self.flow.set_row_spacing(4)
        self.flow.set_column_spacing(4)
        self.flow.set_valign(Gtk.Align.START)
        self.flow.set_halign(Gtk.Align.CENTER)
        self.flow.set_margin_top(4)
        self.flow.set_margin_bottom(8)
        scroller.add(self.flow)
        box.pack_start(scroller, True, True, 0)
        return box

    # --- library ------------------------------------------------------------------------

    def load_library(self):
        self.config = core.load_config()
        folder = self.config["folder"]
        self.library_token += 1
        token = self.library_token
        clear(self.flow)
        self.buttons.clear()

        files = core.wallpapers(folder)
        shown = files[:MAX_LIBRARY]
        rel = folder.replace(core.HOME, "~", 1)
        count = len(files)
        self.library_label.set_text(f"Your pictures · {count} in {rel}")
        if not shown:
            empty = Gtk.Label(label="No pictures here yet.\nChoose another folder or open a file.")
            empty.set_justify(Gtk.Justification.CENTER)
            empty.get_style_context().add_class("dim")
            empty.set_margin_top(40)
            self.flow.add(empty)
            self.flow.show_all()
            self.show_current()
            return

        for path in shown:
            image = Gtk.Image()
            image.set_size_request(THUMB_W, THUMB_H)
            image.set_from_icon_name("image-x-generic-symbolic", Gtk.IconSize.DIALOG)
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_tooltip_text(os.path.basename(path))
            button.get_style_context().add_class("thumb")
            button.add(image)
            button.connect("clicked", self.on_pick, path)
            self.flow.add(button)
            self.buttons[os.path.realpath(path)] = button
            self.pool.submit(self.thumb_job, path, image, token)

        self.flow.show_all()
        self.show_current()
        if count > MAX_LIBRARY:
            self.set_status(f"Showing the first {MAX_LIBRARY} of {count} pictures.")

    def thumb_job(self, path, image, token):
        try:
            pixbuf = core.thumbnail(path, THUMB_W, THUMB_H)
        except Exception:
            pixbuf = None
        GLib.idle_add(self.thumb_done, token, image, pixbuf)

    def thumb_done(self, token, image, pixbuf):
        if self.closed or token != self.library_token:
            return False
        if pixbuf is not None:
            image.set_from_pixbuf(pixbuf)
        return False

    # --- current picture ----------------------------------------------------------------

    def show_current(self):
        self.config = core.load_config()
        state = core.load_state()
        path = state.get("wallpaper")
        current = os.path.realpath(path) if isinstance(path, str) else None

        if current and os.path.isfile(current):
            palette = state.get("palette") or {}
            self.title.set_text(os.path.splitext(os.path.basename(current))[0])
            width, height, fmt = core.image_size(current)
            details = f"{width} × {height}" if width else "Picture"
            if fmt:
                details += f" · {fmt.upper()}"
            self.subtitle.set_text(details)
            self.load_preview(current)
            self.show_palettes(palette)
        else:
            self.title.set_text("Pick a wallpaper")
            self.subtitle.set_text("Click a picture below.")
            self.preview.set_from_icon_name("preferences-desktop-wallpaper-symbolic",
                                            Gtk.IconSize.DIALOG)
            self.preview_key = None
            clear(self.palette_box)

        self.sync_mode_buttons(self.config["mode"])
        for real, button in self.buttons.items():
            context = button.get_style_context()
            if real == current:
                context.add_class("current")
            else:
                context.remove_class("current")
        self.set_status("")

    def load_preview(self, path):
        try:
            key = (path, os.stat(path).st_mtime_ns)
        except OSError:
            key = (path, None)
        if key == self.preview_key:
            return
        self.preview_key = key
        self.preview_token += 1
        token = self.preview_token
        self.pool.submit(self.preview_job, path, token)

    def preview_job(self, path, token):
        try:
            pixbuf = core.preview_pixbuf(path, PREVIEW_W, PREVIEW_H)
        except Exception:
            pixbuf = None
        GLib.idle_add(self.preview_done, token, pixbuf)

    def preview_done(self, token, pixbuf):
        if self.closed or token != self.preview_token:
            return False
        if pixbuf is not None:
            self.preview.set_from_pixbuf(pixbuf)
        else:
            self.preview.set_from_icon_name("image-missing-symbolic", Gtk.IconSize.DIALOG)
        return False

    def show_palettes(self, palette):
        clear(self.palette_box)
        for mode in ("light", "dark"):
            p = palette.get(mode) if isinstance(palette, dict) else None
            if not isinstance(p, dict):
                continue
            row = Gtk.Box(spacing=6)
            label = Gtk.Label(label=mode.title(), xalign=0, width_chars=6)
            label.get_style_context().add_class("dim")
            row.pack_start(label, False, False, 0)
            for key in ("paper", "sheet", "accent", "accent_text", "ink", "muted"):
                colour = p.get(key)
                if isinstance(colour, str):
                    row.pack_start(swatch(colour), False, False, 0)
            self.palette_box.pack_start(row, False, False, 0)
        self.palette_box.show_all()

    def sync_mode_buttons(self, mode):
        self._syncing_mode = True
        for name, button in self.mode_buttons.items():
            button.set_active(name == mode)
            context = button.get_style_context()
            if name == mode:
                context.add_class("suggested-action")
            else:
                context.remove_class("suggested-action")
        self._syncing_mode = False

    # --- actions ------------------------------------------------------------------------

    def set_status(self, text, error=False, ok=False):
        self.status.set_text(text)
        context = self.status.get_style_context()
        context.remove_class("error")
        context.remove_class("ok")
        if error:
            context.add_class("error")
        elif ok:
            context.add_class("ok")

    def run_job(self, job):
        if self.busy:
            return
        self.busy = True
        self.spinner.show()
        self.spinner.start()
        self.set_status("Working…")

        def work():
            try:
                result, error = job(), None
            except Exception as exc:
                result, error = None, str(exc) or exc.__class__.__name__
            GLib.idle_add(self.job_done, result, error)

        threading.Thread(target=work, daemon=True).start()

    def job_done(self, result, error):
        if self.closed:
            return False
        self.busy = False
        self.spinner.stop()
        self.spinner.hide()
        if error:
            self.reload_theme()
            self.show_current()
            self.set_status(error, error=True)
        else:
            self.reload_theme()
            self.show_current()
            if result:
                self.set_status(str(result), ok=True)
        return False

    def on_pick(self, _button, path):
        self.run_job(lambda: core.set_wallpaper(path))

    def on_random(self, _button):
        def job():
            picked = core.next_wallpaper()
            if picked is None:
                raise ValueError("No other pictures in this folder")
            return "Wallpaper changed."

        self.run_job(job)

    def on_mode(self, button, mode):
        if self._syncing_mode or not button.get_active() or self.busy:
            return
        for name, other in self.mode_buttons.items():
            if name != mode and other.get_active():
                other.set_active(False)
        self.sync_mode_buttons(mode)
        if core.load_config()["mode"] == mode:
            return

        def job():
            return core.set_mode(mode) or "Colour mode saved."

        self.run_job(job)

    def choose_file(self, _button=None):
        dialog = Gtk.FileChooserDialog(
            title="Choose a picture", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Open", Gtk.ResponseType.ACCEPT)
        media = Gtk.FileFilter()
        media.set_name("Pictures")
        for ext in core.IMAGE_EXT:
            media.add_pattern("*" + ext)
            media.add_pattern("*" + ext.upper())
        dialog.add_filter(media)
        if os.path.isdir(self.config["folder"]):
            dialog.set_current_folder(self.config["folder"])
        response = dialog.run()
        path = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.ACCEPT and path:
            self.run_job(lambda: core.set_wallpaper(path))

    def choose_folder(self, _button=None):
        dialog = Gtk.FileChooserDialog(
            title="Choose your wallpaper folder", transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Choose", Gtk.ResponseType.ACCEPT)
        if os.path.isdir(self.config["folder"]):
            dialog.set_current_folder(self.config["folder"])
        response = dialog.run()
        folder = dialog.get_filename()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT or not folder:
            return
        try:
            self.config = core.save_config(folder=folder)
        except Exception as exc:
            self.set_status(str(exc), error=True)
            return
        self.preview_key = None
        self.load_library()
        self.show_current()

    def ask_restore(self, _button=None):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE, text="Restore your original look?")
        dialog.format_secondary_text(
            "Your theme, colours and wallpaper go back to how they were. "
            "Your pictures are not touched.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        restore = dialog.add_button("Restore", Gtk.ResponseType.ACCEPT)
        restore.get_style_context().add_class("destructive-action")
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.ACCEPT:
            return

        def job():
            core.restore()
            return "Original look restored."

        self.run_job(job)

    # --- theme --------------------------------------------------------------------------

    def reload_theme(self):
        try:
            if os.path.exists(core.THEME_CSS):
                self.theme_provider.load_from_path(core.THEME_CSS)
            else:
                self.theme_provider.load_from_data(b"")
        except GLib.Error:
            with contextlib.suppress(GLib.Error):
                self.theme_provider.load_from_data(b"")
        try:
            # Reload the app rules so they resolve the freshest @ws_* colours.
            self.app_provider.load_from_data(CSS)
        except GLib.Error:
            pass

    def on_state_changed(self, *_):
        if not self.closed:
            GLib.timeout_add(300, self.refresh_state)
        return False

    def refresh_state(self):
        if not self.closed and not self.busy:
            self.reload_theme()
            self.show_current()
        return False

    def on_destroy(self, *_):
        self.closed = True
        with contextlib.suppress(Exception):
            self.state_monitor.cancel()
        self.pool.shutdown(wait=False)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)

    def do_startup(self):
        Gtk.Application.do_startup(self)

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            window = Window(self)
        window.show_all()
        window.present()
        if core.load_state().get("wallpaper"):
            GLib.idle_add(self.start_helper_once)

    @staticmethod
    def start_helper_once():
        try:
            core.start_helper()
        except Exception:
            pass
        return False


def main():
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("Wallpaper Lite")
    return App().run(None)
