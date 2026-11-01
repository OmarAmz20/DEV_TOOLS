"""Profiles: save a complete look and switch back to it in one click."""
from __future__ import annotations

import json
import os
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import palette, store, system, widgets  # noqa: E402


class ProfilesPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = window

        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=860, tightening_threshold=660)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20,
                            margin_top=26, margin_bottom=36, margin_start=22, margin_end=22)
        clamp.set_child(self.page)
        scroller.set_child(clamp)
        self.append(scroller)

        self.page.append(widgets.page_header(
            "Profiles",
            "Wallpaper, palette, mode, fonts and icons — saved as one look you can return to."))

        actions = Gtk.Box(spacing=8)
        self.save_button = widgets.button("Save this look", "list-add-symbolic")
        self.save_button.add_css_class("suggested-action")
        self.save_button.add_css_class("pill")
        self.save_button.connect("clicked", self.ask_save)
        actions.append(self.save_button)
        imp = widgets.button("Import…", "document-open-symbolic")
        imp.add_css_class("pill")
        imp.connect("clicked", self.import_profile)
        actions.append(imp)
        self.page.append(actions)

        note = Gtk.Label(xalign=0, wrap=True,
                         label="Profiles are yours: export one as JSON to move it to another "
                               "machine, or keep them as a backup.")
        note.add_css_class("aura-hint")
        self.page.append(note)

        self.group_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.page.append(self.group_holder)
        self.empty = Gtk.Label(label="No saved looks yet. Make the desktop yours, then save it here.",
                               wrap=True)
        self.empty.add_css_class("aura-hint")
        self.empty.set_margin_top(12)
        self.page.append(self.empty)

    # --- list ----------------------------------------------------------------------

    def refresh_from_window(self):
        self.rebuild()
        self.save_button.set_sensitive(bool(self.win.state.get("palette") or self.win.preview_palette))

    def rebuild(self):
        widgets.clear_box(self.group_holder)
        profiles = store.load_profiles()
        self.empty.set_visible(not profiles)
        if not profiles:
            return
        group = Adw.PreferencesGroup(title="Saved looks")
        applying_id = self.win.state.get("profile_id")
        for profile in profiles:
            group.add(self._row(profile, profile.get("id") == applying_id))
        self.group_holder.append(group)

    def _row(self, profile, applied):
        pal = profile.get("palette", {})
        mode = profile.get("mode", "auto")
        mode = self.win.effective_mode() if mode == "auto" else mode
        palette_value = pal.get(mode) or pal.get("dark") or {}
        wallpaper = profile.get("wallpaper") or ""
        exists = bool(wallpaper and os.path.exists(wallpaper))
        when = time.strftime("%d %b %Y", time.localtime(profile.get("created", time.time())))

        row = Adw.ActionRow(title=profile.get("name", "Untitled look"))
        subtitle = f"{mode.title()} · {when} · {palette.STYLE_LABELS.get(profile.get('style', 'balanced'), 'Balanced')}"
        if wallpaper:
            subtitle += f" · {os.path.basename(wallpaper)}"
            if not exists:
                subtitle += " (missing)"
        row.set_subtitle(subtitle)

        swatches = widgets.SwatchRow(("paper", "accent", "ink"), size=18, spacing=4)
        swatches.set_palette(palette_value)
        swatches.set_valign(Gtk.Align.CENTER)
        row.add_prefix(swatches)

        if applied:
            badge = Gtk.Label(label="APPLIED", css_classes=["aura-badge", "current"],
                              valign=Gtk.Align.CENTER)
            row.add_prefix(badge)
        if profile.get("id") == self.win.config.get("autostart_profile"):
            login_badge = Gtk.Label(label="AT LOGIN", css_classes=["aura-badge", "current"],
                                    valign=Gtk.Align.CENTER)
            row.add_prefix(login_badge)

        actions = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
        apply = Gtk.Button(label="Reapply" if applied else "Apply")
        apply.add_css_class("flat")
        apply.connect("clicked", lambda _b, p=profile: self.win.apply_profile(p))
        actions.append(apply)

        login = Gtk.Button(icon_name="system-log-out-symbolic",
                           tooltip_text="Reapply this look after login",
                           css_classes=["flat", "circular"])
        login.connect("clicked", lambda _b, p=profile: self.use_at_login(p))
        actions.append(login)

        export = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Export profile as JSON",
                            css_classes=["flat", "circular"])
        export.connect("clicked", lambda _b, p=profile: self.export_profile(p))
        actions.append(export)

        delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete profile",
                            css_classes=["flat", "circular"])
        delete.add_css_class("destructive-action")
        delete.connect("clicked", lambda _b, p=profile: self.ask_delete(p))
        actions.append(delete)
        row.add_suffix(actions)
        return row

    def use_at_login(self, profile):
        store.save_config(autostart_profile=profile["id"])
        try:
            system.set_autostart(True, profile=profile["id"],
                                 delay=self.win.config.get("autostart_delay", 8))
        except OSError as error:
            self.win.toast(f"Could not update the login entry: {error}")
            return
        self.win.reload_config()
        self.rebuild()
        self.win.look_page.sync_from_config()
        self.win.toast(f"“{profile.get('name', 'This look')}” will be applied after login")

    # --- save / import / export -----------------------------------------------------

    def ask_save(self, *_):
        if not (self.win.state.get("palette") or self.win.preview_palette):
            self.win.toast("Choose a wallpaper first, so there is a palette to save")
            return
        default = f"{palette.STYLE_LABELS.get(self.win.config['style'], 'My')} look"
        dialog = Adw.AlertDialog(
            heading="Save this look",
            body="A name makes it easy to find later. The current wallpaper, palette and "
                 "desktop settings are included.")
        entry = Gtk.Entry(text=default, activates_default=True)
        entry.set_margin_top(6)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def response(source, response_id):
            if response_id != "save":
                return
            name = entry.get_text().strip() or default
            self.win.save_current_profile(name)
        dialog.connect("response", response)
        dialog.present(self.win)

    def import_profile(self, *_):
        dialog = Gtk.FileDialog(title="Import a profile", modal=True)
        file_filter = Gtk.FileFilter(name="Aura profile")
        file_filter.add_suffix("json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)

        def done(source, result):
            try:
                chosen = source.open_finish(result)
            except GLib.Error:
                return
            try:
                ok, contents, _etag = chosen.load_contents(None)
                if not ok:
                    raise ValueError("could not read the file")
                value = json.loads(contents.decode("utf-8"))
            except Exception as error:
                self.win.toast(f"Could not import: {error}")
                return
            if not isinstance(value, dict):
                self.win.toast("That does not look like an Aura profile")
                return
            if "palette" not in value and "light" in value and "dark" in value:
                value = {
                    "name": os.path.splitext(os.path.basename(chosen.get_path() or "Imported"))[0],
                    "palette": {"light": value["light"], "dark": value["dark"]},
                    "meta": value.get("meta", {}),
                }
            if "palette" not in value or not palette.valid_palette(value["palette"]):
                self.win.toast("That file has no valid light/dark palette")
                return
            value["id"] = store.new_profile_id()
            value["created"] = time.time()
            store.save_profile(value)
            self.rebuild()
            self.win.toast(f"Imported {value.get('name', 'profile')}")

        dialog.open(self.win, None, done)

    def export_profile(self, profile):
        safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_"
                       for ch in profile.get("name", "aura-look")).strip().replace(" ", "-")
        dialog = Gtk.FileDialog(title="Export profile", initial_name=f"{safe or 'aura-look'}.json",
                                modal=True)
        file_filter = Gtk.FileFilter(name="Aura profile")
        file_filter.add_suffix("json")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)

        def done(source, result):
            try:
                chosen = source.save_finish(result)
            except GLib.Error:
                return
            path = chosen.get_path()
            if not path:
                return
            store.write_json(path, profile)
            self.win.toast(f"Exported {os.path.basename(path)}")

        dialog.save(self.win, None, done)

    def ask_delete(self, profile):
        dialog = Adw.AlertDialog(
            heading=f"Delete “{profile.get('name', 'this look')}”?",
            body="The profile is removed. Your wallpaper and current colours stay as they are.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def response(source, response_id):
            if response_id == "delete":
                store.delete_profile(profile["id"])
                if self.win.config.get("autostart_profile") == profile["id"]:
                    store.save_config(autostart_profile=None)
                    self.win.reload_config()
                    if system.autostart_enabled():
                        system.set_autostart(
                            True, delay=self.win.config.get("autostart_delay", 8))
                    self.win.look_page.sync_from_config()
                self.rebuild()
                self.win.toast("Profile deleted")
        dialog.connect("response", response)
        dialog.present(self.win)
