"""Native wallpaper and reversible colour editing.
Based on Wallpaper Studio by Adil Asselman, MIT license (see LICENSE).
"""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from .backend import NativeBackend, atomic_write, prepare_environment
prepare_environment()
from gi.repository import Gio, GLib
from . import palette, recipes,skins
from . import video_wallpaper as video

APP_ID="io.github.WallpaperStudioVideo"
HOME=str(Path.home())


def _cache_dir():
    override=os.environ.get("WALLPAPER_STUDIO_CACHE_DIR")
    if override:return override
    goinfre=os.environ.get("WALLPAPER_STUDIO_GOINFRE") or os.path.join(HOME,"goinfre")
    if os.path.isdir(goinfre) and os.access(goinfre,os.W_OK):
        return os.path.join(os.path.realpath(goinfre),"wallpaper-studio-video","cache")
    return os.path.join(os.environ.get("XDG_CACHE_HOME",os.path.join(HOME,".cache")),"wallpaper-studio-video")


CONFIG_DIR=os.path.join(os.environ.get("XDG_CONFIG_HOME",os.path.join(HOME,".config")),"wallpaper-studio-video")
CACHE_DIR=_cache_dir()
DATA_DIR=os.path.join(os.environ.get("XDG_DATA_HOME",os.path.join(HOME,".local/share")),"wallpaper-studio-video")
CONFIG=os.path.join(CONFIG_DIR,"config.json")
STATE=os.path.join(CONFIG_DIR,"state.json")
ORIGINALS=os.path.join(CONFIG_DIR,"originals.json")
HISTORY=os.path.join(CONFIG_DIR,"history.json")
THEME_CSS=os.path.join(CONFIG_DIR,"theme.css")
HOOKS=os.path.join(CONFIG_DIR,"hooks")
STOPPED=os.path.join(CONFIG_DIR,"stopped")
RUNTIME=os.environ.get("XDG_RUNTIME_DIR",tempfile.gettempdir())
HELPER_LOCK=os.path.join(RUNTIME,f"wallpaper-studio-video-{os.getuid()}.lock")
AWAKE=os.path.join(RUNTIME,f"wallpaper-studio-video-awake-{os.getuid()}.json")
SESSION_STATE=os.path.join(RUNTIME,f"wallpaper-studio-video-session-{os.getuid()}.json")
BUILT_IN=str(Path(__file__).resolve().parent.parent/"wallpapers")
FOREVER=-1
IMAGE_EXT=(".jpg",".jpeg",".png",".webp",".jxl",".bmp",".tif",".tiff",".gif")
VIDEO_EXT=(".mp4",".webm",".mkv",".mov",".m4v",".avi")
DEFAULT_CONFIG={"mode":"auto","folder":BUILT_IN,"rotate_hours":0,"glass":False,"terminal":True,
    "auto_style":True,"preset":"wallpaper","accent":"","tint":.35,"high_contrast":False,
    "shape":"soft","target":"both","fit":"zoom","favorites":[],"sort":"name","run_hooks":False,
    "skin":"auto","pixel_font":True,"theme_extras":True,"panel_theme":False,"custom_light":{},"custom_dark":{},"custom_name":"My Custom Theme"}
APPEARANCE_KEYS=("preset","mode","accent","tint","high_contrast","shape","glass","terminal","skin","pixel_font","theme_extras","panel_theme","custom_light","custom_dark","custom_name")
BG_KEYS=[("org.gnome.desktop.background",k) for k in ("picture-uri","picture-uri-dark","picture-options")]
STYLE_KEYS=[("org.gnome.desktop.interface",k) for k in ("gtk-theme","color-scheme")]+[("org.gnome.desktop.background","primary-color")]
THEMES_DIR=os.path.join(os.environ.get("XDG_DATA_HOME",os.path.join(HOME,".local/share")),"themes")
OUR_THEMES=("Wallpaper Studio Video A","Wallpaper Studio Video B")
CSS_MARKER="/* wallpaper-studio-video */"
_thread_lock=threading.RLock()
_local=threading.local()


def _read_json(path,default):
    try:
        with open(path,encoding="utf-8") as stream:return json.load(stream)
    except (OSError,ValueError):return default


def _write(path,text):atomic_write(Path(path),text)
def _json(path,data):_write(path,json.dumps(data,indent=2,ensure_ascii=False)+"\n")


@contextlib.contextmanager
def locked():
    with _thread_lock:
        depth=getattr(_local,"depth",0);_local.depth=depth+1;handle=None
        try:
            if depth==0:
                os.makedirs(CONFIG_DIR,exist_ok=True)
                handle=open(os.path.join(CONFIG_DIR,".lock"),"a")
                fcntl.flock(handle,fcntl.LOCK_EX)
            yield
        finally:
            _local.depth=depth
            if handle:handle.close()


def _validate_config(raw,strict=False):
    config=dict(DEFAULT_CONFIG)
    checks={"preset":recipes.PRESETS,"mode":("auto","light","dark"),"fit":NativeBackend.FITS,
            "target":("both","light","dark"),"shape":("soft","crisp","square"),"sort":("name","newest","favorites"),"skin":skins.SKINS}
    for key,value in raw.items():
        if key not in DEFAULT_CONFIG:continue
        valid=True
        if key in checks:valid=isinstance(value,str) and value in checks[key]
        elif key in ("tint","rotate_hours"):
            valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and 0<=value<=(1 if key=="tint" else 168)
        elif isinstance(DEFAULT_CONFIG[key],bool):valid=isinstance(value,bool)
        elif key=="accent":valid=isinstance(value,str) and (not value or recipes.valid_hex(value))
        elif key=="favorites":valid=isinstance(value,list) and all(isinstance(p,str) for p in value)
        elif key=="folder":valid=isinstance(value,str) and bool(value)
        elif key in ('custom_light','custom_dark'):valid=isinstance(value,dict) and all(k in recipes.COLOUR_KEYS and recipes.valid_hex(v) for k,v in value.items())
        elif key=='custom_name':valid=isinstance(value,str) and 1<=len(value.strip())<=48
        if valid:config[key]=value
        elif strict:raise ValueError(f"Invalid value for {key.replace('_',' ')}")
    return config


def load_config():
    raw=_read_json(CONFIG,{})
    config=_validate_config(raw if isinstance(raw,dict) else {})
    try:_check_custom_contrast(config)
    except ValueError:config.update(custom_light={},custom_dark={})
    return config


def _check_custom_contrast(config):
    if config['preset']!='custom':return
    for result in recipes.resolve(recipes.sample_base(),config).values():
        metrics=recipes.metrics(result)
        if metrics['text']<(7 if config['high_contrast'] else 4.5) or metrics['secondary']<4.5:
            raise ValueError('Those backgrounds need conflicting text colours. Keep the window, sidebar and card surfaces similarly light or dark; switch Light/Dark before building that variant.')


def save_config(**changes):
    _validate_config(changes,strict=True)
    with locked():
        config={**load_config(),**changes};_check_custom_contrast(config);_json(CONFIG,config)
    return config


def load_state():
    value=_read_json(STATE,{})
    return value if isinstance(value,dict) else {}
def _save_state(state):_json(STATE,state)
def is_video(path):return bool(path) and str(path).lower().endswith(VIDEO_EXT)
def is_wallpaper(path):return str(path).lower().endswith(IMAGE_EXT+VIDEO_EXT)


def _cache_name(path,ext):
    stat=os.stat(path)
    key=f"{os.path.realpath(path)}:{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]+ext


def video_frame(path):
    """Videos become still frames so the wallpaper keeps using native GNOME."""
    output=os.path.join(CACHE_DIR,"frames",_cache_name(path,".jpg"))
    if os.path.isfile(output):return output
    os.makedirs(os.path.dirname(output),exist_ok=True)
    if shutil.which("ffmpeg"):
        for seek in ("2","0"):
            result=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-ss",seek,"-i",path,
                "-frames:v","1","-vf","scale='min(1920,iw)':-2","-y",output],
                capture_output=True,text=True,timeout=20,check=False)
            if result.returncode==0 and os.path.isfile(output):return output
    if shutil.which("cvlc"):
        with tempfile.TemporaryDirectory(dir=os.path.dirname(output)) as temporary:
            subprocess.run(["cvlc","--intf","dummy","--no-audio","--avcodec-hw=none","--vout","dummy",
                "--video-filter=scene","--scene-format=jpg","--scene-ratio=1000","--scene-prefix=frame",
                f"--scene-path={temporary}","--start-time=2","--run-time=1","--play-and-exit",path],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
            frames=sorted(Path(temporary).glob("*.jpg"))
            if frames:shutil.copyfile(frames[0],output);return output
    raise ValueError("Reading a video frame needs FFmpeg or VLC. Pictures work without either.")


def still_of(path):return video_frame(path) if is_video(path) else path


def _keep_image(path):
    digest=hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
    extension=Path(path).suffix.lower()
    if extension not in IMAGE_EXT:extension=".png"
    destination=Path(DATA_DIR)/"images"/(digest.hexdigest()+extension)
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        fd,temp=tempfile.mkstemp(prefix=".image-",dir=destination.parent)
        try:
            with os.fdopen(fd,"wb") as output,open(path,"rb") as source:shutil.copyfileobj(source,output)
            os.replace(temp,destination)
        finally:
            if os.path.exists(temp):os.unlink(temp)
    return str(destination)


def _settings(schema,path=None):
    source=Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(schema,True) is None:return None
    return Gio.Settings.new_with_path(schema,path) if path else Gio.Settings.new(schema)


def _set(schema,key,value):
    settings=_settings(schema)
    if settings is None or key not in settings.list_keys() or not settings.is_writable(key):return False
    return settings.set_value(key,value)


def _save_originals(keys):
    saved=_read_json(ORIGINALS,{})
    for schema,key in keys:
        name=f"{schema} {key}"
        if name in saved:continue
        settings=_settings(schema)
        if settings is not None and key in settings.list_keys():
            original=settings.get_user_value(key)
            saved[name]=None if original is None else original.print_(True)
    _json(ORIGINALS,saved)


def effective_mode(config=None):
    config=config or load_config()
    if config["mode"] in ("dark","light"):return config["mode"]
    settings=_settings("org.gnome.desktop.interface")
    return "dark" if settings and settings.get_string("color-scheme")=="prefer-dark" else "light"


def preview_palette(path=None,config=None):
    config=config or load_config()
    base=load_state().get("base_palette")
    if path:base=palette.from_image(still_of(path))
    return recipes.resolve(base or recipes.sample_base(),config)


def wallpapers(folder=None):
    folder=folder or load_config()["folder"]
    try:names=os.listdir(folder)
    except OSError:return []
    files=[os.path.join(folder,name) for name in names if not name.startswith(".") and is_wallpaper(name)
           and os.path.isfile(os.path.join(folder,name))]
    return sorted(files,key=lambda value:os.path.basename(value).casefold())


def filtered_wallpapers(query="",favorites=False,kind="all",sort="name"):
    config=load_config();preferred=set(config["favorites"])
    result=[p for p in wallpapers() if query.casefold() in Path(p).stem.casefold()
        and (not favorites or os.path.realpath(p) in preferred)
        and (kind=="all" or (is_video(p) if kind=="video" else not is_video(p)))]
    if sort=="newest":result.sort(key=lambda p:os.path.getmtime(p),reverse=True)
    elif sort=="favorites":result.sort(key=lambda p:(os.path.realpath(p) not in preferred,Path(p).name.casefold()))
    return result


def toggle_favorite(path):
    with locked():
        values=list(load_config()["favorites"]);path=os.path.realpath(path)
        if path in values:values.remove(path)
        else:values.append(path)
        return save_config(favorites=values)["favorites"]


def history():
    value=_read_json(HISTORY,[])
    return [entry for entry in value if isinstance(entry,dict) and isinstance(entry.get("wallpaper"),str)] if isinstance(value,list) else []


def set_wallpaper(path,target=None,fit=None,record=True,still_only=None,
                  video_mute=None,video_fit=None,video_monitor=None):
    path=os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(path) or not is_wallpaper(path):raise ValueError("Choose an existing picture or video.")
    use_video=is_video(path) and still_only is not True
    still=still_of(path);base=palette.from_image(still);durable=_keep_image(still)
    config=load_config();target=target or config["target"];fit=fit or config["fit"]
    with locked():
        _save_originals(BG_KEYS)
        status=NativeBackend().apply_image(durable,target,fit)
        state={**load_state(),"wallpaper":durable,"source":path,"still":durable,
               "base_palette":base,"changed":time.time(),"target":target,"fit":fit,
               "video":use_video,"video_path":path if use_video else ""}
        _save_state(state)
        if record:
            previous=history()
            if not previous:
                originals=_read_json(ORIGINALS,{})
                raw=originals.get("org.gnome.desktop.background picture-uri")
                if raw:
                    import ast
                    from urllib.parse import unquote,urlparse
                    parsed=urlparse(ast.literal_eval(raw))
                    if parsed.scheme=="file" and os.path.isfile(unquote(parsed.path)):
                        previous.append({"source":unquote(parsed.path),"wallpaper":unquote(parsed.path),"changed":0,"target":"both","fit":fit})
            item={key:state[key] for key in ("source","wallpaper","changed","target","fit","video")}
            if not previous or previous[-1]["wallpaper"]!=durable or previous[-1].get("target")!=target:previous.append(item)
            _json(HISTORY,previous[-30:])
    if use_video:
        try:
            video.start(path,mute=video_mute,fit=video_fit,monitor=video_monitor)
        except (OSError,ValueError,RuntimeError) as error:
            use_video=False
            message=f"Video wallpaper could not start: {error}"
            status.warning=f"{status.warning} {message}".strip() if getattr(status,"warning","") else message
            with locked():_save_state({**load_state(),"video":False,"video_path":""})
    else:
        video.stop()
    if config["auto_style"]:
        try:apply_theme(durable)
        except (ValueError,OSError,RuntimeError,GLib.Error) as error:status.warning=f"Wallpaper applied. Colours could not be updated: {error}"
    start();return status


def undo_wallpaper():
    entries=history()
    if len(entries)<2:raise ValueError("There is no earlier wallpaper to restore yet.")
    previous=entries[-2]
    source=(previous.get("source") if previous.get("video") else previous.get("wallpaper")) \
        or previous.get("source") or previous.get("wallpaper")
    result=set_wallpaper(source,previous.get("target","both"),previous.get("fit","zoom"),
                         record=False,still_only=not previous.get("video",False))
    with locked():_json(HISTORY,entries[:-1])
    return result


def next_wallpaper():
    current=load_state().get("source");choices=[p for p in wallpapers() if os.path.realpath(p)!=current]
    if not choices:return None
    path=random.choice(choices);set_wallpaper(path);return path


def _theme_dir(name):
    bundled=Path(__file__).resolve().parent.parent/"vendor"
    for parent in (THEMES_DIR,os.path.join(HOME,".themes"),"/usr/share/themes",str(bundled)):
        path=os.path.join(parent,name)
        if os.path.isdir(path):return path
    return None


def _write_themes(dark):
    adw=_theme_dir("adw-gtk3-dark" if dark else "adw-gtk3")
    base3=Path(adw,"gtk-3.0/gtk.css").as_uri() if adw else f"resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained{'-dark' if dark else ''}.css"
    base4=f"resource:///org/gtk/libgtk/theme/Default/Default-{'dark' if dark else 'light'}.css"
    for name in OUR_THEMES:
        root=Path(THEMES_DIR)/name
        _write(root/"index.theme",f"[X-GNOME-Metatheme]\nName={name}\nType=X-GNOME-Metatheme\nComment=Wallpaper Studio Video\n")
        for version,base in (("gtk-3.0",base3),("gtk-4.0",base4)):
            content=f'@import url("{base}");\n@import url("{Path(THEME_CSS).as_uri()}");\n'
            _write(root/version/"gtk.css",content);_write(root/version/"gtk-dark.css",content)


def _css_file():return Path(os.environ.get("XDG_CONFIG_HOME",Path.home()/".config"))/"gtk-4.0/gtk.css"


def _add_import():
    path=_css_file();text=path.read_text() if path.exists() else ""
    line=f'@import url("{Path(THEME_CSS).as_uri()}"); {CSS_MARKER}\n'
    retained="".join(row for row in text.splitlines(keepends=True) if CSS_MARKER not in row)
    _write(path,line+retained)


def _remove_import():
    path=_css_file()
    if not path.exists():return
    text="".join(row for row in path.read_text().splitlines(keepends=True) if CSS_MARKER not in row)
    if text.strip():_write(path,text)
    else:path.unlink()


def _terminal_profile(p):
    profiles=_settings("org.gnome.Terminal.ProfilesList")
    if not profiles:return
    marker=Path(CONFIG_DIR)/"terminal-profile.json";data=_read_json(marker,None)
    if not data:
        original=profiles.get_user_value("default")
        data={"uuid":str(uuid.uuid4()),"previous_default":profiles.get_string("default"),
              "previous_default_user":None if original is None else original.print_(True)};_json(marker,data)
    uid=data["uuid"];own=_settings("org.gnome.Terminal.Legacy.Profile",f"/org/gnome/terminal/legacy/profiles:/:{uid}/")
    if not own:return
    listed=list(profiles.get_strv("list"))
    if uid not in listed:
        source=_settings("org.gnome.Terminal.Legacy.Profile",f"/org/gnome/terminal/legacy/profiles:/:{profiles.get_string('default')}/")
        if source:
            for key in source.list_keys():
                value=source.get_user_value(key)
                if value is not None and own.is_writable(key):own.set_value(key,value)
        profiles.set_strv("list",listed+[uid])
    profiles.set_string("default",uid)
    values={"visible-name":GLib.Variant("s","Wallpaper Studio Video"),"use-theme-colors":GLib.Variant("b",False),
        "background-color":GLib.Variant("s",p["paper"]),"foreground-color":GLib.Variant("s",p["ink"]),
        "bold-color-same-as-fg":GLib.Variant("b",True),"palette":GLib.Variant("as",p["ansi"]),
        "cursor-colors-set":GLib.Variant("b",True),"cursor-background-color":GLib.Variant("s",p["accent"]),
        "cursor-foreground-color":GLib.Variant("s",p["on_accent"]),"highlight-colors-set":GLib.Variant("b",True),
        "highlight-background-color":GLib.Variant("s",p["accent"]),"highlight-foreground-color":GLib.Variant("s",p["on_accent"])}
    for key,value in values.items():
        if key in own.list_keys() and own.is_writable(key):own.set_value(key,value)


def _restore_terminal():
    marker=Path(CONFIG_DIR)/"terminal-profile.json";data=_read_json(marker,None)
    profiles=_settings("org.gnome.Terminal.ProfilesList")
    if not data or not profiles:return
    uid=data["uuid"];listed=list(profiles.get_strv("list"));previous=data.get("previous_default")
    remaining=[item for item in listed if item!=uid]
    if profiles.get_string("default")==uid:
        if previous in remaining or not remaining:
            if "previous_default_user" in data and data["previous_default_user"] is None:profiles.reset("default")
            elif previous:profiles.set_string("default",previous)
        elif remaining:profiles.set_string("default",remaining[0])
    profiles.set_strv("list",remaining)
    own=_settings("org.gnome.Terminal.Legacy.Profile",f"/org/gnome/terminal/legacy/profiles:/:{uid}/")
    if own:
        for key in own.list_keys():
            if own.is_writable(key):own.reset(key)
    marker.unlink(missing_ok=True)


def apply_theme(source_path=None,config_override=None):
    chosen_base=None
    if source_path:
        state=load_state()
        chosen_base=state.get("base_palette") if os.path.realpath(source_path)==state.get("still") else palette.from_image(still_of(source_path))
    with locked():
        config,state=load_config(),load_state()
        if config_override:config.update({key:config_override[key] for key in APPEARANCE_KEYS if key in config_override})
        mode=effective_mode(config);dark=mode=="dark"
        base=chosen_base or state.get("theme_base_palette") or state.get("base_palette") or recipes.sample_base()
        resolved=recipes.resolve(base,config);p=resolved[mode]
        interface=_settings("org.gnome.desktop.interface")
        if interface is None or not interface.is_writable("gtk-theme"):
            raise ValueError("The GNOME application theme setting is unavailable or locked in this session.")
        _save_originals(STYLE_KEYS)
        from . import assets,desktop
        assets.install_assets()
        _write(THEME_CSS,recipes.gtk_css(p,dark,config));_write_themes(dark);_add_import()
        for name in OUR_THEMES:_write(Path(THEMES_DIR)/name/'gnome-shell/gnome-shell.css',desktop.shell_css(p,config))
        if config["mode"]!="auto":_set("org.gnome.desktop.interface","color-scheme",GLib.Variant("s","prefer-dark" if dark else "default"))
        current=interface.get_string("gtk-theme")
        theme=OUR_THEMES[1] if current==OUR_THEMES[0] else OUR_THEMES[0]
        _set("org.gnome.desktop.interface","gtk-theme",GLib.Variant("s",theme))
        _set("org.gnome.desktop.background","primary-color",GLib.Variant("s",p["paper"]))
        if config["terminal"]:_terminal_profile(p)
        else:_restore_terminal()
        desktop.apply_look(config,theme)
        Gio.Settings.sync()
        _save_state({**state,"palette":resolved,"theme_base_palette":base,"mode":mode,"style_applied":True,"preset":config["preset"],
                     "applied_recipe":{key:config[key] for key in APPEARANCE_KEYS}})
    if config.get("run_hooks"):_run_hooks(p,mode)
    start();return recipes.PRESETS[config["preset"]][0]


def _run_hooks(p,mode):
    if not os.path.isdir(HOOKS):return
    environment={**os.environ,"WS_MODE":mode,"WS_STATE":STATE}
    environment.update({f"WS_{key.upper()}":value for key,value in p.items() if isinstance(value,str)})
    environment.update({f"WS_ANSI_{i}":value for i,value in enumerate(p["ansi"])})
    for name in sorted(os.listdir(HOOKS)):
        path=os.path.join(HOOKS,name)
        if not name.startswith(".") and os.path.isfile(path) and os.access(path,os.X_OK):
            subprocess.Popen([path],env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def restore(scope="all"):
    if scope in ('all','wallpaper'):
        video.stop()
    if scope in ('all','desktop'):
        from . import desktop
        desktop.restore_all()
        if scope=='desktop':return
        from . import widget_control
        widgets=widget_control.load();widgets.update(enabled=False,editing=False);widget_control.save(widgets);widget_control.stop()
    elif scope=='style':
        from . import desktop
        desktop.restore_look()
    with locked():
        saved=_read_json(ORIGINALS,{});failed=[];backend=NativeBackend()
        keys=BG_KEYS if scope=="wallpaper" else STYLE_KEYS if scope=="style" else BG_KEYS+STYLE_KEYS
        for schema,key in keys:
            name=f"{schema} {key}"
            if name not in saved:continue
            settings=_settings(schema)
            try:
                if not settings or not settings.is_writable(key):raise ValueError(f"{key} is currently locked")
                args=["gsettings","reset",schema,key] if saved[name] is None else ["gsettings","set",schema,key,saved[name]]
                backend._run(args)
                del saved[name]
            except (OSError,RuntimeError,ValueError) as error:failed.append(str(error))
        style_pending=any(f"{schema} {key}" in saved for schema,key in STYLE_KEYS)
        wallpaper_pending=any(f"{schema} {key}" in saved for schema,key in BG_KEYS)
        if scope in ("all","style") and not style_pending:
            _restore_terminal();_remove_import()
            for name in OUR_THEMES:shutil.rmtree(os.path.join(THEMES_DIR,name),ignore_errors=True)
            Path(THEME_CSS).unlink(missing_ok=True)
        Gio.Settings.sync();state=load_state()
        if scope in ("all","style") and not style_pending:state["style_applied"]=False
        if scope in ("all","wallpaper"):state.update(video=False,video_path="")
        if scope in ("all","wallpaper") and not wallpaper_pending:
            current=NativeBackend().current_image(effective_mode()=="dark")
            state.update(wallpaper=current,source=current,still=current);_json(HISTORY,[])
        _save_state(state);_json(ORIGINALS,saved)
        if failed:raise ValueError("Some settings could not be restored; their backups were kept. "+"; ".join(failed))
    # The already-working native profile and Shell override are always kept.


def export_recipe(path):
    config=load_config();keys=APPEARANCE_KEYS+('auto_style',)
    _json(path,{"format":"wallpaper-studio-video-theme","version":1,'name':config['custom_name'],"settings":{key:config[key] for key in keys}})


def import_recipe(path):
    if os.path.getsize(path)>65536:raise ValueError("Theme files must be smaller than 64 KB")
    data=_read_json(path,None)
    if not isinstance(data,dict) or data.get("format") not in ("wallpaper-studio-video-theme","wallpaper-studio-plus-theme") or data.get("version")!=1:
        raise ValueError("Choose a Wallpaper Studio Video theme JSON file")
    allowed=set(APPEARANCE_KEYS)|{'auto_style'}
    if not isinstance(data.get("settings"),dict):raise ValueError("Theme settings must be a JSON object")
    changes={key:value for key,value in data["settings"].items() if key in allowed}
    return save_config(**changes)


def saved_recipes():
    result=[]
    for path in (Path(CONFIG_DIR)/'recipes').glob('*.json'):
        data=_read_json(path,{})
        if isinstance(data,dict) and isinstance(data.get('name'),str):result.append((data['name'][:48],str(path)))
    return sorted(result,key=lambda item:item[0].casefold())


def save_recipe(name):
    name=name.strip()
    if not 1<=len(name)<=48:raise ValueError('Give your saved look a name up to 48 characters')
    existing=next((path for title,path in saved_recipes() if title.casefold()==name.casefold()),None)
    path=Path(existing) if existing else Path(CONFIG_DIR)/'recipes'/(str(uuid.uuid4())+'.json')
    save_config(custom_name=name);export_recipe(path)
    return str(path)


def delete_recipe(path):
    path=Path(path)
    if path.resolve().parent!=(Path(CONFIG_DIR)/'recipes').resolve() or path.suffix!='.json':raise ValueError('Choose a saved Plus recipe')
    path.unlink()


def helper_running():
    try:
        with open(HELPER_LOCK,"a+") as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(handle,fcntl.LOCK_UN)
        return False
    except OSError:return True


def start_helper():
    if helper_running():return
    root=Path(__file__).resolve().parent.parent;os.makedirs(CACHE_DIR,exist_ok=True)
    log=Path(CACHE_DIR)/"session.log"
    if log.exists() and log.stat().st_size>2*1024*1024:log.rename(log.with_suffix(".old.log"))
    with open(log,"a",encoding="utf-8") as output:
        subprocess.Popen([sys.executable,str(root/"wallpaper-studio-video"),"session"],cwd=root,
            stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)


def start():
    Path(STOPPED).unlink(missing_ok=True);start_helper()


def stop():
    _write(STOPPED,"paused\n")
    try:
        pid=int(Path(HELPER_LOCK).read_text().strip())
        command=Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        expected=str(Path(__file__).resolve().parent.parent/"wallpaper-studio-video").encode()
        if expected in command and b"session" in command:os.kill(pid,signal.SIGTERM)
    except (OSError,ValueError):pass
    keep_awake(None,start_session=False)


def awake_until():
    request=_read_json(AWAKE,{})
    if not isinstance(request,dict):return None
    if 'helper' in request and request['helper']!=_helper_identity():return None
    until=request.get("until")
    return until if isinstance(until,(int,float)) and (until==FOREVER or until>time.time()) else None


def keep_awake(minutes,start_session=True):
    if minutes is not None and minutes!=FOREVER and not 1<=minutes<=480:raise ValueError("Choose 1–480 minutes")
    identity=_ready_helper() if minutes is not None and start_session else _helper_identity()
    until=None if minutes is None else FOREVER if minutes==FOREVER else time.time()+minutes*60
    with locked():_json(AWAKE,{"until":until,"minutes":minutes,"mode":"awake" if minutes is not None else "off","helper":identity})


def _helper_identity():
    try:
        pid=int(Path(HELPER_LOCK).read_text().strip())
        command=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        expected=str(Path(__file__).resolve().parent.parent/'wallpaper-studio-video').encode()
        if expected not in command or b'session' not in command:return None
        started=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
        boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return f'{boot}:{pid}:{started}'
    except (OSError,ValueError,IndexError):return None


def _ready_helper():
    start()
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        identity=_helper_identity()
        if identity and helper_running():return identity
        time.sleep(.05)
    raise RuntimeError('The session helper did not start. Open the app again or check its session log.')


def arm_activity_guard():
    from . import screen_guard
    screen_guard.probe()
    token=str(uuid.uuid4())
    identity=_ready_helper()
    with locked():_json(AWAKE,{"until":FOREVER,"minutes":FOREVER,"mode":"guard","id":token,"delay":10,"helper":identity})
    return "10-second countdown started. After that, the next input requests a screen lock."


def clear_preview_cache():
    for name in ("thumbs","frames"):shutil.rmtree(Path(CACHE_DIR)/name,ignore_errors=True)


def original_app_present():
    return os.path.isfile(os.path.join(HOME,".config/autostart/wallpaper-studio-desktop.desktop"))
