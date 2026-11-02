"""Command-line interface for 1337-Customizer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import constants, desktop, themes, video, wallpaper, sessiond
from .config import Config
from .library import Library
from .util import notify, read_json, write_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="1337-customizer",
        description="1337-Customizer — wallpapers, looks, fonts, widgets and video wallpapers.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {constants.VERSION}")
    parser.add_argument("--background", action="store_true", help="start enabled helpers without opening the GUI")
    sub = parser.add_subparsers(dest="command")

    set_parser = sub.add_parser("set", help="set a wallpaper")
    set_parser.add_argument("path")
    set_parser.add_argument("--monitor", default=None)
    set_parser.add_argument("--fit", choices=constants.FIT_MODES, default=None)
    set_parser.add_argument("--no-theme", action="store_true")
    set_parser.add_argument("--video", action="store_true", help="force video mode")
    set_parser.add_argument("--still", action="store_true", help="apply a still frame instead of video")

    next_parser = sub.add_parser("next", help="apply the next library wallpaper")
    next_parser.add_argument("--favorites", action="store_true")

    sub.add_parser("undo", help="apply the previous wallpaper")

    theme_parser = sub.add_parser("theme", help="apply or list looks")
    theme_parser.add_argument("name", nargs="?")
    theme_parser.add_argument("--mode", choices=("auto", "light", "dark"), default=None)
    theme_parser.add_argument("--wallpaper", action="store_true", help="sample colours from the current wallpaper")
    theme_parser.add_argument("--list", action="store_true")
    theme_parser.add_argument("--file", help="import a theme JSON and apply it")

    video_parser = sub.add_parser("video", help="control the video wallpaper engine")
    video_parser.add_argument("action", nargs="?", choices=("start", "stop", "status", "build"), default="status")
    video_parser.add_argument("path", nargs="?")
    video_parser.add_argument("--monitor", default=None)
    video_parser.add_argument("--fit", choices=("crop", "fit"), default=None)

    widgets_parser = sub.add_parser("widgets", help="control desktop widgets")
    widgets_parser.add_argument(
        "action", nargs="?", default="status",
        choices=("start", "stop", "edit", "status", "add", "remove", "list", "reset"),
    )
    widgets_parser.add_argument("value", nargs="?", help="widget type for add, or widget id/index for remove")

    slideshow_parser = sub.add_parser("slideshow", help="control the session helper")
    slideshow_parser.add_argument("action", nargs="?", choices=("start", "stop", "status"), default="status")

    fonts_parser = sub.add_parser("fonts", help="apply fonts without opening the studio")
    fonts_parser.add_argument("--ui")
    fonts_parser.add_argument("--mono")
    fonts_parser.add_argument("--doc")
    fonts_parser.add_argument("--scale", type=float)

    restore_parser = sub.add_parser("restore", help="restore changes")
    restore_parser.add_argument("--scope", choices=("look", "wallpaper", "all"), default="look")

    sub.add_parser("doctor", help="print a diagnostics report as JSON")
    sub.add_parser("about", help="print version information")

    theme_export = sub.add_parser("export-theme", help="export the current look")
    theme_export.add_argument("path")
    theme_import = sub.add_parser("import-theme", help="import a look JSON")
    theme_import.add_argument("path")

    autostart = sub.add_parser("autostart", help="manage the login helper")
    autostart.add_argument("action", choices=("on", "off", "status"), default="status", nargs="?")
    return parser


def _print(payload) -> int:
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)
    return 0


def _background() -> int:
    config = Config()
    sessiond.start_if_needed(config)
    if config.get("widgets.enabled") and config.get("widgets.restore_on_login", True):
        try:
            from . import widget_daemon

            widget_daemon.start(edit=False)
        except Exception:
            pass
    if config.get("video.restore_on_login", True):
        video.restart_from_config(config)
    return 0


def _set(config: Config, path: str, monitor: str | None, fit: str | None,
         no_theme: bool, force_video: bool, still: bool) -> int:
    video_mode = force_video or (Path(path).suffix.lower() in constants.VIDEO_EXTENSIONS and not still)
    if video_mode:
        if fit:
            config.set("video.fit", fit, save=False)
        if monitor:
            config.set("video.monitor", monitor, save=False)
        config.set("video.path", path, save=False)
        config.save()
        result = video.start(path, config)
        return _print(result)
    result = wallpaper.apply(
        path, config, monitor=monitor, fit=fit, allow_video=False,
        apply_theme=False if no_theme else None,
    )
    return _print(result)


def _theme(config: Config, args) -> int:
    if args.list:
        return _print([{"id": item["id"], "name": item["name"]} for item in themes.all_presets()])
    if args.file:
        preset = themes.import_theme(read_json(args.file, {}))
        if not preset:
            print("Not a 1337-Customizer theme file", file=sys.stderr)
            return 1
        theme_id = themes.save_custom_theme(preset)
        config.set("appearance.theme", theme_id, save=False)
    elif args.wallpaper:
        config.set("appearance.theme", themes.WALLPAPER_PRESET, save=False)
    elif args.name:
        preset = themes.find_preset(args.name)
        if not preset:
            print(f"Unknown theme: {args.name}", file=sys.stderr)
            return 1
        config.set("appearance.theme", args.name, save=False)
    if args.mode:
        config.set("appearance.mode", args.mode, save=False)
    config.save()
    theme, report = desktop.apply_theme_from_config(config)
    return _print({"theme": theme["name"], "variant": theme["variant"], **report})


def _video(config: Config, args) -> int:
    if args.action == "status":
        return _print(video.state())
    if args.action == "stop":
        return _print({"stopped": video.stop(notify_user=True)})
    if args.action == "build":
        return _print(video.build_engine())
    if not args.path:
        print("video start needs a path", file=sys.stderr)
        return 1
    if args.monitor:
        config.set("video.monitor", args.monitor, save=False)
    if args.fit:
        config.set("video.fit", args.fit, save=False)
    config.set("video.path", args.path, save=False)
    config.save()
    return _print(video.start(args.path, config))


def _widgets(config: Config, action: str, value: str | None = None) -> int:
    from . import widget_daemon, widgets

    items = widgets.normalise_items(config.get("widgets.items", []))
    if action == "list":
        return _print([
            {"index": index, "id": item["id"], "type": item["type"],
             "enabled": item["enabled"], "monitor": item.get("monitor", "")}
            for index, item in enumerate(items)
        ])
    if action == "add":
        if not value or value not in widgets.WIDGET_TYPES:
            print("widgets add needs a type: " + ", ".join(widgets.WIDGET_TYPES), file=sys.stderr)
            return 1
        item = widgets.new_item(value, items)
        items.append(item)
        config.set("widgets.items", items)
        config.save()
        return _print({"added": item["id"], "type": value, "running": widget_daemon.running()})
    if action == "remove":
        if value is None:
            print("widgets remove needs an id or index", file=sys.stderr)
            return 1
        target = None
        for index, item in enumerate(items):
            if item["id"] == value or str(index) == str(value):
                target = item
                break
        if target is None:
            print(f"No widget matches {value}", file=sys.stderr)
            return 1
        items = [item for item in items if item["id"] != target["id"]]
        config.set("widgets.items", items)
        config.save()
        return _print({"removed": target["id"], "remaining": len(items),
                       "running": widget_daemon.running()})
    if action == "reset":
        config.set("widgets.items", widgets.default_items())
        config.save()
        return _print({"reset": True, "running": widget_daemon.running()})
    if action == "status":
        return _print(widget_daemon.status())
    if action == "stop":
        stopped = widget_daemon.stop()
        config.set("widgets.enabled", False)
        config.save()
        return _print({"stopped": stopped})
    config.set("widgets.enabled", True)
    config.save()
    return _print(widget_daemon.start(edit=action == "edit"))


def _slideshow(config: Config, action: str) -> int:
    if action == "status":
        return _print(sessiond.status())
    if action == "stop":
        config.set("wallpaper.slideshow.enabled", False)
        config.save()
        return _print({"stopped": sessiond.stop()})
    config.set("wallpaper.slideshow.enabled", True)
    config.save()
    return _print(sessiond.start())


def _fonts(config: Config, args) -> int:
    if args.ui:
        config.set("appearance.ui_font", args.ui, save=False)
    if args.mono:
        config.set("appearance.mono_font", args.mono, save=False)
    if args.doc:
        config.set("appearance.doc_font", args.doc, save=False)
    if args.scale is not None:
        config.set("appearance.text_scale", float(args.scale), save=False)
    config.set("appearance.apply_fonts", True, save=False)
    config.save()
    return _print(desktop.apply_fonts(config))


def _restore(config: Config, scope: str) -> int:
    payload = {}
    if scope in ("look", "all"):
        payload["look"] = desktop.restore_theme()
    if scope in ("wallpaper", "all"):
        payload["wallpaper"] = wallpaper.restore()
    if scope == "all":
        from . import widget_daemon

        payload["widgets"] = {"stopped": widget_daemon.stop()}
        payload["video"] = {"stopped": video.stop()}
        payload["session"] = {"stopped": sessiond.stop()}
    return _print(payload)


def _autostart(config: Config, action: str) -> int:
    autostart_dir = constants.CONFIG_HOME / "autostart"
    path = autostart_dir / "1337-customizer.desktop"
    if action == "status":
        return _print({"enabled": path.exists(), "path": str(path)})
    if action == "off":
        for target in (path, constants.LEGACY_AUTOSTART):
            try:
                target.unlink()
            except OSError:
                pass
        config.set("autostart", False)
        return _print({"enabled": False})
    launcher = constants.APP_ROOT / "1337-customizer"
    command = str(launcher) if launcher.exists() else "1337-customizer"
    autostart_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        constants.LEGACY_AUTOSTART.unlink()
    except OSError:
        pass
    path.write_text(
        f"""[Desktop Entry]
Type=Application
Name=1337-Customizer helper
Exec={command} --background
Icon=1337-customizer
Terminal=false
X-GNOME-Autostart-enabled=true
""",
        encoding="utf-8",
    )
    config.set("autostart", True)
    return _print({"enabled": True, "path": str(path)})


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    args = parser.parse_args(argv)
    if args.background:
        return _background()
    if not args.command:
        from .app import main as gui_main

        return gui_main([])
    config = Config()
    from .util import set_notifications

    set_notifications(bool(config.get("notifications", True)))
    try:
        if args.command == "set":
            return _set(config, args.path, args.monitor, args.fit, args.no_theme, args.video, args.still)
        if args.command == "next":
            result = wallpaper.next_wallpaper(config)
            return _print(result or {})
        if args.command == "undo":
            library = Library()
            previous = library.history_item(1)
            if not previous:
                print("No previous wallpaper", file=sys.stderr)
                return 1
            return _set(config, previous["path"], previous.get("monitor"), previous.get("fit"), False, False, False)
        if args.command == "theme":
            return _theme(config, args)
        if args.command == "video":
            return _video(config, args)
        if args.command == "widgets":
            return _widgets(config, args.action, getattr(args, "value", None))
        if args.command == "slideshow":
            return _slideshow(config, args.action)
        if args.command == "fonts":
            return _fonts(config, args)
        if args.command == "restore":
            return _restore(config, args.scope)
        if args.command == "doctor":
            return _print(desktop.environment_report())
        if args.command == "about":
            return _print({"name": constants.APP_NAME, "version": constants.VERSION,
                           "app_id": constants.APP_ID, "root": str(constants.APP_ROOT)})
        if args.command == "export-theme":
            theme = desktop.load_applied_theme() or themes.resolve_theme(
                config.get("appearance.theme", "midnight-aurora"),
                mode=config.get("appearance.mode", "dark"),
                schedule=config.get("appearance.dark_schedule"),
                wallpaper_path=themes.wallpaper_path_from_state(),
                overrides=config.get("appearance", {}),
            )
            write_json(args.path, themes.export_theme(theme))
            return _print({"exported": args.path})
        if args.command == "import-theme":
            preset = themes.import_theme(read_json(args.path, {}))
            if not preset:
                print("Not a 1337-Customizer theme file", file=sys.stderr)
                return 1
            theme_id = themes.save_custom_theme(preset)
            config.set("appearance.theme", theme_id)
            return _print({"imported": preset["name"], "id": theme_id})
        if args.command == "autostart":
            return _autostart(config, args.action)
    except Exception as error:
        print(f"1337-customizer: {error}", file=sys.stderr)
        return 1
    parser.print_help()
    return 0
