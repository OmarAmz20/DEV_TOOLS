"""1337-Customizer application shell."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import constants, desktop, themes, wallpaper, widget_daemon  # noqa: E402
from .config import Config  # noqa: E402
from .library import Library  # noqa: E402
from .thumbnails import ThumbCache  # noqa: E402
from .util import ensure_gi_paths, open_path, set_notifications  # noqa: E402

ensure_gi_paths()

PAGE_FACTORIES = {
    "library": ("Wallpapers", "view-grid-symbolic", "Your local collection"),
    "appearance": ("Appearance", "applications-graphics-symbolic", "Colours, structure and preview"),
    "widgets": ("Widgets", "view-app-grid-symbolic", "Live desktop layer"),
    "fonts": ("Type & fonts", "preferences-desktop-font-symbolic", "Families, sizes and previews"),
    "video": ("Video", "media-playback-start-symbolic", "Motion wallpapers"),
    "settings": ("Settings", "emblem-system-symbolic", "Startup, folders and restore"),
}


class LeetCustomizerApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=constants.APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.config = Config()
        self.library = Library()
        self.thumbs = ThumbCache(
            width=int(self.config.get("performance.thumb_size", 360)),
            workers=int(self.config.get("performance.thumb_threads", 4)),
            max_mb=int(self.config.get("performance.cache_mb", 512)),
            preview_max=int(self.config.get("performance.preview_max", 1600)),
        )
        self.window: Adw.ApplicationWindow | None = None
        self.pages: dict[str, Gtk.Widget] = {}
        self.page_order = list(PAGE_FACTORIES)
        self.nav_rows: dict[str, Gtk.ListBoxRow] = {}
        self.nav_list: Gtk.ListBox | None = None
        self.stack: Gtk.Stack | None = None
        self.toast_overlay: Adw.ToastOverlay | None = None
        self.title_widget: Adw.WindowTitle | None = None
        self.current_page = "library"
        self._css_providers = []
        self.connect("startup", self._on_startup)
        self.connect("activate", self._on_activate)
        self.connect("command-line", self._on_command_line)

    # --- lifecycle ----------------------------------------------------------------

    def _on_startup(self, _app) -> None:
        GLib.set_application_name(constants.APP_NAME)
        display = Gdk.Display.get_default()
        if display:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            icon_theme.add_search_path(str(constants.DATA_ROOT / "icons"))
            icon_theme.add_search_path(str(constants.DATA_ROOT))
            Gtk.Window.set_default_icon_name(constants.ICON_NAME)
        self._load_css()
        self._install_actions()
        set_notifications(bool(self.config.get("notifications", True)))
        try:
            self.thumbs.cleanup()
        except Exception:
            pass

    def _load_css(self) -> None:
        display = Gdk.Display.get_default()
        if display is None:
            return
        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(constants.APP_CSS))
            Gtk.StyleContext.add_provider_for_display(display, provider,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
            self._css_providers.append(provider)
        except Exception as error:
            print(f"Could not load app.css: {error}")
        dynamic = ["/* Generated preset swatches */"]
        for preset in themes.all_presets():
            preset_id = preset.get("id", "theme")
            dark = preset.get("dark") or {}
            light = preset.get("light") or {}
            dynamic.append(
                f".preset-{preset_id} {{ background: "
                f"linear-gradient(140deg, {dark.get('bg', '#101018')} 0%, "
                f"{dark.get('surface', '#1a1a26')} 58%, {dark.get('accent', '#7aa2ff')} 145%); }}"
            )
            dynamic.append(
                f".preset-light-{preset_id} {{ background-color: {light.get('bg', '#f5f5f8')}; }}"
            )
        dynamic.append(
            ".preset-__wallpaper__ { background: "
            "linear-gradient(145deg, #0a101c 0%, #172344 55%, #4ec8d8 130%); }"
        )
        provider = Gtk.CssProvider()
        provider.load_from_data("\n".join(dynamic).encode(), -1)
        Gtk.StyleContext.add_provider_for_display(display, provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css_providers.append(provider)

    def _on_activate(self, _app) -> None:
        if self.window is not None:
            self.window.present()
            return
        self._build_window()
        self.config.data["first_run"] = False
        self.config.save()
        try:
            from . import sessiond

            sessiond.start_if_needed(self.config)
        except Exception:
            pass

    def _on_command_line(self, _app, command_line) -> int:
        arguments = command_line.get_arguments()[1:]
        # A normal desktop launch has no extra arguments.  If a CLI flag was
        # passed to the GUI, bring up the studio rather than failing silently.
        if arguments:
            self.activate()
        else:
            self.activate()
        return 0

    def _build_window(self) -> None:
        self.window = Adw.ApplicationWindow(application=self, title=constants.APP_NAME)
        self.window.set_default_size(
            int(self.config.get("ui.window_width", 1420)),
            int(self.config.get("ui.window_height", 900)),
        )
        self.window.set_size_request(940, 650)
        self.window.add_css_class("leet-window")

        self.toast_overlay = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title=constants.APP_NAME, subtitle=constants.APP_SUBTITLE)
        header.set_title_widget(self.title_widget)
        menu = Gio.Menu()
        menu.append("Rescan library", "app.rescan")
        menu.append("Open wallpaper folder", "app.open-folder")
        menu.append("Restore look", "app.restore-look")
        menu.append("Export theme…", "app.export-theme")
        menu.append("Import theme…", "app.import-theme")
        menu.append("Stop desktop widgets", "app.stop-widgets")
        menu.append("Stop video wallpaper", "app.stop-video")
        menu.append("About 1337-Customizer", "app.about")
        menu.append("Quit", "app.quit")
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(menu)
        menu_button.set_tooltip_text("Main menu")
        header.pack_end(menu_button)
        self.sidebar_toggle = Gtk.ToggleButton()
        self.sidebar_toggle.set_icon_name("sidebar-show-symbolic")
        self.sidebar_toggle.add_css_class("flat")
        self.sidebar_toggle.set_tooltip_text("Show or hide the sidebar")
        self.sidebar_toggle.set_active(True)
        header.pack_start(self.sidebar_toggle)
        toolbar.add_top_bar(header)

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)
        self.sidebar = self._build_sidebar()
        self.split_view = Adw.OverlaySplitView()
        self.split_view.set_sidebar(self.sidebar)
        self.split_view.set_content(self.stack)
        self.split_view.set_min_sidebar_width(190)
        self.split_view.set_max_sidebar_width(270)
        self.split_view.set_sidebar_width_fraction(0.18)
        self.split_view.set_pin_sidebar(False)
        self.split_view.set_show_sidebar(True)
        self.sidebar_toggle.connect(
            "toggled", lambda button: self.split_view.set_show_sidebar(button.get_active())
        )
        self.window.connect("notify::width", self._on_window_width)
        for signal in ("notify::fullscreened", "notify::maximized"):
            with __import__("contextlib").suppress(Exception):
                self.window.connect(signal, self._on_window_width)
        toolbar.set_content(self.split_view)
        self.toast_overlay.set_child(toolbar)
        self.window.set_content(self.toast_overlay)
        self.window.connect("close-request", self._on_close)
        self.show_page(str(self.config.get("ui.last_page", "library")))
        self.window.present()
        GLib.idle_add(self._fit_sidebar)

    def _on_window_width(self, *_args) -> None:
        GLib.idle_add(self._fit_sidebar)

    def _fit_sidebar(self) -> bool:
        """Keep the navigation usable when Hyprland tiles the window narrow."""
        if self.window is None or not hasattr(self, "split_view"):
            return False
        width = self.window.get_width()
        if width <= 0:
            return False
        if width < 1120:
            if self.sidebar_toggle.get_active():
                self.sidebar_toggle.set_active(False)
            with __import__("contextlib").suppress(Exception):
                self.split_view.set_collapsed(True)
            self.split_view.set_show_sidebar(False)
        else:
            with __import__("contextlib").suppress(Exception):
                self.split_view.set_collapsed(False)
            if not self.sidebar_toggle.get_active():
                self.sidebar_toggle.set_active(True)
            self.split_view.set_show_sidebar(True)
        return False

    def _build_sidebar(self) -> Gtk.Box:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar.add_css_class("leet-sidebar")
        sidebar.set_size_request(int(self.config.get("ui.sidebar_width", 226)), -1)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.add_css_class("brand-box")
        logo = Gtk.Box()
        logo.add_css_class("logo-tile")
        logo.set_size_request(38, 38)
        brand.append(logo)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = Gtk.Label(label="1337", xalign=0)
        title.add_css_class("brand-title")
        subtitle = Gtk.Label(label="C U S T O M I Z E R", xalign=0)
        subtitle.add_css_class("brand-sub")
        names.append(title)
        names.append(subtitle)
        brand.append(names)
        sidebar.append(brand)

        sep = Gtk.Box()
        sep.add_css_class("sidebar-separator")
        sidebar.append(sep)

        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.nav_list.set_activate_on_single_click(True)
        self.nav_list.add_css_class("sidebar-nav")
        self.nav_list.connect("row-activated", self._nav_activated)
        for key, (label, icon, _subtitle) in PAGE_FACTORIES.items():
            row = Gtk.ListBoxRow()
            row.set_name(key)
            child = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            child.add_css_class("nav-item")
            icon_widget = Gtk.Image.new_from_icon_name(icon)
            icon_widget.add_css_class("nav-icon")
            child.append(icon_widget)
            label_widget = Gtk.Label(label=label, xalign=0)
            label_widget.set_hexpand(True)
            child.append(label_widget)
            row.set_child(child)
            self.nav_rows[key] = row
            self.nav_list.append(row)
        sidebar.append(self.nav_list)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)

        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        footer.add_css_class("sidebar-footer")
        sep2 = Gtk.Box()
        sep2.add_css_class("sidebar-separator")
        footer.append(sep2)
        session = desktop.environment_report()
        if session["backends"].get("dms"):
            wallpaper_backend = "DMS"
        elif session["backends"].get("awww"):
            wallpaper_backend = "awww"
        elif session["backends"].get("gnome"):
            wallpaper_backend = "GNOME"
        else:
            wallpaper_backend = "fallback"
        status = Gtk.Label(
            label=f"{session.get('desktop', 'Linux')} · "
                  f"{'video ready' if session['backends'].get('mpvpaper') else 'static wallpaper'}\n"
                  f"{wallpaper_backend} · "
                  f"{'layer-shell' if session['backends'].get('layer_shell') else 'no layer-shell'}",
            xalign=0,
        )
        status.add_css_class("sidebar-status")
        footer.append(status)
        settings = Gtk.Button()
        settings.set_icon_name("emblem-system-symbolic")
        settings.add_css_class("flat")
        settings.set_tooltip_text("Settings")
        settings.connect("clicked", lambda *_a: self.show_page("settings"))
        footer.append(settings)
        restore = Gtk.Button(label="Restore")
        restore.add_css_class("flat")
        restore.connect("clicked", lambda *_a: self._restore_look())
        footer.append(restore)
        sidebar.append(footer)
        return sidebar

    def _nav_activated(self, _listbox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        key = row.get_name()
        if key:
            self.show_page(key, from_nav=True)

    def show_page(self, key: str, *, from_nav: bool = False) -> None:
        if key not in PAGE_FACTORIES:
            key = "library"
        if self.stack is None:
            return
        if key not in self.pages:
            page = self._create_page(key)
            self.pages[key] = page
            self.stack.add_named(page, key)
        self.stack.set_visible_child_name(key)
        self.current_page = key
        self.config.set("ui.last_page", key, save=False)
        if self.title_widget is not None:
            self.title_widget.set_subtitle(PAGE_FACTORIES[key][2])
        if self.nav_list is not None:
            for nav_key, nav_row in self.nav_rows.items():
                child = nav_row.get_child()
                if child is not None:
                    if nav_key == key:
                        child.add_css_class("active")
                    else:
                        child.remove_css_class("active")
            if not from_nav:
                row = self.nav_rows.get(key)
                if row is not None:
                    with __import__("contextlib").suppress(Exception):
                        self.nav_list.select_row(row)
        page = self.pages.get(key)
        if hasattr(page, "on_shown"):
            with __import__("contextlib").suppress(Exception):
                page.on_shown()
        if hasattr(self, "library_page") and key == "library":
            self.library_page = self.pages["library"]

    def _create_page(self, key: str) -> Gtk.Widget:
        if key == "library":
            from .pages.library_page import LibraryPage

            page = LibraryPage(self)
            self.library_page = page
            return page
        if key == "appearance":
            from .pages.appearance_page import AppearancePage

            return AppearancePage(self)
        if key == "widgets":
            from .pages.widgets_page import WidgetsPage

            return WidgetsPage(self)
        if key == "fonts":
            from .pages.fonts_page import FontsPage

            return FontsPage(self)
        if key == "video":
            from .pages.video_page import VideoPage

            return VideoPage(self)
        if key == "settings":
            from .pages.settings_page import SettingsPage

            return SettingsPage(self)
        raise KeyError(key)

    # --- public helpers -----------------------------------------------------------

    def toast(self, message: str) -> None:
        if self.toast_overlay is None:
            return
        toast = Adw.Toast.new(str(message)[:360])
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def refresh_appearance(self) -> None:
        page = self.pages.get("appearance")
        if page is not None and hasattr(page, "refresh"):
            page.refresh()

    def rebuild_thumbs(self) -> None:
        old = self.thumbs
        self.thumbs = ThumbCache(
            width=int(self.config.get("performance.thumb_size", 360)),
            workers=int(self.config.get("performance.thumb_threads", 4)),
            max_mb=int(self.config.get("performance.cache_mb", 512)),
            preview_max=int(self.config.get("performance.preview_max", 1600)),
        )
        for page in self.pages.values():
            if hasattr(page, "thumbs"):
                page.thumbs = self.thumbs
        try:
            old.executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        if hasattr(self, "library_page"):
            self.library_page.thumbs = self.thumbs

    def _on_close(self, _window) -> bool:
        if self.window is not None:
            width = self.window.get_width()
            height = self.window.get_height()
            if width > 500 and height > 400:
                self.config.set("ui.window_width", width, save=False)
                self.config.set("ui.window_height", height, save=False)
        self.config.save()
        return False

    # --- actions ------------------------------------------------------------------

    def _install_actions(self) -> None:
        actions = {
            "rescan": self._action_rescan,
            "open-folder": self._action_open_folder,
            "restore-look": self._restore_look,
            "stop-widgets": self._stop_widgets,
            "stop-video": self._stop_video,
            "about": self._about,
            "quit": lambda: self.quit(),
            "search": self._action_search,
            "export-theme": self._export_theme,
            "import-theme": self._import_theme,
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, cb=callback: cb())
            self.add_action(action)
        for name, accel in (("rescan", ["<Control>r"]), ("quit", ["<Control>q"]),
                            ("search", ["<Control>f"])):
            self.set_accels_for_action(f"app.{name}", accel)

    def _action_rescan(self) -> None:
        if not hasattr(self, "library_page"):
            self.show_page("library")
        page = getattr(self, "library_page", None)
        if page:
            page.start_scan()
            self.toast("Rescanning library…")

    def _action_search(self) -> None:
        self.show_page("library")
        page = getattr(self, "library_page", None)
        if page is not None:
            with __import__("contextlib").suppress(Exception):
                page.search.grab_focus()

    def _action_open_folder(self) -> None:
        folders = self.config.folders
        open_path(folders[0] if folders else Path.home())

    def _restore_look(self) -> None:
        def worker():
            try:
                desktop.restore_theme()
                GLib.idle_add(lambda: self.toast("Previous look restored"))
            except Exception as error:
                message = str(error)
                GLib.idle_add(lambda: self.toast(f"Restore failed: {message}"[:300]))

        threading.Thread(target=worker, daemon=True).start()

    def _stop_widgets(self) -> None:
        widget_daemon.stop()
        self.config.set("widgets.enabled", False)
        self.config.save()
        self.toast("Desktop widgets stopped")

    def _stop_video(self) -> None:
        from . import video

        stopped = video.stop(notify_user=True)
        self.toast("Video wallpaper stopped" if stopped else "No video wallpaper is running")

    def _export_theme(self) -> None:
        self.show_page("appearance")
        page = self.pages.get("appearance")
        if hasattr(page, "export_theme"):
            page.export_theme()

    def _import_theme(self) -> None:
        self.show_page("appearance")
        page = self.pages.get("appearance")
        if hasattr(page, "import_theme"):
            page.import_theme()

    def _about(self) -> None:
        dialog = Adw.AboutDialog(
            application_name=constants.APP_NAME,
            application_icon=constants.ICON_NAME,
            developer_name="Hamiid",
            version=constants.VERSION,
            comments="A faster wallpaper, theme, font and desktop widget studio.",
            license_type=Gtk.License.MIT_X11,
            developers=["Hamiid"],
            designers=["Hamiid"],
        )
        dialog.present(self.window)

    def run_gui(self, argv: list[str] | None = None) -> int:
        return self.run(argv or [])


def main(argv: list[str] | None = None) -> int:
    return LeetCustomizerApplication().run_gui(argv)
