"""The Aura Studio window and application."""
from __future__ import annotations

import concurrent.futures
import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import core, library, palette, store, system, widgets  # noqa: E402
from .library_page import LibraryPage  # noqa: E402
from .look_page import LookPage, SLIDE_CHOICES  # noqa: E402
from .palette_page import PalettePage  # noqa: E402
from .profiles_page import ProfilesPage  # noqa: E402

APP_ID = "io.github.AuraStudio"
VERSION = "1.0.0"
PAGES = (
    ("library", "Wallpapers", "view-grid-symbolic"),
    ("palette", "Palette Lab", "color-select-symbolic"),
    ("look", "Look & Feel", "applications-graphics-symbolic"),
    ("profiles", "Profiles", "avatar-default-symbolic"),
)


class AuraApp(Adw.Application):
    def __init__(self):
        flags = (Gio.ApplicationFlags.DEFAULT_FLAGS
                 if hasattr(Gio.ApplicationFlags, "DEFAULT_FLAGS")
                 else Gio.ApplicationFlags.FLAGS_NONE)
        super().__init__(application_id=APP_ID, flags=flags)
        self.window = None
        self.theme_provider = Gtk.CssProvider()

    def do_startup(self):
        Adw.Application.do_startup(self)
        GLib.set_prgname(APP_ID)
        GLib.set_application_name("Aura Studio")
        display = Gdk.Display.get_default()
        if display:
            local_icons = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "data", "icons")
            if os.path.isdir(local_icons):
                Gtk.IconTheme.get_for_display(display).add_search_path(local_icons)
            Gtk.StyleContext.add_provider_for_display(
                display, widgets.app_css_provider(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            Gtk.StyleContext.add_provider_for_display(
                display, self.theme_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            self.reload_theme()

    def reload_theme(self):
        css = system.app_theme_css()
        try:
            self.theme_provider.load_from_data(css.encode("utf-8") if css else b"")
        except GLib.Error:
            pass

    def do_activate(self):
        if self.window is None:
            self.window = AuraWindow(self)
        self.window.present()


class AuraWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Aura Studio",
                         default_width=1180, default_height=830)
        self.set_size_request(680, 540)
        self.app = app
        self.config = store.load_config()
        self.state = store.load_state()
        self.selection = None
        self.preview_palette = None
        self._palette_gen = 0
        self._palette_cache = {}
        self._closing = False
        self.busy = False
        self._slide_next = None
        self._slide_warned = False
        self.thumb_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4,
                                                                thread_name_prefix="aura-thumb")
        self.work_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2,
                                                               thread_name_prefix="aura-work")
        self.build_actions()
        self.build_ui()
        self.build_pages()
        self.connect("close-request", self.on_close)

        self.library_page.load_folder()
        self.profiles_page.refresh_from_window()
        self.update_sidebar_footer()
        self._auto_source = GLib.timeout_add_seconds(60, self._tick_auto)
        self._slide_source = GLib.timeout_add_seconds(30, self._tick_slideshow)
        self._schedule_slideshow()

    # --- construction --------------------------------------------------------------

    def build_actions(self):
        self.menu = Gio.Menu()
        file_section = Gio.Menu()
        file_section.append("Open a file…", "win.open")
        file_section.append("Choose wallpaper folder…", "win.folder")
        file_section.append("Rescan library", "win.refresh")
        self.menu.append_section(None, file_section)

        view_section = Gio.Menu()
        view_section.append("Toggle sidebar", "win.sidebar")
        self.menu.append_section(None, view_section)

        app_section = Gio.Menu()
        app_section.append("Restore original look", "win.restore")
        app_section.append("About Aura Studio", "win.about")
        app_section.append("Quit", "win.quit")
        self.menu.append_section(None, app_section)

        for name, callback in (
                ("open", self.on_open),
                ("folder", lambda *_: self.library_page.choose_folder()),
                ("refresh", self.on_refresh),
                ("sidebar", self.on_toggle_sidebar),
                ("restore", self.ask_restore),
                ("about", self.about),
                ("quit", lambda *_: self.app.quit()),
                ("shuffle", lambda *_: self.shuffle_now())):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        self.slideshow_action = Gio.SimpleAction.new_stateful(
            "slideshow", GLib.VariantType.new("i"),
            GLib.Variant.new_int32(int(self.config.get("slide_minutes", 0))))
        self.slideshow_action.connect("activate", self.on_slideshow_action)
        self.add_action(self.slideshow_action)
        self.slideshow_menu = Gio.Menu()
        seconds = Gio.Menu()
        for minutes, label in SLIDE_CHOICES:
            item = Gio.MenuItem.new(label, None)
            item.set_action_and_target_value("win.slideshow", GLib.Variant.new_int32(minutes))
            seconds.append_item(item)
        self.slideshow_menu.append_section(None, seconds)
        self.slideshow_menu.append("Shuffle now", "win.shuffle")

    def build_ui(self):
        self.toasts = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Aura Studio",
                                                subtitle="Wallpapers · Palettes · Looks"))
        self.sidebar_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic",
                                               active=True, tooltip_text="Toggle sidebar")
        self.sidebar_toggle.add_css_class("flat")
        header.pack_start(self.sidebar_toggle)
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        header.pack_start(self.spinner)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=self.menu,
                                       tooltip_text="Menu"))
        toolbar.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=160, hexpand=True, vexpand=True)

        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.add_css_class("aura-sidebar")
        self.nav = Gtk.ListBox(css_classes=["navigation-sidebar"],
                               selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav_rows = {}
        for name, title, icon_name in PAGES:
            row = Gtk.ListBoxRow()
            row.page_name = name
            box = Gtk.Box(spacing=10, margin_top=8, margin_bottom=8,
                          margin_start=10, margin_end=10)
            image = Gtk.Image(icon_name=icon_name)
            label = Gtk.Label(label=title, xalign=0, hexpand=True)
            box.append(image)
            box.append(label)
            row.set_child(box)
            self.nav.append(row)
            self.nav_rows[name] = row
        self.nav.connect("row-selected", self.on_nav)
        self.sidebar.append(self.nav)

        spacer = Gtk.Box(vexpand=True)
        self.sidebar.append(spacer)
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                         margin_top=10, margin_bottom=14, margin_start=14, margin_end=14)
        self.footer_backend = Gtk.Label(xalign=0, wrap=True)
        self.footer_backend.add_css_class("aura-hint")
        self.footer_session = Gtk.Label(xalign=0)
        self.footer_session.add_css_class("aura-hint")
        footer.append(self.footer_backend)
        footer.append(self.footer_session)
        restore = widgets.button("Restore original", "edit-undo-symbolic")
        restore.add_css_class("flat")
        restore.set_margin_top(6)
        restore.connect("clicked", lambda _b: self.ask_restore())
        footer.append(restore)
        self.sidebar.append(footer)

        self.split = Adw.OverlaySplitView(
            sidebar=self.sidebar, content=self.stack, show_sidebar=True,
            min_sidebar_width=214, max_sidebar_width=262, sidebar_width_fraction=0.20)
        self.sidebar_toggle.connect("toggled", self.on_sidebar_toggled)
        self.split.connect("notify::show-sidebar", self.on_sidebar_shown)
        toolbar.set_content(self.split)
        self.toasts.set_child(toolbar)
        self.set_content(self.toasts)

        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self.on_drop)
        self.add_controller(drop)

    def build_pages(self):
        self.library_page = LibraryPage(self)
        self.palette_page = PalettePage(self)
        self.look_page = LookPage(self)
        self.profiles_page = ProfilesPage(self)
        for page in (self.library_page, self.palette_page, self.look_page, self.profiles_page):
            page.set_hexpand(True)
            page.set_vexpand(True)
        self.stack.add_named(self.library_page, "library")
        self.stack.add_named(self.palette_page, "palette")
        self.stack.add_named(self.look_page, "look")
        self.stack.add_named(self.profiles_page, "profiles")
        start_page = os.environ.get("AURA_PAGE", "library")
        if start_page not in self.nav_rows:
            start_page = "library"
        self.stack.set_visible_child_name(start_page)
        self.nav.select_row(self.nav_rows[start_page])

    # --- navigation / small actions ------------------------------------------------

    def on_nav(self, _list, row):
        if row is None:
            return
        name = getattr(row, "page_name", None)
        if not name:
            return
        self.stack.set_visible_child_name(name)
        if name == "palette":
            self.palette_page.refresh_from_window()
        elif name == "look":
            self.look_page.sync_from_config()
        elif name == "profiles":
            self.profiles_page.refresh_from_window()

    def go_to(self, name):
        row = self.nav_rows.get(name)
        if row is not None:
            self.nav.select_row(row)

    def on_toggle_sidebar(self, *_):
        self.sidebar_toggle.set_active(not self.sidebar_toggle.get_active())

    def on_sidebar_toggled(self, button):
        if self.split.get_show_sidebar() != button.get_active():
            self.split.set_show_sidebar(button.get_active())

    def on_sidebar_shown(self, split, _param):
        if self.sidebar_toggle.get_active() != split.get_show_sidebar():
            self.sidebar_toggle.set_active(split.get_show_sidebar())

    def toast(self, message):
        if not message:
            return
        toast = Adw.Toast(title=str(message), timeout=4)
        self.toasts.add_toast(toast)

    def update_sidebar_footer(self):
        backend = system.backend_label()
        self.footer_backend.set_label(f"Wallpaper: {backend}")
        self.footer_session.set_label(f"{system.session_label()} · Aura {VERSION}")

    def open_custom_css(self):
        try:
            os.makedirs(store.CONFIG_DIR, exist_ok=True)
            if not os.path.exists(store.CUSTOM_CSS):
                store.write_text(
                    store.CUSTOM_CSS,
                    "/* Aura Studio custom CSS.\n"
                    " * This file is appended to the generated GTK theme and is\n"
                    " * never overwritten by Aura. Use it for extra tweaks:\n"
                    " *   window { border-radius: 10px; }\n"
                    " */\n")
            self._open_path(store.CUSTOM_CSS)
        except OSError as error:
            self.toast(f"Could not open custom.css: {error}")

    def open_hooks_folder(self):
        try:
            os.makedirs(store.HOOKS, exist_ok=True)
            self._open_path(store.HOOKS)
        except OSError as error:
            self.toast(f"Could not open the hooks folder: {error}")

    def _open_path(self, path):
        try:
            Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(path).get_uri(), None)
        except GLib.Error as error:
            self.toast(f"Could not open {path}: {error.message}")

    def reload_config(self):
        self.config = store.load_config()
        return self.config

    def save_config(self, **changes):
        self.config = store.save_config(**changes)
        return self.config

    def effective_mode(self):
        return core.effective_mode(self.config)

    def accent_from_preview(self):
        value = self.preview_palette or self.state.get("palette")
        if value:
            mode = self.effective_mode()
            return value.get(mode, value.get("dark", {})).get("accent")
        return None

    # --- wallpaper / palette state -------------------------------------------------

    def _palette_key(self, path=None):
        return (os.path.realpath(path or self.selection or ""),
                self.config["style"], self.config.get("accent") or "")

    def select_wallpaper(self, path):
        if not path:
            return
        path = os.path.realpath(path)
        if not os.path.exists(path):
            self.toast(f"Missing file: {os.path.basename(path)}")
            return
        key = self._palette_key(path)
        cached = self._palette_cache.get(key)
        changed = path != self.selection
        self.selection = path
        self.preview_palette = cached
        self.library_page.update_selection(path)
        self.palette_page.refresh_from_window()
        self.look_page.refresh_status()
        if cached is None:
            self.recompute_palette(path)
        elif changed:
            self.palette_page.set_palette(cached)

    def recompute_palette(self, path=None):
        path = path or self.selection
        if not path:
            return
        self._palette_gen += 1
        generation = self._palette_gen
        style = self.config["style"]
        accent = self.config.get("accent")
        key = (os.path.realpath(path), style, accent or "")

        def work():
            still = library.still_for(path, 1600)
            if still is None:
                raise ValueError("This file has no readable picture"
                                 + (" (install ffmpeg for videos)" if library.is_video(path) else ""))
            return palette.from_image(still, style, accent)

        def done(value, error):
            if error:
                if generation == self._palette_gen:
                    self.toast(error)
                return
            if generation != self._palette_gen:
                return
            if key[:2] != self._palette_key(path)[:2]:
                return
            if len(self._palette_cache) > 40:
                self._palette_cache.pop(next(iter(self._palette_cache)))
            self._palette_cache[key] = value
            self.preview_palette = value
            self.library_page.show_palette(value)
            self.palette_page.set_palette(value)
            self.look_page.refresh_status()
            self.profiles_page.save_button.set_sensitive(True)

        self._palette_task(work, done)

    def _palette_task(self, work, done):
        def runner():
            try:
                value, error = work(), None
            except Exception as exc:
                value, error = None, str(exc) or exc.__class__.__name__
            if not self._closing:
                GLib.idle_add(lambda: (done(value, error), False)[1])

        self.work_pool.submit(runner)

    def set_style(self, style):
        if style not in palette.STYLES or style == self.config["style"]:
            return
        self.save_config(style=style)
        self.look_page.sync_from_config()
        self.palette_page.refresh_from_window()
        if self.selection:
            self.preview_palette = self._palette_cache.get(self._palette_key())
            self.recompute_palette()

    def set_accent(self, accent):
        if accent:
            accent = "#" + accent.lstrip("#").upper()
            if not (len(accent) == 7 and all(c in "0123456789ABCDEF" for c in accent[1:])):
                return
        if accent == self.config.get("accent"):
            return
        self.save_config(accent=accent)
        self.look_page.sync_from_config()
        self.palette_page.refresh_from_window()
        if self.selection:
            self.preview_palette = self._palette_cache.get(self._palette_key())
            self.recompute_palette()

    def mode_changed(self):
        if self.preview_palette:
            self.library_page.show_palette(self.preview_palette)
            self.palette_page.set_palette(self.preview_palette)
        self.palette_page.update_accent_button()
        self.look_page.refresh_status()

    def refresh_library(self, notify=False):
        self.reload_config()
        self.library_page.load_folder()
        self.update_sidebar_footer()
        if notify:
            self.toast("Library rescanned")

    def refresh_after_apply(self):
        self.reload_config()
        self.state = store.load_state()
        self.library_page.refresh_current()
        if self.preview_palette:
            self.palette_page.set_palette(self.preview_palette)
        self.look_page.sync_from_config()
        self.profiles_page.refresh_from_window()
        self.update_sidebar_footer()
        self.app.reload_theme()

    # --- long actions --------------------------------------------------------------

    def _run(self, work, done, error_prefix=""):
        if self.busy:
            self.toast("Still working on the last change…")
            return False
        self.busy = True
        self.spinner.set_visible(True)
        self.spinner.start()

        def runner():
            try:
                value, error = work(), None
            except Exception as exc:
                value, error = None, (str(exc) or exc.__class__.__name__)
            if not self._closing:
                GLib.idle_add(finish, value, error)

        def finish(value, error):
            if self._closing:
                return False
            self.busy = False
            self.spinner.stop()
            self.spinner.set_visible(False)
            if error:
                self.toast(f"{error_prefix}{error}")
            elif done:
                try:
                    done(value)
                except Exception as exc:
                    self.toast(f"{error_prefix}{exc}")
            return False

        self.work_pool.submit(runner)
        return True

    def apply_wallpaper(self):
        if not self.selection:
            self.toast("Pick a wallpaper first")
            return
        path = self.selection
        config = dict(self.config)
        preview = self.preview_palette

        def work():
            return core.apply_wallpaper(path, config, preview)

        def done(result):
            self.refresh_after_apply()
            matched = result["matched"]
            backend = result["result"].get("backend")
            message = "Wallpaper set"
            if result["result"].get("fallback"):
                message += f" · {backend} fallback"
            if matched:
                message += " · desktop colours matched"
            self.toast(message)
        self._run(work, done, "Could not set wallpaper: ")

    def apply_colors(self):
        value = self.preview_palette
        if not value:
            self.toast("The palette is still being read — give it a second")
            return
        config = dict(self.config)
        source = self.selection
        still = self.state.get("still")

        def work():
            return core.apply_colours(value, config, source=source, still=still)

        def done(mode):
            self.refresh_after_apply()
            self.toast(f"{mode.title()} colours applied")
        self._run(work, done, "Could not apply colours: ")

    def apply_look(self):
        value = self.preview_palette or self.state.get("palette")
        if not value:
            self.toast("Choose a wallpaper or an image first")
            return
        config = dict(self.config)
        source = self.selection if self.preview_palette else self.state.get("palette_source")
        source = source or self.selection
        still = self.state.get("still")

        def work():
            return core.apply_colours(value, config, source=source, still=still)

        def done(mode):
            self.refresh_after_apply()
            self.toast(f"Look applied in {mode} mode")
        self._run(work, done, "Could not apply the look: ")

    def apply_profile(self, profile):
        def work():
            return core.apply_profile(profile)

        def done(result):
            self.reload_config()
            self.state = store.load_state()
            path = result.get("wallpaper") or self.state.get("wallpaper") or self.selection
            if path and os.path.exists(path):
                self.select_wallpaper(path)
            self.refresh_after_apply()
            self.toast(f"Applied {profile.get('name', 'profile')}")
        self._run(work, done, "Could not apply the profile: ")

    def save_current_profile(self, name):
        applied = bool(self.state.get("palette"))
        value = self.state.get("palette") if applied else self.preview_palette
        if not value:
            self.toast("There is no palette to save yet")
            return
        wallpaper = self.state.get("wallpaper") if applied else self.selection
        source = self.state.get("palette_source") if applied else self.selection
        profile = {
            "name": name,
            "palette": value,
            "wallpaper": wallpaper,
            "palette_source": source,
            "created": time.time(),
        }
        for key in ("mode", "light_from", "dark_from", "style", "accent",
                    "wallpaper_mode"):
            profile[key] = self.config.get(key)
        profile.update(core.options_snapshot(self.config))
        store.save_profile(profile)
        self.profiles_page.refresh_from_window()
        self.toast(f"Saved “{name}”")

    def ask_restore(self, *_):
        dialog = Adw.AlertDialog(
            heading="Restore your original look?",
            body="Aura puts back the theme, colours, fonts, icons, cursor, terminal and "
                 "wallpaper it found before its first change. Your pictures and saved "
                 "profiles stay where they are.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("restore", "Restore")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)

        def response(source, response_id):
            if response_id != "restore":
                return

            def work():
                return core.restore()

            def done(_value):
                self.state = store.load_state()
                self.reload_config()
                self.app.reload_theme()
                self.library_page.refresh_current()
                self.look_page.sync_from_config()
                self.profiles_page.refresh_from_window()
                self.toast("Original look restored")
            self._run(work, done, "Could not restore: ")
        dialog.connect("response", response)
        dialog.present(self)

    # --- files, slideshow ----------------------------------------------------------

    def on_open(self, *_):
        dialog = Gtk.FileDialog(title="Open and apply a wallpaper")
        filters = Gtk.FileFilter(name="Pictures and videos")
        for suffix in library.ALL_EXT:
            filters.add_suffix(suffix.lstrip("."))
        store_filters = Gio.ListStore.new(Gtk.FileFilter)
        store_filters.append(filters)
        dialog.set_filters(store_filters)
        dialog.set_default_filter(filters)
        dialog.set_modal(True)
        if self.selection:
            dialog.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self.selection)))

        def done(source, result):
            try:
                chosen = source.open_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if path:
                self.select_wallpaper(path)
                self.apply_wallpaper()

        dialog.open(self, None, done)

    def on_drop(self, _target, value, _x, _y):
        try:
            path = value.get_path()
        except AttributeError:
            path = None
        if not path or not library.is_wallpaper(path):
            self.toast("Drop a picture or a video")
            return False
        self.select_wallpaper(path)
        self.apply_wallpaper()
        return True

    def on_refresh(self, *_):
        self.refresh_library(notify=True)

    def on_slideshow_action(self, action, parameter):
        minutes = parameter.get_int32() if parameter is not None else 0
        self.slideshow_action.set_state(GLib.Variant.new_int32(minutes))
        self.save_config(slide_minutes=minutes)
        self.look_page.sync_from_config()
        self._slide_warned = False
        self._schedule_slideshow()
        if minutes:
            self.toast(f"Slideshow: every {minutes} minutes while Aura is open")

    def slideshow_changed(self):
        minutes = int(self.config.get("slide_minutes", 0))
        self.slideshow_action.set_state(GLib.Variant.new_int32(minutes))
        self._slide_warned = False
        self._schedule_slideshow()

    def _schedule_slideshow(self):
        minutes = int(self.config.get("slide_minutes", 0))
        self._slide_next = time.monotonic() + minutes * 60 if minutes > 0 else None

    def shuffle_now(self):
        if self.busy:
            self.toast("Still working on the last change…")
            return
        paths = [entry["path"] for entry in library.scan(self.config["folder"])]
        path = library.next_path(paths, self.state.get("wallpaper") or self.selection,
                                 self.config.get("slideshow_order", "shuffle"))
        if not path:
            self.toast("Nothing else to pick in this folder")
            return
        self.select_wallpaper(path)
        self.apply_wallpaper()

    def _tick_slideshow(self):
        if self._closing:
            return False
        if not self._slide_next or self.busy:
            return True
        if time.monotonic() < self._slide_next:
            return True
        self._slide_next = time.monotonic() + max(1, int(self.config.get("slide_minutes", 1))) * 60
        paths = [entry["path"] for entry in library.scan(self.config["folder"])]
        path = library.next_path(paths, self.state.get("wallpaper") or self.selection,
                                 self.config.get("slideshow_order", "shuffle"))
        if not path:
            if not self._slide_warned:
                self.toast("Slideshow is on, but there is nothing else in the folder")
                self._slide_warned = True
            return True
        self._slide_warned = False
        self.select_wallpaper(path)
        self.apply_wallpaper()
        return True

    def _tick_auto(self):
        if self._closing:
            return False
        if self.busy or self.config["mode"] != "auto" or not self.state.get("palette"):
            return True
        if self.state.get("mode_setting") != "auto":
            return True
        mode = self.effective_mode()
        if mode == self.state.get("mode"):
            return True
        value = self.state["palette"]
        config = dict(self.config)
        source = self.state.get("palette_source")
        still = self.state.get("still")
        options = self.state.get("options") or core.options_snapshot(config)

        def work():
            return core.apply_colours(
                value, config, mode=mode, options=options, source=source, still=still)

        def done(_mode):
            self.refresh_after_apply()
            self.toast(f"Auto mode: switched to {mode} colours")
        self._run(work, done)
        return True

    # --- about / close -------------------------------------------------------------

    def about(self, *_):
        dialog = Adw.AboutDialog(
            application_name="Aura Studio",
            application_icon=APP_ID,
            version=VERSION,
            developer_name="Aura Studio",
            comments="Wallpapers, palettes and desktop looks that work together.\n\n"
                     "Inspired by Wallpaper Studio, rebuilt as a library, a palette lab "
                     "and a profile switcher.",
            license_type=Gtk.License.MIT_X11,
        )
        dialog.present(self)

    def on_close(self, *_):
        self._closing = True
        for source in (getattr(self, "_auto_source", None), getattr(self, "_slide_source", None)):
            if source:
                GLib.source_remove(source)
        self.thumb_pool.shutdown(wait=False, cancel_futures=True)
        self.work_pool.shutdown(wait=False, cancel_futures=True)
        return False


def main(argv=None):
    return AuraApp().run(argv)
