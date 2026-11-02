"""One-shot activity guard. Reads idle time, never keys or pointer coordinates.

This requests a real system screen locker. A LightDM greeter switch alone is
deliberately not accepted as a screen locker. No input is synthesized.
"""
from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
import os
from pathlib import Path
import time


class GuardError(RuntimeError):
    pass


class _SaverInfo(ctypes.Structure):
    _fields_ = [('window', ctypes.c_ulong), ('state', ctypes.c_int),
                ('kind', ctypes.c_int), ('til_or_since', ctypes.c_ulong),
                ('idle', ctypes.c_ulong), ('event_mask', ctypes.c_ulong)]


class X11Idle:
    def __init__(self):
        if os.environ.get('XDG_SESSION_TYPE', 'x11') != 'x11':
            raise GuardError('Activity detection currently requires an X11 session.')
        try:
            self.xlib = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
            self.xss = ctypes.CDLL(ctypes.util.find_library('Xss') or 'libXss.so.1')
        except OSError as error:
            raise GuardError('The X11 idle-time library is unavailable.') from error
        self.xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.xlib.XOpenDisplay.restype = ctypes.c_void_p
        self.xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        self.xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.xss.XScreenSaverQueryExtension.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        self.xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_SaverInfo)]
        self.display = self.xlib.XOpenDisplay(None)
        if not self.display:
            raise GuardError('Cannot read idle time from this desktop session.')
        event, error = ctypes.c_int(), ctypes.c_int()
        if not self.xss.XScreenSaverQueryExtension(self.display, ctypes.byref(event), ctypes.byref(error)):
            self.close()
            raise GuardError('This X server does not provide idle-time information.')
        self.root = self.xlib.XDefaultRootWindow(self.display)

    def read(self):
        info = _SaverInfo()
        if not self.display or not self.xss.XScreenSaverQueryInfo(self.display, self.root, ctypes.byref(info)):
            raise GuardError('Idle-time detection stopped working. The guard has stopped.')
        return int(info.idle)

    def close(self):
        if self.display:
            self.xlib.XCloseDisplay(self.display)
            self.display = None


@dataclass(frozen=True)
class Locker:
    service: str
    path: str
    interface: str
    name: str


def _bus_call(service, path, interface, method, value=None, timeout=1000):
    from gi.repository import Gio
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return bus.call_sync(service, path, interface, method, value, None,
                         Gio.DBusCallFlags.NO_AUTO_START, timeout, None).unpack()


def _owner_process(service):
    from gi.repository import GLib
    pid = _bus_call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                    'org.freedesktop.DBus', 'GetConnectionUnixProcessID', GLib.Variant('(s)', (service,)))[0]
    proc = Path('/proc') / str(pid)
    if proc.stat().st_uid != os.getuid():
        return ''
    return Path(os.readlink(proc / 'exe')).name


def find_locker():
    candidates = [
        (Locker('org.gnome.Shell.ScreenShield', '/org/gnome/ScreenSaver', 'org.gnome.ScreenSaver', 'GNOME screen lock'), {'gnome-shell'}),
        (Locker('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver', 'org.freedesktop.ScreenSaver', 'System screen locker'), {'light-locker', 'xfce4-screensaver', 'mate-screensaver', 'cinnamon-screensaver'}),
        (Locker('org.gnome.ScreenSaver', '/org/gnome/ScreenSaver', 'org.gnome.ScreenSaver', 'System screen locker'), {'light-locker', 'gnome-screensaver'}),
        (Locker('org.cinnamon.ScreenSaver', '/org/cinnamon/ScreenSaver', 'org.cinnamon.ScreenSaver', 'Cinnamon screen lock'), {'cinnamon-screensaver'}),
        (Locker('org.mate.ScreenSaver', '/org/mate/ScreenSaver', 'org.mate.ScreenSaver', 'MATE screen lock'), {'mate-screensaver'}),
    ]
    for locker, executables in candidates:
        try:
            if _owner_process(locker.service) not in executables:
                continue
            active = _bus_call(locker.service, locker.path, locker.interface, 'GetActive')
            if len(active) == 1 and isinstance(active[0], bool):
                return locker
        except Exception:
            continue
    raise GuardError('No working screen locker was detected. A LightDM login screen alone cannot protect the session. Keep awake is still available.')


def probe():
    idle = X11Idle()
    try:
        idle.read()
        locker = find_locker()
        return {'available': True, 'name': locker.name, 'message': 'Ready. The next input after the countdown will request a screen lock.'}
    finally:
        idle.close()


def request_lock(locker=None):
    locker = locker or find_locker()
    _bus_call(locker.service, locker.path, locker.interface, 'Lock', timeout=2000)
    return locker


def lock_active(locker):
    try:
        return bool(_bus_call(locker.service, locker.path, locker.interface, 'GetActive', timeout=350)[0])
    except Exception:
        return False


class ActivityWatch:
    """Pure state machine: the arming click is ignored, later input fires once."""
    def __init__(self, delay=10, now=None):
        now = time.monotonic() if now is None else now
        self.deadline = now + delay
        self.phase = 'arming'
        self.remaining = delay

    def step(self, idle_ms, now=None):
        now = time.monotonic() if now is None else now
        if self.phase not in ('arming', 'armed'):
            return False
        self.remaining = max(0, int(self.deadline - now + .999))
        if now < self.deadline:
            return False
        self.phase = 'armed'
        # Idle time is milliseconds; a small tolerance avoids clock/sample jitter.
        last_input = now - idle_ms / 1000
        if last_input > self.deadline + .025:
            self.phase = 'locking'
            return True
        return False
