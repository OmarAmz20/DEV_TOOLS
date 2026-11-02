import unittest
from unittest import mock
try:
    with mock.patch("wallpaper_studio.backend.prepare_environment"):
        from wallpaper_studio import session
    HAVE_GI=True
except ImportError:HAVE_GI=False


@unittest.skipUnless(HAVE_GI,"Session checks need PyGObject")
class SessionTests(unittest.TestCase):
    def controller(self):
        obj=object.__new__(session.Session)
        obj.guard_id=None;obj.guard=None;obj.idle=None;obj.locker=None
        obj.guard_phase='off';obj.guard_message='';obj.cookie=1;obj.awake_error='';obj.lock_sent=0
        obj.publish=mock.Mock();obj.sync_awake=mock.Mock()
        obj.release=mock.Mock(side_effect=lambda:setattr(obj,'cookie',None))
        return obj

    def test_activity_guard_locks_once_and_releases_inhibition(self):
        obj=self.controller();request={'mode':'guard','id':'test'}
        idle=mock.Mock();idle.read.return_value=0
        with mock.patch.object(session.core.os.path,'exists',return_value=False),mock.patch.object(session.core,'_read_json',return_value=request),mock.patch.object(session.core,'awake_until',return_value=-1),mock.patch.object(session.core,'keep_awake') as stop,mock.patch.object(session.screen_guard,'X11Idle',return_value=idle),mock.patch.object(session.screen_guard,'find_locker',return_value=mock.sentinel.locker),mock.patch.object(session.screen_guard,'request_lock') as lock,mock.patch.object(session.screen_guard,'lock_active',return_value=True),mock.patch.object(session.time,'monotonic',return_value=100) as clock,mock.patch.object(session.core,'locked'):
            obj.activity_tick();self.assertEqual(obj.guard_phase,'arming')
            clock.return_value=111;idle.read.return_value=11000
            obj.activity_tick();self.assertEqual(obj.guard_phase,'armed');lock.assert_not_called()
            clock.return_value=112;idle.read.return_value=0
            obj.activity_tick();self.assertEqual(obj.guard_phase,'locking');lock.assert_called_once()
            obj.activity_tick();self.assertEqual(obj.guard_phase,'locked')
            obj.activity_tick();lock.assert_called_once();stop.assert_called_once_with(None,start_session=False)
        obj.release.assert_called_once();idle.close.assert_called_once()

    def test_guard_does_not_arm_without_inhibition(self):
        obj=self.controller();obj.cookie=None;request={'mode':'guard','id':'test'}
        with mock.patch.object(session.core.os.path,'exists',return_value=False),mock.patch.object(session.core,'_read_json',return_value=request),mock.patch.object(session.core,'awake_until',return_value=-1),mock.patch.object(session.core,'keep_awake'),mock.patch.object(session.core,'locked'),mock.patch.object(session.screen_guard,'X11Idle'),mock.patch.object(session.screen_guard,'find_locker'),mock.patch.object(session.screen_guard,'request_lock') as lock:
            obj.activity_tick()
        self.assertEqual(obj.guard_phase,'error');lock.assert_not_called()

    def test_missing_lock_confirmation_reports_error(self):
        obj=self.controller();obj.guard_id='test';obj.guard_phase='locking';obj.lock_sent=100
        with mock.patch.object(session.core.os.path,'exists',return_value=False),mock.patch.object(session.core,'_read_json',return_value={'mode':'guard','id':'test'}),mock.patch.object(session.core,'awake_until',return_value=-1),mock.patch.object(session.core,'keep_awake'),mock.patch.object(session.core,'locked'),mock.patch.object(session.screen_guard,'lock_active',return_value=False),mock.patch.object(session.time,'monotonic',return_value=105):
            obj.activity_tick()
        self.assertEqual(obj.guard_phase,'error');obj.release.assert_called_once()

    def test_request_from_old_helper_is_ignored(self):
        with mock.patch.object(session.core,'_read_json',return_value={'mode':'guard','until':-1,'helper':'old'}),mock.patch.object(session.core,'_helper_identity',return_value='new'):
            self.assertIsNone(session.core.awake_until())

    def test_unapplied_preview_is_never_followed(self):
        obj=object.__new__(session.Session);obj.run=mock.Mock()
        state={"style_applied":True,"mode":"dark","applied_recipe":{"mode":"dark","preset":"nord"}}
        with mock.patch.object(session.core,"load_state",return_value=state),mock.patch.object(session.core,"load_config",return_value={"mode":"auto","preset":"rose"}):
            obj.follow_scheme()
        obj.run.assert_not_called()

    def test_system_following_uses_last_applied_recipe(self):
        obj=object.__new__(session.Session);obj.run=mock.Mock()
        state={"style_applied":True,"mode":"light","applied_recipe":{"mode":"auto","preset":"nord"}}
        with mock.patch.object(session.core,"load_state",return_value=state),mock.patch.object(session.core,"effective_mode",return_value="dark") as mode:
            obj.follow_scheme()
        mode.assert_called_once_with(state["applied_recipe"]);obj.run.assert_called_once_with("follow-style")


if __name__=="__main__":unittest.main()
