"""Session controls for the GTK4 application."""
from gi.repository import Adw, Gtk, GLib
from . import core, screen_guard


def _button(title, callback, suggested=False):
    item=Gtk.Button(label=title, valign=Gtk.Align.CENTER)
    if suggested:item.add_css_class('suggested-action')
    item.connect('clicked', callback)
    return item


class SessionPage:
    def session_page(self):
        page=self.page('Session','Keep the screen awake, then request a lock on the next activity.')
        awake=Adw.PreferencesGroup(title='Keep awake',description='Use the normal desktop request to prevent screen blanking and automatic suspend.')
        self.awake_choice=Adw.ComboRow(title='Keep screen awake',model=Gtk.StringList.new(['Off','30 minutes','1 hour','2 hours','Until this session ends']))
        self.session_syncing=False
        def changed(row,_):
            if not self.session_syncing:
                self.run(lambda:core.keep_awake([None,30,60,120,core.FOREVER][row.get_selected()]),'Keep-awake request updated')
        self.awake_choice.connect('notify::selected',changed)
        awake.add(self.awake_choice)
        self.awake_status=Adw.ActionRow(title='Current status',subtitle='Off')
        awake.add(self.awake_status)
        page.append(awake)

        guard=Adw.PreferencesGroup(title='Lock on next activity',description='Arm a 10-second countdown and move away. After it ends, a key press, mouse movement or mouse click requests a system lock. Arming is never automatic at login.')
        self.guard_status=Adw.ActionRow(title='Checking screen locker…',subtitle='Keep awake alone is available while this check runs.')
        check=_button('Check again',lambda *_:self.check_screen_locker())
        self.guard_status.add_suffix(check);guard.add(self.guard_status)
        row=Adw.ActionRow(title='One-shot activity guard',subtitle='The lock request ends keep awake. Unlock normally to return.')
        self.guard_arm=_button('Arm · 10 seconds',lambda *_:self.run(core.arm_activity_guard),True)
        self.guard_arm.set_sensitive(False);row.add_suffix(self.guard_arm);guard.add(row)
        self.guard_progress=Adw.ActionRow(title='Guard is off',subtitle='This watches idle time only. It never records keys or fakes activity.')
        self.guard_cancel=_button('Stop',lambda *_:self.run(lambda:core.keep_awake(None),'Activity guard stopped'))
        self.guard_progress.add_suffix(self.guard_cancel);guard.add(self.guard_progress)
        test=Adw.ActionRow(title='Test the system locker',subtitle='Locks immediately using the same service as the activity guard.')
        self.guard_test=_button('Lock now',lambda *_:self.run(screen_guard.request_lock,'System lock requested'))
        self.guard_test.set_sensitive(False);test.add_suffix(self.guard_test);guard.add(test)
        page.append(guard)

        details=Adw.PreferencesGroup(title='What to expect')
        details.add(Adw.ActionRow(title='Managed computers',subtitle='A school timer can still end your session. Keep awake does not override administrator logout rules.'))
        details.add(Adw.ActionRow(title='Activity starts the lock request',subtitle='This is not an input shield: the first input may reach an application before the locker activates.'))
        details.add(Adw.ActionRow(title='Your regular lock screen',subtitle='Your system handles authentication. A login-screen preview alone is never treated as a secure lock.'))
        page.append(details)
        self.locker_available=False
        self.check_screen_locker()
        GLib.timeout_add(500,self.refresh_session_status)
        return page

    def check_screen_locker(self):
        def work():
            try:
                status=screen_guard.probe();available=True;title=status['name'];message=status['message']
            except Exception as error:
                available=False;title='Activity guard is unavailable';message=str(error)
            def done():
                if not self.alive:return False
                self.locker_available=available
                self.guard_status.set_title(title);self.guard_status.set_subtitle(message)
                self.guard_test.set_sensitive(available)
                self.refresh_session_status()
                return False
            GLib.idle_add(done)
        self.pool.submit(work)

    def refresh_session_status(self):
        if not self.alive:return False
        request=core._read_json(core.AWAKE,{})
        state=core._read_json(core.SESSION_STATE,{})
        if not isinstance(request,dict):request={}
        if not isinstance(state,dict):state={}
        running=core.helper_running()
        active=bool(state.get('awake_active')) and running
        requested=core.awake_until() is not None
        self.awake_status.set_subtitle('Active' if active else state.get('error') or ('Starting…' if requested and running else 'Off'))
        guard=state.get('guard',{}) if running else {}
        phase=guard.get('phase','off')
        busy=phase in ('arming','armed','locking')
        title={'off':'Guard is off','arming':f"Arming in {guard.get('remaining',10)} seconds…",'armed':'Armed · next activity requests a lock','locking':'Lock requested · waiting for confirmation','locked':'System locker activated','cancelled':'Guard stopped','error':'Guard could not finish'}.get(phase,'Guard is off')
        self.guard_progress.set_title(title)
        self.guard_progress.set_subtitle(guard.get('message') or 'This watches idle time only. It never records keys or fakes activity.')
        self.guard_cancel.set_sensitive(busy)
        self.guard_arm.set_sensitive(self.locker_available and not busy)
        self.guard_arm.set_opacity(1 if self.locker_available and not busy else .4)
        self.guard_test.set_sensitive(self.locker_available and not busy)
        minutes=request.get('minutes') if requested and request.get('mode')!='guard' else None
        options=[None,30,60,120,core.FOREVER]
        selected=options.index(minutes) if minutes in options else 0
        self.session_syncing=True
        self.awake_choice.set_selected(selected)
        self.session_syncing=False
        return True
