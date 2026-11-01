"""Look & Feel: colour mode, desktop options, fonts, icons and slideshow."""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gtk, Pango  # noqa: E402

from . import palette, store, system, widgets  # noqa: E402

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
        self.build_wallpaper()
        self.build_advanced()
        self.build_session()
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
        self._accent_shown = widgets.colour_button_hex(self.accent_button)
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
            "Colours for " + ", ".join(system.terminal_labels(targets)) + "."
            if targets else "No supported terminal found.",
            "terminal")
        if not targets:
            self.terminal_switch.set_sensitive(False)
        self.terminal_rows = {}
        for target in targets:
            row = Adw.SwitchRow(
                title=store.TERMINAL_TARGET_LABELS.get(target, target),
                subtitle="Write an Aura colour profile for this terminal.")
            row.set_active(True)
            row.connect("notify::active", self.on_terminal_target, target)
            group.add(row)
            self.terminal_rows[target] = row
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
        self.opacity_row = Adw.ActionRow(
            title="Window opacity",
            subtitle="How much of the wallpaper shows through.")

        def opacity_changed(scale):
            percent = round(scale.get_value() * 100)
            self.opacity_label.set_label(f"{percent}%")
            if not self.updating:
                self.win.save_config(glass_opacity=round(scale.get_value(), 2))

        self.opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.20, 0.95, 0.05)
        self.opacity_scale.set_size_request(170, -1)
        self.opacity_scale.set_draw_value(False)
        self.opacity_scale.set_valign(Gtk.Align.CENTER)
        self.opacity_scale.connect("value-changed", opacity_changed)
        self.opacity_label = Gtk.Label(label="72%", width_chars=5, xalign=1)
        self.opacity_label.add_css_class("aura-hint")
        box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        box.append(self.opacity_scale)
        box.append(self.opacity_label)
        self.opacity_row.add_suffix(box)
        group.add(self.opacity_row)
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

        self.cursor_size_values = [None, 24, 32, 48, 64, 96, 128]
        cursor_labels = ["System default", "24 px", "32 px", "48 px", "64 px",
                         "96 px", "128 px"]
        current_size = self.win.config.get("cursor_size")
        if current_size is not None and current_size not in self.cursor_size_values:
            self.cursor_size_values.append(current_size)
            cursor_labels.append(f"{current_size} px")
        self.cursor_size_row = Adw.ComboRow(
            title="Cursor size", model=Gtk.StringList.new(cursor_labels))
        self.cursor_size_row.connect("notify::selected", self.on_cursor_size)
        group.add(self.cursor_size_row)

        self.font_row, self.font_button = self._font_row(
            group, "Interface font", "font", preferences["font"])
        self.mono_row, self.mono_button = self._font_row(
            group, "Monospace font", "mono_font", preferences["mono_font"])

        self.scale_row = Adw.ActionRow(title="Text size",
                                       subtitle="Scales text in GTK apps")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.75, 2.0, 0.05)
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

    def build_wallpaper(self):
        group = Adw.PreferencesGroup(
            title="Wallpaper",
            description="How pictures sit on the screen, and how they change over time.")
        self.backend_values = []
        backend_labels = []
        for name, label, available in system.backend_choices():
            self.backend_values.append(name)
            if name == "auto":
                backend_labels.append(f"{label} — currently {system.backend_label()}")
            elif available:
                backend_labels.append(label)
            else:
                backend_labels.append(f"{label} (not available now)")
        self.backend_row = Adw.ComboRow(
            title="Wallpaper engine",
            subtitle="Pin one backend if automatic detection picks the wrong one.",
            model=Gtk.StringList.new(backend_labels))
        self.backend_row.connect("notify::selected", self.on_backend)
        group.add(self.backend_row)

        self.wallpaper_mode_values = list(store.WALLPAPER_MODES)
        self.wallpaper_mode_row = Adw.ComboRow(
            title="Scaling",
            subtitle="Used the next time you set a wallpaper.",
            model=Gtk.StringList.new([store.WALLPAPER_MODE_LABELS[mode]
                                      for mode in self.wallpaper_mode_values]))
        self.wallpaper_mode_row.connect("notify::selected", self.on_wallpaper_mode)
        group.add(self.wallpaper_mode_row)

        self.slide_row = Adw.SpinRow.new(
            Gtk.Adjustment(value=0, lower=0, upper=10080,
                           step_increment=5, page_increment=60), 5, 0)
        self.slide_row.set_title("Change wallpaper")
        self.slide_row.set_subtitle(
            "Minutes between changes; 0 turns the slideshow off. "
            "Runs while Aura is open.")
        self.slide_row.connect("notify::value", self.on_slide_choice)
        group.add(self.slide_row)

        self.slideshow_order_values = list(store.SLIDESHOW_ORDERS)
        self.slideshow_order_row = Adw.ComboRow(
            title="Slideshow order",
            subtitle="Shuffle picks random pictures; in order walks the sorted folder.",
            model=Gtk.StringList.new([store.SLIDESHOW_ORDER_LABELS[order]
                                      for order in self.slideshow_order_values]))
        self.slideshow_order_row.connect("notify::selected", self.on_slideshow_order)
        group.add(self.slideshow_order_row)

        shuffle_row = Adw.ActionRow(title="Pick one now",
                                    subtitle="Apply a different wallpaper immediately.")
        shuffle = Gtk.Button(label="Next wallpaper", valign=Gtk.Align.CENTER)
        shuffle.add_css_class("flat")
        shuffle.connect("clicked", lambda _b: self.win.shuffle_now())
        shuffle_row.add_suffix(shuffle)
        shuffle_row.set_activatable_widget(shuffle)
        group.add(shuffle_row)
        self.page.append(group)

    def build_advanced(self):
        group = Adw.PreferencesGroup(
            title="Finishing touches",
            description="Optional extras for people who want more control.")
        css_row = Adw.ActionRow(
            title="Custom stylesheet",
            subtitle=f"{store.CUSTOM_CSS} — appended to Aura's generated GTK theme.")
        css_row.set_tooltip_text(store.CUSTOM_CSS)
        open_css = Gtk.Button(label="Open…", valign=Gtk.Align.CENTER,
                              css_classes=["flat"])
        open_css.connect("clicked", lambda _b: self.win.open_custom_css())
        css_row.add_suffix(open_css)
        css_row.set_activatable_widget(open_css)
        group.add(css_row)

        self.hooks_row = Adw.ActionRow(
            title="Recolour hooks",
            subtitle="Scripts in this folder run after each recolour.")
        open_hooks = Gtk.Button(label="Open folder", valign=Gtk.Align.CENTER,
                                css_classes=["flat"])
        open_hooks.connect("clicked", lambda _b: self.win.open_hooks_folder())
        self.hooks_row.add_suffix(open_hooks)
        self.hooks_row.set_activatable_widget(open_hooks)
        group.add(self.hooks_row)
        self.page.append(group)

    def build_session(self):
        group = Adw.PreferencesGroup(
            title="At login",
            description="Some desktops forget themes, icons and fonts when you log out.")
        self.login_switch = Adw.SwitchRow(
            title="Reapply my look after login",
            subtitle="Runs in the background, applies the chosen look and exits. "
                     "No window is opened.")
        self.login_switch.connect("notify::active", self.on_login_switch)
        group.add(self.login_switch)

        self.login_delay_row = Adw.SpinRow.new(
            Gtk.Adjustment(value=8, lower=0, upper=300, step_increment=1,
                           page_increment=10), 1, 0)
        self.login_delay_row.set_title("Wait before reapplying")
        self.login_delay_row.set_subtitle(
            "Seconds after login, so the desktop has finished starting.")
        self.login_delay_row.connect("notify::value", self.on_login_delay)
        group.add(self.login_delay_row)

        self.login_look_values = [None]
        self.login_look_labels = ["Last applied look"]
        self.login_look_row = Adw.ComboRow(
            title="Look to reapply",
            subtitle="The last applied look, or a saved profile.")
        self.login_look_row.connect("notify::selected", self.on_login_look)
        group.add(self.login_look_row)
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
        chosen = widgets.colour_button_hex(button)
        if chosen == getattr(self, "_accent_shown", None):
            return
        self._accent_shown = chosen
        self.win.set_accent(chosen)

    def on_switch(self, row, _param, key):
        if self.updating:
            return
        self.win.save_config(**{key: row.get_active()})
        if key == "glass":
            self.opacity_row.set_sensitive(row.get_active())
        elif key == "terminal":
            for target_row in self.terminal_rows.values():
                target_row.set_sensitive(row.get_active())

    def on_terminal_target(self, row, _param, target):
        if self.updating:
            return
        current = self.win.config.get("terminal_targets")
        selected = list(system.terminal_targets() if current is None else current)
        if row.get_active():
            if target not in selected:
                selected.append(target)
        else:
            selected = [item for item in selected if item != target]
        self.win.save_config(terminal_targets=selected)

    def on_backend(self, combo, _param):
        if self.updating:
            return
        index = combo.get_selected()
        if not (0 <= index < len(self.backend_values)):
            return
        name = self.backend_values[index]
        self.win.save_config(wallpaper_backend=name)
        backend = system.detect_backend(refresh=True)
        self.win.update_sidebar_footer()
        self.refresh_status()
        if backend.get("fallback"):
            self.win.toast(
                f"{store.WALLPAPER_BACKEND_LABELS.get(name, name)} is not available; "
                f"using {backend['label']} instead.")
        else:
            self.win.toast(f"Wallpaper engine: {backend['label']}")

    def on_login_delay(self, row, _param):
        if self.updating:
            return
        self.win.save_config(autostart_delay=int(round(row.get_value())))
        if system.autostart_enabled():
            try:
                system.set_autostart(
                    True, profile=self.win.config.get("autostart_profile"),
                    delay=self.win.config["autostart_delay"])
            except OSError as error:
                self.win.toast(f"Could not update the login entry: {error}")

    def on_theme_combo(self, combo, _param, key, values):
        if self.updating:
            return
        index = combo.get_selected()
        value = values[index] if 0 <= index < len(values) else None
        self.win.save_config(**{key: value})
        self.refresh_status()

    def on_cursor_size(self, combo, _param):
        if self.updating:
            return
        index = combo.get_selected()
        value = (self.cursor_size_values[index]
                 if 0 <= index < len(self.cursor_size_values) else None)
        self.win.save_config(cursor_size=value)

    def on_wallpaper_mode(self, combo, _param):
        if self.updating:
            return
        index = combo.get_selected()
        if 0 <= index < len(self.wallpaper_mode_values):
            self.win.save_config(wallpaper_mode=self.wallpaper_mode_values[index])

    def on_slideshow_order(self, combo, _param):
        if self.updating:
            return
        index = combo.get_selected()
        if 0 <= index < len(self.slideshow_order_values):
            self.win.save_config(slideshow_order=self.slideshow_order_values[index])

    def on_login_switch(self, row, _param):
        if self.updating:
            return
        enabled = row.get_active()
        try:
            system.set_autostart(
                enabled, profile=self.win.config.get("autostart_profile"),
                delay=self.win.config.get("autostart_delay", 8))
        except OSError as error:
            self.updating = True
            try:
                row.set_active(not enabled)
            finally:
                self.updating = False
            self.win.toast(f"Could not update the login entry: {error}")
            return
        if enabled and not (self.win.state.get("palette")
                            or self.win.config.get("autostart_profile")):
            self.win.toast("Login reapply is on. Apply a look once so there is "
                           "something to restore.")
        elif enabled:
            self.win.toast("Aura will reapply this look in the background after login")
        else:
            self.win.toast("Login reapply turned off")

    def on_login_look(self, combo, _param):
        if self.updating:
            return
        value = self.login_look_values[combo.get_selected()] \
            if 0 <= combo.get_selected() < len(self.login_look_values) else None
        self.win.save_config(autostart_profile=value)
        if system.autostart_enabled():
            try:
                system.set_autostart(
                    True, profile=value,
                    delay=self.win.config.get("autostart_delay", 8))
            except OSError as error:
                self.win.toast(f"Could not update the login entry: {error}")
                return
        if value:
            name = self.login_look_labels[combo.get_selected()]
            self.win.toast(f"“{name}” will be applied after login")
        else:
            self.win.toast("The last applied look will be restored after login")

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

    def on_slide_choice(self, row, _param):
        if self.updating:
            return
        minutes = max(0, int(round(row.get_value())))
        if minutes == self.win.config.get("slide_minutes"):
            return
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
            self._accent_shown = accent.upper()
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
            self.opacity_row.set_sensitive(bool(config["glass"]))
            opacity = float(config.get("glass_opacity", 0.72))
            self.opacity_scale.set_value(opacity)
            self.opacity_label.set_label(f"{opacity * 100:.0f}%")

            selected_targets = config.get("terminal_targets")
            for target, row in self.terminal_rows.items():
                row.set_active(selected_targets is None or target in selected_targets)
                row.set_sensitive(bool(config["terminal"]))

            for combo, values, key in (
                    (self.icons_combo, self.icon_values, "icon_theme"),
                    (self.cursors_combo, self.cursor_values, "cursor_theme"),
                    (self.cursor_size_row, self.cursor_size_values, "cursor_size")):
                value = config.get(key)
                combo.set_selected(values.index(value) if value in values else 0)

            backend = config.get("wallpaper_backend", "auto")
            self.backend_row.set_selected(
                self.backend_values.index(backend)
                if backend in self.backend_values else 0)

            mode = config.get("wallpaper_mode", "fill")
            self.wallpaper_mode_row.set_selected(
                self.wallpaper_mode_values.index(mode)
                if mode in self.wallpaper_mode_values else 0)
            order = config.get("slideshow_order", "shuffle")
            self.slideshow_order_row.set_selected(
                self.slideshow_order_values.index(order)
                if order in self.slideshow_order_values else 0)

            self.font_button.set_font_desc(Pango.FontDescription.from_string(
                config.get("font") or preferences["font"] or "Adwaita Sans 11"))
            self.mono_button.set_font_desc(Pango.FontDescription.from_string(
                config.get("mono_font") or preferences["mono_font"] or "Adwaita Mono 11"))
            self.font_row.set_subtitle("Custom" if config.get("font") else "System default")
            self.mono_row.set_subtitle("Custom" if config.get("mono_font") else "System default")

            scale = config.get("text_scale") or preferences["text_scale"] or 1.0
            self.scale.set_value(float(scale))
            self.scale_label.set_label(f"{float(scale) * 100:.0f}%")

            self.slide_row.set_value(int(config.get("slide_minutes", 0)))
            self.login_delay_row.set_value(int(config.get("autostart_delay", 8)))
            self.login_switch.set_active(system.autostart_enabled())
            self._sync_login_looks(config.get("autostart_profile"))
        finally:
            self.updating = False
        self.refresh_status()

    def _sync_login_looks(self, selected_id):
        profiles = store.load_profiles()
        self.login_look_values = [None]
        self.login_look_labels = ["Last applied look"]
        for profile in profiles:
            self.login_look_values.append(profile.get("id"))
            self.login_look_labels.append(profile.get("name") or "Untitled look")
        self.login_look_row.set_model(Gtk.StringList.new(self.login_look_labels))
        index = (self.login_look_values.index(selected_id)
                 if selected_id in self.login_look_values else 0)
        self.login_look_row.set_selected(index)

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
