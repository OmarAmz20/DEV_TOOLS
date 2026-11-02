"""Video wallpaper page: pick, tune and run mpvpaper."""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import constants, desktop, video  # noqa: E402
from ..util import human_size, open_path, read_json  # noqa: E402
from . import common  # noqa: E402


class VideoPage(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.config = app.config
        self.videos = []
        self.selected_path = str(self.config.get("video.path", "") or "")
        self.external_path = ""
        self._preview_token = 0
        self._build()
        self.refresh()

    def _build(self) -> None:
        stop = common.button("Stop video", icon="media-playback-stop-symbolic", on_click=self.stop)
        apply = common.button("Set video wallpaper", icon="media-playback-start-symbolic",
                              css="suggested-action", on_click=self.apply)
        outer, content = common.page_scaffold(
            "Video wallpapers", "Real motion on your desktop through a hardened mpvpaper engine.",
            actions=[stop, apply],
        )
        self.append(outer)
        self.content = content

        engine = common.card()
        self.engine_status = common.section("Engine", "mpvpaper uses hardware decoding and pauses when the wallpaper is hidden.")
        engine.append(self.engine_status)
        self.engine_row = common.row("mpvpaper", "Checking…", trailing=common.badge("CHECKING", "warn"))
        engine.append(self.engine_row)
        self.layer_row = common.row("Layer-shell compositor", "Checking…", trailing=common.badge("CHECKING", "warn"))
        engine.append(self.layer_row)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.build_button = common.button("Build video engine", icon="utilities-terminal-symbolic",
                                          on_click=self.build_engine)
        buttons.append(self.build_button)
        buttons.append(common.button("Engine log", icon="text-x-generic-symbolic", on_click=self.show_log))
        engine.append(buttons)
        self.engine_output = Gtk.Label(label="", xalign=0, wrap=True)
        self.engine_output.add_css_class("command-box")
        self.engine_output.set_visible(False)
        engine.append(self.engine_output)
        content.append(engine)

        picker = common.card()
        picker.append(common.section("Choose a video", "Videos from your library, or any file on disk."))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.video_dropdown = common.dropdown([("", "No videos in library")], "")
        self.video_dropdown.set_hexpand(True)
        self.video_dropdown.connect("notify::selected", self._video_selected)
        row.append(self.video_dropdown)
        row.append(common.button("Browse…", icon="document-open-symbolic", on_click=self.browse))
        row.append(common.button("Preview", icon="media-playback-start-symbolic", on_click=self.preview_external))
        picker.append(row)
        self.preview_overlay = Gtk.Overlay()
        self.preview = Gtk.Picture()
        self.preview.add_css_class("preview-image")
        self.preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview.set_size_request(-1, 260)
        self.preview.set_can_shrink(True)
        self.preview_loading = Gtk.Label(label="Choose a video to preview its frame")
        self.preview_loading.add_css_class("dim-label")
        self.preview_loading.set_halign(Gtk.Align.CENTER)
        self.preview_loading.set_valign(Gtk.Align.CENTER)
        self.preview_overlay.set_child(self.preview)
        self.preview_overlay.add_overlay(self.preview_loading)
        picker.append(self.preview_overlay)
        self.video_meta = Gtk.Label(label="", xalign=0)
        self.video_meta.add_css_class("dim-label")
        picker.append(self.video_meta)
        content.append(picker)

        options = common.card()
        options.append(common.section("Playback", "These options are forwarded to mpvpaper."))
        self.monitor_dropdown = common.dropdown(desktop.monitor_choices(),
                                                 self.config.get("video.monitor", "all"))
        self.fit_dropdown = common.dropdown([("crop", "Fill / crop"), ("fit", "Fit / letterbox")],
                                             self.config.get("video.fit", "crop"))
        self.hwdec_dropdown = common.dropdown(
            [("auto-safe", "Hardware (auto-safe)"), ("auto", "Hardware (auto)"),
             ("no", "Software only")],
            self.config.get("video.hwdec", "auto-safe"),
        )
        self.layer_dropdown = common.dropdown([("background", "Background"), ("bottom", "Bottom")],
                                               self.config.get("video.layer", "background"))
        for title, widget in (
            ("Monitor", self.monitor_dropdown),
            ("Fit", self.fit_dropdown),
            ("Hardware decoding", self.hwdec_dropdown),
            ("Layer", self.layer_dropdown),
        ):
            options.append(common.row(title, trailing=widget))
        self.muted_switch = common.switch(bool(self.config.get("video.muted", True)))
        self.loop_switch = common.switch(bool(self.config.get("video.loop", True)))
        self.pause_switch = common.switch(bool(self.config.get("video.auto_pause", True)))
        self.auto_stop_switch = common.switch(bool(self.config.get("video.auto_stop_fullscreen", False)))
        options.append(common.row("Muted", "Video wallpapers are silent by default", trailing=self.muted_switch))
        options.append(common.row("Loop", "Keep playing the clip", trailing=self.loop_switch))
        options.append(common.row("Pause when hidden", "Save CPU and battery", trailing=self.pause_switch))
        options.append(common.row("Stop on fullscreen", "Release resources for games and video", trailing=self.auto_stop_switch))
        speed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        speed_label = Gtk.Label(label="Speed", xalign=0)
        speed_label.set_hexpand(True)
        self.speed = common.scale(float(self.config.get("video.speed", 1.0) or 1.0), 0.25, 4.0, 0.05)
        self.speed.set_size_request(260, -1)
        speed_row.append(speed_label)
        speed_row.append(self.speed)
        options.append(speed_row)
        content.append(options)

        status = common.card()
        status.append(common.section("Running state", "Video wallpapers keep running when the studio closes."))
        self.status_label = Gtk.Label(label="Checking…", xalign=0, wrap=True)
        status.append(self.status_label)
        self.status_processes = Gtk.Label(label="", xalign=0, wrap=True)
        self.status_processes.add_css_class("dim-label")
        status.append(self.status_processes)
        content.append(status)

        tip = Gtk.Label(
            label="Tip: on GNOME Wayland, layer-shell video surfaces are not available. "
                  "1337-Customizer falls back to a high-quality still frame; GNOME extensions such as "
                  "Hidamari can play motion if you prefer.",
            xalign=0, wrap=True,
        )
        tip.add_css_class("dim-label")
        content.append(tip)

    # --- data ---------------------------------------------------------------------

    def refresh(self) -> None:
        items = [item for item in self.app.library.items() if item.kind == "video"]
        self.videos = items
        entries = [(item.path, f"{item.name} · {human_size(item.size)}") for item in items]
        self.video_dropdown.set_model(Gtk.StringList.new([label for _value, label in entries] or ["No videos in library"]))
        selected_index = 0
        for index, (path, _label) in enumerate(entries):
            if path == self.selected_path:
                selected_index = index
                break
        self.video_dropdown.set_selected(selected_index if entries else 0)
        self._video_selected()
        self.refresh_status()

    def refresh_status(self) -> None:
        available = video.engine_available()
        self.engine_row = self._replace_status(
            self.engine_row, "mpvpaper",
            video.engine_source() if available else "Not installed — build from the bundled source",
            "ok" if available else "warn",
        )
        layer_ok = desktop.has_layer_shell()
        self.layer_row = self._replace_status(
            self.layer_row, "Layer-shell compositor",
            "Ready" if layer_ok else "Not available in this session",
            "ok" if layer_ok else "warn",
        )
        state = video.state()
        if state.get("running"):
            self.status_label.set_text(f"Playing {Path(state.get('path', '')).name} on {state.get('monitor', 'all')}.")
            processes = state.get("processes", [])
            self.status_processes.set_text(
                " · ".join(f"{item.get('monitor')} (pid {item.get('pid')})" for item in processes)
                or "No live process"
            )
        else:
            self.status_label.set_text("No video wallpaper is running.")
            self.status_processes.set_text("Set a video to bring the desktop to life.")
        self.build_button.set_visible(not available)

    def _replace_status(self, old: Gtk.Box, title: str, subtitle: str, state: str) -> Gtk.Box:
        parent = old.get_parent()
        if parent is not None:
            parent.remove(old)
        row = common.row(title, subtitle, trailing=common.badge("READY" if state == "ok" else "ACTION NEEDED", state))
        if parent is not None:
            parent.append(row)
        return row

    def _video_selected(self, *_args) -> None:
        index = self.video_dropdown.get_selected()
        if not self.videos:
            if self.external_path:
                self.selected_path = self.external_path
                self.video_meta.set_text(self.external_path)
                self._load_external_preview(self.external_path)
            else:
                self.selected_path = ""
                self.preview.set_paintable(None)
                self.preview_loading.set_visible(True)
                self.video_meta.set_text("")
            return
        if 0 <= index < len(self.videos):
            item = self.videos[index]
            self.selected_path = item.path
            self.config.set("video.path", item.path, save=False)
            self._preview_token += 1
            token = self._preview_token
            self.video_meta.set_text(
                f"{item.resolution} · {human_size(item.size)} · {item.path}"
            )
            self.preview_loading.set_visible(True)

            def loaded(texture):
                if token != self._preview_token:
                    return
                if texture is not None:
                    self.preview.set_paintable(texture)
                    self.preview_loading.set_visible(False)
                else:
                    self.preview_loading.set_visible(True)

            self.app.thumbs.get_preview(item.path, item.mtime, item.size, item.kind, loaded)

    def browse(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose a video")
        filters = self._filters()
        dialog.set_filters(filters)
        dialog.open(self.get_root(), None, self._browsed)

    def _filters(self):
        from gi.repository import Gio

        filters = Gio.ListStore.new(Gtk.FileFilter)
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Video files")
        for pattern in ("*.mp4", "*.webm", "*.mkv", "*.mov", "*.m4v", "*.avi"):
            file_filter.add_pattern(pattern)
        filters.append(file_filter)
        return filters

    def _browsed(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if not file or not file.get_path():
            return
        path = file.get_path()
        self.external_path = path
        self.selected_path = path
        self.videos = []
        self.video_dropdown.set_model(Gtk.StringList.new([Path(path).name]))
        self.video_dropdown.set_selected(0)
        self.video_meta.set_text(path)
        self.config.set("video.path", path, save=False)
        self.config.save()
        self._load_external_preview(path)

    def _load_external_preview(self, path: str) -> None:
        self._preview_token += 1
        token = self._preview_token
        try:
            stat = Path(path).stat()
        except OSError:
            self.preview_loading.set_visible(True)
            return
        self.preview_loading.set_visible(True)

        def loaded(texture):
            if token != self._preview_token:
                return
            if texture is not None:
                self.preview.set_paintable(texture)
                self.preview_loading.set_visible(False)

        self.app.thumbs.get_preview(path, stat.st_mtime, stat.st_size, "video", loaded)

    def preview_external(self) -> None:
        path = self.selected_path
        if path:
            open_path(path)

    # --- actions ------------------------------------------------------------------

    def _collect(self) -> None:
        self.config.set("video.monitor", common.selected_value(
            self.monitor_dropdown, desktop.monitor_choices(), "all"), save=False)
        self.config.set("video.fit", common.selected_value(
            self.fit_dropdown, [("crop", "Fill / crop"), ("fit", "Fit / letterbox")], "crop"), save=False)
        self.config.set("video.hwdec", common.selected_value(
            self.hwdec_dropdown, [("auto-safe", "Hardware (auto-safe)"), ("auto", "Hardware (auto)"),
                                  ("no", "Software only")], "auto-safe"), save=False)
        self.config.set("video.layer", common.selected_value(
            self.layer_dropdown, [("background", "Background"), ("bottom", "Bottom")], "background"), save=False)
        self.config.set("video.muted", self.muted_switch.get_active(), save=False)
        self.config.set("video.loop", self.loop_switch.get_active(), save=False)
        self.config.set("video.auto_pause", self.pause_switch.get_active(), save=False)
        self.config.set("video.auto_stop_fullscreen", self.auto_stop_switch.get_active(), save=False)
        self.config.set("video.speed", round(float(self.speed.get_value()), 2), save=False)
        if self.selected_path:
            self.config.set("video.path", self.selected_path, save=False)
        self.config.set("video.restore_on_login", True, save=False)
        self.config.save()

    def apply(self) -> None:
        path = self.selected_path
        if not path:
            self.app.toast("Choose a video first")
            return
        self._collect()
        self.app.toast("Starting video wallpaper…")
        threading.Thread(target=self._apply_worker, args=(path,), daemon=True).start()

    def _apply_worker(self, path: str) -> None:
        try:
            result = video.start(path, self.config)
            GLib.idle_add(self._applied, result, None)
        except Exception as error:
            GLib.idle_add(self._applied, None, str(error))

    def _applied(self, result, error) -> bool:
        self.refresh_status()
        if error:
            self.app.toast(f"Video engine: {error}"[:360])
        else:
            self.app.toast(f"Video wallpaper running · {Path(result.get('path', '')).name}")
        return False

    def stop(self) -> None:
        stopped = video.stop(notify_user=True)
        self.refresh_status()
        self.app.toast("Video wallpaper stopped" if stopped else "No video wallpaper is running")

    def build_engine(self) -> None:
        self.engine_output.set_visible(True)
        self.engine_output.set_text("Building mpvpaper from source… this can take a minute.")
        threading.Thread(target=self._build_worker, daemon=True).start()

    def _build_worker(self) -> None:
        result = video.build_engine()
        GLib.idle_add(self._built, result)

    def _built(self, result: dict) -> bool:
        self.engine_output.set_text(result.get("output", "No output")[-4000:])
        self.refresh_status()
        self.app.toast("Video engine built" if result.get("ok") else "Engine build failed")
        return False

    def show_log(self) -> None:
        text = video.log_tail(80) or "No engine log yet."
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Video engine log",
            body=text[-4000:],
        )
        dialog.add_response("close", "Close")
        dialog.present()

    def on_shown(self) -> None:
        self.refresh()
