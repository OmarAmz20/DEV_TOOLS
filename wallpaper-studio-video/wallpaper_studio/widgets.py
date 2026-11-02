"""Small sticky GTK 3 desktop windows. Native wallpaper drawing remains GNOME's."""
import calendar
from datetime import datetime
import fcntl
import os
from pathlib import Path
import shutil
import signal
import time
import gi
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango
from . import core,recipes,skins,assets,widget_control as control


def label(text='',style=None):
    result=Gtk.Label(label=text,xalign=0)
    if style:result.get_style_context().add_class(style)
    return result


class Widget(Gtk.Window):
    def __init__(self,host,kind,item):
        super().__init__(type=Gtk.WindowType.TOPLEVEL,title='Studio · '+control.TYPES[kind][0])
        self.host=host;self.kind=kind;self.item=item;self.pending=0
        self.set_wmclass('wallpaper-studio-video-widget','WallpaperStudioVideoWidget')
        self.get_style_context().add_class('widget-window')
        self.set_decorated(False);self.set_resizable(False);self.set_accept_focus(False)
        self.set_skip_taskbar_hint(True);self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL if host.config['editing'] or host.config['layer']=='above-icons' else Gdk.WindowTypeHint.DESKTOP)
        self.set_keep_above(host.config['editing']);self.set_keep_below(not host.config['editing']);self.stick()
        screen=self.get_screen();visual=screen.get_rgba_visual()
        if visual:self.set_visual(visual)
        self.set_app_paintable(True)
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9,border_width=16)
        self.body.get_style_context().add_class('widget-body');self.add(self.body)
        heading=Gtk.EventBox();title=label(control.TYPES[kind][0].upper(),'widget-kicker');heading.add(title)
        heading.connect('button-press-event',self.drag);self.body.pack_start(heading,False,False,0)
        self.primary=label('','widget-large');self.secondary=label('','widget-secondary')
        self.secondary.set_line_wrap(True);self.secondary.set_max_width_chars(36)
        if kind=='calendar':
            self.primary.get_style_context().remove_class('widget-large');self.primary.get_style_context().add_class('widget-calendar')
        if kind in ('clock','timer','calendar'):self.body.pack_start(self.primary,False,False,0)
        self.body.pack_start(self.secondary,False,False,0)
        if kind=='stats':
            self.bars=[]
            for name in ('CPU','RAM','Disk'):
                bar=Gtk.ProgressBar(show_text=True);bar.set_text(name);self.body.pack_start(bar,False,False,0);self.bars.append(bar)
        if kind in ('player','timer','shortcuts'):
            row=Gtk.Box(spacing=6);self.body.pack_end(row,False,False,0)
            buttons=[('⏮',lambda:self.host.media('Previous')),('▶ / Ⅱ',lambda:self.host.media('PlayPause')),('⏭',lambda:self.host.media('Next'))] if kind=='player' else [('Start / pause',host.toggle_timer),('Reset',host.reset_timer)] if kind=='timer' else [('Home',lambda:self.open_uri(Path.home().as_uri())),('Browser',self.open_browser),('Terminal',self.open_terminal)]
            for text,callback in buttons:
                button=Gtk.Button(label=text);button.connect('clicked',lambda _b,cb=callback:cb());row.pack_start(button,True,True,0)
        self.set_css();self.show_all();self.place();self.connect('configure-event',self.moved)
        self.update()

    def open_uri(self,uri):
        try:Gio.AppInfo.launch_default_for_uri(uri,None)
        except GLib.Error as error:self.secondary.set_text(str(error))

    def open_terminal(self):
        terminal=shutil.which('x-terminal-emulator') or shutil.which('gnome-terminal')
        if terminal:
            import subprocess;subprocess.Popen([terminal],start_new_session=True)

    def open_browser(self):
        try:
            browser=Gio.AppInfo.get_default_for_type('text/html',True)
            if browser:browser.launch_uris(['about:blank'],None)
            else:self.secondary.set_text('No default browser found')
        except GLib.Error as error:self.secondary.set_text(str(error))

    def set_css(self):
        p=self.host.palette;config=self.host.recipe;pixel=skins.pixel_style(config);scale=self.item['scale']
        font='Silkscreen' if pixel and config.get('pixel_font',True) else 'Sans'
        rgba=Gdk.RGBA();rgba.parse(p['paper']);alpha=self.host.config['opacity']
        provider=Gtk.CssProvider();provider.load_from_data((f'''
window.widget-window {{ background-color: transparent; }}
.widget-body {{ background-color: rgba({round(rgba.red*255)},{round(rgba.green*255)},{round(rgba.blue*255)},{alpha});
 color: {p['ink']}; border: {3 if pixel else 1}px solid {p['accent']}; border-radius: {0 if pixel else 16}px;
 font-family: "{font}"; font-size: {12*scale}px; }}
.widget-kicker {{ color: {p['accent']}; font-size: {10*scale}px; font-weight: bold; }}
.widget-large {{ color: {p['ink']}; font-size: {32*scale}px; font-weight: bold; }}
.widget-secondary {{ color: {p['muted']}; font-size: {12*scale}px; }}
.widget-calendar {{ font-family: monospace; font-size: {14*scale}px; color: {p['ink']}; }}
button {{ border-radius: {0 if pixel else 7}px; background-image: none; background-color: {p['sheet']}; color: {p['ink']}; border: 1px solid {p['accent']}; padding: 5px; font-size: {11*scale}px; }}
progressbar trough {{ background-color: {p['sheet']}; min-height: 6px; border-radius: 0; }}
progressbar progress {{ background-color: {p['accent']}; min-height: 6px; border-radius: 0; }}
''').encode())
        def apply(widget):
            widget.get_style_context().add_provider(provider,Gtk.STYLE_PROVIDER_PRIORITY_USER+20)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():apply(child)
        apply(self)

    def place(self):
        area=self.host.area();x,y,w,h=control.geometry(self.item,self.kind,area.width,area.height)
        self.set_default_size(w,h);self.resize(w,h);self.move(area.x+x,area.y+y)

    def drag(self,_box,event):
        if self.host.config['editing'] and event.button==1:self.begin_move_drag(event.button,int(event.x_root),int(event.y_root),event.time);return True
        return False

    def moved(self,*_):
        if not self.host.config['editing']:return False
        if self.pending:GLib.source_remove(self.pending)
        self.pending=GLib.timeout_add(150,self.save_position);return False

    def save_position(self):
        self.pending=0;area=self.host.area();x,y=self.get_position();w,h=self.get_size()
        config=control.load();item=config['items'][self.kind]
        item['x']=max(0,min(1,(x-area.x)/max(1,area.width-w)));item['y']=max(0,min(1,(y-area.y)/max(1,area.height-h)))
        control.save(config);return False

    def update(self):
        now=datetime.now()
        if self.kind=='clock':
            fmt='%H:%M' if self.host.config['hour24'] else '%I:%M %p'
            if self.host.config['seconds']:fmt=fmt.replace('%M','%M:%S')
            self.primary.set_text(now.strftime(fmt));self.secondary.set_text(now.strftime('%A, %d %B'))
        elif self.kind=='calendar':
            self.primary.set_text(calendar.TextCalendar().formatmonth(now.year,now.month).rstrip())
            self.secondary.set_text('Today · '+now.strftime('%d %B %Y'))
        elif self.kind=='notes':self.secondary.set_text(self.host.config['note'] or 'Edit this note in Studio → Widgets');self.secondary.set_ellipsize(Pango.EllipsizeMode.END);self.secondary.set_lines(7)
        elif self.kind=='stats':
            cpu=self.host.cpu;ram=control.memory();disk=shutil.disk_usage(Path.home())
            values=[(cpu or 0,'CPU  —' if cpu is None else f'CPU  {cpu:.0f}%'),(100*ram[0]/ram[1] if ram else 0,f'RAM  {ram[0]/2**30:.1f} / {ram[1]/2**30:.1f} GB' if ram else 'RAM  —'),(100*disk.used/disk.total,f'Disk  {disk.used/2**30:.1f} / {disk.total/2**30:.1f} GB')]
            for bar,(value,text) in zip(self.bars,values):bar.set_fraction(max(0,min(1,value/100)));bar.set_text(text)
        elif self.kind=='player':self.secondary.set_text(self.host.track)
        elif self.kind=='shortcuts':self.secondary.set_text('Your everyday essentials')
        elif self.kind=='timer':
            remaining=self.host.remaining();self.primary.set_text(f'{remaining//60:02}:{remaining%60:02}')
            self.secondary.set_text('Focus time' if self.host.deadline else 'Ready when you are' if remaining else 'Session complete')
        return True


class Host:
    def __init__(self):
        assets.register_font();self.windows=[];self.timer_left=None;self.deadline=None;self.track='No active media player';self.player=None;self.pending=0
        self.previous=control.cpu_sample();self.cpu=None;self.count=0;self.reload()
        self.monitor=Gio.File.new_for_path(core.CONFIG_DIR).monitor_directory(Gio.FileMonitorFlags.NONE,None);self.monitor.connect('changed',self.changed)
        GLib.timeout_add_seconds(1,self.tick)

    def area(self):
        display=Gdk.Display.get_default();index=min(self.config['monitor'],max(0,display.get_n_monitors()-1))
        return display.get_monitor(index).get_workarea()

    def reload(self):
        self.pending=0;self.config=control.load()
        if not self.config['enabled']:Gtk.main_quit();return False
        state=core.load_state();applied=bool(state.get('style_applied'))
        self.recipe=(state.get('applied_recipe') or {**core.DEFAULT_CONFIG,'preset':state.get('preset','catppuccin')}) if applied else {**core.DEFAULT_CONFIG,'preset':'catppuccin'}
        mode=state.get('mode') if applied else core.effective_mode(self.recipe)
        self.palette=((state.get('palette') or recipes.resolve(recipes.sample_base(),self.recipe)) if applied else recipes.resolve(recipes.sample_base(),self.recipe))[mode]
        for window in self.windows:
            if window.pending:GLib.source_remove(window.pending)
            window.destroy()
        self.windows=[Widget(self,key,item) for key,item in self.config['items'].items() if item['enabled']]
        return False

    def changed(self,_monitor,file,*_):
        if file.get_basename() not in ('widgets.json','state.json'):return
        # Position saves do not rebuild windows while they are being dragged.
        latest=control.load()
        same={k:v for k,v in latest.items() if k!='items'}=={k:v for k,v in self.config.items() if k!='items'}
        only_positions=same and all({k:v for k,v in latest['items'][kind].items() if k not in ('x','y')}=={k:v for k,v in self.config['items'][kind].items() if k not in ('x','y')} for kind in control.TYPES)
        if file.get_basename()=='widgets.json' and only_positions and self.config['editing']:self.config=latest;return
        if self.pending:GLib.source_remove(self.pending)
        self.pending=GLib.timeout_add(180,self.reload)

    def remaining(self):return max(0,round(self.deadline-time.monotonic())) if self.deadline else self.timer_left if self.timer_left is not None else self.config['focus_minutes']*60
    def toggle_timer(self):
        if self.deadline:self.timer_left=self.remaining();self.deadline=None
        else:self.deadline=time.monotonic()+(self.remaining() or self.config['focus_minutes']*60)
    def reset_timer(self):self.deadline=None;self.timer_left=self.config['focus_minutes']*60

    def tick(self):
        sample=control.cpu_sample();self.cpu=control.cpu_percent(self.previous,sample);self.previous=sample;self.count+=1
        if self.count%4==1:self.poll_media()
        if self.deadline and self.remaining()==0:
            self.deadline=None;self.timer_left=0
            try:
                bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
                bus.call('org.freedesktop.Notifications','/org/freedesktop/Notifications','org.freedesktop.Notifications','Notify',GLib.Variant('(susssasa{sv}i)',('Wallpaper Studio Video',0,'appointment-soon','Focus session complete','Time for a short break.',[],{},6000)),None,Gio.DBusCallFlags.NO_AUTO_START,1000,None,None,None)
            except GLib.Error:pass
        for window in self.windows:window.update()
        return True

    def poll_media(self):
        try:
            bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            names=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','ListNames',None,GLib.VariantType.new('(as)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
            players=sorted(n for n in names if n.startswith('org.mpris.MediaPlayer2.'))
            if not players:self.player=None;self.track='No active media player';return
            if self.player not in players:self.player=players[0]
            metadata=bus.call_sync(self.player,'/org/mpris/MediaPlayer2','org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',('org.mpris.MediaPlayer2.Player','Metadata')),None,Gio.DBusCallFlags.NO_AUTO_START,1000,None).unpack()[0]
            title=metadata.get('xesam:title','Media player');artists=metadata.get('xesam:artist',[])
            self.track=str(title)[:100]+('\n'+' · '.join(artists)[:100] if isinstance(artists,list) else '')
        except (GLib.Error,TypeError,ValueError):self.track='Media player unavailable'

    def media(self,command):
        if not self.player:return
        try:
            bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            bus.call(self.player,'/org/mpris/MediaPlayer2','org.mpris.MediaPlayer2.Player',command,None,None,Gio.DBusCallFlags.NO_AUTO_START,1000,None,None,None)
        except GLib.Error:pass

    def close(self):
        self.monitor.cancel()
        for window in self.windows:window.destroy()


def main():
    if not control.load()['enabled']:return 0
    if os.environ.get('XDG_SESSION_TYPE','x11')!='x11':raise ValueError('Desktop widgets currently need X11')
    with control.lockpath().open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:return 0
        lock.seek(0);lock.truncate();lock.write(str(os.getpid()));lock.flush()
        host=Host();signal.signal(signal.SIGTERM,lambda *_:Gtk.main_quit());signal.signal(signal.SIGINT,lambda *_:Gtk.main_quit())
        if not host.config['enabled']:host.close();return 0
        try:Gtk.main()
        finally:host.close()
    return 0
