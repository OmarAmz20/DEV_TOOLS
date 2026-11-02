"""Desktop widget host — a separate crash-isolated GTK4 process."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import constants, desktop, widgets
from .util import (
    atomic_write_text,
    ensure_gi_paths,
    layer_shell_environment,
    pid_alive,
    popen,
    read_json,
    read_pid,
    stop_pid,
    write_json,
    write_pid,
)

ensure_gi_paths()

# A layer-shell GTK process must preload libgtk4-layer-shell before libwayland.
# The manager sets this up, but re-exec once when the module is run directly.
if __name__ == "__main__" and not os.environ.get("LD_PRELOAD"):
    from .util import find_layer_shell_library

    if find_layer_shell_library():
        environment = layer_shell_environment()
        environment["_LEET_LAYER_READY"] = "1"
        os.execvpe(
            sys.executable,
            [sys.executable, "-m", "leet_customizer.widget_daemon", *sys.argv[1:]],
            environment,
        )

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell  # type: ignore
except Exception:  # pragma: no cover - non-wlroots fallback
    Gtk4LayerShell = None

try:
    import cairo  # type: ignore
except Exception:  # pragma: no cover
    cairo = None

from .config import Config  # noqa: E402
from .widgets import WIDGET_TYPES, WidgetCard, item_type, normalise_items  # noqa: E402


def _daemon_pids() -> list[int]:
    """Find widget-host processes, including stale ones whose PID file vanished."""
    pids: list[int] = []
    current = os.getpid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == current:
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        parts = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
        if not parts:
            continue
        executable = Path(parts[0]).name
        # Match only real Python widget-host processes, never a shell command
        # that merely mentions the module in its arguments.
        is_module = (executable.startswith("python") and len(parts) > 2
                     and parts[1] == "-m" and parts[2] == "leet_customizer.widget_daemon")
        is_script = (executable.startswith("python") and len(parts) > 1
                     and Path(parts[1]).name == "widget_daemon.py")
        if is_module or is_script:
            pids.append(pid)
    return pids


def running() -> bool:
    return bool(read_pid(constants.WIDGET_PID) or _daemon_pids())


def status() -> dict:
    pid = read_pid(constants.WIDGET_PID)
    pids = _daemon_pids()
    state = read_json(constants.WIDGET_STATE, {})
    if not isinstance(state, dict):
        state = {}
    return {"running": bool(pid or pids), "pid": pid or (pids[0] if pids else None),
            "processes": pids, **state}


def _python_command(edit: bool) -> list[str]:
    command = [
        sys.executable, "-m", "leet_customizer.widget_daemon",
        "--config", str(constants.CONFIG_FILE),
        "--pidfile", str(constants.WIDGET_PID),
    ]
    if edit:
        command.append("--edit")
    return command


def start(edit: bool = False) -> dict:
    # Always clean stale hosts first.  A missing PID file must not leave an
    # old layer surface behind (the classic "ghost widgets" problem).
    stop()
    env = layer_shell_environment()
    env["PYTHONPATH"] = str(constants.APP_ROOT) + (
        ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["LEET_WIDGET_STARTED"] = str(time.time())
    constants.LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with open(constants.WIDGET_LOG, "ab") as log:
            log.write(f"\n[{time.strftime('%F %T')}] starting widget host (edit={edit})\n".encode())
            log.flush()
            process = popen(_python_command(edit), env=env, stdout=log, stderr=log)
    except OSError as error:
        raise RuntimeError(f"Could not start widget host: {error}") from error
    for _ in range(30):
        time.sleep(0.1)
        if running():
            current = read_json(constants.WIDGET_STATE, {})
            if not isinstance(current, dict):
                current = {}
            current.update({"running": True, "edit": edit, "pid": process.pid,
                            "started": current.get("started", time.time())})
            write_json(constants.WIDGET_STATE, current)
            return status()
        if process.poll() is not None:
            break
    log = ""
    with contextlib.suppress(OSError):
        log = "\n".join(constants.WIDGET_LOG.read_text(errors="replace").splitlines()[-24:])
    raise RuntimeError(f"Widget host exited during startup.\n{log}")


def stop() -> bool:
    pids = set(_daemon_pids())
    file_pid = read_pid(constants.WIDGET_PID)
    if file_pid:
        pids.add(file_pid)
    stopped = False
    for pid in pids:
        try:
            os.kill(pid, 15)
            stopped = True
        except OSError:
            pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and any(pid_alive(pid) for pid in pids):
        time.sleep(0.05)
    for pid in pids:
        if pid_alive(pid):
            try:
                os.kill(pid, 9)
            except OSError:
                pass
    with contextlib.suppress(OSError):
        constants.WIDGET_PID.unlink()
    with contextlib.suppress(OSError):
        constants.WIDGET_STATE.unlink()
    return stopped


def _gdk_monitors() -> list[Gdk.Monitor]:
    display = Gdk.Display.get_default()
    if display is None:
        return []
    model = display.get_monitors()
    monitors = []
    for index in range(model.get_n_items()):
        item = model.get_item(index)
        if isinstance(item, Gdk.Monitor):
            monitors.append(item)
    return monitors


def _monitor_targets(config) -> list[tuple[str, Gdk.Monitor | None, int, int]]:
    gdk = _gdk_monitors()
    target = config.get("widgets.monitor", "all")
    physical = desktop.monitors()
    values: list[tuple[str, Gdk.Monitor | None, int, int]] = []
    if target and target != "all":
        index = next((i for i, item in enumerate(physical) if item.get("name") == target), 0)
        monitor = gdk[index] if index < len(gdk) else (gdk[0] if gdk else None)
        geometry = monitor.get_geometry() if monitor else None
        width = geometry.width if geometry else 1920
        height = geometry.height if geometry else 1080
        values.append((target, monitor, width, height))
        return values
    if gdk:
        for index, monitor in enumerate(gdk):
            geometry = monitor.get_geometry()
            name = physical[index]["name"] if index < len(physical) else (
                monitor.get_model() or "monitor"
            )
            values.append((name, monitor, geometry.width, geometry.height))
    else:
        for item in physical:
            values.append((item["name"], None, int(item["width"]), int(item["height"])))
    return values


class HostWindow:
    def __init__(self, host: "WidgetHost", config: Config, monitor: Gdk.Monitor | None,
                 width: int, height: int, name: str):
        self.host = host
        self.config = config
        self.name = name
        self.width = width
        self.height = height
        self.edit = host.edit
        self.cards: list[WidgetCard] = []
        self.positions: dict[WidgetCard, tuple[int, int]] = {}
        self.selected_card: WidgetCard | None = None
        self.selection_label: Gtk.Label | None = None
        self.resize_mode = False
        self.window = Gtk.Window(application=host.application)
        self.window.add_css_class("hw-window")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_title(f"1337-Customizer widgets — {name}")
        self.layer_ready = False
        if Gtk4LayerShell is not None and monitor is not None:
            try:
                Gtk4LayerShell.init_for_window(self.window)
                Gtk4LayerShell.set_monitor(self.window, monitor)
                if self.edit:
                    layer = Gtk4LayerShell.Layer.OVERLAY
                elif self.config.get("widgets.layer", "bottom") == "background":
                    layer = Gtk4LayerShell.Layer.BACKGROUND
                else:
                    layer = Gtk4LayerShell.Layer.BOTTOM
                Gtk4LayerShell.set_layer(self.window, layer)
                for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.BOTTOM,
                             Gtk4LayerShell.Edge.LEFT, Gtk4LayerShell.Edge.RIGHT):
                    Gtk4LayerShell.set_anchor(self.window, edge, True)
                Gtk4LayerShell.set_exclusive_zone(self.window, -1)
                Gtk4LayerShell.set_keyboard_mode(
                    self.window,
                    Gtk4LayerShell.KeyboardMode.ON_DEMAND if self.edit
                    else Gtk4LayerShell.KeyboardMode.NONE,
                )
                Gtk4LayerShell.set_namespace(self.window, "1337-widgets")
                self.window.set_default_size(width, height)
                self.layer_ready = True
            except Exception:
                self.layer_ready = False
        if not self.layer_ready:
            self.window.set_default_size(width, height)
            self.window.set_decorated(False)
            with contextlib.suppress(Exception):
                self.window.fullscreen()

        self.fixed = Gtk.Fixed()
        self.fixed.set_hexpand(True)
        self.fixed.set_vexpand(True)
        self.fixed.set_size_request(width, height)
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.fixed)
        self.window.set_child(self.overlay)
        self.toolbar = None
        self._build_cards()
        if self.edit:
            self._build_toolbar()
        self.window.connect("map", self._on_map)
        self.window.connect("realize", self._on_map)
        self.window.present()

    def _build_cards(self) -> None:
        for child in list(self.fixed):
            self.fixed.remove(child)
        self.cards = []
        self.positions = {}
        try:
            items = normalise_items(self.config.get("widgets.items", []))
        except Exception as error:
            print(f"widget config could not be normalised: {error}", file=sys.stderr, flush=True)
            items = widgets.default_items()
        for item in items:
            if not item.get("enabled", True):
                continue
            item_monitor = item.get("monitor") or ""
            if item_monitor not in ("", "all", self.name):
                continue
            try:
                card = WidgetCard(item, self.config, edit=self.edit,
                                  on_note_changed=lambda text, current=item: self._note_changed(current, text))
                width = max(130, int(self.width * item["w"]))
                height = max(70, int(self.height * item["h"]))
                card.set_size_request(width, height)
                x = int(self.width * item["x"])
                y = int(self.height * item["y"])
                self.fixed.put(card, x, y)
                self.positions[card] = (x, y)
                self.cards.append(card)
                if self.edit:
                    self._add_selection(card)
                    self._add_drag(card)
            except Exception as error:
                # One malformed widget must not take down the entire desktop.
                print(f"widget {item.get('id')} skipped: {error}", file=sys.stderr, flush=True)
        self.window.queue_allocate()

    def _build_toolbar(self) -> None:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.add_css_class("hw-toolbar")
        toolbar.set_halign(Gtk.Align.END)
        toolbar.set_valign(Gtk.Align.START)
        toolbar.set_margin_top(18)
        toolbar.set_margin_end(18)
        title = Gtk.Label(label="Editing widgets")
        title.add_css_class("hw-title")
        toolbar.append(title)
        self.selection_label = Gtk.Label(label="click a card")
        self.selection_label.add_css_class("hw-muted")
        toolbar.append(self.selection_label)

        add = Gtk.MenuButton()
        add.set_icon_name("list-add-symbolic")
        add.set_tooltip_text("Add a widget")
        add.set_popover(self._add_popover())
        add.add_css_class("hw-button")
        toolbar.append(add)

        resize = Gtk.ToggleButton(label="Resize")
        resize.add_css_class("hw-button")
        resize.set_tooltip_text("When enabled, dragging a card changes its size")
        resize.connect("toggled", lambda button: setattr(self, "resize_mode", button.get_active()))
        toolbar.append(resize)
        duplicate = Gtk.Button(label="Duplicate")
        duplicate.add_css_class("hw-button")
        duplicate.connect("clicked", lambda _b: self.host.duplicate_selected())
        toolbar.append(duplicate)
        delete = Gtk.Button(label="Delete")
        delete.add_css_class("hw-button")
        delete.add_css_class("destructive-action")
        delete.connect("clicked", lambda _b: self.host.remove_selected())
        toolbar.append(delete)
        save = Gtk.Button(label="Save & lock")
        save.add_css_class("hw-button")
        save.add_css_class("suggested-action")
        save.connect("clicked", self.host.save_and_lock)
        close = Gtk.Button(label="Close")
        close.add_css_class("hw-button")
        close.connect("clicked", lambda _b: self.host.application.quit())
        toolbar.append(save)
        toolbar.append(close)
        self.overlay.add_overlay(toolbar)
        self.toolbar = toolbar

    def _add_popover(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        label = Gtk.Label(label="Add a widget", xalign=0)
        label.add_css_class("hw-title")
        label.set_margin_bottom(4)
        box.append(label)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        with contextlib.suppress(Exception):
            listbox.set_activate_on_single_click(True)
        for kind, metadata in widgets.WIDGET_TYPES.items():
            row = Gtk.ListBoxRow()
            text = Gtk.Label(label=metadata["name"], xalign=0)
            row.set_child(text)
            row.connect("activate", lambda _r, k=kind, p=popover: (p.popdown(), self.host.add_widget(k)))
            listbox.append(row)
        box.append(listbox)
        popover.set_child(box)
        return popover

    def _add_selection(self, card: WidgetCard) -> None:
        gesture = Gtk.GestureClick()
        gesture.set_button(1)
        gesture.connect("pressed", lambda *_a, c=card: self.select_card(c))
        card.add_controller(gesture)

    def select_card(self, card: WidgetCard | None) -> None:
        if self.selected_card is card:
            return
        if self.selected_card is not None:
            self.selected_card.remove_css_class("hw-selected")
        self.selected_card = card
        if card is not None:
            card.add_css_class("hw-selected")
            if self.selection_label is not None:
                name = widgets.WIDGET_TYPES.get(card.item.get("type"), {}).get("name", card.item.get("type"))
                self.selection_label.set_text(name)
        elif self.selection_label is not None:
            self.selection_label.set_text("click a card")

    def select_by_id(self, item_id: str) -> None:
        for card in self.cards:
            if card.item.get("id") == item_id:
                self.select_card(card)
                return
        self.select_card(None)

    def _note_changed(self, item: dict, text: str) -> None:
        item.setdefault("options", {})["text"] = text
        self.host.schedule_save()

    def _add_drag(self, card: WidgetCard) -> None:
        gesture = Gtk.GestureDrag()
        gesture.set_button(1)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        card.add_controller(gesture)
        state = {"x": 0, "y": 0, "w": 0, "h": 0}

        def begin(_gesture, x, y):
            self.select_card(card)
            state["x"], state["y"] = self.positions.get(card, (0, 0))
            state["w"] = int(self.width * card.item.get("w", 0.2))
            state["h"] = int(self.height * card.item.get("h", 0.15))

        def update(_gesture, offset_x, offset_y):
            if self.resize_mode:
                width = max(120, min(self.width - state["x"], state["w"] + int(offset_x)))
                height = max(70, min(self.height - state["y"], state["h"] + int(offset_y)))
                card.set_size_request(width, height)
                card.item["w"] = round(width / max(1, self.width), 4)
                card.item["h"] = round(height / max(1, self.height), 4)
                return
            x = max(0, min(self.width - card.get_allocated_width(), state["x"] + int(offset_x)))
            y = max(0, min(self.height - card.get_allocated_height(), state["y"] + int(offset_y)))
            self.fixed.move(card, x, y)
            self.positions[card] = (x, y)

        def end(_gesture, offset_x, offset_y):
            item = card.item
            if self.resize_mode:
                self.host.schedule_save()
                return
            x, y = self.positions.get(card, (0, 0))
            nx = max(0.0, min(1.0, x / max(1, self.width)))
            ny = max(0.0, min(1.0, y / max(1, self.height)))
            if bool(self.config.get("widgets.snap_grid", True)):
                grid = max(1, int(self.config.get("widgets.grid_size", 2))) / 100
                nx = max(0.0, min(1.0 - item.get("w", 0.2), round(nx / grid) * grid))
                ny = max(0.0, min(1.0 - item.get("h", 0.15), round(ny / grid) * grid))
            item["x"] = round(nx, 4)
            item["y"] = round(ny, 4)
            self.host.schedule_save()

        gesture.connect("drag-begin", begin)
        gesture.connect("drag-update", update)
        gesture.connect("drag-end", end)

    def _on_map(self, *_args) -> bool:
        self.apply_input_region()
        return False

    def apply_input_region(self) -> None:
        surface = self.window.get_surface()
        if surface is None:
            GLib.idle_add(self.apply_input_region)
            return
        if self.edit:
            surface.set_input_region(None)
            return
        click_through = bool(self.config.get("widgets.click_through", True))
        if not click_through:
            surface.set_input_region(None)
            return
        if cairo is None:
            return
        region = cairo.Region()
        for card in self.cards:
            if not card.item.get("interactive", False):
                continue
            x, y = self.positions.get(card, (0, 0))
            width = card.get_allocated_width() or int(self.width * card.item.get("w", 0.2))
            height = card.get_allocated_height() or int(self.height * card.item.get("h", 0.15))
            region.union(cairo.RectangleInt(int(x), int(y), int(width), int(height)))
        surface.set_input_region(region)

    def tick(self) -> None:
        for card in self.cards:
            with contextlib.suppress(Exception):
                card.tick()

    def save_items(self) -> list[dict]:
        items = []
        for card in self.cards:
            note = card.note_text()
            if note is not None:
                card.item.setdefault("options", {})["text"] = note
            items.append(card.item)
        return normalise_items(items)


class WidgetHost:
    def __init__(self, application: Gtk.Application, config: Config, edit: bool):
        self.application = application
        self.config = config
        self.edit = edit
        self.windows: list[HostWindow] = []
        self._save_source = 0
        self._ticks = 0
        self.pid = os.getpid()

    def build(self) -> None:
        # Publish the PID before touching layer-shell so a crash during window
        # construction still leaves a recoverable marker for the manager.
        write_pid(constants.WIDGET_PID, self.pid)
        theme = None
        try:
            theme = desktop.load_applied_theme()
        except Exception:
            theme = None
        css = widgets.widget_css(self.config, theme)
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"), -1)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, 800)
        targets = _monitor_targets(self.config)
        if self.edit and len(targets) > 1:
            targets = targets[:1]
        for name, monitor, width, height in targets:
            try:
                self.windows.append(HostWindow(self, self.config, monitor, width, height, name))
            except Exception as error:
                print(f"widget window {name} skipped: {error}", file=sys.stderr, flush=True)
        write_pid(constants.WIDGET_PID, self.pid)
        write_json(constants.WIDGET_STATE, {
            "running": True, "edit": self.edit, "pid": self.pid,
            "windows": len(self.windows), "started": time.time(),
        })
        GLib.timeout_add_seconds(1, self._tick)
        self._config_mtime = self._current_mtime()
        GLib.timeout_add_seconds(2, self._watch_config)
        if self.edit:
            self._install_shortcuts()

    def _current_mtime(self) -> float:
        try:
            return constants.CONFIG_FILE.stat().st_mtime
        except OSError:
            return 0.0

    def _watch_config(self) -> bool:
        """Refresh locked widgets when the studio saves a new configuration."""
        if self.edit:
            return True
        mtime = self._current_mtime()
        if mtime and mtime != getattr(self, "_config_mtime", 0.0):
            self._config_mtime = mtime
            try:
                self.config.reload()
                for window in self.windows:
                    window._build_cards()
                    window.apply_input_region()
            except Exception as error:
                print(f"widget config reload failed: {error}", file=sys.stderr, flush=True)
        return True

    def _install_shortcuts(self) -> None:
        action = Gio.SimpleAction.new("save-and-lock", None)
        action.connect("activate", lambda *_a: self.save_and_lock())
        self.application.add_action(action)
        self.application.set_accels_for_action("app.save-and-lock", ["<Control>s"])
        quit_action = Gio.SimpleAction.new("close-edit", None)
        quit_action.connect("activate", lambda *_a: self.application.quit())
        self.application.add_action(quit_action)
        self.application.set_accels_for_action("app.close-edit", ["Escape"])

    def _tick(self) -> bool:
        self._ticks += 1
        for window in self.windows:
            with contextlib.suppress(Exception):
                window.tick()
        return True

    def schedule_save(self) -> None:
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(900, self._save_now)

    def _save_now(self) -> bool:
        self._save_source = 0
        self.save_items()
        return False

    def save_items(self) -> None:
        # Start from the saved layout so widgets pinned to another monitor are
        # not accidentally dropped while editing one display.
        collected = {
            item["id"]: item
            for item in normalise_items(self.config.get("widgets.items", []))
        }
        for window in self.windows:
            for item in window.save_items():
                collected[item["id"]] = item
        items = normalise_items(list(collected.values()))
        self.config.set("widgets.items", items, save=True)
        self.config.data.setdefault("widgets", {})["enabled"] = True
        self.config.save()

    def _items(self) -> list[dict]:
        return normalise_items(self.config.get("widgets.items", []))

    def _commit_items(self, items: list[dict], select_id: str | None = None) -> None:
        self.config.set("widgets.items", normalise_items(items), save=True)
        self.config.data.setdefault("widgets", {})["enabled"] = True
        self.config.save()
        self.rebuild(select_id)

    def rebuild(self, select_id: str | None = None) -> None:
        for window in self.windows:
            window._build_cards()
            window.apply_input_region()
            if select_id:
                window.select_by_id(select_id)

    def add_widget(self, kind: str) -> None:
        items = self._items()
        item = widgets.new_item(kind, items)
        items.append(item)
        self._commit_items(items, item["id"])

    def remove_selected(self) -> None:
        if not self.windows or self.windows[0].selected_card is None:
            return
        item_id = self.windows[0].selected_card.item.get("id")
        items = [item for item in self._items() if item.get("id") != item_id]
        self._commit_items(items)

    def duplicate_selected(self) -> None:
        if not self.windows or self.windows[0].selected_card is None:
            return
        original = self.windows[0].selected_card.item
        items = self._items()
        clone = json.loads(json.dumps(original))
        clone["id"] = f"{original.get('type', 'widget')}-{os.urandom(3).hex()}"
        clone["x"] = round(min(0.94 - clone.get("w", 0.2), clone.get("x", 0) + 0.025), 4)
        clone["y"] = round(min(0.94 - clone.get("h", 0.15), clone.get("y", 0) + 0.025), 4)
        items.append(clone)
        self._commit_items(items, clone["id"])

    def save_and_lock(self) -> None:
        self.save_items()
        self._relaunch_locked()

    def _relaunch_locked(self) -> None:
        command = _python_command(False)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(constants.APP_ROOT) + (
            ":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        os.execvpe(sys.executable, [sys.executable, *command[1:]], env)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="1337-widgets")
    parser.add_argument("--config", default=str(constants.CONFIG_FILE))
    parser.add_argument("--pidfile", default=str(constants.WIDGET_PID))
    parser.add_argument("--edit", action="store_true")
    args = parser.parse_args(argv)
    config = Config(args.config)
    try:
        config.data.setdefault("widgets", {})["items"] = widgets.normalise_items(
            config.get("widgets.items", [])
        )
    except Exception:
        config.data.setdefault("widgets", {})["items"] = widgets.default_items()
    if args.edit:
        config.data["widgets"]["enabled"] = True

    constants.STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_handle = open(constants.STATE_DIR / "widgets.lock", "w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another widget host is already running", file=sys.stderr, flush=True)
        return 1

    application = Gtk.Application(
        application_id="io.github.LeetCustomizer.Widgets",
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )

    def activate(app):
        host = WidgetHost(app, config, args.edit)
        app._host = host
        host.build()

    application.connect("activate", activate)

    def shutdown(_app):
        with contextlib.suppress(OSError):
            if read_pid(args.pidfile) == os.getpid():
                Path(args.pidfile).unlink()
        with contextlib.suppress(OSError):
            constants.WIDGET_STATE.unlink()

    application.connect("shutdown", shutdown)
    return application.run([])


if __name__ == "__main__":
    raise SystemExit(main())
