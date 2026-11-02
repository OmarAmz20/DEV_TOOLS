"""Dock page and live preview."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import dock
from .custom_pages import action, text


def _icon(entry: dict, size: int = 28) -> Gtk.Widget:
    if entry.get("desktop_file"):
        try:
            info = Gio.DesktopAppInfo.new_from_filename(entry["desktop_file"])
            icon = info.get_icon() if info else None
            if icon is not None:
                image = Gtk.Image.new_from_gicon(icon)
                image.set_pixel_size(size)
                return image
        except Exception:
            pass
    icon = entry.get("icon") or "application-x-executable"
    if Path(icon).is_file():
        image = Gtk.Image.new_from_file(icon)
        image.set_pixel_size(size)
        return image
    image = Gtk.Image.new_from_icon_name(icon)
    image.set_pixel_size(size)
    return image


class DockPage:
    def dock_page(self):
        self.dock_data = dock.load()
        self.dock_rows = []
        self.dock_preview_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.dock_preview_css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )
        page = self.page(
            "Dock",
            "A dock you actually own: place it on any edge, choose a monitor, tune its style and add the apps you use.",
        )
        top = Gtk.Box(spacing=10)
        self.dock_start_button = action("Start dock", lambda: self.apply_dock(True))
        self.dock_start_button.add_css_class("suggested-action")
        self.dock_stop_button = action("Stop", lambda: self.apply_dock(False))
        top.append(self.dock_start_button)
        top.append(self.dock_stop_button)
        top.append(Gtk.Box(hexpand=True))
        self.dock_status = text("Checking…", "studio-pill", halign=Gtk.Align.START)
        top.append(self.dock_status)
        page.append(top)

        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview.append(text("Live preview", "studio-section"))
        stage = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        stage.add_css_class("dock-preview-stage")
        self.dock_preview = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        self.dock_preview.add_css_class("dock-card")
        stage.append(self.dock_preview)
        preview.append(stage)
        page.append(preview)

        options = Adw.PreferencesGroup(title="Dock style", description="Changes appear in the preview immediately; Start applies them to the desktop.")
        self.dock_enabled = self._switch("Show this dock", "Start the dock on this desktop", "enabled", options)
        self.dock_position = self._combo("Position", [("bottom", "Bottom"), ("top", "Top"),
                                                      ("left", "Left"), ("right", "Right")],
                                         "position", options)
        self.dock_alignment = self._combo("Alignment", [("start", "Start"), ("center", "Center"),
                                                        ("end", "End")], "alignment", options)
        monitors = [("all", "All monitors")]
        display = Gdk.Display.get_default()
        for index in range(display.get_monitors().get_n_items() if display else 1):
            monitors.append((str(index), f"Monitor {index + 1}"))
        self.dock_monitor = self._combo("Monitor", monitors, "monitor", options)
        self.dock_style = self._combo("Skin", [(item, item.title()) for item in dock.STYLES],
                                      "style", options)
        self.dock_icon_size = self._spin("Icon size", 20, 96, 1, "icon_size", options)
        self.dock_spacing = self._spin("Spacing", 0, 32, 1, "spacing", options)
        self.dock_padding = self._spin("Edge padding", 2, 40, 1, "padding", options)
        self.dock_radius = self._spin("Corner radius", 0, 40, 1, "radius", options)
        self.dock_opacity = self._scale("Background opacity", .25, 1.0, .01, "opacity", options)
        self.dock_labels = self._switch("Show app labels", "Add a label below every icon", "show_labels", options)
        self.dock_reserve = self._switch("Reserve screen space", "Keep maximized windows above the dock strip", "reserve_space", options)
        self.dock_autostart = self._switch("Start at login", "Create a per-user autostart entry", "autostart", options)
        row = Adw.ActionRow(title="Accent colour", subtitle="Hex colour; leave blank to follow your current look")
        self.dock_accent = Gtk.Entry(text=self.dock_data.get("accent", ""), placeholder_text="#7aa2ff",
                                     width_chars=10, max_length=7, valign=Gtk.Align.CENTER)
        self.dock_accent.connect("changed", lambda *_a: self.refresh_dock_preview())
        row.add_suffix(self.dock_accent)
        options.add(row)
        page.append(options)

        self.dock_apps_group = Adw.PreferencesGroup(
            title="Dock apps",
            description="Launch applications or custom commands. Reorder them to change the dock order.",
        )
        apps_tools = Gtk.Box(spacing=6)
        apps_tools.append(action("Add application…", self.add_dock_application))
        apps_tools.append(action("Add command…", lambda: self.edit_dock_app(None)))
        apps_tools.append(action("Add separator", self.add_dock_separator))
        page.append(apps_tools)
        page.append(self.dock_apps_group)

        page.append(action("Apply dock", lambda: self.apply_dock(None)))
        self.refresh_dock_page()
        return page

    def _switch(self, title: str, subtitle: str, key: str, group: Adw.PreferencesGroup) -> Gtk.Switch:
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        switch = Gtk.Switch(active=bool(self.dock_data.get(key)), valign=Gtk.Align.CENTER)
        switch.connect("notify::active", lambda item, _: self.refresh_dock_preview())
        row.add_suffix(switch)
        group.add(row)
        return switch

    def _combo(self, title: str, values: list[tuple[str, str]], key: str,
               group: Adw.PreferencesGroup) -> Gtk.DropDown:
        row = Adw.ActionRow(title=title)
        combo = Gtk.DropDown.new_from_strings([label for _value, label in values])
        selected = self.dock_data.get(key)
        combo.set_selected(next((i for i, (value, _label) in enumerate(values) if str(value) == str(selected)), 0))
        combo.connect("notify::selected", lambda *_a: self.refresh_dock_preview())
        row.add_suffix(combo)
        group.add(row)
        return combo

    def _spin(self, title: str, low: int, high: int, step: int, key: str,
              group: Adw.PreferencesGroup) -> Gtk.SpinButton:
        row = Adw.ActionRow(title=title)
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        spin.set_value(int(self.dock_data.get(key, low)))
        spin.connect("value-changed", lambda *_a: self.refresh_dock_preview())
        row.add_suffix(spin)
        group.add(row)
        return spin

    def _scale(self, title: str, low: float, high: float, step: float, key: str,
               group: Adw.PreferencesGroup) -> Gtk.Scale:
        row = Adw.ActionRow(title=title)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        scale.set_value(float(self.dock_data.get(key, .86)))
        scale.set_size_request(180, -1)
        scale.set_valign(Gtk.Align.CENTER)
        scale.connect("value-changed", lambda *_a: self.refresh_dock_preview())
        row.add_suffix(scale)
        group.add(row)
        return scale

    def _dock_form(self) -> dict:
        positions = ["bottom", "top", "left", "right"]
        alignments = ["start", "center", "end"]
        monitors = ["all"] + [str(i) for i in range(
            Gdk.Display.get_default().get_monitors().get_n_items()
            if Gdk.Display.get_default() else 1
        )]
        return {
            "enabled": self.dock_enabled.get_active(),
            "position": positions[self.dock_position.get_selected()],
            "alignment": alignments[self.dock_alignment.get_selected()],
            "monitor": monitors[self.dock_monitor.get_selected()],
            "style": dock.STYLES[self.dock_style.get_selected()],
            "icon_size": int(self.dock_icon_size.get_value()),
            "spacing": int(self.dock_spacing.get_value()),
            "padding": int(self.dock_padding.get_value()),
            "radius": int(self.dock_radius.get_value()),
            "opacity": round(float(self.dock_opacity.get_value()), 2),
            "show_labels": self.dock_labels.get_active(),
            "reserve_space": self.dock_reserve.get_active(),
            "autostart": self.dock_autostart.get_active(),
            "accent": self.dock_accent.get_text().strip(),
        }

    def _save_dock(self) -> dict:
        form = self._dock_form()
        self.dock_data = dock.save({**self.dock_data, **form})
        try:
            dock.set_autostart(bool(self.dock_data.get("autostart")))
        except OSError as error:
            self.toast(f"Autostart: {error}")
        self.refresh_dock_preview()
        return self.dock_data

    def apply_dock(self, start: bool | None = None) -> None:
        data = self._save_dock()
        if start is False:
            data["enabled"] = False
            self.dock_enabled.set_active(False)
            self.dock_data = dock.save(data)
        elif start is True:
            self.dock_enabled.set_active(True)
            data["enabled"] = True
            self.dock_data = dock.save(data)
        target = bool(self.dock_data.get("enabled"))
        self.dock_status.set_text("Starting…" if target else "Stopping…")
        def worker():
            try:
                result = dock.start() if target else dock.stop()
                error = None
            except Exception as exc:
                result, error = None, str(exc)
            GLib.idle_add(self._dock_done, result, error, target)
        threading.Thread(target=worker, daemon=True).start()

    def _dock_done(self, result, error, target: bool) -> bool:
        if not getattr(self, "alive", True):
            return False
        self.dock_status.set_text("RUNNING" if target and dock.running() else "STOPPED")
        if error:
            self.toast(error)
        else:
            self.toast("Dock running" if target else "Dock stopped")
        self.refresh_dock_page()
        return False

    def refresh_dock_page(self) -> None:
        self.refresh_dock_preview()
        self.dock_status.set_text("RUNNING" if dock.running() else "STOPPED")
        for row in self.dock_rows:
            self.dock_apps_group.remove(row)
        self.dock_rows = []
        for index, entry in enumerate(self.dock_data.get("apps", [])):
            if entry.get("separator"):
                row = Adw.ActionRow(title="Separator")
                row.add_suffix(action("Remove", lambda _b=None, eid=entry["id"]: self.remove_dock_app(eid)))
                self.dock_apps_group.add(row)
                self.dock_rows.append(row)
                continue
            row = Adw.ActionRow(title=entry.get("label", "Application"),
                                subtitle=entry.get("command") or Path(entry.get("desktop_file", "")).name)
            row.add_prefix(_icon(entry, 26))
            row.add_suffix(action("Edit", lambda _b=None, e=entry: self.edit_dock_app(e)))
            row.add_suffix(action("↑", lambda _b=None, eid=entry["id"]: self.move_dock_app(eid, -1)))
            row.add_suffix(action("↓", lambda _b=None, eid=entry["id"]: self.move_dock_app(eid, 1)))
            row.add_suffix(action("Remove", lambda _b=None, eid=entry["id"]: self.remove_dock_app(eid)))
            self.dock_apps_group.add(row)
            self.dock_rows.append(row)

    def refresh_dock_preview(self) -> None:
        if not hasattr(self, "dock_preview"):
            return
        config = {**self._dock_form(), "apps": self.dock_data.get("apps", [])}
        self.dock_data.update(config)
        self.dock_preview_css.load_from_data(dock.css(config).encode(), -1)
        for child in list(self.dock_preview):
            self.dock_preview.remove(child)
        self.dock_preview.set_orientation(
            Gtk.Orientation.HORIZONTAL if config["position"] in ("bottom", "top")
            else Gtk.Orientation.VERTICAL
        )
        self.dock_preview.set_spacing(int(config["spacing"]))
        for entry in config.get("apps", []):
            if entry.get("separator"):
                sep = Gtk.Separator(
                    orientation=Gtk.Orientation.VERTICAL if config["position"] in ("bottom", "top")
                    else Gtk.Orientation.HORIZONTAL
                )
                sep.add_css_class("dock-separator")
                self.dock_preview.append(sep)
                continue
            button = Gtk.Button()
            button.add_css_class("dock-button")
            button.set_tooltip_text(entry.get("label", "Open"))
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            content.append(_icon(entry, int(config["icon_size"])))
            if config.get("show_labels"):
                label = Gtk.Label(label=str(entry.get("label", ""))[:16])
                label.add_css_class("dock-label")
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.set_max_width_chars(16 if config["position"] in ("bottom", "top") else 10)
                label.set_tooltip_text(str(entry.get("label", "")))
                content.append(label)
            button.set_child(content)
            button.connect("clicked", lambda _b, app_entry=entry: dock.launch_app(app_entry))
            self.dock_preview.append(button)

    def remove_dock_app(self, identifier: str) -> None:
        self.dock_data = dock.remove_app(identifier)
        self.refresh_dock_page()

    def add_dock_separator(self) -> None:
        self.dock_data = dock.add_app({"separator": True})
        self.refresh_dock_page()

    def move_dock_app(self, identifier: str, offset: int) -> None:
        self.dock_data = dock.move_app(identifier, offset)
        self.refresh_dock_page()

    def add_dock_application(self) -> None:
        dialog = Gtk.FileChooserNative(title="Add a desktop application",
                                       transient_for=self, action=Gtk.FileChooserAction.OPEN)
        file_filter = Gtk.FileFilter(name="Desktop applications")
        file_filter.add_pattern("*.desktop")
        dialog.add_filter(file_filter)
        def response(item, result):
            if result == Gtk.ResponseType.ACCEPT:
                path = item.get_file().get_path()
                try:
                    info = Gio.DesktopAppInfo.new_from_filename(path)
                    if not info:
                        raise ValueError("Not a valid desktop application")
                    icon = info.get_icon()
                    self.dock_data = dock.add_app({
                        "label": info.get_name(),
                        "icon": icon.to_string() if icon else "application-x-executable",
                        "desktop_file": path,
                        "command": "",
                    })
                    self.refresh_dock_page()
                except (OSError, ValueError) as error:
                    self.toast(str(error))
            item.destroy()
        dialog.connect("response", response)
        dialog.show()

    def edit_dock_app(self, entry: dict | None) -> None:
        window = Gtk.Window(transient_for=self.get_root(), modal=True, title="Dock app")
        window.set_default_size(520, 360)
        header = Gtk.HeaderBar()
        save_button = Gtk.Button(label="Save")
        save_button.add_css_class("suggested-action")
        header.pack_end(save_button)
        window.set_titlebar(header)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                          margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        label = Gtk.Entry(text=entry.get("label", "") if entry else "", placeholder_text="Label")
        icon = Gtk.Entry(text=entry.get("icon", "") if entry else "", placeholder_text="Icon name or file path")
        command = Gtk.Entry(text=entry.get("command", "") if entry else "", placeholder_text="Command to run")
        for title, field in (("Label", label), ("Icon", icon), ("Command", command)):
            row = Adw.ActionRow(title=title)
            row.add_suffix(field)
            content.append(row)
        window.set_child(content)
        def save(_button=None):
            item = {
                "id": entry.get("id") if entry else None,
                "label": label.get_text().strip(),
                "icon": icon.get_text().strip() or "application-x-executable",
                "command": command.get_text().strip(),
                "desktop_file": entry.get("desktop_file", "") if entry else "",
            }
            normalised = dock.normalise_app(item)
            if not normalised:
                self.toast("A label and a command (or desktop file) are required")
                return
            apps = list(self.dock_data.get("apps", []))
            if entry:
                apps = [normalised if app.get("id") == entry.get("id") else app for app in apps]
            else:
                apps.append(normalised)
            self.dock_data = dock.save({**self.dock_data, "apps": apps})
            window.close()
            self.refresh_dock_page()
        save_button.connect("clicked", save)
        window.present()
