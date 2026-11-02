"""Small UI helpers shared by the studio pages."""

from __future__ import annotations

from typing import Callable, Iterable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402


def page_scaffold(title: str, subtitle: str = "", *, actions: Iterable[Gtk.Widget] = ()):
    """Return (outer, content). The outer expands; content is a scrolled column."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("page-scroll")
    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    header.add_css_class("page-header")
    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    labels.set_hexpand(True)
    title_label = Gtk.Label(label=title, xalign=0)
    title_label.add_css_class("page-title")
    subtitle_label = Gtk.Label(label=subtitle, xalign=0)
    subtitle_label.add_css_class("page-subtitle")
    subtitle_label.set_wrap(True)
    labels.append(title_label)
    if subtitle:
        labels.append(subtitle_label)
    header.append(labels)
    for action in actions:
        header.append(action)
    outer.append(header)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)
    viewport = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    viewport.set_margin_top(8)
    viewport.set_margin_bottom(28)
    viewport.set_margin_start(28)
    viewport.set_margin_end(28)
    scrolled.set_child(viewport)
    outer.append(scrolled)
    return outer, viewport


def section(title: str, subtitle: str = "", *, trailing: Gtk.Widget | None = None) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    labels.set_hexpand(True)
    title_label = Gtk.Label(label=title, xalign=0)
    title_label.add_css_class("section-title")
    labels.append(title_label)
    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        sub.add_css_class("section-subtitle")
        labels.append(sub)
    head.append(labels)
    if trailing is not None:
        head.append(trailing)
    box.append(head)
    return box


def card(*children: Gtk.Widget, css: str = "glass-panel", spacing: int = 10) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    if css:
        box.add_css_class(css)
    for child in children:
        box.append(child)
    return box


def row(title: str, subtitle: str = "", *, trailing: Gtk.Widget | None = None,
        css: str = "setting-row") -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    if css:
        box.add_css_class(css)
    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    labels.set_hexpand(True)
    label = Gtk.Label(label=title, xalign=0)
    label.add_css_class("setting-title")
    labels.append(label)
    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0)
        sub.set_wrap(True)
        sub.add_css_class("setting-subtitle")
        labels.append(sub)
    box.append(labels)
    if trailing:
        trailing.set_valign(Gtk.Align.CENTER)
        box.append(trailing)
    return box


def button(label: str, *, icon: str | None = None, css: str | None = None,
           tooltip: str | None = None, on_click: Callable | None = None) -> Gtk.Button:
    if icon and label:
        widget = Gtk.Button()
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.append(Gtk.Image.new_from_icon_name(icon))
        text = Gtk.Label(label=label)
        content.append(text)
        widget.set_child(content)
        widget.set_tooltip_text(tooltip or label)
    elif icon:
        widget = Gtk.Button(icon_name=icon)
        if tooltip:
            widget.set_tooltip_text(tooltip)
    else:
        widget = Gtk.Button(label=label)
        if tooltip:
            widget.set_tooltip_text(tooltip)
    if css:
        widget.add_css_class(css)
    if on_click:
        widget.connect("clicked", lambda _button: on_click())
    return widget


def pill(label: str, *, active: bool = False) -> Gtk.Label:
    widget = Gtk.Label(label=label)
    widget.add_css_class("pill")
    if active:
        widget.add_css_class("active")
    return widget


def badge(label: str, kind: str = "accent") -> Gtk.Label:
    widget = Gtk.Label(label=label)
    widget.add_css_class({"accent": "badge-accent", "ok": "badge-ok",
                          "warn": "badge-warn"}.get(kind, "badge-accent"))
    return widget


def stat(value: str, label: str) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    box.add_css_class("stat-card")
    value_label = Gtk.Label(label=value, xalign=0)
    value_label.add_css_class("stat-value")
    label_label = Gtk.Label(label=label, xalign=0)
    label_label.add_css_class("stat-label")
    box.append(value_label)
    box.append(label_label)
    return box


def dropdown(items: list[tuple[str, str]], selected: str | None = None) -> Gtk.DropDown:
    labels = [label for _value, label in items]
    model = Gtk.StringList.new(labels)
    widget = Gtk.DropDown(model=model)
    for index, (value, _label) in enumerate(items):
        if value == selected:
            widget.set_selected(index)
            break
    return widget


def selected_value(widget: Gtk.DropDown, items: list[tuple[str, str]], fallback: str = "") -> str:
    index = widget.get_selected()
    if 0 <= index < len(items):
        return items[index][0]
    return fallback


def switch(active: bool = False) -> Gtk.Switch:
    widget = Gtk.Switch()
    widget.set_active(active)
    widget.set_valign(Gtk.Align.CENTER)
    return widget


def spin(value: float, minimum: float, maximum: float, step: float = 1.0,
         digits: int = 0) -> Gtk.SpinButton:
    widget = Gtk.SpinButton.new_with_range(minimum, maximum, step)
    widget.set_digits(digits)
    widget.set_value(value)
    widget.set_valign(Gtk.Align.CENTER)
    return widget


def scale(value: float, minimum: float, maximum: float, step: float = 0.01) -> Gtk.Scale:
    widget = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimum, maximum, step)
    widget.set_value(value)
    widget.set_hexpand(True)
    widget.set_draw_value(True)
    return widget


def file_uri(path: str) -> str:
    from urllib.parse import quote

    return "file://" + quote(str(path))


def color_button(color: str) -> Gtk.ColorDialogButton:
    dialog = Gtk.ColorDialog()
    button = Gtk.ColorDialogButton(dialog=dialog)
    rgba = Gdk.RGBA()
    rgba.parse(color or "#7aa2ff")
    button.set_rgba(rgba)
    return button


def font_button(description: str = "") -> Gtk.FontDialogButton:
    dialog = Gtk.FontDialog()
    button = Gtk.FontDialogButton(dialog=dialog)
    if description:
        from gi.repository import Pango

        button.set_font_desc(Pango.FontDescription.from_string(description))
    return button


def toast(app, message: str) -> None:
    if hasattr(app, "toast"):
        app.toast(message)


def wrap_scroll(widget: Gtk.Widget, height: int = 260) -> Gtk.ScrolledWindow:
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_min_content_height(height)
    scroll.set_child(widget)
    return scroll


def labelled_entry(value: str = "", placeholder: str = "") -> Gtk.Entry:
    entry = Gtk.Entry()
    entry.set_text(value)
    if placeholder:
        entry.set_placeholder_text(placeholder)
    return entry
