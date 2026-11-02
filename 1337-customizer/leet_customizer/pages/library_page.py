"""Wallpaper library: virtualised grid, preview, apply and history."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gio, Gtk  # noqa: E402

from .. import desktop, palette, themes, video, wallpaper  # noqa: E402
from ..library import Library, WallpaperItem  # noqa: E402
from ..util import human_size, open_path  # noqa: E402
from . import common  # noqa: E402


class WallpaperCard(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.add_css_class("thumb-card")
        self.set_size_request(188, 148)
        self.path = ""
        self.overlay = Gtk.Overlay()
        self.picture = Gtk.Picture()
        self.picture.add_css_class("thumb-picture")
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.set_size_request(176, 99)
        self.picture.set_can_shrink(True)
        self.placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.placeholder.set_halign(Gtk.Align.CENTER)
        self.placeholder.set_valign(Gtk.Align.CENTER)
        placeholder_label = Gtk.Label(label="◌")
        placeholder_label.add_css_class("title-1")
        self.placeholder.append(placeholder_label)
        self.overlay.set_child(self.picture)
        self.overlay.add_overlay(self.placeholder)
        badge_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        badge_row.set_halign(Gtk.Align.START)
        badge_row.set_valign(Gtk.Align.START)
        badge_row.set_margin_top(6)
        badge_row.set_margin_start(6)
        self.kind_badge = Gtk.Label(label="")
        self.kind_badge.add_css_class("kind-badge")
        self.kind_badge.set_visible(False)
        badge_row.append(self.kind_badge)
        self.star = Gtk.Label(label="★")
        self.star.add_css_class("favorite-star")
        self.star.set_halign(Gtk.Align.END)
        self.star.set_valign(Gtk.Align.START)
        self.star.set_margin_top(5)
        self.star.set_margin_end(7)
        self.star.set_visible(False)
        self.overlay.add_overlay(badge_row)
        self.overlay.add_overlay(self.star)
        self.append(self.overlay)
        self.name_label = Gtk.Label(label="", xalign=0)
        self.name_label.add_css_class("thumb-name")
        self.name_label.set_ellipsize(3)
        self.meta_label = Gtk.Label(label="", xalign=0)
        self.meta_label.add_css_class("thumb-meta")
        self.append(self.name_label)
        self.append(self.meta_label)

    def bind(self, item: WallpaperItem, selected: bool) -> None:
        self.path = item.path
        self.name_label.set_text(item.name)
        self.meta_label.set_text(f"{item.resolution}   ·   {item.kind_label}")
        self.kind_badge.set_text(item.kind_label.upper())
        self.kind_badge.set_visible(item.kind != "image")
        self.star.set_visible(item.favorite)
        self.picture.set_paintable(None)
        self.placeholder.set_visible(True)
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")

    def show_texture(self, texture) -> None:
        if texture is None:
            return
        self.picture.set_paintable(texture)
        self.placeholder.set_visible(False)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")


class LibraryPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.config = app.config
        self.library: Library = app.library
        self.thumbs = app.thumbs
        self._scanning = False
        self._stopping = False
        self._search_source = 0
        self._preview_token = 0
        self.current_item: WallpaperItem | None = None
        self.filter_mode = self.config.get("library.filter", "all")
        self.sort_mode = self.config.get("library.sort", "name")
        self._cards: dict[str, WallpaperCard] = {}
        self._selected_path = ""
        self._build()
        self.reload()
        if not self.library.stats().get("total") and self.config.folders:
            GLib.idle_add(self.start_scan)
        elif self.config.get("library.scan_on_start", True):
            stats = self.library.stats()
            if time.time() - float(stats.get("last_scan", 0)) > 1800:
                GLib.timeout_add(500, self.start_scan)

    # --- construction -------------------------------------------------------------

    def _build(self) -> None:
        add_button = common.button("Add folder", icon="folder-new-symbolic", css="suggested-action",
                                   tooltip="Add a wallpaper folder", on_click=self.pick_folder)
        rescan = common.button("", icon="view-refresh-symbolic", tooltip="Rescan folders",
                               on_click=self.start_scan)
        open_folder = common.button("", icon="folder-open-symbolic", tooltip="Open wallpaper folder",
                                    on_click=lambda: open_path(self.config.folders[0] if self.config.folders else Path.home()))
        actions = [open_folder, rescan, add_button]
        outer, content = common.page_scaffold(
            "Wallpapers",
            "A fast, local library for pictures, GIFs and video wallpapers.",
            actions=actions,
        )
        self.append(outer)
        self.content = content

        self.stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.stats_row.set_homogeneous(True)
        self.stat_values = {}
        for key, label in (("total", "Wallpapers"), ("favorites", "Favourites"),
                           ("videos", "Videos"), ("bytes", "On disk")):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            box.add_css_class("stat-card")
            value = Gtk.Label(label="—", xalign=0)
            value.add_css_class("stat-value")
            caption = Gtk.Label(label=label, xalign=0)
            caption.add_css_class("stat-label")
            box.append(value)
            box.append(caption)
            self.stat_values[key] = value
            self.stats_row.append(box)
        content.append(self.stats_row)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.add_css_class("toolbar-row")
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search by name or folder…")
        self.search.set_hexpand(True)
        self.search.add_css_class("search-entry")
        self.search.connect("search-changed", self._search_changed)
        toolbar.append(self.search)

        self.filter_buttons: dict[str, Gtk.ToggleButton] = {}
        filter_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for value, label in (("all", "All"), ("favorites", "Favourites"),
                             ("image", "Images"), ("video", "Videos"),
                             ("animated", "Animated")):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("pill")
            button.set_active(value == self.filter_mode)
            button.connect("toggled", self._filter_clicked, value)
            self.filter_buttons[value] = button
            filter_group.append(button)
        toolbar.append(filter_group)

        self.sort_dropdown = common.dropdown([
            ("name", "Name"), ("newest", "Newest"), ("size", "Largest"),
            ("resolution", "Highest resolution"), ("favorites", "Favourites first"),
        ], self.sort_mode)
        self.sort_dropdown.connect("notify::selected", self._sort_changed)
        toolbar.append(self.sort_dropdown)
        content.append(toolbar)

        main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_row.set_vexpand(True)
        content.append(main_row)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left.set_hexpand(True)
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_vexpand(True)
        self.grid = Gtk.GridView()
        self.grid.set_min_columns(2)
        self.grid.set_max_columns(6)
        self.grid.set_hexpand(True)
        self.grid.set_margin_top(2)
        self.grid.set_margin_bottom(10)
        self.grid.add_css_class("wallpaper-grid")
        self.store = Gio.ListStore.new(WallpaperItem)
        self.filter = Gtk.CustomFilter.new(self._filter_func)
        self.filter_model = Gtk.FilterListModel(model=self.store, filter=self.filter)
        self.sorter = Gtk.CustomSorter.new(self._sort_func)
        self.sort_model = Gtk.SortListModel(model=self.filter_model, sorter=self.sorter)
        self.selection = Gtk.SingleSelection(model=self.sort_model)
        self.selection.set_autoselect(False)
        self.selection.set_can_unselect(True)
        self.selection.connect("notify::selected", self._selection_changed)
        self.factory = Gtk.SignalListItemFactory()
        self.factory.connect("setup", self._setup_card)
        self.factory.connect("bind", self._bind_card)
        self.grid.set_factory(self.factory)
        self.grid.set_model(self.selection)
        self.grid.connect("activate", lambda *_args: self.apply_selected())
        self.scroll.set_child(self.grid)
        left.append(self.scroll)

        status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        status.add_css_class("status-bar")
        self.status_label = Gtk.Label(label="Ready", xalign=0)
        self.status_label.set_hexpand(True)
        self.progress = Gtk.ProgressBar()
        self.progress.set_size_request(180, -1)
        self.progress.set_visible(False)
        status.append(self.status_label)
        status.append(self.progress)
        left.append(status)
        main_row.append(left)

        self.preview = self._build_preview()
        self.preview.set_hexpand(False)
        main_row.append(self.preview)

        self.drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        self.drop.connect("drop", self._on_drop)
        self.add_controller(self.drop)
        self.search.connect("activate", lambda *_a: self._focus_first())

    def _build_preview(self) -> Gtk.Box:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.add_css_class("preview-panel")
        panel.set_size_request(342, -1)
        panel.set_margin_start(10)

        self.preview_overlay = Gtk.Overlay()
        self.preview_picture = Gtk.Picture()
        self.preview_picture.add_css_class("preview-image")
        self.preview_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview_picture.set_size_request(318, 185)
        self.preview_picture.set_can_shrink(True)
        self.preview_loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.preview_loading.set_halign(Gtk.Align.CENTER)
        self.preview_loading.set_valign(Gtk.Align.CENTER)
        self.preview_loading.append(Gtk.Label(label="◌"))
        loading_label = Gtk.Label(label="Choose a wallpaper")
        loading_label.add_css_class("dim-label")
        self.preview_loading.append(loading_label)
        self.preview_overlay.set_child(self.preview_picture)
        self.preview_overlay.add_overlay(self.preview_loading)
        panel.append(self.preview_overlay)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.preview_title = Gtk.Label(label="Nothing selected", xalign=0)
        self.preview_title.add_css_class("preview-title")
        self.preview_title.set_ellipsize(3)
        self.preview_title.set_hexpand(True)
        self.favorite_button = common.button("", icon="non-starred-symbolic", tooltip="Favourite",
                                             on_click=self.toggle_favorite)
        title_row.append(self.preview_title)
        title_row.append(self.favorite_button)
        panel.append(title_row)

        self.preview_subtitle = Gtk.Label(label="Pick a picture from the grid.", xalign=0)
        self.preview_subtitle.add_css_class("dim-label")
        panel.append(self.preview_subtitle)

        meta = Gtk.Grid(column_spacing=14, row_spacing=4)
        self.meta_labels = {}
        for index, (key, label) in enumerate((("type", "Type"), ("resolution", "Resolution"),
                                               ("size", "File size"), ("folder", "Folder"))):
            key_label = Gtk.Label(label=label, xalign=0)
            key_label.add_css_class("meta-key")
            value_label = Gtk.Label(label="—", xalign=1)
            value_label.add_css_class("meta-value")
            value_label.set_hexpand(True)
            value_label.set_ellipsize(3)
            meta.attach(key_label, 0, index, 1, 1)
            meta.attach(value_label, 1, index, 1, 1)
            self.meta_labels[key] = value_label
        panel.append(meta)

        options = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.monitor_dropdown = common.dropdown(desktop.monitor_choices(),
                                                self.config.get("wallpaper.monitor", "all"))
        self.monitor_dropdown.set_hexpand(True)
        self.fit_dropdown = common.dropdown([(item, item.title()) for item in ("crop", "fit", "stretch", "center")],
                                            self.config.get("wallpaper.fit", "crop"))
        options.append(self.monitor_dropdown)
        options.append(self.fit_dropdown)
        panel.append(options)

        apply_button = common.button("Apply wallpaper", icon="emblem-ok-symbolic",
                                     css="suggested-action", on_click=self.apply_selected)
        apply_button.set_hexpand(True)
        self.apply_button = apply_button
        panel.append(apply_button)

        quick = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        quick.set_homogeneous(True)
        quick.append(common.button("Match colours", icon="applications-graphics-symbolic",
                                   tooltip="Create and apply a palette from this picture",
                                   on_click=self.match_colours))
        quick.append(common.button("Open folder", icon="folder-open-symbolic",
                                   on_click=self.open_current_folder))
        panel.append(quick)

        undo = common.button("Undo last wallpaper", icon="edit-undo-symbolic",
                             on_click=self.undo_last)
        panel.append(undo)

        history_label = Gtk.Label(label="Recent choices", xalign=0)
        history_label.add_css_class("section-title")
        panel.append(history_label)
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        panel.append(self.history_box)
        panel.set_valign(Gtk.Align.START)
        return panel

    # --- model / cards ------------------------------------------------------------

    def reload(self) -> None:
        selected_path = self._selected_path or (self.current_item.path if self.current_item else "")
        items = self.library.items()
        self.store.remove_all()
        for item in items:
            self.store.append(item)
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)
        self._update_stats()
        self._restore_selection(selected_path)
        if not items:
            self._show_empty_preview()
        self._update_status()
        self._refresh_history()

    def _restore_selection(self, path: str) -> None:
        if not path:
            if self.sort_model.get_n_items():
                self.selection.set_selected(0)
            else:
                self._show_empty_preview()
            return
        for index in range(self.sort_model.get_n_items()):
            item = self.sort_model.get_item(index)
            if item.path == path:
                self.selection.set_selected(index)
                return
        if self.sort_model.get_n_items():
            self.selection.set_selected(0)

    def _setup_card(self, _factory, list_item: Gtk.ListItem) -> None:
        card = WallpaperCard()
        list_item.set_child(card)
        list_item.connect("notify::selected", lambda item, _p: self._card_selected(item))

    def _card_selected(self, list_item: Gtk.ListItem) -> None:
        card = list_item.get_child()
        if isinstance(card, WallpaperCard):
            card.set_selected(bool(list_item.get_selected()))

    def _bind_card(self, _factory, list_item: Gtk.ListItem) -> None:
        item = list_item.get_item()
        card = list_item.get_child()
        if not isinstance(item, WallpaperItem) or not isinstance(card, WallpaperCard):
            return
        card.bind(item, bool(list_item.get_selected()))
        self._cards[item.path] = card
        path = item.path

        def loaded(texture, target=card, expected=path):
            if target.path == expected:
                target.show_texture(texture)

        self.thumbs.get_texture(item.path, item.mtime, item.size, item.kind, loaded)

    def _filter_func(self, item: WallpaperItem, _data=None) -> bool:
        if not isinstance(item, WallpaperItem):
            return False
        mode = self.filter_mode
        if mode == "favorites" and not item.favorite:
            return False
        if mode == "image" and item.kind != "image":
            return False
        if mode == "video" and item.kind != "video":
            return False
        if mode == "animated" and item.kind != "animated":
            return False
        text = (self.search.get_text() or "").strip().lower() if hasattr(self, "search") else ""
        if text and text not in item.name.lower() and text not in item.path.lower():
            return False
        return True

    def _sort_func(self, first: WallpaperItem, second: WallpaperItem, _data=None) -> int:
        if not isinstance(first, WallpaperItem) or not isinstance(second, WallpaperItem):
            return 0
        if self.sort_mode == "newest":
            return -1 if first.mtime > second.mtime else (1 if first.mtime < second.mtime else 0)
        if self.sort_mode == "size":
            return -1 if first.size > second.size else (1 if first.size < second.size else 0)
        if self.sort_mode == "resolution":
            left = first.width * first.height
            right = second.width * second.height
            return -1 if left > right else (1 if left < right else 0)
        if self.sort_mode == "favorites":
            if first.favorite != second.favorite:
                return -1 if first.favorite else 1
        return -1 if first.name.casefold() < second.name.casefold() else (
            1 if first.name.casefold() > second.name.casefold() else 0
        )

    def _search_changed(self, _entry) -> None:
        if self._search_source:
            GLib.source_remove(self._search_source)
        self._search_source = GLib.timeout_add(180, self._apply_search)

    def _apply_search(self) -> bool:
        self._search_source = 0
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_status()
        return False

    def _filter_clicked(self, button: Gtk.ToggleButton, value: str) -> None:
        if not button.get_active():
            if not any(widget.get_active() for widget in self.filter_buttons.values()):
                button.set_active(True)
            return
        self.filter_mode = value
        for key, widget in self.filter_buttons.items():
            if key != value:
                widget.set_active(False)
        self.config.set("library.filter", value, save=False)
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_status()

    def _sort_changed(self, *_args) -> None:
        self.sort_mode = common.selected_value(self.sort_dropdown, [
            ("name", "Name"), ("newest", "Newest"), ("size", "Largest"),
            ("resolution", "Highest resolution"), ("favorites", "Favourites first"),
        ], "name")
        self.config.set("library.sort", self.sort_mode, save=False)
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

    def _focus_first(self) -> None:
        if self.sort_model.get_n_items():
            self.selection.set_selected(0)
            self.grid.grab_focus()

    # --- selection / preview ------------------------------------------------------

    def _selection_changed(self, *_args) -> None:
        item = self.selection.get_selected_item()
        if isinstance(item, WallpaperItem):
            self.current_item = item
            self._selected_path = item.path
            self._show_preview(item)
        else:
            self.current_item = None
            self._show_empty_preview()

    def _show_empty_preview(self) -> None:
        self.preview_title.set_text("Nothing selected")
        self.preview_subtitle.set_text("Pick a picture from the grid.")
        self.preview_picture.set_paintable(None)
        self.preview_loading.set_visible(True)
        for label in self.meta_labels.values():
            label.set_text("—")
        self.favorite_button.set_icon_name("non-starred-symbolic")
        self.apply_button.set_label("Apply wallpaper")
        self._refresh_history()

    def _show_preview(self, item: WallpaperItem) -> None:
        self._preview_token += 1
        token = self._preview_token
        self.preview_title.set_text(item.name)
        self.preview_subtitle.set_text(f"{item.kind_label} · {Path(item.path).parent.name}")
        self.meta_labels["type"].set_text(item.kind_label)
        self.meta_labels["resolution"].set_text(item.resolution)
        self.meta_labels["size"].set_text(item.size_text)
        self.meta_labels["folder"].set_text(str(Path(item.path).parent))
        self.favorite_button.set_icon_name("starred-symbolic" if item.favorite else "non-starred-symbolic")
        if item.is_video:
            self.apply_button.set_label("Set video wallpaper")
        elif item.is_animated:
            self.apply_button.set_label("Set animated wallpaper")
        else:
            self.apply_button.set_label("Apply wallpaper")
        self.preview_loading.set_visible(True)

        def loaded(texture):
            if token != self._preview_token:
                return
            if texture is not None:
                self.preview_picture.set_paintable(texture)
                self.preview_loading.set_visible(False)
            else:
                self.preview_loading.set_visible(True)

        self.thumbs.get_preview(item.path, item.mtime, item.size, item.kind, loaded)
        self._refresh_history()

    def toggle_favorite(self) -> None:
        if not self.current_item:
            return
        value = self.library.toggle_favorite(self.current_item.path)
        self.current_item.favorite = value
        self.current_item.notify("favorite")
        self.favorite_button.set_icon_name("starred-symbolic" if value else "non-starred-symbolic")
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_stats()
        self._refresh_history()
        self.app.toast("Added to favourites" if value else "Removed from favourites")

    def open_current_folder(self) -> None:
        if self.current_item:
            open_path(Path(self.current_item.path).parent)

    # --- apply / slideshow --------------------------------------------------------

    def apply_selected(self, item: WallpaperItem | None = None, *,
                       monitor: str | None = None, fit: str | None = None,
                       quiet: bool = False) -> None:
        item = item or self.current_item
        if not item:
            return
        monitor = monitor or common.selected_value(self.monitor_dropdown, desktop.monitor_choices(),
                                                    self.config.get("wallpaper.monitor", "all"))
        fit = fit or common.selected_value(self.fit_dropdown,
                                           [(value, value.title()) for value in ("crop", "fit", "stretch", "center")],
                                           self.config.get("wallpaper.fit", "crop"))
        self.config.set("wallpaper.monitor", monitor, save=False)
        self.config.set("wallpaper.fit", fit, save=False)
        if item.is_video:
            self.config.set("video.monitor", monitor, save=False)
            self.config.set("video.fit", fit, save=False)
        self.config.save()
        self.status_label.set_text(f"Applying {item.name}…")
        self.progress.set_visible(True)
        self.progress.pulse()

        def worker():
            try:
                result = wallpaper.apply(item.path, self.config, monitor=monitor, fit=fit)
            except Exception as error:
                result = {"ok": False, "error": str(error)}
            GLib.idle_add(self._apply_done, item, result, quiet)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_done(self, item: WallpaperItem, result: dict, quiet: bool) -> bool:
        self.progress.set_visible(False)
        self.status_label.set_text("Ready")
        if not result.get("ok"):
            self.app.toast(f"Could not apply: {result.get('error', 'unknown error')}")
            return False
        message = f"Applied {item.name}"
        if result.get("warning"):
            message = result["warning"]
        if not quiet:
            self.app.toast(message)
        self._refresh_history()
        return False

    def match_colours(self) -> None:
        if not self.current_item:
            return
        item = self.current_item
        self.status_label.set_text("Sampling colours…")
        self.progress.set_visible(True)

        def worker():
            try:
                appearance = self.config.get("appearance", {})
                resolved = themes.resolve_theme(
                    themes.WALLPAPER_PRESET,
                    mode=appearance.get("mode", "dark"),
                    schedule=appearance.get("dark_schedule"),
                    wallpaper_path=item.path,
                    overrides=appearance,
                )
                report = desktop.apply_theme(self.config, resolved)
                return resolved, report
            except Exception as error:
                return None, {"ok": False, "warnings": [str(error)]}

        def done(resolved, report):
            self.progress.set_visible(False)
            self.status_label.set_text("Ready")
            if resolved is None:
                self.app.toast("Could not sample this picture")
                return False
            self.config.set("appearance.theme", themes.WALLPAPER_PRESET)
            self.config.set("appearance.mode", resolved["variant"])
            self.config.save()
            self.app.toast(f"Matched colours from {item.name}")
            if hasattr(self.app, "refresh_appearance"):
                self.app.refresh_appearance()
            return False

        import threading
        threading.Thread(target=lambda: GLib.idle_add(done, *worker()), daemon=True).start()

    def undo_last(self) -> None:
        recent = self.library.recent(2)
        if len(recent) < 2:
            self.app.toast("No previous wallpaper yet")
            return
        target = recent[1]
        item = self.library.item(target["path"])
        if item is None:
            self.app.toast("The previous file is no longer in the library")
            return
        self._restore_selection(item.path)
        self.apply_selected(item, monitor=target.get("monitor", "all"),
                            fit=target.get("fit", "crop"))

    def _refresh_history(self) -> None:
        for child in list(self.history_box):
            self.history_box.remove(child)
        recent = self.library.recent(6)
        if not recent:
            label = Gtk.Label(label="Nothing applied yet.", xalign=0)
            label.add_css_class("dim-label")
            self.history_box.append(label)
            return
        for entry in recent[:5]:
            name = Path(entry["path"]).name
            stamp = time.strftime("%H:%M", time.localtime(entry["at"]))
            button = Gtk.Button(label=f"{name}   ·   {stamp}")
            button.add_css_class("flat")
            button.add_css_class("history-row")
            button.set_halign(Gtk.Align.FILL)
            button.connect("clicked", lambda _b, path=entry["path"]: self._select_path(path))
            self.history_box.append(button)

    def _select_path(self, path: str) -> None:
        for index in range(self.sort_model.get_n_items()):
            item = self.sort_model.get_item(index)
            if item.path == path:
                self.selection.set_selected(index)
                return
        item = self.library.item(path)
        if item:
            self._apply_history(item, path)

    def _apply_history(self, item: WallpaperItem, path: str) -> None:
        self.apply_selected(item)

    # --- stats / status -----------------------------------------------------------

    def _update_stats(self) -> None:
        stats = self.library.stats()
        values = {
            "total": str(stats.get("total", 0)),
            "favorites": str(stats.get("favorites", 0)),
            "videos": str(stats.get("videos", 0)),
            "bytes": human_size(stats.get("bytes", 0)),
        }
        for key, label in self.stat_values.items():
            label.set_text(values.get(key, "—"))

    def _update_status(self) -> None:
        count = self.sort_model.get_n_items()
        total = self.store.get_n_items()
        suffix = f" · {count} shown" if count != total else ""
        self.status_label.set_text(f"{total} wallpapers{suffix}")

    # --- scanning / folders -------------------------------------------------------

    def start_scan(self) -> bool:
        if self._scanning:
            return False
        folders = self.config.folders
        if not folders:
            self.app.toast("Add a folder first")
            return False
        self._scanning = True
        self.progress.set_visible(True)
        self.progress.pulse()
        self.status_label.set_text("Scanning folders…")

        def worker():
            def progress(done, total, name):
                if done == total or done % max(1, total // 20) == 0:
                    GLib.idle_add(self._scan_progress, done, total, name)
            try:
                result = self.library.scan(
                    folders,
                    recursive=bool(self.config.get("library.recursive", True)),
                    progress=progress,
                    should_stop=lambda: self._stopping,
                )
            except Exception as error:
                GLib.idle_add(self._scan_failed, str(error))
                return
            GLib.idle_add(self._scan_done, result)
        threading.Thread(target=worker, daemon=True).start()
        return False

    def _scan_progress(self, done: int, total: int, name: str) -> bool:
        self.progress.set_fraction(done / max(1, total))
        self.status_label.set_text(f"Scanning {done}/{total} · {name}")
        return False

    def _scan_done(self, result: dict) -> bool:
        self._scanning = False
        self.progress.set_visible(False)
        self.status_label.set_text(
            f"Scanned {result.get('total', 0)} files in {result.get('seconds', 0):.2f}s "
            f"(+{result.get('added', 0)} new)"
        )
        self.reload()
        self.app.toast(f"Library refreshed · {result.get('added', 0)} new")
        return False

    def _scan_failed(self, message: str) -> bool:
        self._scanning = False
        self.progress.set_visible(False)
        self.status_label.set_text("Scan failed")
        self.app.toast(f"Library scan failed: {message[:240]}")
        return False

    def pick_folder(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Add a wallpaper folder")
        dialog.select_folder(self.get_root(), None, self._folder_selected)

    def _folder_selected(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder is None:
            return
        path = folder.get_path()
        if path and self.config.add_folder(path):
            self.start_scan()
            self.app.toast(f"Added {Path(path).name}")

    def _on_drop(self, _target, _x, _y, file_list: Gdk.FileList) -> bool:
        added = False
        for file in file_list.get_files():
            path = file.get_path()
            if not path:
                continue
            if Path(path).is_dir():
                added = self.config.add_folder(path) or added
            else:
                added = self.config.add_folder(Path(path).parent) or added
        if added:
            self.start_scan()
        return True

    def on_shown(self) -> None:
        if not self.library.stats().get("total") and not self._scanning:
            GLib.idle_add(self.start_scan)
