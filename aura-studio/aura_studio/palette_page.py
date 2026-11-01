"""Palette Lab: pick any image, tune the palette, preview and export it."""
from __future__ import annotations

import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import library, palette, store, system, widgets  # noqa: E402

EXPORT_LABELS = {
    "css": ("GTK stylesheet", "aura-theme.css", "css"),
    "json": ("JSON palette", "aura-palette.json", "json"),
    "kitty": ("Kitty terminal theme", "aura-kitty.conf", "conf"),
}


class PalettePage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = window
        self.image_path = None
        self.image_gen = 0
        self.updating = False
        self.current_palette = None

        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=1060, tightening_threshold=720)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                            margin_top=26, margin_bottom=36, margin_start=22, margin_end=22)
        clamp.set_child(self.page)
        scroller.set_child(clamp)
        self.append(scroller)

        self.build_header()
        self.build_source()
        self.build_controls()
        self.build_previews()
        self.build_actions()

    # --- construction --------------------------------------------------------------

    def build_header(self):
        suffix = widgets.button("Choose image…", "document-open-symbolic")
        suffix.add_css_class("pill")
        suffix.connect("clicked", self.choose_image)
        self.page.append(widgets.page_header(
            "Palette Lab",
            "Extract a usable desktop palette from any picture — wallpaper or not.",
            suffix))

    def build_source(self):
        card = Gtk.Box(spacing=18)
        card.add_css_class("aura-card")
        card.set_margin_top(2)

        frame = Gtk.Box()
        frame.set_size_request(220, 124)
        frame.add_css_class("aura-inset")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        self.source_picture = Gtk.Picture(can_shrink=True, keep_aspect_ratio=True,
                                          content_fit=Gtk.ContentFit.COVER, hexpand=True,
                                          vexpand=True)
        self.source_picture.set_visible(False)
        self.source_placeholder = Gtk.Image(icon_name="image-x-generic-symbolic", pixel_size=48,
                                            hexpand=True, halign=Gtk.Align.CENTER,
                                            valign=Gtk.Align.CENTER)
        self.source_placeholder.add_css_class("dim-label")
        frame.append(self.source_picture)
        frame.append(self.source_placeholder)
        card.append(frame)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        info.set_valign(Gtk.Align.CENTER)
        self.source_title = Gtk.Label(xalign=0, wrap=True, label="No image selected")
        self.source_title.add_css_class("title-2")
        info.append(self.source_title)
        self.source_meta = Gtk.Label(xalign=0, wrap=True,
                                     label="Choose a picture, or use the one selected in Wallpapers.")
        self.source_meta.add_css_class("aura-hint")
        info.append(self.source_meta)

        buttons = Gtk.Box(spacing=8)
        buttons.set_margin_top(6)
        self.wallpaper_button = widgets.button("Set as wallpaper", "emblem-photos-symbolic")
        self.wallpaper_button.add_css_class("flat")
        self.wallpaper_button.connect("clicked", lambda _b: self.win.apply_wallpaper())
        buttons.append(self.wallpaper_button)
        self.favourite_button = Gtk.Button(icon_name="non-starred-symbolic", tooltip_text="Favourite")
        self.favourite_button.add_css_class("flat")
        self.favourite_button.connect("clicked", self.toggle_favourite)
        buttons.append(self.favourite_button)
        info.append(buttons)
        card.append(info)
        self.wallpaper_button.set_sensitive(False)
        self.favourite_button.set_sensitive(False)
        self.page.append(card)

    def build_controls(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("aura-card")

        style_row = Gtk.Box(spacing=12)
        style_label = Gtk.Label(label="Palette style", xalign=0)
        style_label.add_css_class("aura-section-title")
        style_label.set_hexpand(True)
        style_row.append(style_label)
        styles = Gtk.Box(css_classes=["linked"])
        self.style_buttons = {}
        first = None
        for style in palette.STYLES:
            button = Gtk.ToggleButton(label=palette.STYLE_LABELS[style],
                                      tooltip_text=palette.STYLE_DESCRIPTIONS[style])
            button.set_group(first)
            first = first or button
            button.connect("toggled", self.on_style, style)
            styles.append(button)
            self.style_buttons[style] = button
        style_row.append(styles)
        card.append(style_row)

        accent_row = Gtk.Box(spacing=12)
        accent_label = Gtk.Label(label="Accent", xalign=0)
        accent_label.add_css_class("aura-section-title")
        accent_label.set_hexpand(True)
        accent_row.append(accent_label)
        self.accent_button = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(with_alpha=False, title="Choose an accent colour"))
        self.accent_button.set_tooltip_text("Use a custom accent instead of the picture's")
        self._accent_shown = widgets.colour_button_hex(self.accent_button)
        self.accent_button.connect("notify::rgba", self.on_custom_accent)
        accent_row.append(self.accent_button)
        self.reset_accent = Gtk.Button(label="Use image accent")
        self.reset_accent.add_css_class("flat")
        self.reset_accent.connect("clicked", lambda _b: self.win.set_accent(None))
        accent_row.append(self.reset_accent)
        card.append(accent_row)

        self.accent_hint = Gtk.Label(xalign=0, wrap=True)
        self.accent_hint.add_css_class("aura-hint")
        card.append(self.accent_hint)
        self.page.append(card)

    def build_previews(self):
        previews = Gtk.Box(spacing=16, homogeneous=True)
        self.light_card = widgets.PaletteCard("Light", "light")
        self.dark_card = widgets.PaletteCard("Dark", "dark")
        self.light_card.set_hexpand(True)
        self.dark_card.set_hexpand(True)
        previews.append(self.light_card)
        previews.append(self.dark_card)
        self.page.append(previews)

    def build_actions(self):
        row = Gtk.Box(spacing=8)
        row.set_margin_top(2)
        self.apply_button = widgets.button("Apply colours", "color-select-symbolic")
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.add_css_class("pill")
        self.apply_button.connect("clicked", lambda _b: self.win.apply_colors())
        row.append(self.apply_button)

        copy = widgets.button("Copy palette", "edit-copy-symbolic")
        copy.add_css_class("flat")
        copy.connect("clicked", self.copy_palette)
        row.append(copy)

        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6,
                      margin_bottom=6, margin_start=6, margin_end=6)
        for kind, (label, _name, _suffix) in EXPORT_LABELS.items():
            button = Gtk.Button(label=label)
            button.add_css_class("flat")
            button.set_halign(Gtk.Align.FILL)
            button.connect("clicked", lambda _b, k=kind: self.export(k))
            box.append(button)
        popover.set_child(box)
        export = Gtk.MenuButton(icon_name="document-save-symbolic", tooltip_text="Export palette")
        export.add_css_class("flat")
        export.set_popover(popover)
        row.append(export)
        self.page.append(row)

        self.apply_hint = Gtk.Label(xalign=0, wrap=True)
        self.apply_hint.add_css_class("aura-hint")
        self.apply_hint.set_label(
            "Applying colours uses the mode chosen in Look & Feel. The wallpaper stays as it is.")
        self.page.append(self.apply_hint)

    # --- image ----------------------------------------------------------------------

    def choose_image(self, *_):
        dialog = Gtk.FileDialog(title="Choose an image")
        filters = Gtk.FileFilter(name="Pictures and videos")
        for suffix in library.ALL_EXT:
            filters.add_suffix(suffix.lstrip("."))
        store_filters = Gio.ListStore.new(Gtk.FileFilter)
        store_filters.append(filters)
        dialog.set_filters(store_filters)
        dialog.set_default_filter(filters)
        dialog.set_modal(True)
        if self.win.selection:
            dialog.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self.win.selection)))

        def done(source, result):
            try:
                chosen = source.open_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if path:
                self.win.select_wallpaper(path)

        dialog.open(self.win, None, done)

    def toggle_favourite(self, *_):
        if not self.win.selection:
            return
        active = store.toggle_favorite(self.win.selection)
        self.win.reload_config()
        self.win.library_page.refresh_favourite()
        self.refresh_favourite()
        self.win.toast("Added to favourites" if active else "Removed from favourites")

    def refresh_favourite(self):
        if self.win.selection:
            self.favourite_button.set_icon_name(
                "starred-symbolic" if store.is_favorite(self.win.selection) else "non-starred-symbolic")

    # --- palette state -------------------------------------------------------------

    def refresh_from_window(self):
        path = self.win.selection
        if path != self.image_path:
            self.image_path = path
            self.load_source_image(path)
        self.updating = True
        try:
            for style, button in self.style_buttons.items():
                button.set_active(style == self.win.config["style"])
            self.refresh_favourite()
        finally:
            self.updating = False

        self.update_source_meta(path)
        self.update_accent_button()
        self.set_palette(self.win.preview_palette)

    def load_source_image(self, path):
        self.image_gen += 1
        generation = self.image_gen
        if not path or not os.path.exists(path):
            self.source_picture.set_paintable(None)
            self.source_picture.set_visible(False)
            self.source_placeholder.set_visible(True)
            self.source_title.set_label("No image selected")
            self.source_meta.set_label("Choose a picture, or use the one selected in Wallpapers.")
            self.wallpaper_button.set_sensitive(False)
            self.favourite_button.set_sensitive(False)
            return
        self.wallpaper_button.set_sensitive(True)
        self.favourite_button.set_sensitive(True)
        self.source_picture.set_visible(True)
        self.source_placeholder.set_visible(False)
        self.source_title.set_label(os.path.splitext(os.path.basename(path))[0])
        self.win.thumb_pool.submit(self._load_source, path, generation)

    def _load_source(self, path, generation):
        try:
            pixbuf = library.thumbnail(path, 500, 280)
        except Exception:
            pixbuf = None
        if pixbuf is None:
            return

        def apply():
            if generation == self.image_gen:
                self.source_picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            return False
        GLib.idle_add(apply)

    def update_source_meta(self, path):
        if not path or not os.path.exists(path):
            return
        bits = [library.kind(path), store.human_size(os.path.getsize(path))]
        dims = None if library.is_video(path) else library.dimensions(path)
        if dims:
            bits.append(f"{dims[0]} × {dims[1]}")
        if library.is_video(path):
            bits.append("palette from one frame")
        if not path.startswith(self.win.config["folder"] + os.sep):
            bits.append("outside the library")
        self.source_meta.set_label(" · ".join(bits))
        self.wallpaper_button.set_sensitive(True)

    def update_accent_button(self):
        self.updating = True
        try:
            custom = self.win.config.get("accent")
            fallback = (self.current_palette or self.win.preview_palette or {}).get(
                self.win.effective_mode(), {}).get("accent", "#888888")
            shown = (custom or fallback).upper()
            self._accent_shown = shown
            widgets.set_colour_button(self.accent_button, shown)
            if custom:
                self.accent_hint.set_label(f"Custom accent {custom.upper()} · "
                                           "the image still supplies the background tint.")
            else:
                self.accent_hint.set_label("The accent is chosen from the picture's vivid colours. "
                                           "Pick a colour to override it.")
            self.reset_accent.set_sensitive(bool(custom))
        finally:
            self.updating = False

    def set_palette(self, palette_value):
        self.current_palette = palette_value
        if not palette_value:
            self.apply_button.set_sensitive(False)
            self.light_card.set_visible(False)
            self.dark_card.set_visible(False)
            return
        self.light_card.set_visible(True)
        self.dark_card.set_visible(True)
        self.light_card.set_palette(palette_value["light"])
        self.dark_card.set_palette(palette_value["dark"])
        self.apply_button.set_sensitive(True)
        mode = self.win.effective_mode()
        self.apply_hint.set_label(
            f"Applying colours now uses the {mode} palette "
            f"({self.win.config['mode']} mode). The wallpaper stays as it is.")
        self.update_accent_button()

    # --- actions --------------------------------------------------------------------

    def on_style(self, button, style):
        if self.updating or not button.get_active():
            return
        self.win.set_style(style)

    def on_custom_accent(self, button, _param):
        if self.updating:
            return
        chosen = widgets.colour_button_hex(button)
        if chosen == getattr(self, "_accent_shown", None):
            return
        self._accent_shown = chosen
        self.win.set_accent(chosen)

    def copy_palette(self, *_):
        value = self.current_palette or self.win.preview_palette
        if not value:
            self.win.toast("No palette to copy yet")
            return
        text = json.dumps(palette.palette_json(value), indent=2, ensure_ascii=False)
        Gdk.Display.get_default().get_clipboard().set(text)
        self.win.toast("Palette copied as JSON")

    def export(self, kind):
        value = self.current_palette or self.win.preview_palette
        if not value:
            self.win.toast("No palette to export yet")
            return
        label, name, suffix = EXPORT_LABELS[kind]
        file_filter = Gtk.FileFilter(name=label)
        file_filter.add_suffix(suffix)
        dialog = Gtk.FileDialog(title=label, initial_name=name, modal=True)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)

        def done(source, result):
            try:
                chosen = source.save_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if not path:
                return
            try:
                system.export_palette(kind, value, self.win.effective_mode(), path)
            except Exception as error:
                self.win.toast(f"Could not export: {error}")
                return
            self.win.toast(f"Exported {os.path.basename(path)}")

        dialog.save(self.win, None, done)
