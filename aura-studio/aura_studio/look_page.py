"""Look & Feel: colour mode, desktop options, fonts, icons and slideshow."""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gtk, Pango  # noqa: E402

from . import palette, system, widgets  # noqa: E402

SORT_STYLES = list(palette.STYLES)
SLIDE_CHOICES = [
    (0, "Off"),
    (15, "Every 15 minutes"),
    (30, "Every 30 minutes"),
    (60, "Every hour"),
    (180, "Every 3 hours"),
    (360, "Every 6 hours"),
    (720, "Every 12 hours"),
    (1440, "Once a day"),
]
DESKTOP_KEYS = ("icon_theme", "cursor_theme", "font", "mono_font", "text_scale")


class LookPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = window
        self.updating = False
        self.auto_rows = []

        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=820, tightening_threshold=640)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                            margin_top=26, margin_bottom=36, margin_start=22, margin_end=22)
        clamp.set_child(self.page)
        scroller.set_child(clamp)
        self.append(scroller)

        self.page.append(widgets.page_header(
            "Look & Feel",
            "The colours follow your wallpaper. Shape everything else here."))
        self.build_status()
        self.build_appearance()
        self.build_targets()
        self.build_desktop()
        self.build_slideshow()
        self.build_apply()
        self.sync_from_config()

    # --- sections ------------------------------------------------------------------

    def build_status(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("aura-card")
        top = Gtk.Box(spacing=10)
        self.status_title = Gtk.Label(xalign=0, label="Ready when you are", hexpand=True)
        self.status_title.add_css_class("aura-section-title")
        top.append(self.status_title)
        self.status_badge = Gtk.Label(label="NOT APPLIED YET")
        self.status_badge.add_css_class("aura-badge")
        top.append(self.status_badge)
        card.append(top)
        self.status_line = Gtk.Label(xalign=0, wrap=True)
        self.status_line.add_css_class("aura-hint")
        card.append(self.status_line)
        self.status_swatches = widgets.SwatchRow(size=20, spacing=7)
        card.append(self.status_swatches)
        self.page.append(card)

    def build_appearance(self):
        group = Adw.PreferencesGroup(title="Appearance",
                                     description="Light, dark, or let the clock decide.")
        self.mode_row = Adw.ActionRow(title="Colour mode",
                                      subtitle="Auto is light by day and dark at night.")
        modes = Gtk.Box(css_classes=["linked"], valign=Gtk.Align.CENTER)
        self.mode_buttons = {}
        first = None
        for mode, label in (("light", "Light"), ("dark", "Dark"), ("auto", "Auto")):
            button = Gtk.ToggleButton(label=label)
            button.set_group(first)
            first = first or button
            button.connect("toggled", self.on_mode, mode)
            modes.append(button)
            self.mode_buttons[mode] = button
        self.mode_row.add_suffix(modes)
        group.add(self.mode_row)

        self.light_row = Adw.SpinRow.new(
            Gtk.Adjustment(value=7, lower=0, upper=23, step_increment=1), 1, 0)
        self.light_row.set_title("Light from")
        self.light_row.set_subtitle("Hour of the day (24-hour clock)")
        self.light_row.connect("notify::value", self.on_times)
        group.add(self.light_row)
        self.auto_rows.append(self.light_row)

        self.dark_row = Adw.SpinRow.new(
            Gtk.Adjustment(value=19, lower=0, upper=23, step_increment=1), 1, 0)
        self.dark_row.set_title("Dark from")
        self.dark_row.set_subtitle("Hour of the day (24-hour clock)")
        self.dark_row.connect("notify::value", self.on_times)
        group.add(self.dark_row)
        self.auto_rows.append(self.dark_row)

        self.style_row = Adw.ComboRow(
            title="Palette style",
            model=Gtk.StringList.new([palette.STYLE_LABELS[s] for s in SORT_STYLES]))
        self.style_row.connect("notify::selected", self.on_style)
        group.add(self.style_row)

        self.accent_row = Adw.ActionRow(title="Accent",
                                        subtitle="A custom accent overrides the picture's accent.")
        suffix = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        self.accent_button = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(with_alpha=False, title="Choose an accent colour"))
        self.accent_button.connect("notify::rgba", self.on_accent)
        suffix.append(self.accent_button)
        self.accent_reset = Gtk.Button(label="Use image", css_classes=["flat"])
        self.accent_reset.connect("clicked", lambda _b: self.win.set_accent(None))
        suffix.append(self.accent_reset)
        self.accent_row.add_suffix(suffix)
        group.add(self.accent_row)
        self.page.append(group)

    def build_targets(self):
        group = Adw.PreferencesGroup(title="Where the colours go")
        self.gtk_switch = self._switch_row(
            group, "GTK apps", "Theme, window backgrounds and controls for GTK 3 and 4 apps.",
            "recolour_gtk")
        targets = system.terminal_targets()
        self.terminal_switch = self._switch_row(
            group, "Terminal colours",
            "GNOME Terminal profile and Kitty theme." if targets else "No supported terminal found.",
            "terminal")
        if not targets:
            self.terminal_switch.set_sensitive(False)
        self.lock_switch = self._switch_row(
            group, "Lock screen",
            "Uses the wallpaper on the GNOME lock screen."
            if system.lock_screen_available() else
            "Only available on a GNOME session.",
            "lock_screen")
        if not system.lock_screen_available():
            self.lock_switch.set_sensitive(False)
        self.glass_switch = self._switch_row(
            group, "See-through windows",
            "Let the wallpaper show through app windows. Menus stay solid.", "glass")
        self.page.append(group)

    def _switch_row(self, group, title, subtitle, key):
        row = Adw.SwitchRow(title=title, subtitle=subtitle)
        row.set_active(bool(self.win.config.get(key)))
        row.connect("notify::active", self.on_switch, key)
        group.add(row)
        return row

    def build_desktop(self):
        group = Adw.PreferencesGroup(
            title="Desktop details",
            description="Optional. These are applied together with the colours.")
        preferences = system.current_preferences()

        self.icons_combo, self.icon_values = self._theme_combo(
            group, "Icon theme", system.icon_themes(), preferences["icon_theme"], "icon_theme")
        self.cursors_combo, self.cursor_values = self._theme_combo(
            group, "Cursor theme", system.cursor_themes(), preferences["cursor_theme"], "cursor_theme")

        self.font_row, self.font_button = self._font_row(
            group, "Interface font", "font", preferences["font"])
        self.mono_row, self.mono_button = self._font_row(
            group, "Monospace font", "mono_font", preferences["mono_font"])

        self.scale_row = Adw.ActionRow(title="Text size",
                                       subtitle="Scales text in GTK apps")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.8, 1.5, 0.05)
        self.scale.set_size_request(170, -1)
        self.scale.set_draw_value(False)
        self.scale.add_mark(1.0, Gtk.PositionType.BOTTOM, None)
        self.scale.set_valign(Gtk.Align.CENTER)
        self.scale.connect("value-changed", self.on_scale)
        self.scale_label = Gtk.Label(label="100%", width_chars=5, xalign=1)
        self.scale_label.add_css_class("aura-hint")
        box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        box.append(self.scale)
        box.append(self.scale_label)
        self.scale_row.add_suffix(box)
        group.add(self.scale_row)
        self.page.append(group)

    def _theme_combo(self, group, title, names, current, key):
        values = [None, *names]
        labels = [f"System — {current or 'default'}", *names]
        if self.win.config.get(key) and self.win.config[key] not in names:
            values.append(self.win.config[key])
            labels.append(self.win.config[key])
        combo = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
        config_value = self.win.config.get(key)
        if config_value in values and config_value is not None:
            combo.set_selected(values.index(config_value))
        else:
            combo.set_selected(0)
        combo.connect("notify::selected", self.on_theme_combo, key, values)
        group.add(combo)
        return combo, values

    def _font_row(self, group, title, key, current):
        row = Adw.ActionRow(title=title,
                            subtitle="System default" if not self.win.config.get(key) else "Custom")
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        button = Gtk.FontDialogButton(dialog=Gtk.FontDialog(), level=Gtk.FontLevel.FONT)
        button.set_use_font(True)
        button.set_use_size(True)
        button.set_font_desc(Pango.FontDescription.from_string(
            self.win.config.get(key) or current or "Adwaita Sans 11"))
        button.connect("notify::font-desc", self.on_font, key, row)
        box.append(button)
        reset = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Use the system font",
                           css_classes=["flat"])
        reset.connect("clicked", self.on_reset_font, key, row, button)
        box.append(reset)
        row.add_suffix(box)
        group.add(row)
        return row, button

    def build_slideshow(self):
        group = Adw.PreferencesGroup(
            title="Slideshow",
            description="Runs while Aura is open. A new wallpaper is picked from your folder.")
        self.slide_row = Adw.ComboRow(
            title="Change wallpaper",
            model=Gtk.StringList.new([label for _minutes, label in SLIDE_CHOICES]))
        self.slide_row.connect("notify::selected", self.on_slide_choice)
        group.add(self.slide_row)

        shuffle_row = Adw.ActionRow(title="Shuffle now",
                                    subtitle="Pick a random wallpaper and apply it immediately.")
        shuffle = Gtk.Button(label="Shuffle", valign=Gtk.Align.CENTER)
        shuffle.add_css_class("flat")
        shuffle.connect("clicked", lambda _b: self.win.shuffle_now())
        shuffle_row.add_suffix(shuffle)
        shuffle_row.set_activatable_widget(shuffle)
        group.add(shuffle_row)
        self.page.append(group)

    def build_apply(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("aura-card")
        label = Gtk.Label(xalign=0, wrap=True,
                          label="Apply the colours and every desktop option above. "
                                "Nothing changes on your desktop until you press the button.")
        label.add_css_class("aura-hint")
        card.append(label)
        row = Gtk.Box(spacing=8)
        apply = widgets.button("Apply this look", "object-select-symbolic")
        apply.add_css_class("suggested-action")
        apply.add_css_class("pill")
        apply.connect("clicked", lambda _b: self.win.apply_look())
        row.append(apply)
        restore = Gtk.Button(label="Restore original look")
        restore.add_css_class("flat")
        restore.connect("clicked", lambda _b: self.win.ask_restore())
        row.append(restore)
        card.append(row)
        self.page.append(card)

    # --- handlers ------------------------------------------------------------------

    def on_mode(self, button, mode):
        if self.updating or not button.get_active():
            return
        self.win.save_config(mode=mode)
        self.update_mode_rows()
        self.win.mode_changed()

    def update_mode_rows(self):
        for row in self.auto_rows:
            row.set_visible(self.win.config["mode"] == "auto")
        mode = self.win.config["mode"]
        if mode == "auto":
            self.mode_row.set_subtitle(
                f"Light from {self.win.config['light_from']:02d}:00, "
                f"dark from {self.win.config['dark_from']:02d}:00.")
        else:
            self.mode_row.set_subtitle(f"Always {'dark' if mode == 'dark' else 'light'}.")

    def on_times(self, row, _param):
        if self.updating:
            return
        hours = int(round(row.get_value()))
        key = "light_from" if row is self.light_row else "dark_from"
        self.win.save_config(**{key: hours})
        self.update_mode_rows()
        self.win.mode_changed()

    def on_style(self, combo, _param):
        if self.updating:
            return
        index = combo.get_selected()
        if 0 <= index < len(SORT_STYLES):
            self.win.set_style(SORT_STYLES[index])

    def on_accent(self, button, _param):
        if self.updating:
            return
        self.win.set_accent(widgets.colour_button_hex(button))

    def on_switch(self, row, _param, key):
        if self.updating:
            return
        self.win.save_config(**{key: row.get_active()})

    def on_theme_combo(self, combo, _param, key, values):
        if self.updating:
            return
        index = combo.get_selected()
        value = values[index] if 0 <= index < len(values) else None
        self.win.save_config(**{key: value})
        self.refresh_status()

    def on_font(self, button, _param, key, row):
        if self.updating:
            return
        desc = button.get_font_desc()
        if desc is None:
            return
        text = desc.to_string()
        self.win.save_config(**{key: text})
        row.set_subtitle("Custom")

    def on_reset_font(self, _button, key, row, font_button):
        self.win.save_config(**{key: None})
        preferences = system.current_preferences()
        value = preferences["font"] if key == "font" else preferences["mono_font"]
        self.updating = True
        try:
            font_button.set_font_desc(Pango.FontDescription.from_string(value or "Adwaita Sans 11"))
        finally:
            self.updating = False
        row.set_subtitle("System default")

    def on_scale(self, scale):
        value = round(scale.get_value(), 2)
        self.scale_label.set_label(f"{value * 100:.0f}%")
        if self.updating:
            return
        self.win.save_config(text_scale=value)

    def on_slide_choice(self, combo, _param):
        if self.updating:
            return
        index = combo.get_selected()
        if 0 <= index < len(SLIDE_CHOICES):
            minutes = SLIDE_CHOICES[index][0]
            self.win.save_config(slide_minutes=minutes)
            self.win.slideshow_changed()

    # --- syncing -------------------------------------------------------------------

    def sync_from_config(self):
        self.updating = True
        try:
            config = self.win.config
            for mode, button in self.mode_buttons.items():
                button.set_active(config["mode"] == mode)
            self.light_row.set_value(config["light_from"])
            self.dark_row.set_value(config["dark_from"])
            self.update_mode_rows()
            if config["style"] in SORT_STYLES:
                self.style_row.set_selected(SORT_STYLES.index(config["style"]))
            self.style_row.set_subtitle(palette.STYLE_DESCRIPTIONS.get(config["style"], ""))

            preferences = system.current_preferences()
            accent = config.get("accent") or self.win.accent_from_preview() or "#888888"
            widgets.set_colour_button(self.accent_button, accent)
            self.accent_reset.set_sensitive(bool(config.get("accent")))
            if config.get("accent"):
                self.accent_row.set_subtitle(f"Custom accent {config['accent'].upper()}.")
            else:
                self.accent_row.set_subtitle("The picture's most vivid colour.")

            self.gtk_switch.set_active(bool(config["recolour_gtk"]))
            self.terminal_switch.set_active(bool(config["terminal"]))
            self.lock_switch.set_active(bool(config["lock_screen"]))
            self.glass_switch.set_active(bool(config["glass"]))

            for combo, values, key in (
                    (self.icons_combo, self.icon_values, "icon_theme"),
                    (self.cursors_combo, self.cursor_values, "cursor_theme")):
                value = config.get(key)
                combo.set_selected(values.index(value) if value in values else 0)

            self.font_button.set_font_desc(Pango.FontDescription.from_string(
                config.get("font") or preferences["font"] or "Adwaita Sans 11"))
            self.mono_button.set_font_desc(Pango.FontDescription.from_string(
                config.get("mono_font") or preferences["mono_font"] or "Adwaita Mono 11"))
            self.font_row.set_subtitle("Custom" if config.get("font") else "System default")
            self.mono_row.set_subtitle("Custom" if config.get("mono_font") else "System default")

            scale = config.get("text_scale") or preferences["text_scale"] or 1.0
            self.scale.set_value(float(scale))
            self.scale_label.set_label(f"{float(scale) * 100:.0f}%")

            minutes = config.get("slide_minutes", 0)
            values = [value for value, _label in SLIDE_CHOICES]
            self.slide_row.set_selected(values.index(minutes) if minutes in values else 0)
        finally:
            self.updating = False
        self.refresh_status()

    def refresh_status(self):
        state = self.win.state or {}
        palette_value = state.get("palette") if state.get("palette") else self.win.preview_palette
        mode = state.get("mode") or self.win.effective_mode()
        if palette_value:
            p = palette_value.get("dark" if mode == "dark" else "light", {})
            self.status_swatches.set_palette(p)
        else:
            self.status_swatches.set_palette({})

        applied = bool(state.get("palette"))
        if applied:
            source = state.get("palette_source") or state.get("wallpaper") or "an image"
            self.status_title.set_label("Look applied")
            self.status_badge.set_label("APPLIED")
            self.status_badge.remove_css_class("current")
            self.status_badge.add_css_class("current")
            self.status_line.set_label(
                f"{os.path.basename(source)} · {mode} · "
                f"{palette.STYLE_LABELS.get(state.get('style', 'balanced'), 'Balanced')} · "
                f"wallpaper via {system.backend_label()} on {system.session_label()}.")
        else:
            self.status_title.set_label("Ready when you are")
            self.status_badge.set_label("NOT APPLIED YET")
            self.status_badge.remove_css_class("current")
            self.status_line.set_label(
                f"Wallpaper backend: {system.backend_label()} · session: {system.session_label()}. "
                "Apply a look to start.")
