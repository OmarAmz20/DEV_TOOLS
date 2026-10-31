"""wallpaper-lite — a small wallpaper picker with colours from the picture.

    wallpaper-lite               open the window
    wallpaper-lite set FILE      use a picture
    wallpaper-lite next          a random different picture from your folder
    wallpaper-lite light|dark    choose the colour mode
    wallpaper-lite apply         re-apply the current picture and mode
    wallpaper-lite restore       put your original look back
    wallpaper-lite stop          stop the X11 desktop helper
    wallpaper-lite desktop       the desktop helper (internal)
"""
import sys

# Some AppImages export a private GSettings backend; always use the real one.
import os

if os.environ.get("GSETTINGS_BACKEND") == "keyfile":
    os.environ["GSETTINGS_BACKEND"] = "dconf"


def main(argv):
    command = argv[1] if len(argv) > 1 else "open"

    if command in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if command == "open":
        from . import app
        return app.main()
    if command == "desktop":
        from . import desktop
        return desktop.main()

    from . import core

    try:
        if command == "set" and len(argv) > 2:
            message = core.set_wallpaper(argv[2])
            print(message or "Wallpaper applied.")
        elif command == "next":
            picked = core.next_wallpaper()
            if picked is None:
                print("wallpaper-lite: no other pictures in", core.load_config()["folder"],
                      file=sys.stderr)
                return 1
            print("Wallpaper:", picked)
        elif command in ("light", "dark"):
            core.set_mode(command)
            print("Colour mode:", command)
        elif command == "apply":
            message = core.apply_theme()
            print(message or "Nothing to apply yet.")
        elif command == "restore":
            core.restore()
            print("Original look restored.")
        elif command == "stop":
            core.stop_helper()
            print("Desktop helper stopped.")
        else:
            print(__doc__.strip())
            return 1
    except (ValueError, OSError) as exc:
        print(f"wallpaper-lite: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
