"""CLI entry point; all imports prepare the same personal GNOME profile."""
import argparse
import json
import sys
from .backend import prepare_environment, NativeBackend


def main(argv=None):
    parser=argparse.ArgumentParser(prog="wallpaper-studio-video",description="Native GNOME wallpapers and editable desktop themes")
    commands=parser.add_subparsers(dest="command")
    opened=commands.add_parser("open");opened.add_argument("--page",choices=["library","appearance","widgets","dock","desktop","session","history","preferences","video"],default="library")
    widget=commands.add_parser('widgets');widget.add_argument('action',nargs='?',choices=['run','show','hide','edit','lock','stop'],default='show')
    change=commands.add_parser("set");change.add_argument("file");change.add_argument("--target",choices=["both","light","dark"])
    change.add_argument("--fit",choices=sorted(NativeBackend.FITS));change.add_argument("--no-theme",action="store_true")
    change.add_argument("--still",action="store_true",help="use a still frame even when the file is a video")
    dock=commands.add_parser("dock");dock.add_argument("action",nargs="?",choices=["start","stop","status"],default="status")
    video=commands.add_parser("video");video.add_argument("action",nargs="?",choices=["set","start","stop","status"],default="status")
    video.add_argument("file",nargs="?");video.add_argument("--fit",choices=["cover","contain"])
    video.add_argument("--monitor",type=int)
    mute=video.add_mutually_exclusive_group();mute.add_argument("--mute",dest="mute",action="store_true",default=None)
    mute.add_argument("--no-mute",dest="mute",action="store_false")
    theme=commands.add_parser("theme");theme.add_argument("name")
    for name in ("next","undo","apply","follow-style","light","dark","auto","start","stop","session","setup","doctor"):
        commands.add_parser(name)
    restore=commands.add_parser("restore");restore.add_argument("--scope",choices=["all","style","wallpaper","desktop"],default="all")
    awake=commands.add_parser("awake");awake.add_argument("minutes",nargs="?",default="60")
    guard=commands.add_parser('guard');guard.add_argument('action',nargs='?',choices=['arm','off','check'],default='check')
    for name in ("export-theme","import-theme"):
        item=commands.add_parser(name);item.add_argument("file")
    args=parser.parse_args(argv)
    prepare_environment()
    if args.command in (None,"open"):
        from .app import main as open_app
        return open_app(getattr(args,"page","library"))
    if args.command=="session":
        from .session import main as session_main
        return session_main()
    if args.command=="dock":
        from . import dock
        if args.action=="start": print(json.dumps(dock.start(),indent=2))
        elif args.action=="stop": print(json.dumps({"stopped":dock.stop()},indent=2))
        else: print(json.dumps(dock.status(),indent=2))
        return 0
    if args.command=='widgets' and args.action=='run':
        try:
            from .widgets import main as widgets_main
            return widgets_main()
        except (ValueError,ImportError,RuntimeError) as error:
            print('Widgets: '+str(error),file=sys.stderr);return 1
    from . import core
    try:
        if args.command=='widgets':
            from . import widget_control
            if args.action=='stop':widget_control.stop()
            else:
                config=widget_control.load();config['enabled']=args.action!='hide'
                if args.action in ('edit','lock'):config['editing']=args.action=='edit'
                print(widget_control.apply(config))
        elif args.command=="set":
            if args.no_theme:core.save_config(auto_style=False)
            status=core.set_wallpaper(args.file,args.target,args.fit,still_only=args.still)
            print(status.summary)
            if status.warning:print(status.warning,file=sys.stderr)
        elif args.command=="video":
            from . import video_wallpaper as video
            if args.action=="set":
                if not args.file:raise ValueError("Choose an existing video file")
                status=core.set_wallpaper(args.file,still_only=False,video_mute=args.mute,
                                          video_fit=args.fit,video_monitor=args.monitor)
                print(video.status_text())
                if status.warning:print(status.warning,file=sys.stderr)
            elif args.action=="start":
                video.start(mute=args.mute,fit=args.fit,monitor=args.monitor)
                print(video.status_text())
            elif args.action=="stop":
                video.stop();print(video.status_text())
            else:
                print(json.dumps(video.status(),indent=2))
        elif args.command=="next":
            path=core.next_wallpaper()
            if not path:raise ValueError("No other wallpapers in this folder")
            print(path)
        elif args.command=="undo":print(core.undo_wallpaper().summary)
        elif args.command=="theme":core.save_config(preset=args.name);print(core.apply_theme())
        elif args.command=="apply":print(core.apply_theme())
        elif args.command=="follow-style":
            state=core.load_state()
            if state.get("style_applied") and state.get("applied_recipe"):core.apply_theme(config_override=state["applied_recipe"])
        elif args.command in ("light","dark","auto"):
            core.save_config(mode=args.command);core.apply_theme()
        elif args.command=="restore":core.restore(args.scope);print("Previous settings restored. Your native wallpaper setup was kept.")
        elif args.command=="start":core.start();print("Session helper started")
        elif args.command=="stop":core.stop();print("Rotation and colour following paused. Your native wallpaper remains set.")
        elif args.command=="setup":print(NativeBackend().ensure_setup().summary)
        elif args.command=="doctor":
            print(json.dumps(vars(NativeBackend().status()),indent=2))
        elif args.command=="awake":
            value=None if args.minutes=="off" else core.FOREVER if args.minutes=="on" else int(args.minutes)
            core.keep_awake(value);print("GNOME presentation request updated")
        elif args.command=='guard':
            from . import screen_guard
            if args.action=='arm':print(core.arm_activity_guard())
            elif args.action=='off':core.keep_awake(None);print('Keep awake and activity guard stopped')
            else:print(json.dumps(screen_guard.probe(),indent=2))
        elif args.command=="export-theme":core.export_recipe(args.file);print("Theme exported")
        elif args.command=="import-theme":core.import_recipe(args.file);print("Theme loaded for preview. Apply it in the app or run 'apply'.")
    except (ValueError,OSError,RuntimeError) as error:
        print(f"Wallpaper Studio Video: {error}",file=sys.stderr);return 1
    return 0
