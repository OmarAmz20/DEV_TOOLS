"""Settings, folders, desktop controls and maintenance."""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import constants, desktop, sessiond, themes, video, wallpaper, widget_daemon  # noqa: E402
from ..util import open_path, read_json, write_json  # noqa: E402
from . import common  # noqa: E402


AUTOSTART_DIR = constants.CONFIG_HOME / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "1337-customizer.desktop"


class SettingsPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.config = app.config
        self._loading = False
        self._build()
        self.refresh()

    def _build(self) -> None:
        outer, content = common.page_scaffold(
            "Settings", "Startup, folders, desktop controls and recovery.",
            actions=[common.button("Doctor", icon="dialog-information-symbolic", on_click=self.doctor)],
        )
        self.append(outer)
        self.content = content

        general = common.card()
        general.append(common.section("General", "How 1337-Customizer starts and behaves."))
        self.autostart = common.switch(bool(self.config.get("autostart", False)))
        self.autostart.connect("notify::active", lambda *_a: self.toggle_autostart())
        general.append(common.row("Launch at login", "Restore widgets, video and slideshow after login",
                                  trailing=self.autostart))
        self.notifications = common.switch(bool(self.config.get("notifications", True)))
        self.notifications.connect("notify::active", lambda *_a: self._save_general())
        general.append(common.row("Notifications", "Show a notification when something is applied",
                                  trailing=self.notifications))
        self.recursive = common.switch(bool(self.config.get("library.recursive", True)))
        self.recursive.connect("notify::active", lambda *_a: self._save_general())
        general.append(common.row("Recursive scan", "Include subfolders inside wallpaper folders",
                                  trailing=self.recursive))
        self.scan_start = common.switch(bool(self.config.get("library.scan_on_start", True)))
        self.scan_start.connect("notify::active", lambda *_a: self._save_general())
        general.append(common.row("Scan on start", "Refresh the index in the background",
                                  trailing=self.scan_start))
        content.append(general)

        folders = common.card()
        folder_head = common.section("Wallpaper folders", "Add as many folders as you like; duplicates are ignored.",
                                     trailing=common.button("Add", icon="folder-new-symbolic",
                                                            on_click=self.add_folder))
        folders.append(folder_head)
        self.folder_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        folders.append(self.folder_box)
        content.append(folders)

        slideshow = common.card()
        slideshow.append(common.section("Slideshow", "A lightweight helper rotates pictures while you work."))
        self.slide_enabled = common.switch(bool(self.config.get("wallpaper.slideshow.enabled", False)))
        self.slide_enabled.connect("notify::active", lambda *_a: self.save_slideshow())
        slideshow.append(common.row("Enable slideshow", "The helper keeps running after the studio closes",
                                    trailing=self.slide_enabled))
        interval_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        interval_label = Gtk.Label(label="Interval (minutes)", xalign=0)
        interval_label.set_hexpand(True)
        self.slide_minutes = common.spin(float(self.config.get("wallpaper.slideshow.minutes", 30)), 1, 1440, 5)
        self.slide_minutes.connect("value-changed", lambda *_a: self.save_slideshow())
        interval_row.append(interval_label)
        interval_row.append(self.slide_minutes)
        slideshow.append(interval_row)
        self.slide_order = common.dropdown([("shuffle", "Shuffle"), ("name", "Name order")],
                                           self.config.get("wallpaper.slideshow.order", "shuffle"))
        self.slide_order.connect("notify::selected", lambda *_a: self.save_slideshow())
        slideshow.append(common.row("Order", trailing=self.slide_order))
        self.slide_favorites = common.switch(bool(self.config.get("wallpaper.slideshow.favorites_only", False)))
        self.slide_favorites.connect("notify::active", lambda *_a: self.save_slideshow())
        slideshow.append(common.row("Favourites only", "Rotate only starred wallpapers",
                                    trailing=self.slide_favorites))
        self.slide_skip_video = common.switch(bool(self.config.get("wallpaper.slideshow.skip_videos", True)))
        self.slide_skip_video.connect("notify::active", lambda *_a: self.save_slideshow())
        slideshow.append(common.row("Skip videos", "Slideshow uses still pictures only",
                                    trailing=self.slide_skip_video))
        self.slide_start = common.switch(bool(self.config.get("wallpaper.slideshow.apply_on_start", False)))
        self.slide_start.connect("notify::active", lambda *_a: self.save_slideshow())
        slideshow.append(common.row("Change on helper start", trailing=self.slide_start))
        helper_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.helper_status = Gtk.Label(label="Checking…", xalign=0)
        self.helper_status.set_hexpand(True)
        helper_row.append(self.helper_status)
        helper_row.append(common.button("Start", icon="media-playback-start-symbolic",
                                        on_click=self.start_helper))
        helper_row.append(common.button("Stop", icon="media-playback-stop-symbolic",
                                        on_click=self.stop_helper))
        slideshow.append(helper_row)
        content.append(slideshow)

        desktop_controls = common.card()
        desktop_controls.append(common.section("Desktop controls", "Native settings for GTK, icons, cursors and window behaviour."))
        self.icon_dropdown = self._theme_dropdown(desktop.list_icon_themes(),
                                                   str(self.config.get("desktop.icon_theme", "") or
                                                       desktop.get_value(desktop.INTERFACE, "icon-theme", "") or ""))
        desktop_controls.append(common.row("Icon theme", trailing=self.icon_dropdown))
        self.cursor_dropdown = self._theme_dropdown(desktop.list_cursor_themes(),
                                                     str(self.config.get("desktop.cursor_theme", "") or
                                                         desktop.get_value(desktop.INTERFACE, "cursor-theme", "") or ""))
        desktop_controls.append(common.row("Cursor theme", trailing=self.cursor_dropdown))
        cursor_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cursor_label = Gtk.Label(label="Cursor size", xalign=0)
        cursor_label.set_hexpand(True)
        self.cursor_size = common.spin(float(desktop.get_value(desktop.INTERFACE, "cursor-size", 24) or 24), 16, 72, 2)
        cursor_row.append(cursor_label)
        cursor_row.append(self.cursor_size)
        desktop_controls.append(cursor_row)
        self.button_layout = Gtk.Entry()
        self.button_layout.set_text(str(desktop.get_value(desktop.WM, "button-layout", "") or ""))
        self.button_layout.set_placeholder_text("appmenu:minimize,maximize,close")
        desktop_controls.append(common.row("Titlebar buttons", "GNOME / GTK layout", trailing=self.button_layout))
        self.animations = common.switch(bool(desktop.get_value(desktop.INTERFACE, "gtk-enable-animations", True)))
        self.overlay_scroll = common.switch(bool(desktop.get_value(desktop.INTERFACE, "gtk-overlay-scrolling", True)))
        self.primary_paste = common.switch(bool(desktop.get_value(desktop.INTERFACE, "gtk-enable-primary-paste", True)))
        desktop_controls.append(common.row("Animations", "GTK transition animations", trailing=self.animations))
        desktop_controls.append(common.row("Overlay scrollbars", trailing=self.overlay_scroll))
        desktop_controls.append(common.row("Middle-click paste", trailing=self.primary_paste))
        controls_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        controls_buttons.append(common.button("Apply desktop controls", icon="emblem-ok-symbolic",
                                              css="suggested-action", on_click=self.apply_desktop))
        controls_buttons.append(common.button("Restore controls", icon="edit-undo-symbolic",
                                              on_click=self.restore_desktop))
        desktop_controls.append(controls_buttons)
        content.append(desktop_controls)

        restore = common.card()
        restore.append(common.section("Restore & helpers", "Nothing is applied automatically except helpers you enable."))
        restore_buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        restore_buttons.append(common.button("Restore look", icon="edit-undo-symbolic", on_click=self.restore_look))
        restore_buttons.append(common.button("Restore wallpaper", icon="edit-undo-symbolic",
                                             on_click=self.restore_wallpaper))
        restore_buttons.append(common.button("Stop all helpers", icon="media-playback-stop-symbolic",
                                             on_click=self.stop_helpers))
        restore.append(restore_buttons)
        self.helper_summary = Gtk.Label(label="", xalign=0, wrap=True)
        self.helper_summary.add_css_class("dim-label")
        restore.append(self.helper_summary)
        content.append(restore)

        about = common.card()
        about.append(common.section("1337-Customizer", f"Version {constants.VERSION} · built for your desktop"))
        about.append(common.row("Application data", str(constants.DATA_DIR),
                                trailing=common.button("Open", icon="folder-open-symbolic",
                                                       on_click=lambda: open_path(constants.DATA_DIR))))
        about.append(common.row("Configuration", str(constants.CONFIG_FILE),
                                trailing=common.button("Open", icon="folder-open-symbolic",
                                                       on_click=lambda: open_path(constants.CONFIG_DIR))))
        about.append(common.row("About", "Credits, links and the component list",
                                trailing=common.button("Show", icon="help-about-symbolic",
                                                       on_click=self.about)))
        content.append(about)

    def _theme_dropdown(self, values: list[str], selected: str) -> Gtk.DropDown:
        if not values:
            values = ["Adwaita"]
        if selected not in values:
            values = [selected, *values] if selected else values
        dropdown = Gtk.DropDown(model=Gtk.StringList.new(values))
        if selected in values:
            dropdown.set_selected(values.index(selected))
        return dropdown

    def _selected_string(self, dropdown: Gtk.DropDown) -> str:
        item = dropdown.get_selected_item()
        return item.get_string() if item else ""

    # --- general ------------------------------------------------------------------

    def _save_general(self) -> None:
        self.config.set("autostart", self.autostart.get_active(), save=False)
        self.config.set("notifications", self.notifications.get_active(), save=False)
        self.config.set("library.recursive", self.recursive.get_active(), save=False)
        self.config.set("library.scan_on_start", self.scan_start.get_active(), save=False)
        self.config.save()
        from ..util import set_notifications

        set_notifications(self.notifications.get_active())

    def toggle_autostart(self) -> None:
        enabled = self.autostart.get_active()
        self.config.set("autostart", enabled, save=False)
        self.config.save()
        AUTOSTART_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        if enabled:
            try:
                constants.LEGACY_AUTOSTART.unlink()
            except OSError:
                pass
            launcher = constants.APP_ROOT / "1337-customizer"
            command = str(launcher) if launcher.exists() else "1337-customizer"
            text = f"""[Desktop Entry]
Type=Application
Name=1337-Customizer helper
Comment=Restore 1337-Customizer wallpapers and widgets after login
Exec={command} --background
Icon=1337-customizer
Terminal=false
X-GNOME-Autostart-enabled=true
"""
            from ..util import atomic_write_text

            atomic_write_text(AUTOSTART_FILE, text, mode=0o644)
            self.app.toast("1337-Customizer will start with your session")
        else:
            try:
                AUTOSTART_FILE.unlink()
            except OSError:
                pass
            try:
                constants.LEGACY_AUTOSTART.unlink()
            except OSError:
                pass
            self.app.toast("Autostart disabled")

    # --- folders ------------------------------------------------------------------

    def refresh(self) -> None:
        self._loading = True
        try:
            self._refresh_controls()
        finally:
            self._loading = False

    def _refresh_controls(self) -> None:
        for child in list(self.folder_box):
            self.folder_box.remove(child)
        for folder in self.config.folders:
            row = common.row(Path(folder).name, folder,
                             trailing=common.button("", icon="user-trash-symbolic",
                                                    tooltip="Remove folder", on_click=lambda f=folder: self.remove_folder(f)))
            self.folder_box.append(row)
        if not self.config.folders:
            label = Gtk.Label(label="No folders yet. Add one to start building your library.", xalign=0)
            label.add_css_class("dim-label")
            self.folder_box.append(label)
        self.helper_status.set_text(
            "Running" if sessiond.running() else "Stopped"
        )
        self.slide_enabled.set_active(bool(self.config.get("wallpaper.slideshow.enabled", False)))
        self.slide_minutes.set_value(float(self.config.get("wallpaper.slideshow.minutes", 30)))
        self.slide_start.set_active(bool(self.config.get("wallpaper.slideshow.apply_on_start", False)))
        self.slide_favorites.set_active(bool(self.config.get("wallpaper.slideshow.favorites_only", False)))
        self.slide_skip_video.set_active(bool(self.config.get("wallpaper.slideshow.skip_videos", True)))
        self.slide_order.set_selected(0 if self.config.get("wallpaper.slideshow.order", "shuffle") == "shuffle" else 1)
        self.helper_summary.set_text(
            f"session helper: {'running' if sessiond.running() else 'stopped'}   ·   "
            f"widget host: {'running' if widget_daemon.running() else 'stopped'}   ·   "
            f"video: {'running' if video.running() else 'stopped'}"
        )

    def add_folder(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Add wallpaper folder")
        dialog.select_folder(self.get_root(), None, self._folder_done)

    def _folder_done(self, dialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        path = folder.get_path() if folder else None
        if path and self.config.add_folder(path):
            self.refresh()
            self.app.toast("Folder added")
            if hasattr(self.app, "library_page"):
                self.app.library_page.start_scan()

    def remove_folder(self, folder: str) -> None:
        if self.config.remove_folder(folder):
            self.refresh()
            self.app.toast("Folder removed; its entries stay until the next scan")

    # --- slideshow ----------------------------------------------------------------

    def save_slideshow(self) -> None:
        if self._loading:
            return
        self.config.update({"wallpaper": {"slideshow": {
            "enabled": self.slide_enabled.get_active(),
            "minutes": int(self.slide_minutes.get_value()),
            "order": "shuffle" if self.slide_order.get_selected() == 0 else "name",
            "favorites_only": self.slide_favorites.get_active(),
            "skip_videos": self.slide_skip_video.get_active(),
            "apply_on_start": self.slide_start.get_active(),
        }}})
        if self.slide_enabled.get_active():
            sessiond.start()
        elif sessiond.running():
            sessiond.stop()
        self.refresh()

    def start_helper(self) -> None:
        sessiond.start()
        self.refresh()
        self.app.toast("Session helper started")

    def stop_helper(self) -> None:
        sessiond.stop()
        self.refresh()
        self.app.toast("Session helper stopped")

    # --- desktop controls ---------------------------------------------------------

    def apply_desktop(self) -> None:
        self.config.update({"desktop": {
            "icon_theme": self._selected_string(self.icon_dropdown),
            "cursor_theme": self._selected_string(self.cursor_dropdown),
            "cursor_size": int(self.cursor_size.get_value()),
            "button_layout": self.button_layout.get_text(),
            "animations": self.animations.get_active(),
            "overlay_scrolling": self.overlay_scroll.get_active(),
            "primary_paste": self.primary_paste.get_active(),
        }})
        self.config.set("appearance.apply_icons", True, save=False)
        self.config.set("appearance.icon_theme", self._selected_string(self.icon_dropdown), save=False)
        self.config.set("appearance.apply_cursor", True, save=False)
        self.config.set("appearance.cursor_theme", self._selected_string(self.cursor_dropdown), save=False)
        self.config.set("appearance.cursor_size", int(self.cursor_size.get_value()), save=False)
        self.config.set("appearance.button_layout", self.button_layout.get_text(), save=False)
        self.config.set("appearance.animations", self.animations.get_active(), save=False)
        self.config.set("appearance.overlay_scrolling", self.overlay_scroll.get_active(), save=False)
        self.config.set("appearance.primary_paste", self.primary_paste.get_active(), save=False)
        self.config.save()
        desktop.apply_desktop_controls(self.config)
        self.app.toast("Desktop controls applied")

    def restore_desktop(self) -> None:
        restored = desktop.restore_desktop_backup({
            "icon-theme", "cursor-theme", "cursor-size", "button-layout",
            "gtk-enable-animations", "gtk-overlay-scrolling", "gtk-enable-primary-paste",
        })
        self.app.toast(f"Restored {restored} desktop setting(s)")

    # --- restore / helpers --------------------------------------------------------

    def restore_look(self) -> None:
        def worker():
            result = desktop.restore_theme()
            GLib.idle_add(lambda: self.app.toast("Previous look restored"))
        threading.Thread(target=worker, daemon=True).start()

    def restore_wallpaper(self) -> None:
        def worker():
            result = wallpaper.restore()
            GLib.idle_add(lambda: self.app.toast(
                f"Restored {Path(result.get('path', '')).name}" if result.get("restored") else "No previous wallpaper found"
            ))
        threading.Thread(target=worker, daemon=True).start()

    def stop_helpers(self) -> None:
        sessiond.stop()
        widget_daemon.stop()
        video.stop(notify_user=True)
        self.refresh()
        self.app.toast("Session, widget and video helpers stopped")

    # --- dialogs ------------------------------------------------------------------

    def doctor(self) -> None:
        report = desktop.environment_report()
        text = json.dumps(report, indent=2, ensure_ascii=False)
        dialog = Adw.MessageDialog(transient_for=self.get_root(),
                                   heading="1337-Customizer diagnostics",
                                   body=text[-6000:])
        dialog.add_response("close", "Close")
        dialog.set_extra_child(Gtk.Label(label=text, xalign=0, wrap=True, selectable=True))
        dialog.present()

    def about(self) -> None:
        dialog = Adw.AboutDialog(
            application_name=constants.APP_NAME,
            application_icon=constants.ICON_NAME,
            developer_name="Hamiid",
            version=constants.VERSION,
            comments="A faster wallpaper, theme, font and desktop widget studio for Linux.",
            website="https://github.com/",
            license_type=Gtk.License.MIT_X11,
            developers=["Hamiid"],
            designers=["Hamiid"],
        )
        dialog.present(self.get_root())

    def on_shown(self) -> None:
        self.refresh()
