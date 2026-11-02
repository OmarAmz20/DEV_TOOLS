#!/usr/bin/env python3
"""Current-user installation; the existing GNOME setup is never edited here."""
import argparse
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from bootstrap_runtime import has_gtk,has_widgets,download_runtime,runtime_environment

APP="io.github.WallpaperStudioVideo"


def desktop_exec(path):
    return '"'+str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'


def install(source,launch=False,no_runtime=False):
    home=Path.home();data=Path(os.environ.get("XDG_DATA_HOME",home/".local/share"))
    config=Path(os.environ.get("XDG_CONFIG_HOME",home/".config"))
    if not data.is_absolute() or not config.is_absolute():raise RuntimeError("XDG data/config directories must be absolute paths")
    parent=data/"wallpaper-studio-video";runtime=parent/"runtime";destination=parent/"app"
    link=home/".local/bin/wallpaper-studio-video"
    launcher=parent/"launch.sh"
    if (link.exists() or link.is_symlink()) and (not link.is_symlink() or link.resolve()!=launcher.resolve()):
        raise RuntimeError(f"Another command already uses {link}. It was left unchanged.")
    python=None;environment=dict(os.environ);uses_runtime=False
    for candidate in dict.fromkeys(["/usr/bin/python3",sys.executable,shutil.which("python3")]):
        if candidate and Path(candidate).is_file() and has_gtk(candidate) and has_widgets(candidate):python=candidate;break
    if python is None:
        python="/usr/bin/python3"
        if not Path(python).is_file():raise RuntimeError("A system Python 3 is required")
        environment=runtime_environment(runtime)
        if not has_gtk(python,environment) or not has_widgets(python,environment):
            if no_runtime:raise RuntimeError("GTK 4/libadwaita are missing. Run without --no-runtime for the Ubuntu user-local runtime.")
            download_runtime(runtime,python);environment=runtime_environment(runtime)
        uses_runtime=True
    parent.mkdir(parents=True,exist_ok=True)
    # Stop only this app's helper through its own verified PID path.
    if launcher.is_file():
        subprocess.run([str(launcher),"video","stop"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        subprocess.run([str(launcher),"stop"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    helper_lock=Path(os.environ.get('XDG_RUNTIME_DIR',tempfile.gettempdir()))/f'wallpaper-studio-video-{os.getuid()}.lock'
    if helper_lock.exists():
        deadline=time.monotonic()+5
        while True:
            try:
                with helper_lock.open('a+') as handle:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()>deadline:raise RuntimeError('The old session helper is still closing. Open this download again in a moment.')
                time.sleep(.1)
    if launcher.is_file():subprocess.run([str(launcher),'widgets','stop'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
    staged=Path(tempfile.mkdtemp(prefix=".app-",dir=parent))
    try:
        for name in ("wallpaper_studio","wallpapers","vendor","data","tests","examples","packaging"):
            if (source/name).is_dir():shutil.copytree(source/name,staged/name,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
        for name in ("wallpaper-studio-video","bootstrap_runtime.py","install_app.py","install.sh","uninstall.sh","README.md","QUICKSTART.md","VALIDATION.md","LICENSE","NOTICE.md"):
            if (source/name).is_file():shutil.copy2(source/name,staged/name)
        old=parent/".previous-app"
        if old.exists():shutil.rmtree(old)
        if destination.exists():destination.rename(old)
        try:staged.rename(destination)
        except Exception:
            if old.exists():old.rename(destination)
            raise
        if old.exists():shutil.rmtree(old)
    finally:
        if staged.exists():shutil.rmtree(staged)
    script="#!/usr/bin/env bash\nset -euo pipefail\n"
    if uses_runtime:
        for key in ("LD_LIBRARY_PATH","PYTHONPATH","GI_TYPELIB_PATH","XDG_DATA_DIRS"):
            # Values are evaluated by Python now and shell-quoted, never eval'd.
            # Runtime paths are scoped to this launcher and its children.
            script+="export "+key+"="+shlex.quote(environment[key])+"\n"
    script+="exec "+shlex.quote(python)+" "+shlex.quote(str(destination/"wallpaper-studio-video"))+' "$@"\n'
    launcher.write_text(script);launcher.chmod(0o755)
    bin_dir=home/".local/bin";bin_dir.mkdir(parents=True,exist_ok=True)
    link=bin_dir/"wallpaper-studio-video"
    if link.exists() or link.is_symlink():
        if not link.is_symlink() or link.resolve()!=launcher.resolve():
            raise RuntimeError(f"An unrelated command already exists: {link}. It was kept; use {launcher} instead.")
        link.unlink()
    link.symlink_to(launcher)
    icons=data/"icons/hicolor/scalable/apps";icons.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(destination/"data"/(APP+".svg"),icons/(APP+".svg"))
    applications=data/"applications";applications.mkdir(parents=True,exist_ok=True)
    (applications/(APP+".desktop")).write_text(f"[Desktop Entry]\nType=Application\nName=Wallpaper Studio Video\nComment=Native GNOME wallpapers and editable colour recipes\nExec={desktop_exec(launcher)}\nIcon={APP}\nCategories=Settings;DesktopSettings;GTK;\nKeywords=wallpaper;background;theme;colour;color;\nStartupNotify=true\n")
    autostart=config/"autostart";autostart.mkdir(parents=True,exist_ok=True)
    (autostart/"wallpaper-studio-video-session.desktop").write_text(f"[Desktop Entry]\nType=Application\nName=Wallpaper Studio Video session\nComment=Wallpaper rotation and automatic colour mode\nExec={desktop_exec(launcher)} session\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n")
    (autostart/'wallpaper-studio-video-widgets.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Wallpaper Studio Video widgets\nComment=Your enabled desktop widgets\nExec={desktop_exec(launcher)} widgets run\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n')
    (autostart/'wallpaper-studio-video-video.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Wallpaper Studio Video video wallpaper\nComment=Restore the video desktop background\nExec={desktop_exec(launcher)} video start\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n')
    subprocess.run([python,'-c','from wallpaper_studio.assets import install_assets;install_assets()'],cwd=destination,env={**environment,'PYTHONPATH':str(destination)+':'+environment.get('PYTHONPATH','')},check=True)
    extension_source=destination/'wallpaper_studio/video_extension'
    extension_dest=data/'gnome-shell/extensions/wallpaper-studio-video@local'
    if extension_source.is_dir():
        shutil.copytree(extension_source,extension_dest,dirs_exist_ok=True)
        schemas=extension_dest/'schemas'
        if schemas.is_dir() and shutil.which('glib-compile-schemas'):
            subprocess.run(['glib-compile-schemas',str(schemas)],check=False)
        if os.environ.get('XDG_SESSION_TYPE','').lower()=='wayland' and shutil.which('gnome-extensions'):
            subprocess.run(['gnome-extensions','enable','wallpaper-studio-video@local'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if shutil.which("update-desktop-database"):subprocess.run(["update-desktop-database","-q",str(applications)],check=False)
    video_probe='import gi;gi.require_version("Gst","1.0");from gi.repository import Gst;Gst.init(None);r=Gst.Registry.get();assert r.find_feature("gtksink",Gst.ElementFactory) or r.find_feature("gtk4paintablesink",Gst.ElementFactory)'
    if subprocess.run([python,'-c',video_probe],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0:
        print("Video playback needs: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtk-4.0 gstreamer1.0-gtk3 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav")
        print("Ubuntu 22.04/24.04 use gstreamer1.0-gtk3; Ubuntu 25.10+ may also install gstreamer1.0-gtk4.")
    if os.environ.get('XDG_SESSION_TYPE','').lower()=='wayland':
        print("Video wallpaper on Wayland: log out and back in once so GNOME Shell loads the bundled extension.")
    print("Installed version 2.2. Open Wallpaper Studio Video from your applications.")
    print("Command: "+str(link))
    print("Your existing wallpaper profile and GNOME login override were kept.")
    if launch:subprocess.Popen([str(launcher),"open"],start_new_session=True)
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch",action="store_true");parser.add_argument("--no-runtime",action="store_true")
    args=parser.parse_args()
    if os.geteuid()==0:parser.error("Run as your normal desktop user, without sudo.")
    try:install(Path(__file__).resolve().parent,args.launch,args.no_runtime)
    except (RuntimeError,OSError,subprocess.SubprocessError) as error:
        print("Installation: "+str(error),file=sys.stderr);return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
