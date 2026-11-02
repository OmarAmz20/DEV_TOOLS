"""Small session helper: rotation, auto colours and GNOME presentation requests.

Wallpaper drawing stays entirely with GNOME. There is no X11 desktop window,
window restacking, injected pointer input or Shell restart in this helper.
"""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from gi.repository import Gio, GLib
from . import core
from . import screen_guard


class Session:
    def __init__(self):
        self.busy=None
        self.cookie=None
        self.proxy=None
        self.inhibit_flags=0
        self.awake_error=""
        self.guard_id=None
        self.guard=None
        self.idle=None
        self.locker=None
        self.guard_phase="off"
        self.guard_message=""
        self.lock_sent=0
        self.pending=0
        self.loop=GLib.MainLoop()
        os.makedirs(core.CONFIG_DIR,exist_ok=True)
        self.monitor=Gio.File.new_for_path(core.CONFIG_DIR).monitor_directory(Gio.FileMonitorFlags.NONE,None)
        self.monitor.connect("changed",self.changed)
        self.runtime_monitor=Gio.File.new_for_path(os.path.dirname(core.AWAKE)).monitor_directory(Gio.FileMonitorFlags.NONE,None)
        self.runtime_monitor.connect("changed",self.runtime_changed)
        self.interface=Gio.Settings.new("org.gnome.desktop.interface")
        self.interface.connect("changed::color-scheme",lambda *_:self.follow_scheme())
        GLib.timeout_add_seconds(20,self.tick)
        GLib.timeout_add(250,self.activity_tick)
        GLib.idle_add(lambda:self.tick() and False)

    def runtime_changed(self,_monitor,file,*_):
        if file.get_basename()==os.path.basename(core.AWAKE):self.sync_awake()

    def changed(self,_monitor,file,*_):
        if file.get_basename()=="stopped" and os.path.exists(core.STOPPED):self.loop.quit()
        elif file.get_basename()=="config.json":
            if self.pending:GLib.source_remove(self.pending)
            self.pending=GLib.timeout_add(300,self.config_changed)

    def config_changed(self):
        self.pending=0;self.follow_scheme();return False

    def follow_scheme(self):
        state=core.load_state()
        applied=state.get("applied_recipe",{})
        if applied.get("mode")=="auto" and state.get("style_applied") and state.get("mode")!=core.effective_mode(applied):
            self.run("follow-style")
        return False

    def run(self,command):
        if self.busy is not None and self.busy.poll() is None:return
        launcher=Path(__file__).resolve().parent.parent/"wallpaper-studio-video"
        self.busy=subprocess.Popen([sys.executable,str(launcher),command],stdin=subprocess.DEVNULL)

    def locked(self):
        try:
            bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            value=bus.call_sync("org.gnome.ScreenSaver","/org/gnome/ScreenSaver","org.gnome.ScreenSaver",
                "GetActive",None,None,Gio.DBusCallFlags.NO_AUTO_START,1000,None)
            return bool(value.unpack()[0])
        except GLib.Error:return False

    def tick(self):
        if os.path.exists(core.STOPPED):self.loop.quit();return False
        self.sync_awake()
        config,state=core.load_config(),core.load_state()
        hours=float(config["rotate_hours"])
        if hours and state.get("changed") and time.time()-state["changed"]>=hours*3600:
            if not self.locked():self.run("next")
        else:self.follow_scheme()
        return True

    def sync_awake(self):
        requested=core.awake_until() is not None
        request=core._read_json(core.AWAKE,{})
        flags=13 if request.get('mode')=='guard' else 12
        if self.cookie is not None and flags!=self.inhibit_flags:self.release()
        if requested and self.cookie is None:
            try:
                if self.proxy is None:
                    self.proxy=Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,
                        Gio.DBusProxyFlags.DO_NOT_AUTO_START,None,"org.gnome.SessionManager",
                        "/org/gnome/SessionManager","org.gnome.SessionManager",None)
                reply=self.proxy.call_sync("Inhibit",GLib.Variant("(susu)",(core.APP_ID,0,"Wallpaper Studio Video keep awake",flags)),
                    Gio.DBusCallFlags.NO_AUTO_START,2000,None)
                self.cookie=reply.unpack()[0]
                self.inhibit_flags=flags
                self.awake_error=""
            except GLib.Error as exc:self.awake_error=str(exc)
        elif not requested:self.release();self.awake_error=""
        self.publish()

    def publish(self):
        previous=core._read_json(core.SESSION_STATE,{})
        updated={"awake_active":self.cookie is not None,"error":self.awake_error,
                 "guard":{"phase":self.guard_phase,"message":self.guard_message,
                          "remaining":self.guard.remaining if self.guard and self.guard_phase=='arming' else 0}}
        if previous!=updated:core._json(core.SESSION_STATE,updated)

    def close_idle(self):
        if self.idle:self.idle.close();self.idle=None

    def finish_guard(self,phase,message):
        self.guard_phase=phase;self.guard_message=message
        self.close_idle()
        with core.locked():
            current=core._read_json(core.AWAKE,{})
            if current.get('mode')=='guard' and current.get('id')==self.guard_id:
                core.keep_awake(None,start_session=False)
        self.release();self.publish()

    def activity_tick(self):
        if os.path.exists(core.STOPPED):return True
        request=core._read_json(core.AWAKE,{})
        if not isinstance(request,dict):return True
        if request.get('mode')!='guard' or core.awake_until() is None:
            if self.guard_phase in ('arming','armed','locking'):
                self.guard_phase='cancelled';self.guard_message='Activity guard stopped.';self.close_idle();self.publish()
            return True
        token=request.get('id')
        if not isinstance(token,str) or len(token)>64:return True
        if token!=self.guard_id:
            self.close_idle();self.guard_id=token
            try:
                self.idle=screen_guard.X11Idle();self.locker=screen_guard.find_locker()
                self.guard=screen_guard.ActivityWatch(delay=10)
                self.guard_phase='arming';self.guard_message='Move away before the countdown ends.'
                self.sync_awake()
                if self.cookie is None:raise screen_guard.GuardError('Keep awake could not start. The guard was not armed. '+self.awake_error)
            except Exception as error:
                self.finish_guard('error',str(error));return True
        try:
            if self.guard_phase in ('arming','armed'):
                triggered=self.guard.step(self.idle.read())
                self.guard_phase=self.guard.phase
                if self.guard_phase=='armed':self.guard_message='Armed. The next key press or mouse activity requests a screen lock.'
                if triggered:
                    self.guard_message='Input detected. Requesting the system screen lock…';self.publish()
                    screen_guard.request_lock(self.locker);self.lock_sent=time.monotonic()
            elif self.guard_phase=='locking':
                if screen_guard.lock_active(self.locker):
                    self.finish_guard('locked','The system locker confirmed activation. Keep awake has ended.')
                elif time.monotonic()-self.lock_sent>4:
                    self.finish_guard('error','The lock request was not confirmed. Keep awake has stopped; check your screen locker.')
            self.publish()
        except Exception as error:self.finish_guard('error',str(error))
        return True

    def release(self):
        if self.cookie is not None:
            try:self.proxy.call_sync("Uninhibit",GLib.Variant("(u)",(self.cookie,)),Gio.DBusCallFlags.NO_AUTO_START,1000,None)
            except GLib.Error:pass
            self.cookie=None
            self.inhibit_flags=0

    def close(self):
        self.release();self.close_idle();self.monitor.cancel();self.runtime_monitor.cancel()
        if core._read_json(core.AWAKE,{}).get('mode')=='guard':core.keep_awake(None,start_session=False)
        core._json(core.SESSION_STATE,{"awake_active":False,"error":"","guard":{"phase":"off","message":""}})


def main():
    with open(core.HELPER_LOCK,"a+") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:return 0
        if os.path.exists(core.STOPPED):return 0
        lock.seek(0);lock.truncate();lock.write(str(os.getpid()));lock.flush()
        session=Session()
        signal.signal(signal.SIGTERM,lambda *_:session.loop.quit())
        signal.signal(signal.SIGINT,lambda *_:session.loop.quit())
        try:session.loop.run()
        finally:session.close()
    return 0
