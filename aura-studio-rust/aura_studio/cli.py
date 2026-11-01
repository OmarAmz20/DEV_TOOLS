"""Command line entry point for Aura Studio."""
from __future__ import annotations

import json
import os
import shutil
import sys
import time

USAGE = """Aura Studio — wallpapers, palettes and desktop looks.

Usage:
  aura-studio                     open the window
  aura-studio set FILE            set a picture/video and match the colours
  aura-studio set FILE --no-colors  set only the wallpaper
  aura-studio next                the next wallpaper from your folder
  aura-studio light|dark|auto     change colour mode using the applied palette
  aura-studio palette FILE        print the palette extracted from a picture
  aura-studio palette FILE --json print it as JSON (also: --css)
  aura-studio profiles            list saved profiles
  aura-studio apply-profile NAME  apply a saved profile (name or id)
  aura-studio apply-saved         reapply the saved look, then exit (login)
  aura-studio autostart on|off    reapply the saved look after login
  aura-studio autostart status    show whether login reapply is enabled
  aura-studio reapply-wallpaper   restore the last wallpaper
  aura-studio restore             undo everything Aura changed
  aura-studio status              show backend, mode and current wallpaper
  aura-studio doctor              diagnose GTK, dconf and wallpaper backends
  aura-studio config              print every setting as JSON
  aura-studio config get KEY      print one setting
  aura-studio config set KEY VAL  change a setting (JSON values are accepted)
  aura-studio config unset KEY    return one setting to its default
  aura-studio config path         print the settings file path

Examples:
  aura-studio config set wallpaper_backend gnome
  aura-studio config set glass true
  aura-studio config set glass_opacity 0.82
  aura-studio config set terminal_targets '["kitty", "gnome-terminal"]'

Everything is stored in ~/.config/aura-studio and your cache directory.
When ~/goinfre exists, Aura uses ~/goinfre/aura-studio for its large cache.
"""


def _print_palette(path, mode="json"):
    from . import library, palette
    still = library.still_for(os.path.realpath(path), 1920)
    if not still:
        raise ValueError("could not read a picture from this file")
    value = palette.from_image(still)
    if mode == "json":
        print(json.dumps(palette.palette_json(value), indent=2, ensure_ascii=False))
        return 0
    if mode == "css":
        print(palette.css_for_export(value, dark=True))
        return 0
    from . import color
    for name in ("light", "dark"):
        p = value[name]
        body = color.contrast(p["ink"], p["paper"])
        accent = color.contrast(p["accent_text"], p["paper"])
        print(f"{name:>5}: paper {p['paper']}  accent {p['accent']}  ink {p['ink']}  "
              f"text {body:.1f}:1  accent {accent:.1f}:1")
    return 0


def _apply_mode(mode):
    from . import core, store
    config = store.save_config(mode=mode)
    state = store.load_state()
    if not state.get("palette"):
        raise ValueError("no palette applied yet — set a wallpaper first")
    core.apply_colours(state["palette"], config, mode=core.effective_mode(config),
                       options=state.get("options"),
                       source=state.get("palette_source") or state.get("wallpaper"),
                       still=state.get("still"))
    print(f"{core.effective_mode(config)} colours applied")
    return 0


def _option(argv, name):
    """Read --name VALUE or --name=VALUE from a simple argument list."""
    for index, argument in enumerate(argv):
        if argument == name and index + 1 < len(argv):
            return argv[index + 1]
        if argument.startswith(name + "="):
            return argument.split("=", 1)[1]
    return None


def _profile_id(value):
    from . import store
    needle = str(value).casefold()
    for profile in store.load_profiles():
        if profile.get("id") == value or \
                needle == str(profile.get("name", "")).casefold():
            return profile.get("id")
    return value


def _log_autostart(message):
    from . import store
    try:
        os.makedirs(store.CONFIG_DIR, exist_ok=True)
        with open(os.path.join(store.CONFIG_DIR, "autostart.log"), "a",
                  encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    except OSError:
        pass


def _apply_saved(argv):
    from . import core
    delay = _option(argv, "--delay")
    if delay:
        try:
            time.sleep(max(0.0, min(300.0, float(delay))))
        except (TypeError, ValueError):
            pass
    profile = _option(argv, "--profile")
    if profile:
        profile = _profile_id(profile)
    logging = "--log" in argv
    try:
        result = core.apply_saved(profile)
    except Exception as error:
        message = f"could not reapply the saved look: {error}"
        if logging:
            _log_autostart(message)
        print(f"aura-studio: {message}", file=sys.stderr)
        return 1

    if result is None:
        message = "nothing saved to reapply yet"
    elif result.get("result"):
        wallpaper = (result.get("wallpaper") or result["result"].get("source")
                     or result["result"].get("path") or "")
        backend = result["result"].get("backend", "desktop")
        message = f"reapplied {os.path.basename(wallpaper)} via {backend}"
    elif result.get("wallpaper"):
        message = f"reapplied {os.path.basename(result['wallpaper'])}"
    else:
        message = f"reapplied the {result.get('mode', 'saved')} colours"
    if logging:
        _log_autostart(message)
    if "--quiet" not in argv:
        print(message[0].upper() + message[1:])
    return 0


def _autostart(argv):
    from . import store, system
    action = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else "status"
    if action in ("on", "enable", "install", "true"):
        profile = _option(argv, "--profile")
        if profile:
            profile = _profile_id(profile)
            store.save_config(autostart_profile=profile)
        delay = _option(argv, "--delay")
        if delay is not None:
            try:
                store.save_config(autostart_delay=int(delay))
            except ValueError:
                raise ValueError("--delay needs a number of seconds")
        system.set_autostart(True, profile=profile,
                             delay=system.autostart_delay(store.load_config()))
        print("Login reapply enabled.")
        print(f"  Entry: {system.AUTOSTART_FILE}")
        return 0
    if action in ("off", "disable", "uninstall", "false"):
        system.set_autostart(False)
        print("Login reapply disabled.")
        return 0
    if action in ("status", "show"):
        print("enabled" if system.autostart_enabled() else "disabled")
        if system.autostart_enabled():
            print(f"  Entry: {system.AUTOSTART_FILE}")
        return 0
    raise ValueError(f"autostart needs on, off or status (not {action!r})")


def _typed_value(text):
    """Turn a CLI argument into the JSON type the config expects."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _config(argv):
    from . import store
    if len(argv) < 2 or argv[1] in ("show", "list"):
        print(json.dumps(store.load_config(), indent=2, ensure_ascii=False))
        return 0
    action = argv[1]
    if action == "path":
        print(store.CONFIG)
        return 0
    if len(argv) < 3:
        raise ValueError(f"config {action} needs a key")
    key = argv[2]
    if key not in store.DEFAULT_CONFIG:
        raise ValueError(f"unknown setting: {key}")
    if action == "get":
        print(json.dumps(store.load_config()[key], ensure_ascii=False))
        return 0
    if action == "unset":
        config = store.save_config(**{key: store.DEFAULT_CONFIG[key]})
        print(json.dumps(config[key], ensure_ascii=False))
        return 0
    if action == "set":
        if len(argv) < 4:
            raise ValueError("config set needs a value")
        value = _typed_value(" ".join(argv[3:]))
        config = store.save_config(**{key: value})
        print(json.dumps(config[key], ensure_ascii=False))
        return 0
    raise ValueError(f"config needs get, set, unset or path (not {action!r})")


def _doctor(argv):
    """A small Ubuntu/desktop health check that is safe to paste into a report."""
    from . import __version__, store, system
    checks = []

    def add(name, ok, detail, required=True):
        checks.append({"check": name, "ok": bool(ok), "required": required,
                       "detail": detail})

    add("Aura Studio", True, __version__)
    add("Session", True, system.session_label())
    add("Wallpaper backend", system.detect_backend(refresh=True)["name"] != "none",
        system.backend_label())
    preference = store.load_config().get("wallpaper_backend", "auto")
    add("Backend preference", True, preference)
    add("Config directory", os.access(store.CONFIG_DIR, os.W_OK) or
        not os.path.exists(store.CONFIG_DIR), store.CONFIG_DIR)

    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk
        gtk = f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"
        adw = f"{Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}.{Adw.MICRO_VERSION}"
        add("GTK", Gtk.get_major_version() == 4 and Gtk.get_minor_version() >= 10, gtk)
        add("libadwaita", Adw.MINOR_VERSION >= 5 or Adw.MAJOR_VERSION > 1, adw)
    except Exception as error:
        add("GTK / libadwaita", False, str(error))

    writable = system._gnome_ready()
    add("GSettings wallpaper key", writable,
        "writable" if writable else "missing or locked (Aura will use another backend)",
        required=False)
    add("GSettings backend", True, os.environ.get("GSETTINGS_BACKEND") or "default")
    add("Host gsettings", system._host_gsettings_enabled(),
        "/usr/bin/gsettings" if system._host_gsettings_enabled() else
        "not used (isolated backend)", required=False)
    for name, command, required in (("dconf", "dconf", False),
                                    ("ffmpeg", "ffmpeg", False),
                                    ("feh", "feh", False)):
        path = shutil.which(command)
        add(name, bool(path), path or "not installed (optional)", required=required)
    terminals = system.terminal_targets()
    add("Terminals", True, ", ".join(terminals) or "none detected (optional)",
        required=False)
    add("Login reapply", True,
        system.AUTOSTART_FILE if system.autostart_enabled() else "disabled (optional)")
    add("Custom CSS", True,
        store.CUSTOM_CSS if os.path.exists(store.CUSTOM_CSS) else
        f"{store.CUSTOM_CSS} (not created yet)")

    if "--json" in argv:
        print(json.dumps(checks, indent=2, ensure_ascii=False))
    else:
        for item in checks:
            if item["ok"]:
                mark = "ok  "
            else:
                mark = "warn" if item["required"] else "info"
            print(f"{mark}  {item['check']:<24} {item['detail']}")
        if not all(item["ok"] for item in checks if item["required"]):
            print("\nSome checks need attention. Run this command with --json for details.")
    return 0 if all(item["ok"] for item in checks if item["required"]) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("open", "gui", "window"):
        from .app import main as gui
        return gui()
    command = argv[0]

    try:
        if command in ("-h", "--help", "help"):
            print(USAGE)
            return 0
        if command in ("-v", "--version", "version"):
            from . import __version__
            print(f"Aura Studio {__version__}")
            return 0
        if command == "set":
            files = [arg for arg in argv[1:] if not arg.startswith("--")]
            if not files:
                raise ValueError("set needs a file")
            from . import core, store
            result = core.apply_wallpaper(
                os.path.realpath(files[0]), store.load_config(),
                match_colors="--no-colors" not in argv)
            print(f"Wallpaper set via {result['result']['backend']}"
                  + (f" · {result['mode']} colours matched" if result["matched"] else ""))
            return 0
        if command == "next":
            from . import core
            result = core.next_wallpaper()
            if not result:
                raise ValueError("no other wallpaper in the folder")
            print(result["result"]["source"])
            return 0
        if command in ("light", "dark", "auto"):
            return _apply_mode(command)
        if command == "palette":
            if len(argv) < 2:
                raise ValueError("palette needs a file")
            mode = "text"
            if "--json" in argv:
                mode = "json"
            elif "--css" in argv:
                mode = "css"
            return _print_palette(argv[1], mode)
        if command == "profiles":
            from . import store
            profiles = store.load_profiles()
            if not profiles:
                print("No saved profiles.")
            for profile in profiles:
                print(f"{profile.get('id')}  {profile.get('name')}")
            return 0
        if command == "apply-profile":
            if len(argv) < 2:
                raise ValueError("apply-profile needs a name or id")
            from . import core, store
            needle = argv[1].casefold()
            profiles = [p for p in store.load_profiles()
                        if needle in str(p.get("name", "")).casefold() or needle == p.get("id")]
            if not profiles:
                raise ValueError("no profile matches that name")
            result = core.apply_profile(profiles[0])
            print(f"Applied {profiles[0].get('name')} · {result['mode']}")
            return 0
        if command == "apply-saved":
            return _apply_saved(argv[1:])
        if command == "autostart":
            return _autostart(argv)
        if command == "config":
            return _config(argv)
        if command == "doctor":
            return _doctor(argv)
        if command == "reapply-wallpaper":
            from . import core, library, store
            state = store.load_state()
            path = state.get("wallpaper")
            if not path or not os.path.isfile(path) or not library.is_wallpaper(path):
                return 0
            result = core.apply_wallpaper(path, store.load_config(), match_colors=False)
            print(f"Wallpaper restored via {result['result']['backend']}")
            return 0
        if command == "restore":
            from . import core
            core.restore()
            print("Original look restored")
            return 0
        if command == "status":
            from . import system
            print(json.dumps(system.status(), indent=2, ensure_ascii=False))
            return 0
        raise ValueError(f"unknown command: {command}")
    except Exception as error:
        print(f"aura-studio: {error}", file=sys.stderr)
        return 1
