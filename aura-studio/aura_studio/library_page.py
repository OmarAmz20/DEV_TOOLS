"""The wallpaper library: browse, search, favourite, preview and apply."""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import library, store, widgets  # noqa: E402

SORTS = ("Name A–Z", "Name Z–A", "Newest first", "Oldest first")


class LibraryPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = window
        self.entries = []
        self.cards = {}
        self.gen = 0
        self.search_text = ""
        self.filter_favorites = False
        self.sort_index = 0
        self.selected = None
        self.hero_gen = 0

        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=1120, tightening_threshold=720)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                            margin_top=26, margin_bottom=36, margin_start=22, margin_end=22)
        clamp.set_child(self.page)
        scroller.set_child(clamp)
        self.append(scroller)

        self.build_header()
        self.build_hero()
        self.build_controls()
        self.build_grid()

    # --- construction --------------------------------------------------------------

    def build_header(self):
        suffix = Gtk.Box(spacing=8)
        self.folder_button = widgets.icon_button("folder-open-symbolic",
                                                 "Choose a different wallpaper folder",
                                                 self.choose_folder)
        suffix.append(self.folder_button)

        refresh = widgets.icon_button("view-refresh-symbolic", "Rescan the folder", self.refresh)
        suffix.append(refresh)

        self.slideshow_button = Gtk.MenuButton(icon_name="preferences-system-time-symbolic",
                                               tooltip_text="Slideshow")
        self.slideshow_button.set_menu_model(self.win.slideshow_menu)
        self.slideshow_button.add_css_class("flat")
        suffix.append(self.slideshow_button)
        self.page.append(widgets.page_header(
            "Wallpapers",
            "Browse your collection, preview the palette, then put it on the desktop.",
            suffix))

    def build_hero(self):
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        hero.add_css_class("aura-hero")
        hero.set_margin_top(2)

        picture_box = Gtk.Box()
        picture_box.set_size_request(-1, 240)
        picture_box.set_hexpand(True)
        self.hero_picture = Gtk.Picture(can_shrink=True, keep_aspect_ratio=True,
                                        content_fit=Gtk.ContentFit.COVER, hexpand=True,
                                        vexpand=True)
        self.hero_placeholder = Gtk.Image(icon_name="folder-pictures-symbolic",
                                          pixel_size=64, hexpand=True,
                                          halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.hero_placeholder.add_css_class("dim-label")
        picture_box.append(self.hero_picture)
        picture_box.append(self.hero_placeholder)
        picture_box.add_css_class("aura-inset")
        picture_box.set_overflow(Gtk.Overflow.HIDDEN)
        self.hero_picture.set_visible(False)
        self.hero_placeholder.set_visible(True)
        hero.append(picture_box)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        self.hero_title = Gtk.Label(xalign=0, wrap=True, label="Pick a wallpaper")
        self.hero_title.add_css_class("title-1")
        self.hero_meta = Gtk.Label(xalign=0, wrap=True,
                                   label="Your pictures never leave this folder.")
        self.hero_meta.add_css_class("dim-label")
        info.append(self.hero_title)
        info.append(self.hero_meta)

        preview_label = Gtk.Label(label="PALETTE PREVIEW", xalign=0)
        preview_label.add_css_class("caption-heading")
        preview_label.add_css_class("dim-label")
        preview_label.set_margin_top(6)
        info.append(preview_label)
        self.hero_swatches = widgets.SwatchRow(
            ("paper", "paper2", "sheet", "ink", "muted", "accent"), size=26, spacing=8)
        info.append(self.hero_swatches)
        self.hero_contrast = Gtk.Label(xalign=0, label="")
        self.hero_contrast.add_css_class("aura-hint")
        info.append(self.hero_contrast)

        buttons = Adw.WrapBox(child_spacing=8, line_spacing=8)
        buttons.set_margin_top(8)
        self.apply_button = widgets.button("Set wallpaper", "emblem-photos-symbolic")
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.add_css_class("pill")
        self.apply_button.set_sensitive(False)
        self.apply_button.connect("clicked", lambda _b: self.win.apply_wallpaper())
        buttons.append(self.apply_button)

        self.match_check = Gtk.CheckButton(label="Match colours")
        self.match_check.set_active(bool(self.win.config.get("match_colors", True)))
        self.match_check.set_tooltip_text("Recolour apps from this wallpaper as it is applied")
        self.match_check.connect("toggled", self.on_match_toggled)
        buttons.append(self.match_check)

        self.hero_fav = Gtk.Button(icon_name="non-starred-symbolic")
        self.hero_fav.add_css_class("flat")
        self.hero_fav.set_tooltip_text("Favourite")
        self.hero_fav.set_sensitive(False)
        self.hero_fav.connect("clicked", self.toggle_hero_favorite)
        buttons.append(self.hero_fav)

        palette_button = Gtk.Button(label="Palette Lab")
        palette_button.add_css_class("flat")
        palette_button.connect("clicked", lambda _b: self.win.go_to("palette"))
        buttons.append(palette_button)
        info.append(buttons)

        hero.append(info)
        self.page.append(hero)

    def build_controls(self):
        self.search = Gtk.SearchEntry(placeholder_text="Search wallpapers…", hexpand=True)
        self.search.set_max_width_chars(38)
        self.search.connect("search-changed", self.on_search)
        self.page.append(self.search)

        filters_row = Gtk.Box(spacing=10)
        filters = Gtk.Box(css_classes=["linked"], valign=Gtk.Align.CENTER)
        self.all_button = Gtk.ToggleButton(label="All", active=True)
        self.fav_button = Gtk.ToggleButton(label="Favourites", group=self.all_button)
        self.all_button.connect("toggled", self.on_filter, False)
        self.fav_button.connect("toggled", self.on_filter, True)
        filters.append(self.all_button)
        filters.append(self.fav_button)
        filters_row.append(filters)

        spacer = Gtk.Box(hexpand=True)
        filters_row.append(spacer)
        self.sort_dropdown = Gtk.DropDown(model=Gtk.StringList.new(list(SORTS)))
        self.sort_dropdown.set_tooltip_text("Sort wallpapers")
        self.sort_dropdown.connect("notify::selected", self.on_sort)
        filters_row.append(self.sort_dropdown)
        self.page.append(filters_row)

        self.summary = Gtk.Label(xalign=0, label="", wrap=True)
        self.summary.add_css_class("aura-hint")
        self.page.append(self.summary)

    def build_grid(self):
        self.grid = Gtk.FlowBox(homogeneous=True, selection_mode=Gtk.SelectionMode.NONE,
                                min_children_per_line=1, max_children_per_line=6,
                                row_spacing=12, column_spacing=12,
                                valign=Gtk.Align.START)
        self.page.append(self.grid)
        self.empty = Adw.StatusPage(icon_name="folder-pictures-symbolic",
                                    title="No wallpapers here",
                                    description="Choose another folder or drop a picture onto the window.")
        self.empty.add_css_class("compact")
        self.empty.set_visible(False)
        self.page.append(self.empty)

    # --- data ----------------------------------------------------------------------

    def load_folder(self, force_select=False):
        folder = self.win.config["folder"]
        self.entries = library.scan(folder)
        self.summary.set_label(
            f"{len(self.entries)} wallpaper{'s' if len(self.entries) != 1 else ''} · "
            f"{folder.replace(os.path.expanduser('~'), '~', 1)}")
        self.rebuild()
        if force_select or not self.selected:
            current = self.win.selection or self.win.state.get("wallpaper")
            paths = [entry["path"] for entry in self.entries]
            if force_select and current and os.path.realpath(current) not in {
                    os.path.realpath(path) for path in paths}:
                current = paths[0] if paths else None
            if current and os.path.exists(current):
                self.win.select_wallpaper(current)
            elif paths:
                self.win.select_wallpaper(paths[0])
        self.refresh_current()

    def refresh(self, *_):
        self.win.refresh_library(notify=True)

    def rebuild(self):
        self.gen += 1
        widgets.clear_box(self.grid)
        self.cards.clear()
        entries = self.filtered_entries()
        self.favorite_paths = {os.path.realpath(p)
                               for p in self.win.config.get("favorites", [])}
        self.grid.set_visible(bool(entries))
        self.empty.set_visible(not entries)
        if not entries:
            self.empty.set_description(
                "No favourites yet. Star a wallpaper to keep it here."
                if self.filter_favorites and not self.search_text
                else "Try another search or rescan the folder.")
        for entry in entries:
            self.grid.append(self._make_card(entry, self.gen))

    def filtered_entries(self):
        entries = list(self.entries)
        if self.filter_favorites:
            favorites = {os.path.realpath(p) for p in self.win.config.get("favorites", [])}
            entries = [entry for entry in entries
                       if os.path.realpath(entry["path"]) in favorites]
        if self.search_text:
            needle = self.search_text.casefold()
            entries = [entry for entry in entries if needle in entry["name"].casefold()]
        if self.sort_index == 0:
            entries.sort(key=lambda entry: entry["name"].lower())
        elif self.sort_index == 1:
            entries.sort(key=lambda entry: entry["name"].lower(), reverse=True)
        elif self.sort_index == 2:
            entries.sort(key=lambda entry: entry["mtime"], reverse=True)
        else:
            entries.sort(key=lambda entry: entry["mtime"])
        return entries

    def _make_card(self, entry, generation):
        path = entry["path"]
        picture = Gtk.Picture(can_shrink=True, keep_aspect_ratio=True,
                              width_request=250, height_request=140)
        button = Gtk.Button(child=picture, css_classes=["aura-thumb", "flat"])
        button.set_size_request(250, 148)
        button.set_tooltip_text(entry["name"])
        button.connect("clicked", lambda _b, p=path: self.win.select_wallpaper(p))

        overlay = Gtk.Overlay(child=button)
        overlay.set_halign(Gtk.Align.CENTER)

        self.cards[path] = {
            "button": button,
            "picture": picture,
            "star": None,
            "current": None,
            "overlay": overlay,
        }

        is_favorite = os.path.realpath(path) in self.favorite_paths
        star = Gtk.Button(css_classes=["aura-star", "flat"],
                          icon_name="starred-symbolic" if is_favorite else "non-starred-symbolic",
                          halign=Gtk.Align.END, valign=Gtk.Align.START)
        star.set_tooltip_text("Favourite")
        star.connect("clicked", self.toggle_card_favorite, path)
        overlay.add_overlay(star)
        self.cards[path]["star"] = star

        current = Gtk.Label(label="CURRENT", css_classes=["aura-badge", "current"],
                            halign=Gtk.Align.START, valign=Gtk.Align.START,
                            margin_start=7, margin_top=7)
        current.set_visible(False)
        overlay.add_overlay(current)
        self.cards[path]["current"] = current

        if entry["kind"] != "Picture":
            badge = Gtk.Label(label=entry["kind"].upper(), css_classes=["aura-badge"],
                              halign=Gtk.Align.START, valign=Gtk.Align.END,
                              margin_start=7, margin_bottom=7)
            overlay.add_overlay(badge)

        gesture = Gtk.GestureClick()
        gesture.connect("pressed", self.on_card_pressed, path)
        overlay.add_controller(gesture)
        if self.selected and os.path.realpath(self.selected) == os.path.realpath(path):
            button.add_css_class("selected")

        self.win.thumb_pool.submit(self._load_thumb, path, picture, generation)
        return overlay

    def _load_thumb(self, path, picture, generation):
        try:
            pixbuf = library.thumbnail(path)
        except Exception:
            pixbuf = None
        if pixbuf is None:
            return

        def apply():
            if generation == self.gen and picture.get_root() is not None:
                picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            return False
        GLib.idle_add(apply)

    def on_card_pressed(self, _gesture, presses, _x, _y, path):
        if presses == 2:
            self.win.select_wallpaper(path)
            self.win.apply_wallpaper()

    # --- interactions --------------------------------------------------------------

    def on_search(self, entry):
        self.search_text = entry.get_text().strip()
        self.rebuild()

    def on_filter(self, button, favorites):
        if button.get_active():
            self.filter_favorites = favorites
            self.rebuild()

    def on_sort(self, dropdown, _param):
        self.sort_index = dropdown.get_selected()
        self.rebuild()

    def on_match_toggled(self, check):
        self.win.save_config(match_colors=check.get_active())
        self.win.look_page.sync_from_config()

    def toggle_card_favorite(self, button, path):
        active = store.toggle_favorite(path)
        button.set_icon_name("starred-symbolic" if active else "non-starred-symbolic")
        button.remove_css_class("active") if not active else button.add_css_class("active")
        self.win.reload_config()
        self.win.palette_page.refresh_favourite()
        if self.filter_favorites:
            self.rebuild()
        self.update_selection(self.selected)

    def toggle_hero_favorite(self, *_):
        if not self.selected:
            return
        active = store.toggle_favorite(self.selected)
        self.win.reload_config()
        self.update_favorite_buttons(self.selected, active)
        if self.filter_favorites:
            self.rebuild()
        self.win.toast("Added to favourites" if active else "Removed from favourites")

    def update_favorite_buttons(self, path, active=None):
        if active is None:
            active = store.is_favorite(path)
        if self.selected == path:
            self.hero_fav.set_icon_name("starred-symbolic" if active else "non-starred-symbolic")
        card = self.cards.get(path)
        if card and card["star"]:
            card["star"].set_icon_name("starred-symbolic" if active else "non-starred-symbolic")
            if active:
                card["star"].add_css_class("active")
            else:
                card["star"].remove_css_class("active")

    def choose_folder(self, *_):
        dialog = Gtk.FileDialog(title="Choose your wallpaper folder", modal=True)
        folder = self.win.config["folder"]
        if os.path.isdir(folder):
            dialog.set_initial_folder(Gio.File.new_for_path(folder))

        def done(source, result):
            try:
                chosen = source.select_folder_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if not path:
                return
            self.win.save_config(folder=path)
            self.load_folder(force_select=True)
            self.win.toast(f"Wallpaper folder: {path.replace(os.path.expanduser('~'), '~', 1)}")

        dialog.select_folder(self.win, None, done)

    # --- display -------------------------------------------------------------------

    def update_selection(self, path):
        self.selected = path
        previous = getattr(self, "_last_selected", None)
        if previous and previous in self.cards:
            self.cards[previous]["button"].remove_css_class("selected")
        if path in self.cards:
            self.cards[path]["button"].add_css_class("selected")
        self._last_selected = path
        self.show_hero(path)

    def show_hero(self, path):
        self.hero_gen += 1
        generation = self.hero_gen
        if not path or not os.path.exists(path):
            self.hero_picture.set_paintable(None)
            self.hero_picture.set_visible(False)
            self.hero_placeholder.set_visible(True)
            self.hero_title.set_label("Pick a wallpaper")
            self.hero_meta.set_label("Your pictures never leave this folder.")
            self.hero_swatches.set_palette({})
            self.hero_contrast.set_label("")
            self.apply_button.set_sensitive(False)
            self.hero_fav.set_sensitive(False)
            return

        self.hero_picture.set_visible(True)
        self.hero_placeholder.set_visible(False)
        self.apply_button.set_sensitive(True)
        self.hero_fav.set_sensitive(True)
        name = os.path.basename(path)
        kind = library.kind(path)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        dims = None if library.is_video(path) else library.dimensions(path)
        bits = [kind, store.human_size(size)]
        if dims:
            bits.append(f"{dims[0]} × {dims[1]}")
        if kind == "Video":
            bits.append("applied as a still frame")
        self.hero_title.set_label(os.path.splitext(name)[0])
        self.hero_meta.set_label(" · ".join(bits))
        self.update_favorite_buttons(path)
        if self.win.preview_palette:
            self.show_palette(self.win.preview_palette)
        else:
            self.hero_swatches.set_palette({})
            self.hero_contrast.set_label("Reading colours…")

        self.win.thumb_pool.submit(self._load_hero, path, generation)

    def _load_hero(self, path, generation):
        try:
            pixbuf = library.preview(path)
        except Exception:
            pixbuf = None
        if pixbuf is None:
            return

        def apply():
            if generation == self.hero_gen:
                self.hero_picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            return False
        GLib.idle_add(apply)

    def show_palette(self, palette):
        if not palette:
            return
        self.hero_swatches.set_palette(palette["dark"] if self.win.effective_mode() == "dark"
                                       else palette["light"])
        p = palette["dark"] if self.win.effective_mode() == "dark" else palette["light"]
        from . import color
        body = color.contrast(p["ink"], p["paper"])
        accent = color.contrast(p["accent_text"], p["paper"])
        self.hero_contrast.set_label(
            f"{'Dark' if self.win.effective_mode() == 'dark' else 'Light'} preview · "
            f"text {body:.1f}:1 ({color.contrast_label(body)}) · "
            f"accent {accent:.1f}:1 ({color.contrast_label(accent)})")

    def refresh_current(self):
        wallpaper = self.win.state.get("wallpaper")
        current = os.path.realpath(wallpaper) if wallpaper else ""
        for path, card in self.cards.items():
            is_current = bool(current) and os.path.realpath(path) == current
            card["current"].set_visible(is_current)
            if is_current:
                card["button"].add_css_class("current")
            else:
                card["button"].remove_css_class("current")

    def refresh_favourite(self):
        self.update_favorite_buttons(self.selected)
        self.update_selection(self.selected)
