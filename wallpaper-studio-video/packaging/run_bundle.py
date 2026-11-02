"""Embedded bootstrap for the single-file Linux launcher (Python standard library)."""
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile

TRAILER=struct.Struct('<8sQQ32s')
MAGIC=b'WSPRUN21'
APP='io.github.WallpaperStudioVideo'


def notify(title,message,error=False):
    zenity=shutil.which('zenity')
    if zenity:
        subprocess.run([zenity,'--error' if error else '--info','--title='+title,'--text='+html.escape(message),'--width=460'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return
    try:
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk
        dialog=Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.OK,text=title)
        dialog.format_secondary_text(message);dialog.run();dialog.destroy()
        return
    except Exception:pass
    try:
        import tkinter
        from tkinter import messagebox
        root=tkinter.Tk();root.withdraw()
        (messagebox.showerror if error else messagebox.showinfo)(title,message)
        root.destroy()
    except Exception:
        print(title+': '+message,file=sys.stderr)


def inspect_bundle(path):
    with Path(path).open('rb') as stream:
        size=stream.seek(0,2)
        if size<TRAILER.size:raise RuntimeError('The download is incomplete. Download the app again.')
        stream.seek(-TRAILER.size,2)
        magic,offset,length,digest=TRAILER.unpack(stream.read(TRAILER.size))
        if magic!=MAGIC or offset+length+TRAILER.size!=size or not 0<length<128*1024*1024:
            raise RuntimeError('The download is incomplete or damaged. Download the app again.')
        stream.seek(offset);remaining=length;checksum=hashlib.sha256()
        while remaining:
            chunk=stream.read(min(1024*1024,remaining))
            if not chunk:raise RuntimeError('The download is incomplete.')
            checksum.update(chunk);remaining-=len(chunk)
        if checksum.digest()!=digest:raise RuntimeError('The app checksum did not match. Download the app again.')
        return offset,length,digest.hex()


def unpack_bundle(path,offset,destination):
    total=0
    with Path(path).open('rb') as stream:
        stream.seek(offset)
        with tarfile.open(fileobj=stream,mode='r|gz') as archive:
            for index,member in enumerate(archive):
                relative=Path(member.name)
                if index>3000 or relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0]!='wallpaper-studio-video':
                    raise RuntimeError('Invalid app archive path.')
                if not (member.isfile() or member.isdir()):raise RuntimeError('Unsupported app archive entry.')
                total+=member.size
                if total>256*1024*1024:raise RuntimeError('App archive is unexpectedly large.')
                target=destination/relative
                if member.isdir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as source,target.open('wb') as output:shutil.copyfileobj(source,output)
                target.chmod(0o755 if member.mode&0o111 else 0o644)
    return destination/'wallpaper-studio-video'


def application_running():
    if not shutil.which('gdbus'):return False
    result=subprocess.run(['gdbus','call','--session','--dest','org.freedesktop.DBus','--object-path','/org/freedesktop/DBus','--method','org.freedesktop.DBus.NameHasOwner',APP],capture_output=True,text=True,timeout=3)
    return result.returncode==0 and 'true' in result.stdout


def close_for_update():
    if not application_running():return True
    if shutil.which('zenity'):
        result=subprocess.run(['zenity','--question','--title=Update Wallpaper Studio Video','--text=Close the current Wallpaper Studio Video window and update? Saved settings and pictures will be kept. Apply any pending widget edits first.','--ok-label=Close and update','--cancel-label=Cancel','--width=460'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if result.returncode:return False
    else:
        notify('Close Wallpaper Studio Video','Close the existing app window, then open this download again.')
        return False
    subprocess.run(['gdbus','call','--session','--dest',APP,'--object-path','/io/github/WallpaperStudioVideo','--method','org.gtk.Actions.Activate','quit','[]','{}'],capture_output=True,timeout=3,check=True)
    import time
    for _ in range(30):
        if not application_running():return True
        time.sleep(.1)
    raise RuntimeError('The old app window did not close. Close it normally and open this download again.')


def progress_window():
    zenity=shutil.which('zenity')
    if zenity:
        command=[zenity,'--progress','--pulsate','--auto-close','--no-cancel','--title=Wallpaper Studio Video','--text=Preparing the app for your account…','--width=470']
    else:
        code='''import gi,sys,html
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
w=Gtk.Window(title='Wallpaper Studio Video');w.set_default_size(460,170);w.set_deletable(False);w.set_position(Gtk.WindowPosition.CENTER)
b=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,margin=24);w.add(b)
t=Gtk.Label(label='Preparing Wallpaper Studio Video',xalign=0);b.pack_start(t,False,False,0)
s=Gtk.Label(label='Setting up for your account. The first run may take a few minutes.',xalign=0,wrap=True);b.pack_start(s,False,False,0)
p=Gtk.ProgressBar();b.pack_start(p,False,False,0)
def pulse():p.pulse();return True
def line(stream,condition):
    value=stream.readline()
    if not value:Gtk.main_quit();return False
    s.set_text(html.unescape(value.lstrip('# ').strip()));return True
GLib.timeout_add(110,pulse);GLib.io_add_watch(sys.stdin,GLib.IO_IN|GLib.IO_HUP,line)
w.show_all();Gtk.main()
'''
        command=[sys.executable,'-c',code]
    return subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)


def launch(launcher,cache):
    log=cache/'app.log'
    if log.exists() and log.stat().st_size>1024*1024:log.replace(cache/'app.previous.log')
    with log.open('a') as output:
        subprocess.Popen([str(launcher),'open'],stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)


def main():
    path=Path(sys.argv[1])
    options=sys.argv[2:]
    try:
        offset,length,digest=inspect_bundle(path)
        if options==['--verify']:
            print(json.dumps({'valid':True,'version':'2.2','payload_bytes':length,'sha256':digest}));return 0
        if options:
            print('Open this file without arguments. --verify checks the download.');return 0
        if os.geteuid()==0:raise RuntimeError('Open the app as your normal desktop user, without sudo.')
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError('Open this download from your desktop session.')
        os.umask(0o077)
        home=Path.home();data=Path(os.environ.get('XDG_DATA_HOME',home/'.local/share'))
        cache=Path(os.environ.get('XDG_CACHE_HOME',home/'.cache'))/'wallpaper-studio-video'
        if not data.is_absolute() or not cache.is_absolute():raise RuntimeError('Desktop data and cache paths must be absolute.')
        cache.mkdir(parents=True,exist_ok=True)
        with (cache/'install.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:notify('Wallpaper Studio Video','Setup is already running. Wait for its window to finish.');return 0
            parent=data/'wallpaper-studio-video';launcher=parent/'launch.sh'
            try:stamp=json.loads((parent/'bundle.json').read_text())
            except (OSError,ValueError):stamp={}
            if stamp.get('sha256')==digest and launcher.is_file() and (parent/'app/wallpaper-studio-video').is_file():
                launch(launcher,cache);return 0
            if not close_for_update():return 0
            progress=progress_window()
            try:
                with tempfile.TemporaryDirectory(prefix='wallpaper-studio-video-') as temporary:
                    source=unpack_bundle(path,offset,Path(temporary))
                    with (cache/'install.log').open('w') as log:
                        process=subprocess.Popen([sys.executable,'-u',str(source/'install_app.py')],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                        tail=[]
                        for line in process.stdout:
                            log.write(line);log.flush();tail=(tail+[line.strip()])[-8:]
                            if progress and progress.poll() is None:
                                try:progress.stdin.write('# '+html.escape(line.strip())+'\n');progress.stdin.flush()
                                except (BrokenPipeError,OSError):pass
                        code=process.wait()
                        if code:raise RuntimeError('\n'.join(tail)+'\n\nSetup details: '+str(cache/'install.log'))
                    (parent/'bundle.json').write_text(json.dumps({'version':'2.2','sha256':digest})+'\n')
            finally:
                if progress:
                    try:progress.stdin.close();progress.wait(timeout=3)
                    except (OSError,subprocess.TimeoutExpired):progress.terminate()
            launch(launcher,cache)
        return 0
    except Exception as error:
        if options==['--verify']:
            print(str(error),file=sys.stderr);return 1
        notify('Wallpaper Studio Video — could not open',str(error),error=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
