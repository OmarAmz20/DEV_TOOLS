"""Font browser, installer and typography settings."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from .. import desktop  # noqa: E402
from ..util import popen  # noqa: E402
from . import common  # noqa: E402


def _font_attrs(family: str, size: int = 16) -> Pango.AttrList:
    attrs = Pango.AttrList()
    attrs.insert(Pango.attr_family_new(family))
    attrs.insert(Pango.attr_size_new_absolute(size * Pango.SCALE))
    return attrs


class FontsPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.config = app.config
        self.fonts: list[str] = []
        self.selected_family = ""
        self._row_families = {}
        self._search_source = 0
        self._build()
        self.refresh()

    def _build(self) -> None:
        install = common.button("Install font", icon="document-open-symbolic",
                                on_click=self.install_fonts)
        apply_button = common.button("Apply font settings", icon="emblem-ok-symbolic",
                                     css="suggested-action", on_click=self.apply)
        reset = common.button("", icon="edit-undo-symbolic", tooltip="Restore previous font settings",
                              on_click=self.reset)
        outer, content = common.page_scaffold(
            "Type & fonts", "Browse your installed families, preview them live and tune readability.",
            actions=[reset, install, apply_button],
        )
        self.append(outer)
        self.content = content

        current = common.card()
        current.append(common.section("Current typography", "Applied through GTK and the desktop interface settings."))
        self.current_labels = {}
        for key, title in (("font-name", "Interface"), ("monospace-font-name", "Monospace"),
                           ("document-font-name", "Documents"), ("text-scaling-factor", "Text scale"),
                           ("cursor-size", "Cursor size")):
            label = Gtk.Label(label="—", xalign=1)
            label.add_css_class("meta-value")
            self.current_labels[key] = label
            current.append(common.row(title, trailing=label))
        content.append(current)

        pickers = common.card()
        pickers.append(common.section("Choose fonts", "Set the family and size for each role."))
        self.ui_font = common.font_button(desktop.get_value(desktop.INTERFACE, "font-name", "") or "")
        self.mono_font = common.font_button(desktop.get_value(desktop.INTERFACE, "monospace-font-name", "") or "")
        self.doc_font = common.font_button(desktop.get_value(desktop.INTERFACE, "document-font-name", "") or "")
        for title, widget in (
            ("Interface font", self.ui_font),
            ("Monospace font", self.mono_font),
            ("Document font", self.doc_font),
        ):
            row = common.row(title, trailing=widget)
            pickers.append(row)
        scale_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        scale_label = Gtk.Label(label="Text scale", xalign=0)
        scale_label.set_hexpand(True)
        self.scale = common.scale(float(desktop.get_value(desktop.INTERFACE, "text-scaling-factor", 1.0) or 1.0),
                                  0.75, 2.0, 0.05)
        self.scale.set_size_request(250, -1)
        scale_row.append(scale_label)
        scale_row.append(self.scale)
        pickers.append(scale_row)
        cursor_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        cursor_label = Gtk.Label(label="Cursor size", xalign=0)
        cursor_label.set_hexpand(True)
        self.cursor_size = common.spin(float(desktop.get_value(desktop.INTERFACE, "cursor-size", 24) or 24),
                                       16, 72, 2)
        cursor_row.append(cursor_label)
        cursor_row.append(self.cursor_size)
        pickers.append(cursor_row)
        content.append(pickers)

        preview = common.card()
        preview.append(common.section("Preview", "Type a sample and inspect the selected family."))
        self.sample = Gtk.Entry()
        self.sample.set_text("The quick brown fox jumps over the lazy dog · 0123456789")
        self.sample.connect("changed", lambda *_a: self._update_preview())
        preview.append(self.sample)
        self.preview_label = Gtk.Label(label=self.sample.get_text(), xalign=0)
        self.preview_label.set_wrap(True)
        self.preview_label.add_css_class("font-preview")
        preview.append(self.preview_label)
        self.preview_name = Gtk.Label(label="", xalign=0)
        self.preview_name.add_css_class("dim-label")
        preview.append(self.preview_name)
        content.append(preview)

        browser = common.section("Installed families", "Click a family to preview it. Use the buttons to assign it.")
        content.append(browser)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter families…")
        self.search.set_hexpand(True)
        self.search.connect("search-changed", self._search_changed)
        toolbar.append(self.search)
        self.use_ui = common.button("Use for interface", icon="emblem-ok-symbolic",
                                    on_click=lambda: self._use_for("ui"))
        self.use_mono = common.button("Use for monospace", on_click=lambda: self._use_for("mono"))
        toolbar.append(self.use_ui)
        toolbar.append(self.use_mono)
        content.append(toolbar)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.connect("row-activated", self._row_activated)
        self.listbox.connect("row-selected", self._row_selected)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(420)
        scroll.set_child(self.listbox)
        content.append(scroll)

    def refresh(self) -> None:
        self.fonts = desktop.list_font_families()
        for key, label in self.current_labels.items():
            value = desktop.get_value(desktop.INTERFACE, key)
            if key == "text-scaling-factor":
                label.set_text(f"{float(value or 1.0):.2f}×")
            elif key == "cursor-size":
                label.set_text(f"{value or 24} px")
            else:
                label.set_text(str(value or "System default"))
        self._filter_fonts()
        self._update_preview()

    def _search_changed(self, _entry) -> None:
        if self._search_source:
            GLib.source_remove(self._search_source)
        self._search_source = GLib.timeout_add(150, self._filter_fonts)

    def _filter_fonts(self) -> bool:
        self._search_source = 0
        query = (self.search.get_text() or "").strip().lower()
        for child in list(self.listbox):
            self.listbox.remove(child)
        shown = 0
        for family in self.fonts:
            if query and query not in family.lower():
                continue
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            name = Gtk.Label(label=family, xalign=0)
            name.add_css_class("font-name")
            sample = Gtk.Label(label=self.sample.get_text() if hasattr(self, "sample") else family, xalign=0)
            sample.set_attributes(_font_attrs(family, 13))
            sample.add_css_class("dim-label")
            box.append(name)
            box.append(sample)
            row.set_child(box)
            self._row_families[row] = family
            self.listbox.append(row)
            shown += 1
            if shown >= 500:
                break
        return False

    def _row_activated(self, _listbox, row: Gtk.ListBoxRow) -> None:
        self._row_selected(_listbox, row)

    def _row_selected(self, _listbox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        self.selected_family = self._row_families.get(row, "")
        self._update_preview()

    def _update_preview(self) -> None:
        family = self.selected_family or self.current_family() or "Adwaita Sans"
        text = self.sample.get_text() or "1337-Customizer"
        self.preview_label.set_text(text)
        self.preview_label.set_attributes(_font_attrs(family, 22))
        self.preview_name.set_text(f"{family} · 22 pt")

    def current_family(self) -> str:
        value = str(desktop.get_value(desktop.INTERFACE, "font-name", "") or "")
        return value.rsplit(" ", 1)[0] if value else ""

    def _use_for(self, role: str) -> None:
        if not self.selected_family:
            self.app.toast("Pick a family first")
            return
        if role == "ui":
            description = f"{self.selected_family} 11"
            self.ui_font.set_font_desc(Pango.FontDescription.from_string(description))
            desktop.set_string(desktop.INTERFACE, "font-name", description)
        else:
            description = f"{self.selected_family} 11"
            self.mono_font.set_font_desc(Pango.FontDescription.from_string(description))
            desktop.set_string(desktop.INTERFACE, "monospace-font-name", description)
        self.config.set("appearance.apply_fonts", True, save=False)
        self.config.save()
        self.refresh()
        self.app.toast(f"{self.selected_family} applied")

    def apply(self) -> None:
        self.config.set("appearance.apply_fonts", True, save=False)
        for key, button in (("ui_font", self.ui_font), ("mono_font", self.mono_font),
                            ("doc_font", self.doc_font)):
            desc = button.get_font_desc()
            self.config.set(f"appearance.{key}", desc.to_string() if desc else "", save=False)
        self.config.set("appearance.text_scale", round(float(self.scale.get_value()), 2), save=False)
        self.config.set("appearance.cursor_size", int(self.cursor_size.get_value()), save=False)
        self.config.save()
        changed = desktop.apply_fonts(self.config)
        desktop.set_int(desktop.INTERFACE, "cursor-size", int(self.cursor_size.get_value()))
        self.refresh()
        self.app.toast("Font settings applied")
        if not changed:
            self.app.toast("Some font keys were not writable")

    def install_fonts(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Install font files")
        filters = Gio_filter()
        dialog.set_filters(filters)
        dialog.open_multiple(self.get_root(), None, self._installed)

    def _installed(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        paths = []
        if hasattr(files, "get_n_items"):
            for index in range(files.get_n_items()):
                file = files.get_item(index)
                path = file.get_path() if file else None
                if path:
                    paths.append(path)
        else:
            for file in files:
                path = file.get_path() if file else None
                if path:
                    paths.append(path)
        if not paths:
            return
        result = desktop.install_font_files(paths)
        self.refresh()
        if result["errors"]:
            self.app.toast(f"Installed {len(result['copied'])}; {len(result['errors'])} failed")
        else:
            self.app.toast(f"Installed {len(result['copied'])} font file(s)")

    def reset(self) -> None:
        restored = desktop.restore_desktop_backup({
            "font-name", "monospace-font-name", "document-font-name",
            "text-scaling-factor", "cursor-size",
        })
        self.refresh()
        self.app.toast(f"Restored {restored} font setting(s)")


def Gio_filter():
    from gi.repository import Gio

    filters = Gio.ListStore.new(Gtk.FileFilter)
    file_filter = Gtk.FileFilter()
    file_filter.set_name("Font files")
    for pattern in ("*.ttf", "*.otf", "*.ttc", "*.woff", "*.woff2"):
        file_filter.add_pattern(pattern)
    filters.append(file_filter)
    return filters
