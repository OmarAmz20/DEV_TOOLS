"""Widget layout editor and desktop host controls."""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import constants, desktop, themes, video, wallpaper, widget_daemon, widgets  # noqa: E402
from ..util import open_path, read_json, write_json  # noqa: E402
from . import common  # noqa: E402


class WidgetEditorRow(Gtk.Expander):
    def __init__(self, page: "WidgetsPage", item: dict):
        super().__init__()
        self.page = page
        self.item = item
        metadata = widgets.WIDGET_TYPES.get(item["type"], widgets.WIDGET_TYPES["clock"])
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        self.enable = common.switch(bool(item.get("enabled", True)))
        self.enable.connect("notify::active", lambda *_a: self._set("enabled", self.enable.get_active()))
        header.append(self.enable)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        labels.set_hexpand(True)
        title = Gtk.Label(label=metadata["name"], xalign=0)
        title.add_css_class("setting-title")
        subtitle = Gtk.Label(label=metadata["description"], xalign=0)
        subtitle.add_css_class("setting-subtitle")
        subtitle.set_ellipsize(3)
        labels.append(title)
        labels.append(subtitle)
        header.append(labels)
        duplicate = common.button("", icon="edit-copy-symbolic", tooltip="Duplicate widget",
                                  on_click=lambda: page.duplicate_item(item))
        move_up = common.button("", icon="go-up-symbolic", tooltip="Move up in stacking order",
                                on_click=lambda: page.move_item(item, 1))
        move_down = common.button("", icon="go-down-symbolic", tooltip="Move down in stacking order",
                                  on_click=lambda: page.move_item(item, 1))
        header.append(duplicate)
        header.append(move_up)
        header.append(move_down)
        remove = common.button("", icon="user-trash-symbolic", tooltip="Remove widget",
                               on_click=lambda: page.remove_item(item))
        header.append(remove)
        self.set_label_widget(header)
        self.set_expanded(False)
        self.connect("notify::expanded", self._expanded_changed)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        body.set_margin_top(10)
        body.set_margin_start(6)
        body.set_margin_end(6)
        body.set_margin_bottom(8)

        grid = Gtk.Grid(column_spacing=12, row_spacing=7)
        self.x = self._percent_spin(item["x"])
        self.y = self._percent_spin(item["y"])
        self.w = self._percent_spin(item["w"], 0.06, 0.9)
        self.h = self._percent_spin(item["h"], 0.05, 0.9)
        for index, (label, widget) in enumerate((("X", self.x), ("Y", self.y),
                                                  ("Width", self.w), ("Height", self.h))):
            title = Gtk.Label(label=label, xalign=0)
            title.add_css_class("meta-key")
            grid.attach(title, index, 0, 1, 1)
            grid.attach(widget, index, 1, 1, 1)
        body.append(grid)

        sliders = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.opacity = common.scale(float(item.get("opacity", 1.0)), 0.2, 1.0, 0.05)
        self.opacity.connect("value-changed", lambda *_a: self._set("opacity", round(self.opacity.get_value(), 2)))
        self.scale = common.scale(float(item.get("scale", 1.0)), 0.65, 2.0, 0.05)
        self.scale.connect("value-changed", lambda *_a: self._set("scale", round(self.scale.get_value(), 2)))
        for label_text, widget in (("Opacity", self.opacity), ("Scale", self.scale)):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            label = Gtk.Label(label=label_text, xalign=0)
            label.add_css_class("meta-key")
            box.append(label)
            widget.set_hexpand(True)
            box.append(widget)
            sliders.append(box)
        body.append(sliders)

        self.interactive = common.switch(bool(item.get("interactive", False)))
        self.interactive.connect("notify::active", lambda *_a: self._set("interactive", self.interactive.get_active()))
        body.append(common.row("Interactive", "Allow clicks on this widget while locked", trailing=self.interactive))
        body.append(self._style_ui(item, metadata))
        body.append(self._options_ui(item, metadata))
        self.set_child(body)

    def _expanded_changed(self, *_args) -> None:
        if self.get_expanded():
            self.page.set_selected_item(self.item)

    def _percent_spin(self, value: float, minimum: float = 0.0, maximum: float = 0.94):
        spin = common.spin(round(value * 100, 1), minimum * 100, maximum * 100, 1, 1)
        spin.set_width_chars(6)
        spin.connect("value-changed", lambda *_a: self._set_percent())
        return spin

    def _set_percent(self) -> None:
        x = round(float(self.x.get_value()) / 100, 3)
        y = round(float(self.y.get_value()) / 100, 3)
        w = round(float(self.w.get_value()) / 100, 3)
        h = round(float(self.h.get_value()) / 100, 3)
        x, w = max(0.0, min(x, 0.94)), max(0.06, min(w, 0.9))
        y, h = max(0.0, min(y, 0.94)), max(0.05, min(h, 0.9))
        if x + w > 1:
            w = max(0.06, 1 - x)
        if y + h > 1:
            h = max(0.05, 1 - y)
        self.item.update({"x": x, "y": y, "w": w, "h": h})
        self.page.schedule_save()

    def _set(self, key: str, value) -> None:
        self.item[key] = value
        self.page.schedule_save()
        self.page.canvas.queue_draw()

    def _set_option(self, key: str, value) -> None:
        self.item.setdefault("options", {})[key] = value
        self.page.schedule_save()

    def _style_ui(self, item: dict, metadata: dict) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        box.append(common.section("Custom style", "Override the global widget style for this card."))
        theme = common.dropdown(
            [("", "Use global style")] + [(name, name.title()) for name in constants.WIDGET_THEMES
                                          if name != "glass"],
            item.get("theme", ""),
        )

        def theme_selected(*_args):
            index = theme.get_selected()
            item["theme"] = "" if index == 0 else (
                [name for name in constants.WIDGET_THEMES if name != "glass"][index - 1]
            )
            self.page.schedule_save()
            self.page.canvas.queue_draw()

        theme.connect("notify::selected", theme_selected)
        box.append(common.row("Widget style", "Global or per-widget", trailing=theme))
        monitor = common.dropdown([("", "Use global")] + desktop.monitor_choices(),
                                  item.get("monitor", ""))
        monitor.connect("notify::selected", lambda *_a: self._set(
            "monitor", "" if monitor.get_selected() == 0 else desktop.monitor_choices()[monitor.get_selected() - 1][0]
        ))
        box.append(common.row("Monitor", "Pin this card to one display", trailing=monitor))

        for title, key, fallback in (
            ("Accent override", "accent", "#7aa2ff"),
            ("Background override", "bg", "#151829"),
            ("Text override", "fg", "#f7f7fb"),
        ):
            color = common.color_button(str(item.get(key) or fallback))
            auto = common.button("Auto", css="flat", on_click=lambda _b=None, k=key: self._clear_color(k, color, fallback))
            controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            controls.append(color)
            controls.append(auto)

            def changed(_button, k=key, widget=color):
                rgba = widget.get_rgba()
                item[k] = "#%02x%02x%02x" % (
                    round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)
                )
                self.page.schedule_save()
                self.page.canvas.queue_draw()

            color.connect("notify::rgba", changed)
            box.append(common.row(title, "Auto follows the current look", trailing=controls))

        radius = common.spin(float(item.get("radius", -1)), -1, 40, 1)
        radius.connect("value-changed", lambda *_a: self._set("radius", int(radius.get_value())))
        box.append(common.row("Corner radius", "-1 follows the global structure", trailing=radius))
        border = common.spin(float(item.get("border_width", -1)), -1, 8, 1)
        border.connect("value-changed", lambda *_a: self._set("border_width", int(border.get_value())))
        box.append(common.row("Border width", "-1 follows the global structure", trailing=border))
        padding = common.spin(float(item.get("padding", -1)), -1, 56, 1)
        padding.connect("value-changed", lambda *_a: self._set("padding", int(padding.get_value())))
        box.append(common.row("Inner padding", "-1 follows the text scale", trailing=padding))
        align = common.dropdown([("start", "Left"), ("center", "Centre"), ("end", "Right")],
                                item.get("align", "start"))
        align.connect("notify::selected", lambda *_a: self._set(
            "align", ["start", "center", "end"][align.get_selected()]))
        box.append(common.row("Text alignment", trailing=align))
        shadow = common.switch(bool(item.get("shadow", True)))
        shadow.connect("notify::active", lambda *_a: self._set("shadow", shadow.get_active()))
        box.append(common.row("Drop shadow", trailing=shadow))
        return box

    def _clear_color(self, key: str, button, fallback: str) -> None:
        rgba = Gdk.RGBA()
        rgba.parse(fallback)
        button.set_rgba(rgba)
        # The color button's notify handler runs above; clear the override
        # afterwards so "Auto" really means auto.
        self.item[key] = ""
        self.page.schedule_save()
        self.page.canvas.queue_draw()

    def _options_ui(self, item: dict, metadata: dict) -> Gtk.Widget:
        kind = item["type"]
        options = item.setdefault("options", {})
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        box.append(common.section("Options", metadata["description"]))
        if kind == "clock":
            seconds = common.switch(bool(options.get("seconds", False)))
            seconds.connect("notify::active", lambda *_a: self._set_option("seconds", seconds.get_active()))
            box.append(common.row("Seconds", trailing=seconds))
            twenty_four = common.switch(bool(options.get("24h", True)))
            twenty_four.connect("notify::active", lambda *_a: self._set_option("24h", twenty_four.get_active()))
            box.append(common.row("24-hour time", trailing=twenty_four))
            date = common.switch(bool(options.get("show_date", True)))
            date.connect("notify::active", lambda *_a: self._set_option("show_date", date.get_active()))
            box.append(common.row("Show date", trailing=date))
            fmt = common.labelled_entry(str(options.get("format", "")), "Custom time format, e.g. %H:%M")
            fmt.connect("changed", lambda *_a: self._set_option("format", fmt.get_text()))
            box.append(common.row("Time format", "Uses strftime syntax", trailing=fmt))
            date_fmt = common.labelled_entry(str(options.get("date_format", "%A, %d %B")), "Date format")
            date_fmt.connect("changed", lambda *_a: self._set_option("date_format", date_fmt.get_text()))
            box.append(common.row("Date format", trailing=date_fmt))
        elif kind == "calendar":
            weeks = common.switch(bool(options.get("show_week_numbers", False)))
            weeks.connect("notify::active", lambda *_a: self._set_option("show_week_numbers", weeks.get_active()))
            box.append(common.row("Week numbers", trailing=weeks))
            heading = common.switch(bool(options.get("show_heading", True)))
            heading.connect("notify::active", lambda *_a: self._set_option("show_heading", heading.get_active()))
            box.append(common.row("Month heading", trailing=heading))
        elif kind == "system":
            for key, title in (("cpu", "CPU"), ("ram", "Memory"), ("disk", "Home disk")):
                switch = common.switch(bool(options.get(key, True)))
                switch.connect("notify::active", lambda *_a, k=key: self._set_option(k, switch.get_active()))
                box.append(common.row(title, trailing=switch))
        elif kind == "note":
            view = Gtk.TextView()
            view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            view.get_buffer().set_text(str(options.get("text", "")))
            view.set_size_request(-1, 100)
            view.get_buffer().connect("changed", lambda buffer: self._set_option(
                "text", buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)))
            box.append(view)
        elif kind == "media":
            controls = common.switch(bool(options.get("show_controls", True)))
            controls.connect("notify::active", lambda *_a: self._set_option("show_controls", controls.get_active()))
            box.append(common.row("Transport controls", trailing=controls))
            artist = common.switch(bool(options.get("show_artist", True)))
            artist.connect("notify::active", lambda *_a: self._set_option("show_artist", artist.get_active()))
            box.append(common.row("Show artist", trailing=artist))
        elif kind == "timer":
            minutes = common.spin(float(options.get("minutes", 25)), 1, 180, 5)
            minutes.connect("value-changed", lambda *_a: self._set_option("minutes", int(minutes.get_value())))
            box.append(common.row("Focus length", "Minutes", trailing=minutes))
        elif kind == "launcher":
            view = Gtk.TextView()
            view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            text = "\n".join(f"{entry.get('label', 'Open')} | {entry.get('command', '')}"
                             for entry in options.get("commands", []) if isinstance(entry, dict))
            view.get_buffer().set_text(text)
            view.set_size_request(-1, 110)
            view.get_buffer().connect("changed", lambda buffer: self._commands_changed(buffer))
            box.append(view)
            hint = Gtk.Label(label="One per line: Label | command", xalign=0)
            hint.add_css_class("dim-label")
            box.append(hint)
        elif kind == "weather":
            lat = common.spin(float(options.get("latitude", 0) or 0), -90, 90, 0.1, 4)
            lat.connect("value-changed", lambda *_a: self._set_option("latitude", round(lat.get_value(), 4)))
            lon = common.spin(float(options.get("longitude", 0) or 0), -180, 180, 0.1, 4)
            lon.connect("value-changed", lambda *_a: self._set_option("longitude", round(lon.get_value(), 4)))
            city = common.labelled_entry(str(options.get("city", "")), "City label")
            city.connect("changed", lambda *_a: self._set_option("city", city.get_text()))
            lookup = common.button("Look up", icon="system-search-symbolic",
                                   on_click=lambda: self._lookup_city(city, lat, lon))
            city_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            city.set_hexpand(True)
            city_row.append(city)
            city_row.append(lookup)
            box.append(common.row("City", "Look up coordinates, or enter them below", trailing=city_row))
            box.append(common.row("Latitude", trailing=lat))
            box.append(common.row("Longitude", trailing=lon))
            units = common.dropdown([("celsius", "Celsius"), ("fahrenheit", "Fahrenheit")],
                                    str(options.get("units", "celsius")))
            units.connect("notify::selected", lambda *_a: self._set_option(
                "units", "celsius" if units.get_selected() == 0 else "fahrenheit"))
            box.append(common.row("Units", trailing=units))
        elif kind == "battery":
            state = common.switch(bool(options.get("show_state", True)))
            state.connect("notify::active", lambda *_a: self._set_option("show_state", state.get_active()))
            box.append(common.row("Show charging state", trailing=state))
        elif kind == "worldclock":
            entry = common.labelled_entry(",".join(options.get("zones", [])), "UTC, Europe/London, Asia/Tokyo")
            entry.connect("changed", lambda *_a: self._set_option(
                "zones", [zone.strip() for zone in entry.get_text().split(",") if zone.strip()][:4]))
            box.append(common.row("Time zones", "IANA names, comma separated", trailing=entry))
            twenty_four = common.switch(bool(options.get("24h", True)))
            twenty_four.connect("notify::active", lambda *_a: self._set_option("24h", twenty_four.get_active()))
            box.append(common.row("24-hour time", trailing=twenty_four))
        elif kind == "countdown":
            label = common.labelled_entry(str(options.get("label", "Countdown")), "Event name")
            label.connect("changed", lambda *_a: self._set_option("label", label.get_text()))
            box.append(common.row("Label", trailing=label))
            date = common.labelled_entry(str(options.get("date", "")), "YYYY-MM-DD")
            date.connect("changed", lambda *_a: self._set_option("date", date.get_text()))
            box.append(common.row("Target date", "YYYY-MM-DD", trailing=date))
        elif kind == "network":
            interface = common.labelled_entry(str(options.get("interface", "")), "auto")
            interface.connect("changed", lambda *_a: self._set_option("interface", interface.get_text()))
            box.append(common.row("Interface", "Leave empty for all", trailing=interface))
            show_ip = common.switch(bool(options.get("show_ip", True)))
            show_ip.connect("notify::active", lambda *_a: self._set_option("show_ip", show_ip.get_active()))
            box.append(common.row("Show local IP", trailing=show_ip))
        elif kind == "quote":
            view = Gtk.TextView()
            view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            view.get_buffer().set_text(str(options.get("text", "")))
            view.set_size_request(-1, 80)
            view.get_buffer().connect("changed", lambda buffer: self._set_option(
                "text", buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)))
            box.append(view)
            author = common.labelled_entry(str(options.get("author", "")), "Author (optional)")
            author.connect("changed", lambda *_a: self._set_option("author", author.get_text()))
            box.append(common.row("Author", trailing=author))
        return box

    def _commands_changed(self, buffer) -> None:
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        commands = []
        for line in text.splitlines():
            if not line.strip():
                continue
            if "|" in line:
                label, command = line.split("|", 1)
            else:
                label, command = line.strip(), line.strip()
            commands.append({"label": label.strip()[:20] or "Open", "command": command.strip()})
        self._set_option("commands", commands[:4])

    def _lookup_city(self, city_entry: Gtk.Entry, lat, lon) -> None:
        city = city_entry.get_text().strip()
        if not city:
            self.page.app.toast("Type a city name first")
            return
        self.page.app.toast(f"Looking up {city}…")

        def worker():
            query = urllib.parse.urlencode({"name": city, "count": 1, "language": "en", "format": "json"})
            try:
                with urllib.request.urlopen(
                    "https://geocoding-api.open-meteo.com/v1/search?" + query, timeout=8
                ) as response:
                    payload = json.loads(response.read().decode())
                result = (payload.get("results") or [None])[0]
            except Exception:
                result = None
            GLib.idle_add(self._city_done, result, city, city_entry, lat, lon)

        threading.Thread(target=worker, daemon=True).start()

    def _city_done(self, result, fallback: str, city_entry: Gtk.Entry, lat, lon) -> bool:
        if not result:
            self.page.app.toast(f"Could not find {fallback}")
            return False
        name = result.get("name") or fallback
        country = result.get("country") or ""
        label = f"{name}, {country}".strip(", ")
        lat.set_value(float(result.get("latitude", 0) or 0))
        lon.set_value(float(result.get("longitude", 0) or 0))
        city_entry.set_text(label)
        self._set_option("city", label)
        self.page.app.toast(f"Found {label}")
        return False


class WidgetsPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.config = app.config
        self.items = widgets.ensure_default_items(self.config)
        self.selected_index = 0
        self._save_source = 0
        self._loading = False
        self._canvas_texture = None
        self._rows: dict[str, WidgetEditorRow] = {}
        self._resize_start = None
        self._resize_active = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        apply = common.button("Apply widgets", icon="emblem-ok-symbolic", css="suggested-action",
                              on_click=self.apply)
        edit = common.button("Edit on desktop", icon="document-edit-symbolic", on_click=self.edit_on_desktop)
        stop = common.button("Stop", icon="media-playback-stop-symbolic", on_click=self.stop)
        add_menu = Gtk.MenuButton()
        add_menu.set_icon_name("list-add-symbolic")
        add_menu.set_tooltip_text("Add a widget")
        add_menu.set_popover(self._add_popover())
        outer, content = common.page_scaffold(
            "Widgets", "A native desktop layer with 13 widget types, live data and per-widget styling.",
            actions=[stop, edit, add_menu, apply],
        )
        self.append(outer)
        self.content = content

        status = common.card()
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        labels.set_hexpand(True)
        status_title = Gtk.Label(label="Desktop host", xalign=0)
        status_title.add_css_class("section-title")
        labels.append(status_title)
        self.host_status = Gtk.Label(label="Checking…", xalign=0)
        self.host_status.add_css_class("dim-label")
        labels.append(self.host_status)
        status_box.append(labels)
        status_box.append(common.button("Open layout folder", icon="folder-open-symbolic",
                                        on_click=lambda: open_path(constants.LAYOUT_DIR)))
        status.append(status_box)
        content.append(status)

        add_card = common.card()
        add_card.append(common.section("Add a widget", "One click. No menu hunting."))
        palette = Gtk.FlowBox()
        palette.set_selection_mode(Gtk.SelectionMode.NONE)
        palette.set_max_children_per_line(7)
        palette.set_min_children_per_line(2)
        palette.set_column_spacing(6)
        palette.set_row_spacing(6)
        for kind, metadata in widgets.WIDGET_TYPES.items():
            button = Gtk.Button(label=metadata["name"])
            button.add_css_class("pill")
            button.set_tooltip_text(metadata["description"])
            button.connect("clicked", lambda _b, k=kind: self.add_item(k))
            palette.append(button)
        add_card.append(palette)
        content.append(add_card)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        top.set_homogeneous(False)
        canvas_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        canvas_box.set_hexpand(True)
        canvas_box.append(common.section("Layout canvas", "Drag widgets to move them. Sizes are relative to the monitor."))
        self.canvas_frame = Gtk.AspectFrame(obey_child=False, ratio=16 / 9, xalign=0.5, yalign=0.5)
        self.canvas_frame.add_css_class("widget-canvas")
        self.canvas_frame.set_size_request(-1, 330)
        self.canvas_picture = Gtk.Picture()
        self.canvas_picture.set_content_fit(Gtk.ContentFit.COVER)
        self.canvas_picture.set_can_shrink(True)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_draw_func(self._draw_canvas)
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.canvas_overlay = Gtk.Overlay()
        self.canvas_overlay.set_child(self.canvas_picture)
        self.canvas_overlay.add_overlay(self.canvas)
        self.canvas_frame.set_child(self.canvas_overlay)
        canvas_box.append(self.canvas_frame)
        hint = Gtk.Label(label="Selected: none", xalign=0)
        hint.add_css_class("dim-label")
        self.canvas_hint = hint
        canvas_box.append(hint)
        gesture_hint = Gtk.Label(label="Drag to move · right-drag to resize · click to expand its controls")
        gesture_hint.add_css_class("dim-label")
        canvas_box.append(gesture_hint)
        top.append(canvas_box)

        globals_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        globals_box.set_size_request(310, -1)
        globals_box.append(common.section("Global style", "One visual system for the desktop layer."))
        main_card = common.card()
        self.theme_dropdown = common.dropdown([(item, item.title()) for item in constants.WIDGET_THEMES],
                                               self.config.get("widgets.theme", "glass"))
        self.theme_dropdown.connect("notify::selected", lambda *_a: self._global_changed())
        main_card.append(common.row("Widget style", trailing=self.theme_dropdown))
        self.monitor_dropdown = common.dropdown(desktop.monitor_choices(),
                                                 self.config.get("widgets.monitor", "all"))
        self.monitor_dropdown.connect("notify::selected", lambda *_a: self._global_changed())
        main_card.append(common.row("Monitor", trailing=self.monitor_dropdown))
        self.layer_dropdown = common.dropdown([("bottom", "Bottom layer"), ("background", "Background")],
                                               self.config.get("widgets.layer", "bottom"))
        self.layer_dropdown.connect("notify::selected", lambda *_a: self._global_changed())
        main_card.append(common.row("Layer", trailing=self.layer_dropdown))
        self.opacity = common.scale(float(self.config.get("widgets.opacity", 0.88)), 0.3, 1.0, 0.02)
        self.opacity.connect("value-changed", lambda *_a: self._global_changed())
        main_card.append(common.row("Opacity", trailing=self.opacity))
        self.scale = common.scale(float(self.config.get("widgets.font_scale", 1.0)), 0.7, 1.6, 0.05)
        self.scale.connect("value-changed", lambda *_a: self._global_changed())
        main_card.append(common.row("Text scale", trailing=self.scale))
        self.font_entry = Gtk.Entry()
        self.font_entry.set_text(str(self.config.get("widgets.font_family", "")))
        self.font_entry.set_placeholder_text("System font")
        self.font_entry.connect("changed", lambda *_a: self._global_changed())
        main_card.append(common.row("Font family", "Used by every widget", trailing=self.font_entry))
        self.accent_button = common.color_button(str(self.config.get("widgets.accent", "") or "#7aa2ff"))
        self.accent_button.connect("notify::rgba", lambda *_a: self._global_changed())
        main_card.append(common.row("Accent override", trailing=self.accent_button))
        self.click_through = common.switch(bool(self.config.get("widgets.click_through", True)))
        self.click_through.connect("notify::active", lambda *_a: self._global_changed())
        main_card.append(common.row("Click through", "Only interactive widgets accept clicks",
                                    trailing=self.click_through))
        self.restore_login = common.switch(bool(self.config.get("widgets.restore_on_login", True)))
        self.restore_login.connect("notify::active", lambda *_a: self._global_changed())
        main_card.append(common.row("Restore on login", trailing=self.restore_login))
        self.snap_grid = common.switch(bool(self.config.get("widgets.snap_grid", True)))
        self.snap_grid.connect("notify::active", lambda *_a: self._global_changed())
        main_card.append(common.row("Snap to grid", "Align dragged widgets to a grid", trailing=self.snap_grid))
        self.grid_size = common.spin(float(self.config.get("widgets.grid_size", 2)), 1, 10, 1)
        self.grid_size.connect("value-changed", lambda *_a: self._global_changed())
        main_card.append(common.row("Grid size", "Percent of the monitor", trailing=self.grid_size))
        globals_box.append(main_card)
        top.append(globals_box)
        content.append(top)

        layout_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.preset_dropdown = common.dropdown(
            [(key, label) for key, (label, _items) in widgets.LAYOUT_PRESETS.items()],
            "dashboard",
        )
        layout_actions.append(self.preset_dropdown)
        layout_actions.append(common.button("Apply preset", icon="emblem-ok-symbolic",
                                            on_click=self.apply_layout_preset))
        layout_actions.append(common.button("Export", icon="document-save-symbolic",
                                            on_click=self.export_layout))
        layout_actions.append(common.button("Import", icon="document-open-symbolic",
                                            on_click=self.import_layout))
        layout_actions.append(common.button("Reset", icon="edit-undo-symbolic",
                                            on_click=self.reset_layout))
        list_head = common.section("Widget stack", "Click a widget to open its controls; use the action bar for quick edits.",
                                   trailing=layout_actions)
        content.append(list_head)
        selection_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        selection_bar.set_homogeneous(False)
        self.selection_status = Gtk.Label(label="Selected: none", xalign=0)
        self.selection_status.add_css_class("setting-title")
        self.selection_status.set_hexpand(False)
        selection_bar.append(self.selection_status)
        selection_bar.append(common.button("Duplicate", icon="edit-copy-symbolic",
                                          on_click=self.duplicate_selected))
        selection_bar.append(common.button("Delete", icon="user-trash-symbolic",
                                          css="destructive-action", on_click=self.remove_selected))
        selection_bar.append(common.button("Bring forward", icon="go-up-symbolic",
                                          on_click=lambda: self.move_selected(1)))
        selection_bar.append(common.button("Send back", icon="go-down-symbolic",
                                          on_click=lambda: self.move_selected(-1)))
        content.append(selection_bar)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.append(self.list_box)

        note = Gtk.Label(
            label="Widgets run in a separate process. If you close the studio they keep running; "
                  "use Stop or the edit toolbar to finish editing.",
            xalign=0, wrap=True,
        )
        note.add_css_class("dim-label")
        content.append(note)

        click = Gtk.GestureClick()
        click.connect("pressed", self._canvas_clicked)
        self.canvas.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.canvas.add_controller(drag)
        resize = Gtk.GestureDrag()
        resize.set_button(3)
        resize.connect("drag-begin", self._resize_begin)
        resize.connect("drag-update", self._resize_update)
        resize.connect("drag-end", self._resize_end)
        self.canvas.add_controller(resize)
        self._drag_start = None
        self._drag_active = None

    def _add_popover(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Add a widget", xalign=0)
        title.add_css_class("section-title")
        title.set_margin_bottom(5)
        box.append(title)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        with __import__("contextlib").suppress(Exception):
            listbox.set_activate_on_single_click(True)
        for kind, metadata in widgets.WIDGET_TYPES.items():
            row = Gtk.ListBoxRow()
            label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            label = Gtk.Label(label=metadata["name"], xalign=0)
            label.add_css_class("setting-title")
            subtitle = Gtk.Label(label=metadata["description"], xalign=0)
            subtitle.add_css_class("setting-subtitle")
            subtitle.set_ellipsize(3)
            label_box.append(label)
            label_box.append(subtitle)
            row.set_child(label_box)
            row.connect("activate", lambda _r, k=kind: self.add_item(k))
            listbox.append(row)
        box.append(listbox)
        popover.set_child(box)
        return popover

    # --- state --------------------------------------------------------------------

    def schedule_save(self) -> None:
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(300, self._save_now)

    def _save_now(self) -> bool:
        self._save_source = 0
        self.save()
        return False

    def save(self) -> None:
        self.items = [widgets.normalise_item(item) for item in self.items]
        self.config.set("widgets.items", self.items, save=False)
        self._collect_globals(save=False)
        self.config.save()
        self.canvas.queue_draw()
        self._update_canvas_hint()

    def _collect_globals(self, *, save: bool = True) -> None:
        self.config.set("widgets.theme", common.selected_value(
            self.theme_dropdown, [(item, item.title()) for item in constants.WIDGET_THEMES], "glass"), save=False)
        self.config.set("widgets.monitor", common.selected_value(
            self.monitor_dropdown, desktop.monitor_choices(), "all"), save=False)
        self.config.set("widgets.layer", "bottom" if self.layer_dropdown.get_selected() == 0 else "background", save=False)
        self.config.set("widgets.opacity", round(float(self.opacity.get_value()), 2), save=False)
        self.config.set("widgets.font_scale", round(float(self.scale.get_value()), 2), save=False)
        self.config.set("widgets.font_family", self.font_entry.get_text().strip(), save=False)
        rgba = self.accent_button.get_rgba()
        accent = ""
        if rgba and not (abs(rgba.red - 0x7a / 255) < 0.01 and abs(rgba.green - 0xa2 / 255) < 0.01
                         and abs(rgba.blue - 0xff / 255) < 0.01):
            accent = "#%02x%02x%02x" % (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))
        self.config.set("widgets.accent", accent, save=False)
        self.config.set("widgets.click_through", self.click_through.get_active(), save=False)
        self.config.set("widgets.snap_grid", self.snap_grid.get_active(), save=False)
        self.config.set("widgets.grid_size", int(self.grid_size.get_value()), save=False)
        self.config.set("widgets.restore_on_login", self.restore_login.get_active(), save=False)
        if save:
            self.config.save()

    def _global_changed(self) -> None:
        if self._loading:
            return
        self._collect_globals()
        self.canvas.queue_draw()

    def refresh(self) -> None:
        self._loading = True
        try:
            self.items = widgets.normalise_items(self.config.get("widgets.items", []))
            self._select_controls()
            self._rebuild_list()
            self._refresh_status()
            self._load_canvas_background()
            self._update_canvas_hint()
            self.canvas.queue_draw()
        finally:
            self._loading = False

    def _select_controls(self) -> None:
        self.theme_dropdown.set_selected(constants.WIDGET_THEMES.index(
            self.config.get("widgets.theme", "glass")) if self.config.get("widgets.theme", "glass") in constants.WIDGET_THEMES else 0)
        monitor = self.config.get("widgets.monitor", "all")
        for index, (value, _label) in enumerate(desktop.monitor_choices()):
            if value == monitor:
                self.monitor_dropdown.set_selected(index)
                break
        self.layer_dropdown.set_selected(0 if self.config.get("widgets.layer", "bottom") == "bottom" else 1)
        self.opacity.set_value(float(self.config.get("widgets.opacity", 0.88)))
        self.scale.set_value(float(self.config.get("widgets.font_scale", 1.0)))
        self.font_entry.set_text(str(self.config.get("widgets.font_family", "")))
        self.click_through.set_active(bool(self.config.get("widgets.click_through", True)))
        self.snap_grid.set_active(bool(self.config.get("widgets.snap_grid", True)))
        self.grid_size.set_value(float(self.config.get("widgets.grid_size", 2)))
        self.restore_login.set_active(bool(self.config.get("widgets.restore_on_login", True)))

    def _rebuild_list(self) -> None:
        for child in list(self.list_box):
            self.list_box.remove(child)
        self._rows = {}
        for item in self.items:
            row = WidgetEditorRow(self, item)
            self._rows[item["id"]] = row
            self.list_box.append(row)
        if not self.items:
            label = Gtk.Label(label="No widgets yet. Use the + button to add one.", xalign=0)
            label.add_css_class("dim-label")
            self.list_box.append(label)

    def _refresh_status(self) -> None:
        status = widget_daemon.status()
        if status.get("running"):
            self.host_status.set_text(
                f"Running · {'edit mode' if status.get('edit') else 'locked'} · "
                f"{status.get('windows', 0)} display(s) · pid {status.get('pid')}"
            )
        else:
            layer = "layer-shell ready" if desktop.has_layer_shell() else "no layer-shell in this session"
            self.host_status.set_text(f"Stopped · {layer}")

    # --- canvas -------------------------------------------------------------------

    def _load_canvas_background(self) -> None:
        path = wallpaper.current_path()
        if not path:
            self.canvas_picture.set_paintable(None)
            return
        item = self.app.library.item(path)
        kind = item.kind if item else ("video" if path.lower().endswith(tuple(constants.VIDEO_EXTENSIONS)) else "image")
        mtime = item.mtime if item else 0
        size = item.size if item else 0

        def loaded(texture):
            if texture is not None:
                self._canvas_texture = texture
                self.canvas_picture.set_paintable(texture)

        self.app.thumbs.get_preview(path, mtime, size, kind, loaded)

    def _draw_canvas(self, _area, cr, width, height) -> None:
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        if not self.items:
            return
        global_accent = self.config.get("widgets.accent") or "#7aa2ff"
        if self.snap_grid.get_active():
            grid = max(1, int(self.grid_size.get_value())) / 100
            cr.set_source_rgba(1, 1, 1, 0.055)
            cr.set_line_width(1)
            step = grid * width
            x = step
            while x < width:
                cr.move_to(x, 0)
                cr.line_to(x, height)
                x += step
            step = grid * height
            y = step
            while y < height:
                cr.move_to(0, y)
                cr.line_to(width, y)
                y += step
            cr.stroke()
        for index, item in enumerate(self.items):
            accent = item.get("accent") or global_accent
            rgba = Gdk.RGBA()
            with __import__("contextlib").suppress(Exception):
                rgba.parse(accent)
            if not item.get("enabled", True):
                continue
            x = item["x"] * width
            y = item["y"] * height
            w = item["w"] * width
            h = item["h"] * height
            selected = index == self.selected_index
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 0.24 if selected else 0.14)
            self._rounded_rect(cr, x, y, w, h, 8)
            cr.fill()
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 0.95 if selected else 0.55)
            cr.set_line_width(2 if selected else 1)
            self._rounded_rect(cr, x, y, w, h, 8)
            cr.stroke()
            metadata = widgets.WIDGET_TYPES.get(item["type"], {})
            cr.set_source_rgba(1, 1, 1, 0.94 if selected else 0.78)
            cr.select_font_face("Sans", 0, 1 if selected else 0)
            cr.set_font_size(11)
            text = metadata.get("name", item["type"])
            cr.move_to(x + 9, y + 20)
            cr.show_text(text)
            cr.set_font_size(8)
            cr.set_source_rgba(1, 1, 1, 0.58)
            cr.move_to(x + 9, y + 34)
            cr.show_text(f"{int(item['w'] * 100)}% × {int(item['h'] * 100)}%")

    @staticmethod
    def _rounded_rect(cr, x, y, width, height, radius):
        radius = min(radius, width / 2, height / 2)
        cr.new_sub_path()
        cr.arc(x + width - radius, y + radius, radius, -1.5708, 0)
        cr.arc(x + width - radius, y + height - radius, radius, 0, 1.5708)
        cr.arc(x + radius, y + height - radius, radius, 1.5708, 3.1416)
        cr.arc(x + radius, y + radius, radius, 3.1416, 4.7124)
        cr.close_path()

    def _canvas_hit(self, x: float, y: float) -> int | None:
        width = self.canvas.get_width() or 1
        height = self.canvas.get_height() or 1
        nx, ny = x / width, y / height
        for index in range(len(self.items) - 1, -1, -1):
            item = self.items[index]
            if not item.get("enabled", True):
                continue
            if item["x"] <= nx <= item["x"] + item["w"] and item["y"] <= ny <= item["y"] + item["h"]:
                return index
        return None

    def _canvas_clicked(self, _gesture, _n, x, y) -> None:
        index = self._canvas_hit(x, y)
        if index is not None:
            self.selected_index = index
            self._focus_row(self.items[index])
            self._update_canvas_hint()
            self.canvas.queue_draw()

    def _drag_begin(self, _gesture, x, y) -> None:
        index = self._canvas_hit(x, y)
        if index is None:
            self._drag_active = None
            return
        self.selected_index = index
        item = self.items[index]
        self._focus_row(item)
        self._drag_active = index
        self._drag_start = (item["x"], item["y"], x, y)
        self._update_canvas_hint()
        self.canvas.queue_draw()

    def _drag_update(self, _gesture, offset_x, offset_y) -> None:
        if self._drag_active is None or self._drag_start is None:
            return
        item = self.items[self._drag_active]
        start_x, start_y, _x, _y = self._drag_start
        width = self.canvas.get_width() or 1
        height = self.canvas.get_height() or 1
        x = max(0.0, min(1 - item["w"], start_x + offset_x / width))
        y = max(0.0, min(1 - item["h"], start_y + offset_y / height))
        if self.snap_grid.get_active():
            grid = max(1, int(self.grid_size.get_value())) / 100
            x = round(x / grid) * grid
            y = round(y / grid) * grid
            x = max(0.0, min(1 - item["w"], x))
            y = max(0.0, min(1 - item["h"], y))
        item["x"] = round(x, 4)
        item["y"] = round(y, 4)
        self._refresh_row(item)
        self.canvas.queue_draw()

    def _drag_end(self, _gesture, _offset_x, _offset_y) -> None:
        if self._drag_active is not None:
            self.schedule_save()
        self._drag_active = None
        self._drag_start = None
        self._update_canvas_hint()

    def _resize_begin(self, _gesture, x, y) -> None:
        index = self._canvas_hit(x, y)
        if index is None:
            self._resize_active = None
            return
        item = self.items[index]
        self.selected_index = index
        self._focus_row(item)
        self._resize_active = index
        self._resize_start = (item["x"], item["y"], item["w"], item["h"])
        self._update_canvas_hint()
        self.canvas.queue_draw()

    def _resize_update(self, _gesture, offset_x, offset_y) -> None:
        if self._resize_active is None or self._resize_start is None:
            return
        item = self.items[self._resize_active]
        start_x, start_y, start_w, start_h = self._resize_start
        width = self.canvas.get_width() or 1
        height = self.canvas.get_height() or 1
        new_w = max(0.06, min(0.9, start_w + offset_x / width))
        new_h = max(0.05, min(0.9, start_h + offset_y / height))
        new_w = min(new_w, 1 - start_x)
        new_h = min(new_h, 1 - start_y)
        item["w"] = round(new_w, 4)
        item["h"] = round(new_h, 4)
        self._refresh_row(item)
        self.canvas.queue_draw()

    def _resize_end(self, _gesture, _offset_x, _offset_y) -> None:
        if self._resize_active is not None:
            self.schedule_save()
        self._resize_active = None
        self._resize_start = None
        self._update_canvas_hint()

    def _focus_row(self, item: dict) -> None:
        row = self._rows.get(item.get("id", ""))
        if row is not None:
            row.set_expanded(True)
            with __import__("contextlib").suppress(Exception):
                row.grab_focus()

    def _selected_item(self) -> dict | None:
        if 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def set_selected_item(self, item: dict) -> None:
        if item in self.items:
            self.selected_index = self.items.index(item)
            self._update_canvas_hint()
            self.canvas.queue_draw()

    def _focus_item(self, item: dict) -> None:
        self.set_selected_item(item)
        row = self._rows.get(item.get("id", ""))
        if row is not None:
            row.set_expanded(True)

    def duplicate_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            self.app.toast("Select a widget first")
            return
        self.duplicate_item(item)

    def remove_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            self.app.toast("Select a widget first")
            return
        self.remove_item(item)

    def move_selected(self, offset: int) -> None:
        item = self._selected_item()
        if item is None:
            self.app.toast("Select a widget first")
            return
        self.move_item(item, offset)

    def _refresh_row(self, item: dict) -> None:
        for child in self.list_box:
            if isinstance(child, WidgetEditorRow) and child.item is item:
                with __import__("contextlib").suppress(Exception):
                    child.x.set_value(round(item["x"] * 100, 1))
                    child.y.set_value(round(item["y"] * 100, 1))
                    child.w.set_value(round(item["w"] * 100, 1))
                    child.h.set_value(round(item["h"] * 100, 1))
                break

    def _update_canvas_hint(self) -> None:
        if 0 <= self.selected_index < len(self.items):
            item = self.items[self.selected_index]
            name = widgets.WIDGET_TYPES.get(item["type"], {}).get("name", item["type"])
            self.canvas_hint.set_text(f"Selected: {name} · x {item['x']:.2f}, y {item['y']:.2f}")
            if hasattr(self, "selection_status"):
                self.selection_status.set_text(f"Selected: {name}")
        else:
            self.canvas_hint.set_text("Selected: none")
            if hasattr(self, "selection_status"):
                self.selection_status.set_text("Selected: none")

    # --- actions ------------------------------------------------------------------

    def add_item(self, kind: str) -> None:
        item = widgets.new_item(kind, self.items)
        self.items.append(item)
        self.selected_index = len(self.items) - 1
        self._rebuild_list()
        self.save()
        self._focus_item(item)
        self._update_canvas_hint()
        self.canvas.queue_draw()

    def remove_item(self, item: dict) -> None:
        self.items = [entry for entry in self.items if entry.get("id") != item.get("id")]
        self.selected_index = min(self.selected_index, max(0, len(self.items) - 1))
        self._rebuild_list()
        self.save()
        self.canvas.queue_draw()

    def duplicate_item(self, item: dict) -> None:
        clone = json.loads(json.dumps(item))
        clone["id"] = f"{item.get('type', 'widget')}-{uuid.uuid4().hex[:6]}"
        clone["x"] = round(min(0.94 - clone.get("w", 0.2), clone.get("x", 0.0) + 0.025), 4)
        clone["y"] = round(min(0.94 - clone.get("h", 0.15), clone.get("y", 0.0) + 0.025), 4)
        index = self.items.index(item) if item in self.items else len(self.items)
        self.items.insert(index + 1, clone)
        self.selected_index = index + 1
        self._rebuild_list()
        self.save()
        self._focus_item(clone)
        self.canvas.queue_draw()
        self.app.toast("Widget duplicated")

    def move_item(self, item: dict, offset: int) -> None:
        if item not in self.items:
            return
        index = self.items.index(item)
        target = max(0, min(len(self.items) - 1, index + offset))
        if target == index:
            return
        self.items.insert(target, self.items.pop(index))
        self.selected_index = target
        self._rebuild_list()
        self.save()
        self.canvas.queue_draw()

    def apply_layout_preset(self) -> None:
        name = common.selected_value(
            self.preset_dropdown,
            [(key, label) for key, (label, _items) in widgets.LAYOUT_PRESETS.items()],
            "dashboard",
        )
        self.items = widgets.layout_preset(name)
        self.selected_index = 0
        self.save()
        self.refresh()
        self.app.toast(f"{widgets.LAYOUT_PRESETS[name][0]} layout applied")

    def _apply_worker(self, edit: bool) -> None:
        try:
            result = widget_daemon.start(edit=edit)
            GLib.idle_add(self._applied, result, None, edit)
        except Exception as error:
            GLib.idle_add(self._applied, None, str(error), edit)

    def _applied(self, result, error, edit: bool) -> bool:
        self._refresh_status()
        if error:
            self.app.toast(f"Widget host: {error}"[:360])
        else:
            self.app.toast("Desktop widgets editing — drag and save on the desktop" if edit else "Desktop widgets applied")
            if edit:
                GLib.timeout_add(700, self._minimise)
        return False

    def apply(self) -> None:
        self.save()
        self.config.set("widgets.enabled", True)
        self.config.save()
        threading.Thread(target=self._apply_worker, args=(False,), daemon=True).start()

    def edit_on_desktop(self) -> None:
        self.save()
        self.config.set("widgets.enabled", True)
        self.config.save()
        threading.Thread(target=self._apply_worker, args=(True,), daemon=True).start()

    def _minimise(self) -> bool:
        root = self.get_root()
        if root is not None:
            with __import__("contextlib").suppress(Exception):
                root.minimize()
        return False

    def stop(self) -> None:
        widget_daemon.stop()
        self.config.set("widgets.enabled", False)
        self.config.save()
        self._refresh_status()
        self.app.toast("Desktop widgets stopped")

    def export_layout(self) -> None:
        self.save()
        dialog = Gtk.FileDialog()
        dialog.set_title("Export widget layout")
        dialog.set_initial_name("1337-widgets.json")
        dialog.save(self.get_root(), None, self._export_done)

    def _export_done(self, dialog, result) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        path = file.get_path() if file else None
        if not path:
            return
        payload = {
            "format": "1337-widget-layout",
            "version": 1,
            "items": self.items,
            "style": {
                "theme": self.config.get("widgets.theme", "glass"),
                "opacity": self.config.get("widgets.opacity", 0.88),
                "font_scale": self.config.get("widgets.font_scale", 1.0),
                "font_family": self.config.get("widgets.font_family", ""),
                "accent": self.config.get("widgets.accent", ""),
                "layer": self.config.get("widgets.layer", "bottom"),
            },
        }
        write_json(path, payload)
        self.app.toast("Widget layout exported")

    def import_layout(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Import widget layout")
        dialog.open(self.get_root(), None, self._import_done)

    def _import_done(self, dialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        path = file.get_path() if file else None
        if not path:
            return
        payload = read_json(path, {})
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            self.app.toast("That file is not a 1337-Customizer widget layout")
            return
        self.items = widgets.normalise_items(payload["items"])
        self.selected_index = 0
        self.save()
        self.refresh()
        self.app.toast(f"Loaded {len(self.items)} widget(s)")

    def reset_layout(self) -> None:
        self.items = widgets.default_items()
        self.selected_index = 0
        self.save()
        self.refresh()
        self.app.toast("Default widget layout restored")

    def on_shown(self) -> None:
        self._refresh_status()
