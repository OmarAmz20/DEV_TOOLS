import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

# The state machine and native idle reader also run without the GTK editor.
path=Path(__file__).resolve().parent.parent/'wallpaper_studio/screen_guard.py'
spec=importlib.util.spec_from_file_location('studio_guard_test',path)
guard=importlib.util.module_from_spec(spec);sys.modules[spec.name]=guard;spec.loader.exec_module(guard)


class ActivityTests(unittest.TestCase):
    def test_arming_click_and_countdown_input_are_ignored(self):
        watch=guard.ActivityWatch(now=100)
        self.assertFalse(watch.step(0,now=100))
        self.assertFalse(watch.step(0,now=109))
        self.assertEqual(watch.phase,'arming')

    def test_idle_desktop_stays_armed(self):
        watch=guard.ActivityWatch(now=100)
        for now in (110,111,180,10000):
            self.assertFalse(watch.step(int((now-100)*1000),now=now))
        self.assertEqual(watch.phase,'armed')

    def test_any_new_input_triggers_once(self):
        watch=guard.ActivityWatch(now=100)
        self.assertFalse(watch.step(10000,now=110))
        self.assertTrue(watch.step(12,now=111))
        self.assertFalse(watch.step(0,now=112))
        self.assertEqual(watch.phase,'locking')

    def test_continuous_mouse_motion_after_countdown_triggers(self):
        watch=guard.ActivityWatch(now=100)
        self.assertTrue(watch.step(0,now=110.25))

    def test_clock_rounding_does_not_trigger(self):
        watch=guard.ActivityWatch(now=100)
        self.assertFalse(watch.step(0,now=110.001))

    def test_wayland_is_not_misrepresented_as_supported(self):
        with mock.patch.dict('os.environ',{'XDG_SESSION_TYPE':'wayland'}):
            with self.assertRaisesRegex(guard.GuardError,'X11'):guard.X11Idle()


try:
    import gi
    HAVE_GI=True
except ImportError:HAVE_GI=False


@unittest.skipUnless(HAVE_GI,'Locker transport needs PyGObject')
class LockerTests(unittest.TestCase):
    def test_gnome_locker_is_detected_even_when_not_active(self):
        with mock.patch.object(guard,'_owner_process',return_value='gnome-shell'),mock.patch.object(guard,'_bus_call',return_value=(False,)):
            locker=guard.find_locker()
        self.assertEqual(locker.service,'org.gnome.Shell.ScreenShield')

    def test_proxy_is_not_a_real_locker(self):
        with mock.patch.object(guard,'_owner_process',return_value='gsd-screensaver-proxy'),mock.patch.object(guard,'_bus_call') as call:
            with self.assertRaisesRegex(guard.GuardError,'No working screen locker'):guard.find_locker()
        call.assert_not_called()

    def test_light_locker_is_accepted(self):
        def owner(service):
            if service=='org.freedesktop.ScreenSaver':return 'light-locker'
            raise OSError('no owner')
        with mock.patch.object(guard,'_owner_process',side_effect=owner),mock.patch.object(guard,'_bus_call',return_value=(False,)):
            self.assertEqual(guard.find_locker().service,'org.freedesktop.ScreenSaver')

    def test_lock_service_disappearing_is_not_confirmed(self):
        locker=guard.Locker('a','/a','a','a')
        with mock.patch.object(guard,'_bus_call',side_effect=RuntimeError('gone')):
            self.assertFalse(guard.lock_active(locker))
            with self.assertRaises(RuntimeError):guard.request_lock(locker)


if __name__=='__main__':unittest.main()
