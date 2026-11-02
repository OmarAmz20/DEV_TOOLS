"""Widget configuration and process control, shared by the studio and GTK 3 host."""
import copy
import fcntl
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
from . import core

TYPES={
 'clock':('Clock','Time and date',(280,140)),
 'calendar':('Calendar','Current month and today',(280,230)),
 'stats':('System stats','CPU, memory and disk usage',(280,170)),
 'notes':('Sticky note','A note you edit in the studio',(280,195)),
 'player':('Now playing','MPRIS media title and playback controls',(320,150)),
 'timer':('Focus timer','Start, pause and reset a work session',(280,165)),
 'shortcuts':('Quick launch','Home, browser and your preferred terminal',(320,125)),
}
POSITIONS={'clock':(.025,.04),'calendar':(.025,.37),'stats':(.97,.04),'notes':(.97,.39),
           'player':(.025,.96),'timer':(.52,.96),'shortcuts':(.52,.04)}
DEFAULT={'enabled':False,'editing':False,'monitor':0,'opacity':.96,'seconds':False,'hour24':True,'layer':'desktop',
 'note':'Make something good today.','focus_minutes':25,
 'items':{key:{'enabled':key in ('clock','stats','notes','timer'),'x':pos[0],'y':pos[1],'scale':1.0} for key,pos in POSITIONS.items()}}


def path():return Path(core.CONFIG_DIR)/'widgets.json'
def lockpath():return Path(core.RUNTIME)/f'wallpaper-studio-video-widgets-{os.getuid()}.lock'


def validate(data):
    result=copy.deepcopy(DEFAULT)
    if not isinstance(data,dict):return result
    if data.get('layer') in ('desktop','above-icons'):result['layer']=data['layer']
    for key in ('enabled','editing','seconds','hour24'):
        if isinstance(data.get(key),bool):result[key]=data[key]
    for key,low,high in (('monitor',0,32),('opacity',.55,1),('focus_minutes',1,180)):
        value=data.get(key)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and low<=value<=high:result[key]=int(value) if key!='opacity' else value
    if isinstance(data.get('note'),str):result['note']=data['note'][:4000]
    items=data.get('items',{})
    if isinstance(items,dict):
        for key,value in items.items():
            if key not in TYPES or not isinstance(value,dict):continue
            if isinstance(value.get('enabled'),bool):result['items'][key]['enabled']=value['enabled']
            for option,low,high in (('x',0,1),('y',0,1),('scale',.65,1.6)):
                v=value.get(option)
                if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and low<=v<=high:result['items'][key][option]=v
    return result


def load():return validate(core._read_json(path(),{}))


def save(data):
    with core.locked():
        data=validate(data);core._json(path(),data)
    return data


def running():
    try:
        with lockpath().open('a+') as handle:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return False
    except OSError:return True


def start():
    if os.environ.get('XDG_SESSION_TYPE','x11')!='x11':raise ValueError('Desktop widgets need an X11 session. Wallpapers and themes also work without widgets.')
    if running():return
    check=subprocess.run([sys.executable,'-c','import gi;gi.require_version("Gtk","3.0");from gi.repository import Gtk'],capture_output=True,text=True,timeout=10)
    if check.returncode:raise ValueError('Widgets need the GTK 3 runtime. Run this version’s installer again; it can supply it without sudo.')
    root=Path(__file__).resolve().parent.parent;Path(core.CACHE_DIR).mkdir(parents=True,exist_ok=True)
    with (Path(core.CACHE_DIR)/'widgets.log').open('a') as log:
        subprocess.Popen([sys.executable,str(root/'wallpaper-studio-video'),'widgets','run'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)


def apply(data):
    checked=validate(data)
    if checked['enabled']:
        if not any(item['enabled'] for item in checked['items'].values()):raise ValueError('Enable at least one widget')
        save(checked);start()
    else:save(checked)
    return 'Widgets updated'


def stop():
    try:
        pid=int(lockpath().read_text().strip());args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        expected=str(Path(__file__).resolve().parent.parent/'wallpaper-studio-video').encode()
        if expected in args and b'widgets' in args and b'run' in args:os.kill(pid,signal.SIGTERM)
    except (OSError,ValueError):pass


def preset(name,data=None):
    data=validate(data or load());enabled={'minimal':('clock',),'study':('clock','stats','notes','timer'),'hud':tuple(TYPES)}
    if name not in enabled:raise ValueError('Unknown widget layout')
    data.update(enabled=True,editing=False)
    for key in TYPES:data['items'][key].update(enabled=key in enabled[name],x=POSITIONS[key][0],y=POSITIONS[key][1],scale=1.0)
    return data


def geometry(item,kind,width,height):
    w,h=TYPES[kind][2];scale=item['scale'];w=min(round(w*scale),width);h=min(round(h*scale),height)
    return round(item['x']*max(0,width-w)),round(item['y']*max(0,height-h)),w,h


def export_layout(destination,data=None):
    data=validate(data or load())
    keys=('monitor','opacity','seconds','hour24','layer','focus_minutes','items')
    core._json(destination,{'format':'wallpaper-studio-video-widgets','version':1,'layout':{key:data[key] for key in keys}})


def import_layout(source,current=None):
    if Path(source).stat().st_size>65536:raise ValueError('Widget layouts must be smaller than 64 KB')
    data=core._read_json(source,{})
    if not isinstance(data,dict) or data.get('format')!='wallpaper-studio-video-widgets' or data.get('version')!=1 or not isinstance(data.get('layout'),dict):raise ValueError('Choose a Wallpaper Studio Video widget layout JSON')
    allowed={'monitor','opacity','seconds','hour24','layer','focus_minutes','items'}
    return validate({**validate(current or load()),**{key:value for key,value in data['layout'].items() if key in allowed}})


def cpu_sample(path='/proc/stat'):
    try:
        fields=Path(path).read_text().splitlines()[0].split()[1:9];numbers=[int(n) for n in fields]
        return sum(numbers),numbers[3]+(numbers[4] if len(numbers)>4 else 0)
    except (OSError,ValueError,IndexError):return None


def cpu_percent(previous,current):
    if not previous or not current:return None
    total=current[0]-previous[0];idle=current[1]-previous[1]
    return max(0,min(100,100*(total-idle)/total)) if total>0 else None


def memory(path='/proc/meminfo'):
    try:
        rows=dict(line.split(':',1) for line in Path(path).read_text().splitlines())
        total=int(rows['MemTotal'].split()[0])*1024;available=int(rows['MemAvailable'].split()[0])*1024
        return total-available,total
    except (OSError,KeyError,ValueError):return None
