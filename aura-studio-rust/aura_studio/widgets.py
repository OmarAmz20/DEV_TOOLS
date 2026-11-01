"""Reusable GTK widgets and the small amount of CSS Aura itself uses."""
from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from . import color  # noqa: E402

APP_CSS = b"""
.aura-page-title { font-size: 30px; font-weight: 800; letter-spacing: -0.6px; }
.aura-page-sub { font-size: 14px; opacity: 0.62; }
.aura-section-title { font-size: 17px; font-weight: 700; }
.aura-hero { border-radius: 18px; background-color: @card_bg_color; padding: 16px; }
.aura-hero picture { border-radius: 14px; }
.aura-thumb { padding: 0; border-radius: 12px; background-color: @card_bg_color; }
.aura-thumb picture { border-radius: 10px; }
.aura-thumb.selected { outline: 3px solid @accent_bg_color; outline-offset: 2px; }
.aura-badge {
  background: rgba(0, 0, 0, 0.66); color: white; border-radius: 7px;
  padding: 2px 7px; font-size: 0.75em; font-weight: 800; letter-spacing: 0.4px;
}
.aura-badge.current { background: @accent_bg_color; color: @accent_fg_color; }
.aura-star {
  background: rgba(0, 0, 0, 0.48); color: white; min-width: 30px; min-height: 30px;
  padding: 0; border-radius: 999px; margin: 7px;
}
.aura-star:hover { background: rgba(0, 0, 0, 0.70); }
.aura-star.active { background: @accent_bg_color; color: @accent_fg_color; }
.aura-card { background-color: @card_bg_color; border-radius: 16px; padding: 16px; }
.aura-inset { background-color: @view_bg_color; border-radius: 12px; }
.aura-preview { border-radius: 12px; }
.aura-mono { font-family: monospace; }
.aura-hint { opacity: 0.62; font-size: 0.9em; }
.aura-contrast-ok { color: @success_color; font-weight: 700; }
.aura-contrast-warn { color: @warning_color; font-weight: 700; }
.aura-sidebar { background-color: @sidebar_bg_color; }
.aura-sidebar row { border-radius: 9px; margin: 2px 8px; }
.aura-sidebar row:selected { background-color: alpha(@accent_bg_color, 0.22); }
.aura-current-dot { color: @success_color; }
.aura-big-number { font-size: 24px; font-weight: 800; }
"""


def app_css_provider():
    provider = Gtk.CssProvider()
    provider.load_from_data(APP_CSS)
    return provider


# --- little widgets ---------------------------------------------------------------

def swatch(hexcolor, size=22, radius=6):
    area = Gtk.DrawingArea(content_width=size, content_height=size,
                           tooltip_text=hexcolor)
    area.colour = hexcolor
    area.radius = radius

    def draw(_area, cr, width, height):
        rgb = color.parse_hex(area.colour, (0, 0, 0))
        rounded(cr, 0.5, 0.5, width - 1, height - 1, area.radius)
        cr.set_source_rgb(*rgb)
        cr.fill()
        rounded(cr, 0.5, 0.5, width - 1, height - 1, area.radius)
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.35)
        cr.set_line_width(1)
        cr.stroke()

    area.set_draw_func(draw)
    return area


def rounded(cr, x, y, width, height, radius):
    radius = max(0, min(radius, width / 2, height / 2))
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _rgba(cr, hexcolor, alpha=1.0):
    rgb = color.parse_hex(hexcolor, (0, 0, 0))
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)


class SwatchRow(Gtk.Box):
    """A compact strip of named palette colours."""

    def __init__(self, keys=("paper", "accent", "ink", "muted", "sheet"), size=22, spacing=6):
        super().__init__(spacing=spacing)
        self.keys = keys
        self.size = size
        self.colours = {}

    def set_palette(self, palette):
        while child := self.get_first_child():
            self.remove(child)
        for key in self.keys:
            value = palette.get(key, "#000000")
            self.colours[key] = value
            self.append(swatch(value, self.size))


class PalettePreview(Gtk.DrawingArea):
    """A tiny abstract desktop drawn with a palette, not a screenshot."""

    def __init__(self, palette=None, height=176):
        super().__init__(content_height=height, hexpand=True)
        self.set_size_request(140, height)
        self.add_css_class("aura-preview")
        self.palette = palette
        self.set_draw_func(self._draw)

    def set_palette(self, palette):
        self.palette = palette
        self.queue_draw()

    def _draw(self, _area, cr, width, height):
        if not self.palette:
            _rgba(cr, "#777777", 0.12)
            rounded(cr, 0, 0, width, height, 12)
            cr.fill()
            return
        p = self.palette
        _rgba(cr, p["paper2"])
        cr.paint()

        # soft aura circles behind the window
        cr.save()
        cr.rectangle(0, 0, width, height)
        cr.clip()
        _rgba(cr, p["accent"], 0.20)
        cr.arc(width * 0.83, height * 0.12, height * 0.62, 0, math.tau)
        cr.fill()
        _rgba(cr, p["accent"], 0.08)
        cr.arc(width * 0.12, height * 0.95, height * 0.50, 0, math.tau)
        cr.fill()
        cr.restore()

        margin = max(10, width * 0.045)
        x, y = margin, margin * 0.85
        w, h = width - margin * 2, height - margin * 1.7
        radius = 12

        _rgba(cr, "#000000" if color.contrast(p["ink"], p["paper"]) < 8 else p["ink"], 0.16)
        rounded(cr, x + 3, y + 4, w, h, radius)
        cr.fill()

        _rgba(cr, p["sheet"])
        rounded(cr, x, y, w, h, radius)
        cr.fill()

        cr.save()
        rounded(cr, x, y, w, h, radius)
        cr.clip()

        header = h * 0.16
        _rgba(cr, p["paper2"])
        cr.rectangle(x, y, w, header)
        cr.fill()

        # window controls
        for i, key in enumerate(("accent", "muted", "ink")):
            _rgba(cr, p[key], 0.75 if key != "ink" else 0.35)
            cr.arc(x + 14 + i * 12, y + header / 2, 3.1, 0, math.tau)
            cr.fill()

        # title bar content
        _rgba(cr, p["ink"], 0.35)
        rounded(cr, x + 54, y + header / 2 - 3, w * 0.24, 6, 3)
        cr.fill()

        sidebar = w * 0.22
        _rgba(cr, p["paper"])
        cr.rectangle(x, y + header, sidebar, h - header)
        cr.fill()
        for i in range(4):
            _rgba(cr, p["accent"] if i == 0 else p["muted"], 0.75 if i == 0 else 0.35)
            rounded(cr, x + 12, y + header + 14 + i * 16, sidebar - 24, 7, 3.5)
            cr.fill()

        left = x + sidebar
        content_w = w - sidebar
        # heading
        _rgba(cr, p["ink"], 0.92)
        rounded(cr, left + 18, y + header + 16, content_w * 0.42, 10, 5)
        cr.fill()
        _rgba(cr, p["muted"], 0.55)
        rounded(cr, left + 18, y + header + 34, content_w * 0.62, 5, 2.5)
        cr.fill()
        rounded(cr, left + 18, y + header + 44, content_w * 0.50, 5, 2.5)
        cr.fill()

        # accent card and button
        card_y = y + header + 62
        card_h = h - (card_y - y) - 16
        _rgba(cr, p["accent"], 0.16)
        rounded(cr, left + 18, card_y, content_w * 0.55, card_h, 8)
        cr.fill()
        _rgba(cr, p["accent"])
        rounded(cr, left + 28, card_y + 12, content_w * 0.24, 18, 9)
        cr.fill()
        _rgba(cr, p["on_accent"])
        rounded(cr, left + 36, card_y + 19, content_w * 0.12, 4, 2)
        cr.fill()
        _rgba(cr, p["ink"], 0.30)
        for i in range(3):
            rounded(cr, left + 30, card_y + 42 + i * 10, content_w * (0.36 - i * 0.06), 4, 2)
            cr.fill()

        # a little graph
        _rgba(cr, p["accent"], 0.72)
        base_x = left + content_w * 0.70
        base_y = y + h - 28
        points = [(0, 0), (0.18, -18), (0.36, -9), (0.54, -32), (0.72, -22), (0.90, -44)]
        for i, (px, py) in enumerate(points):
            cx = base_x + px * (content_w * 0.22)
            cy = base_y + py * (card_h / 70)
            if i:
                cr.line_to(cx, cy)
            else:
                cr.move_to(cx, cy)
        cr.set_line_width(2.5)
        cr.stroke()
        cr.restore()


class PaletteCard(Gtk.Box):
    """Light or dark preview + named colours + contrast summary."""

    def __init__(self, title, mode):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.mode = mode
        self.add_css_class("aura-card")
        self.set_margin_top(2)
        self.set_margin_bottom(2)

        header = Gtk.Box(spacing=8)
        label = Gtk.Label(label=title, xalign=0, hexpand=True)
        label.add_css_class("aura-section-title")
        self.contrast_badge = Gtk.Label(label="")
        self.contrast_badge.add_css_class("aura-hint")
        header.append(label)
        header.append(self.contrast_badge)
        self.append(header)

        self.preview = PalettePreview()
        self.preview.set_hexpand(True)
        self.append(self.preview)

        self.swatches = SwatchRow(("paper", "paper2", "sheet", "ink", "muted", "accent"),
                                  size=20, spacing=5)
        self.append(self.swatches)

        self.contrast_line = Gtk.Label(xalign=0, wrap=True)
        self.contrast_line.add_css_class("aura-hint")
        self.append(self.contrast_line)
        self.palette = None

    def set_palette(self, palette):
        self.palette = palette
        self.preview.set_palette(palette)
        self.swatches.set_palette(palette)
        body = color.contrast(palette["ink"], palette["paper"])
        accent = color.contrast(palette["accent_text"], palette["paper"])
        grade = color.contrast_label(min(body, accent))
        self.contrast_badge.set_label(grade)
        self.contrast_badge.set_tooltip_text(
            f"Text {body:.1f}:1 ({color.contrast_label(body)}) · "
            f"accent text {accent:.1f}:1 ({color.contrast_label(accent)})")
        self.contrast_line.set_label(f"Text {body:.1f}:1 · accent {accent:.1f}:1")


def page_header(title, subtitle, suffix=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    heading = Gtk.Label(label=title, xalign=0)
    heading.add_css_class("aura-page-title")
    box.append(heading)
    sub = Gtk.Label(label=subtitle, xalign=0, wrap=True)
    sub.add_css_class("aura-page-sub")
    box.append(sub)
    if suffix is not None:
        outer = Gtk.Box(spacing=16)
        outer.append(box)
        box.set_hexpand(True)
        suffix.set_valign(Gtk.Align.CENTER)
        outer.append(suffix)
        return outer
    return box


def button(label=None, icon_name=None, tooltip=None, css=None):
    """A button that can show an icon *and* a label (unlike Gtk.Button's properties)."""
    widget = Gtk.Button()
    if label and icon_name:
        widget.set_child(Adw.ButtonContent(icon_name=icon_name, label=label))
    elif label:
        widget.set_label(label)
    elif icon_name:
        widget.set_icon_name(icon_name)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    if css:
        widget.add_css_class(css)
    return widget


def icon_button(icon_name, tooltip, callback, css=None):
    button = Gtk.Button(icon_name=icon_name, tooltip_text=tooltip)
    button.add_css_class("flat")
    if css:
        button.add_css_class(css)
    button.connect("clicked", callback)
    return button


def set_colour_button(button, hexcolor):
    rgba = Gdk.RGBA()
    rgb = color.parse_hex(hexcolor)
    if rgb:
        rgba.red, rgba.green, rgba.blue, rgba.alpha = (*rgb, 1.0)
        button.set_rgba(rgba)


def colour_button_hex(button):
    rgba = button.get_rgba()
    return color.rgb_hex((rgba.red, rgba.green, rgba.blue))


def clear_box(widget):
    while child := widget.get_first_child():
        widget.remove(child)
