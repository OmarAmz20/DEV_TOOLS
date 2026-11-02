"""Appearance page: preset looks, tokens, structure and live preview."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import constants, desktop, palette, sessiond, themes  # noqa: E402
from ..util import read_json, write_json  # noqa: E402
from . import common  # noqa: E402


class ColorDot(Gtk.DrawingArea):
    def __init__(self, color: str, size: int = 16) -> None:
        super().__init__()
        self.color = color
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(self._draw)

    def set_color(self, color: str) -> None:
        self.color = color
        self.queue_draw()

    def _draw(self, _area, cr, width, height):
        rgba = Gdk.RGBA()
        rgba.parse(self.color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        radius = min(width, height) / 2
        cr.arc(width / 2, height / 2, radius - 1, 0, 6.28318)
        cr.fill()


class ThemeCard(Gtk.Box):
    def __init__(self, preset: dict, on_click) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.preset = preset
        self.add_css_class("theme-card")
        self.add_css_class("preset-" + preset.get("id", "wallpaper"))
        self.set_size_request(166, 92)
        self.set_valign(Gtk.Align.START)
        dark = preset.get("dark") or {}
        provider = Gtk.CssProvider()
        provider.load_from_data(
            (
                ".theme-card { background-image: linear-gradient(140deg, "
                f"{dark.get('bg', '#101018')} 0%, {dark.get('surface', '#1a1a26')} 58%, "
                f"{dark.get('accent', '#7aa2ff')} 145%); }}"
            ).encode(),
            -1,
        )
        Gtk.StyleContext.add_provider(self.get_style_context(), provider, 800)
        title = Gtk.Label(label=preset.get("name", "Theme"), xalign=0)
        title.add_css_class("theme-name")
        title.set_ellipsize(3)
        description = Gtk.Label(label=preset.get("description", ""), xalign=0)
        description.add_css_class("theme-description")
        description.set_ellipsize(3)
        description.set_max_width_chars(24)
        self.append(title)
        self.append(description)
        dots = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        dots.set_margin_top(5)
        dark = preset.get("dark") or {}
        light = preset.get("light") or {}
        for color in (dark.get("bg", "#111116"), dark.get("accent", "#7aa2ff"),
                      light.get("bg", "#f4f6fb")):
            dots.append(ColorDot(color, 13))
        self.append(dots)
        gesture = Gtk.GestureClick()
        gesture.connect("released", lambda *_a: on_click(preset))
        self.add_controller(gesture)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")


class AppearancePage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.config = app.config
        self.cards: list[ThemeCard] = []
        self._preview_provider = None
        self._preview_theme = None
        self._debounce = 0
        self._build()
        self.refresh()

    # --- construction -------------------------------------------------------------

    def _build(self) -> None:
        apply_button = common.button("Apply look", icon="emblem-ok-symbolic", css="suggested-action",
                                     on_click=self.apply_look)
        match_button = common.button("", icon="applications-graphics-symbolic",
                                     tooltip="Use the current wallpaper's colours", on_click=self.use_wallpaper)
        custom_button = common.button("", icon="document-new-symbolic",
                                      tooltip="Save a custom look", on_click=self.open_custom_dialog)
        restore_button = common.button("", icon="edit-undo-symbolic", tooltip="Restore the previous look",
                                       on_click=self.confirm_restore)
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu = Gio_menu()
        menu_button.set_menu_model(menu)
        outer, content = common.page_scaffold(
            "Appearance", "Twenty-four curated looks, accessible tokens and a live preview.",
            actions=[menu_button, restore_button, custom_button, match_button, apply_button],
        )
        self.append(outer)
        self.content = content

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        top.set_homogeneous(False)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        left.set_hexpand(True)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right.set_size_request(330, -1)
        top.append(left)
        top.append(right)
        content.append(top)

        controls = common.card()
        title = Gtk.Label(label="Look controls", xalign=0)
        title.add_css_class("section-title")
        controls.append(title)
        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.mode_dropdown = common.dropdown([("auto", "Auto"), ("light", "Light only"), ("dark", "Dark only")],
                                              self.config.get("appearance.mode", "auto"))
        self.mode_dropdown.set_hexpand(True)
        self.mode_dropdown.connect("notify::selected", lambda *_a: self._changed())
        mode_label = Gtk.Label(label="Appearance mode", xalign=0)
        mode_label.add_css_class("setting-title")
        mode_row.append(mode_label)
        mode_row.append(self.mode_dropdown)
        controls.append(mode_row)

        structure_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.structure_dropdown = common.dropdown([(item, item.title()) for item in constants.STRUCTURES],
                                                   self.config.get("appearance.structure", "rounded"))
        self.structure_dropdown.set_hexpand(True)
        self.structure_dropdown.connect("notify::selected", lambda *_a: self._changed())
        structure_label = Gtk.Label(label="Window structure", xalign=0)
        structure_label.add_css_class("setting-title")
        structure_row.append(structure_label)
        structure_row.append(self.structure_dropdown)
        controls.append(structure_row)

        self.radius = self._scale_control(controls, "Corner radius", 0, 28,
                                          self.config.get("appearance.radius", 14), 1)
        self.border = self._scale_control(controls, "Border width", 0, 4,
                                          self.config.get("appearance.border_width", 1), 1)
        self.transparency = self._scale_control(controls, "Window transparency", 0, 0.45,
                                                self.config.get("appearance.transparency", 0.0), 0.01)
        switch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.shadow_switch = common.switch(bool(self.config.get("appearance.shadow", True)))
        self.shadow_switch.connect("notify::active", lambda *_a: self._changed())
        shadow_label = Gtk.Label(label="Soft shadows", xalign=0)
        shadow_label.add_css_class("setting-title")
        shadow_label.set_hexpand(True)
        switch_row.append(shadow_label)
        switch_row.append(self.shadow_switch)
        controls.append(switch_row)

        accent_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.accent_button = common.color_button(self.config.get("appearance.accent_override", "") or "#7aa2ff")
        self.accent_button.connect("notify::rgba", lambda *_a: self._changed())
        accent_label = Gtk.Label(label="Accent override", xalign=0)
        accent_label.add_css_class("setting-title")
        accent_label.set_hexpand(True)
        accent_row.append(accent_label)
        accent_row.append(self.accent_button)
        clear_accent = Gtk.Button(label="Use preset")
        clear_accent.connect("clicked", self._clear_accent)
        accent_row.append(clear_accent)
        controls.append(accent_row)
        left.append(controls)

        apply_options = common.card()
        apply_title = Gtk.Label(label="Apply to", xalign=0)
        apply_title.add_css_class("section-title")
        apply_options.append(apply_title)
        self.apply_theme_switch = common.switch(bool(self.config.get("appearance.apply_theme", True)))
        self.apply_theme_switch.connect("notify::active", lambda *_a: self._changed())
        apply_options.append(common.row("GTK applications", "Themes and colours for GTK 3/4 apps",
                                        trailing=self.apply_theme_switch))
        terminal_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.terminal_dropdown = common.dropdown(
            [(item, item.title()) for item in constants.TERMINALS],
            self.config.get("appearance.terminal", "auto"),
        )
        self.terminal_dropdown.connect("notify::selected", lambda *_a: self._changed())
        term_label = Gtk.Label(label="Terminal", xalign=0)
        term_label.add_css_class("setting-title")
        term_label.set_hexpand(True)
        terminal_row.append(term_label)
        terminal_row.append(self.terminal_dropdown)
        apply_options.append(terminal_row)
        self.icons_switch = common.switch(bool(self.config.get("appearance.apply_icons", False)))
        self.icons_switch.connect("notify::active", lambda *_a: self._changed())
        apply_options.append(common.row("Icon theme", "Use a selected icon pack", trailing=self.icons_switch))
        self.cursor_switch = common.switch(bool(self.config.get("appearance.apply_cursor", False)))
        self.cursor_switch.connect("notify::active", lambda *_a: self._changed())
        apply_options.append(common.row("Cursor theme", "Use a selected cursor pack", trailing=self.cursor_switch))
        left.append(apply_options)

        schedule = common.card()
        schedule.append(common.section("Light / dark schedule", "The helper switches the applied look at the times you choose."))
        self.schedule_switch = common.switch(bool(self.config.get("appearance.dark_schedule.enabled", False)))
        self.schedule_switch.connect("notify::active", lambda *_a: self._save_schedule())
        schedule.append(common.row("Enable schedule", "Uses the auto appearance mode", trailing=self.schedule_switch))
        self.light_start = common.labelled_entry(
            str(self.config.get("appearance.dark_schedule.light_start", "07:00")), "07:00")
        self.light_start.connect("changed", lambda *_a: self._schedule_changed())
        schedule.append(common.row("Light starts", "24-hour time", trailing=self.light_start))
        self.dark_start = common.labelled_entry(
            str(self.config.get("appearance.dark_schedule.dark_start", "19:00")), "19:00")
        self.dark_start.connect("changed", lambda *_a: self._schedule_changed())
        schedule.append(common.row("Dark starts", "24-hour time", trailing=self.dark_start))
        left.append(schedule)

        right.append(common.section("Live preview", "Real controls, real tokens"))
        self.preview_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.preview_root.add_css_class("hp-root")
        self._preview_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self._preview_provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        preview_title = Gtk.Label(label="1337-Customizer", xalign=0)
        preview_title.add_css_class("hp-title")
        preview_subtitle = Gtk.Label(label="A surface that follows your tokens", xalign=0)
        preview_subtitle.add_css_class("hp-muted")
        self.preview_root.append(preview_title)
        self.preview_root.append(preview_subtitle)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.add_css_class("hp-card")
        card.append(Gtk.Label(label="Card title", xalign=0))
        secondary_label = Gtk.Label(label="Secondary information sits here.", xalign=0)
        secondary_label.add_css_class("hp-muted")
        card.append(secondary_label)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        primary = Gtk.Button(label="Primary")
        primary.add_css_class("hp-button")
        primary.add_css_class("primary")
        secondary = Gtk.Button(label="Secondary")
        secondary.add_css_class("hp-button")
        buttons.append(primary)
        buttons.append(secondary)
        card.append(buttons)
        entry = Gtk.Entry()
        entry.set_text("Search wallpapers…")
        entry.add_css_class("hp-entry")
        card.append(entry)
        progress = Gtk.ProgressBar()
        progress.set_fraction(0.64)
        progress.add_css_class("hp-progress")
        card.append(progress)
        self.preview_root.append(card)
        right.append(self.preview_root)
        self.contrast_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right.append(common.section("Contrast"))
        right.append(self.contrast_box)
        self.swatch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        right.append(common.section("Palette"))
        right.append(self.swatch_box)

        themes_section = common.section(
            "Curated looks", "Pick a preset, then tune the structure and tokens.",
            trailing=common.button("Wallpaper colours", icon="applications-graphics-symbolic",
                                   on_click=self.use_wallpaper),
        )
        content.append(themes_section)
        self.grid = Gtk.FlowBox()
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_max_children_per_line(6)
        self.grid.set_min_children_per_line(2)
        self.grid.set_column_spacing(8)
        self.grid.set_row_spacing(8)
        self.grid.set_valign(Gtk.Align.START)
        content.append(self.grid)

    def _scale_control(self, parent: Gtk.Box, title: str, minimum: float, maximum: float,
                       value: float, step: float) -> Gtk.Scale:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("setting-title")
        label.set_hexpand(True)
        widget = common.scale(float(value), minimum, maximum, step)
        widget.set_size_request(220, -1)
        widget.connect("value-changed", lambda *_a: self._changed())
        row.append(label)
        row.append(widget)
        parent.append(row)
        return widget

    # --- state --------------------------------------------------------------------

    def _mode(self) -> str:
        return common.selected_value(self.mode_dropdown, [("auto", "Auto"), ("light", "Light only"),
                                                          ("dark", "Dark only")], "auto")

    def _structure(self) -> str:
        return common.selected_value(self.structure_dropdown,
                                     [(item, item.title()) for item in constants.STRUCTURES], "rounded")

    def _schedule_changed(self) -> None:
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(400, self._save_schedule)

    def _save_schedule(self) -> bool:
        self._debounce = 0
        values = {
            "enabled": self.schedule_switch.get_active(),
            "light_start": self.light_start.get_text().strip() or "07:00",
            "dark_start": self.dark_start.get_text().strip() or "19:00",
        }
        self.config.set("appearance.dark_schedule", values, save=False)
        self.config.save()
        try:
            if sessiond.autostart_needed(self.config):
                sessiond.start()
            elif sessiond.running():
                sessiond.stop()
        except Exception:
            pass
        return False

    def _terminal(self) -> str:
        return common.selected_value(self.terminal_dropdown,
                                     [(item, item.title()) for item in constants.TERMINALS], "auto")

    def _accent(self) -> str:
        rgba = self.accent_button.get_rgba()
        if rgba is None:
            return ""
        return "#%02x%02x%02x" % (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))

    def _clear_accent(self) -> None:
        rgba = Gdk.RGBA()
        rgba.parse("#7aa2ff")
        self.accent_button.set_rgba(rgba)
        self._changed()

    def _update_config(self) -> None:
        appearance = self.config.data.setdefault("appearance", {})
        appearance["mode"] = self._mode()
        appearance["structure"] = self._structure()
        appearance["radius"] = int(self.radius.get_value())
        appearance["border_width"] = int(self.border.get_value())
        appearance["transparency"] = round(float(self.transparency.get_value()), 2)
        appearance["shadow"] = self.shadow_switch.get_active()
        accent = self._accent()
        appearance["accent_override"] = accent if self._accent_changed() else ""
        appearance["apply_theme"] = self.apply_theme_switch.get_active()
        appearance["terminal"] = self._terminal()
        appearance["apply_icons"] = self.icons_switch.get_active()
        appearance["apply_cursor"] = self.cursor_switch.get_active()

    def _accent_changed(self) -> bool:
        rgba = self.accent_button.get_rgba()
        if rgba is None:
            return False
        return not (abs(rgba.red - 0x7a / 255) < 0.01 and abs(rgba.green - 0xa2 / 255) < 0.01
                    and abs(rgba.blue - 0xff / 255) < 0.01)

    def _changed(self) -> None:
        if self._debounce:
            GLib.source_remove(self._debounce)
        self._debounce = GLib.timeout_add(120, self._refresh_preview)

    def selected_theme_id(self) -> str:
        return str(self.config.get("appearance.theme", "midnight-aurora"))

    def _resolved(self) -> dict:
        self._update_config()
        return themes.resolve_theme(
            self.selected_theme_id(),
            mode=self._mode(),
            schedule=self.config.get("appearance.dark_schedule"),
            wallpaper_path=themes.wallpaper_path_from_state(),
            overrides=self.config.get("appearance", {}),
        )

    def _refresh_preview(self) -> bool:
        self._debounce = 0
        theme = self._resolved()
        self._preview_theme = theme
        if self._preview_provider is not None:
            self._preview_provider.load_from_data(themes.generate_preview_css(theme).encode(), -1)
        for label in list(self.contrast_box):
            self.contrast_box.remove(label)
        for name, background, ratio in themes.contrast_report(theme):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            label = Gtk.Label(label=name, xalign=0)
            label.set_hexpand(True)
            label.add_css_class("dim-label")
            value = Gtk.Label(label=f"{ratio:.1f}:1")
            value.add_css_class("badge-ok" if ratio >= 4.5 else "badge-warn")
            row.append(label)
            row.append(value)
            self.contrast_box.append(row)
        for child in list(self.swatch_box):
            self.swatch_box.remove(child)
        for key in ("bg", "surface", "surface2", "accent", "text", "text_dim"):
            self.swatch_box.append(ColorDot(theme["colors"][key], 22))
        self._refresh_card_selection(theme.get("id", self.selected_theme_id()))
        return False

    def _refresh_card_selection(self, theme_id: str) -> None:
        for card in self.cards:
            card.set_selected(card.preset.get("id") == theme_id)

    # --- presets ------------------------------------------------------------------

    def refresh(self) -> None:
        for child in list(self.grid):
            self.grid.remove(child)
        self.cards = []
        presets = themes.all_presets()
        presets = sorted(presets, key=lambda item: (item.get("name", "").casefold()))
        wallpaper_card = {
            "id": themes.WALLPAPER_PRESET,
            "name": "Wallpaper colours",
            "description": "Sample a light and dark palette from the current picture.",
            "dark": {"bg": "#080a12", "accent": "#7aa2ff"},
            "light": {"bg": "#f8f9fc"},
            "structure": "rounded",
        }
        for preset in [wallpaper_card] + presets:
            card = ThemeCard(preset, self.select_preset)
            self.cards.append(card)
            self.grid.append(card)
        self._refresh_preview()
        self._update_apply_state()

    def select_preset(self, preset: dict) -> None:
        theme_id = preset.get("id", "midnight-aurora")
        self.config.set("appearance.theme", theme_id, save=False)
        if preset.get("structure"):
            self.config.set("appearance.structure", preset["structure"], save=False)
            self._select_value(self.structure_dropdown, constants.STRUCTURES, preset["structure"])
        self.config.save()
        self._refresh_preview()

    def _select_value(self, dropdown: Gtk.DropDown, values: tuple[str, ...], value: str) -> None:
        with __import__("contextlib").suppress(Exception):
            dropdown.set_selected(values.index(value))

    def _update_apply_state(self) -> None:
        pass

    def use_wallpaper(self) -> None:
        self.config.set("appearance.theme", themes.WALLPAPER_PRESET)
        self.config.save()
        self._refresh_preview()
        self.app.toast("Using colours from the current wallpaper")

    def apply_look(self) -> None:
        self._update_config()
        self.config.save()
        self.app.toast("Applying look…")

        def worker():
            try:
                theme, report = desktop.apply_theme_from_config(self.config)
            except Exception as error:
                theme, report = None, {"ok": False, "warnings": [str(error)]}
            GLib.idle_add(self._applied, theme, report)

        threading.Thread(target=worker, daemon=True).start()

    def _applied(self, theme, report) -> bool:
        if report.get("ok"):
            self.app.toast(f"Applied {theme['name']} · {theme['variant']}")
        else:
            self.app.toast("Theme warning: " + "; ".join(report.get("warnings", []))[:240])
        self._refresh_preview()
        return False

    def confirm_restore(self) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Restore the previous look?",
            body="1337-Customizer will remove its theme files, terminal includes and restore the desktop settings it changed.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("restore", "Restore")
        dialog.set_response_appearance("restore", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", lambda _d, response: self._do_restore() if response == "restore" else None)
        dialog.present()

    def _do_restore(self) -> None:
        def worker():
            try:
                result = desktop.restore_theme()
            except Exception as error:
                result = {"error": str(error)}
            GLib.idle_add(self._restored, result)

        threading.Thread(target=worker, daemon=True).start()

    def _restored(self, result) -> bool:
        self.app.toast("Previous look restored" if not result.get("error") else f"Restore warning: {result['error']}")
        self._refresh_preview()
        return False

    def open_custom_dialog(self) -> None:
        dialog = CustomThemeDialog(self)
        dialog.present()

    # --- import / export ----------------------------------------------------------

    def export_theme(self) -> None:
        theme = self._resolved()
        dialog = Gtk.FileDialog()
        dialog.set_title("Export 1337-Customizer theme")
        dialog.set_initial_name(f"{theme['name'].replace(' ', '-').lower()}.json")
        dialog.save(self.get_root(), None, lambda d, result: self._export_done(theme, d, result))

    def _export_done(self, theme, dialog, result) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        if not file or not file.get_path():
            return
        write_json(file.get_path(), themes.export_theme(theme))
        self.app.toast("Theme exported")

    def import_theme(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Import a 1337-Customizer theme")
        dialog.open(self.get_root(), None, self._import_done)

    def _import_done(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path() if file else None
        if not path:
            return
        preset = themes.import_theme(read_json(path, {}))
        if not preset:
            self.app.toast("That file is not a 1337-Customizer theme")
            return
        theme_id = themes.save_custom_theme(preset)
        self.config.set("appearance.theme", theme_id)
        self.config.save()
        self.refresh()
        self.app.toast(f"Imported {preset['name']}")


def Gio_menu():
    from gi.repository import Gio, GLib

    menu = Gio.Menu()
    menu.append("Export theme…", "app.export-theme")
    menu.append("Import theme…", "app.import-theme")
    menu.append("Restore previous look", "app.restore-look")
    return menu


class CustomThemeDialog(Adw.Window):
    def __init__(self, page: AppearancePage):
        super().__init__(transient_for=page.get_root(), modal=True)
        self.page = page
        self.set_default_size(560, 520)
        self.set_title("Custom look")
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        header.pack_end(save)
        toolbar.add_top_bar(header)
        self.name = Gtk.Entry()
        self.name.set_text("My 1337-Customizer look")
        self.name.set_placeholder_text("Look name")
        self.structure = common.dropdown([(item, item.title()) for item in constants.STRUCTURES], "rounded")
        self.light_bg = common.color_button("#f4f6fb")
        self.light_surface = common.color_button("#ffffff")
        self.light_accent = common.color_button("#4c6fff")
        self.dark_bg = common.color_button("#0b0d17")
        self.dark_surface = common.color_button("#151829")
        self.dark_accent = common.color_button("#7aa2ff")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.append(common.row("Look name", "Saved in ~/.config/1337-customizer/themes", trailing=self.name))
        content.append(common.row("Structure", trailing=self.structure))
        content.append(self._section("Light seeds", self.light_bg, self.light_surface, self.light_accent))
        content.append(self._section("Dark seeds", self.dark_bg, self.dark_surface, self.dark_accent))
        toolbar.set_content(content)
        self.set_content(toolbar)
        self.present()

    def _section(self, title: str, bg, surface, accent) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("section-title")
        box.append(label)
        for name, widget in (("Background", bg), ("Surface", surface), ("Accent", accent)):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            label = Gtk.Label(label=name, xalign=0)
            label.set_hexpand(True)
            row.append(label)
            row.append(widget)
            box.append(row)
        return box

    @staticmethod
    def _hex(color_button) -> str:
        rgba = color_button.get_rgba()
        return "#%02x%02x%02x" % (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))

    def _save(self, *_args) -> None:
        preset = themes.theme_from_seeds(
            self.name.get_text().strip() or "My 1337-Customizer look",
            light_bg=self._hex(self.light_bg),
            light_surface=self._hex(self.light_surface),
            light_accent=self._hex(self.light_accent),
            dark_bg=self._hex(self.dark_bg),
            dark_surface=self._hex(self.dark_surface),
            dark_accent=self._hex(self.dark_accent),
            structure=common.selected_value(self.structure, [(item, item.title()) for item in constants.STRUCTURES], "rounded"),
            description="A personal 1337-Customizer look",
        )
        theme_id = themes.save_custom_theme(preset)
        self.page.config.set("appearance.theme", theme_id)
        self.page.config.save()
        self.page.refresh()
        self.page.app.toast(f"Saved {preset['name']}")
        self.close()
