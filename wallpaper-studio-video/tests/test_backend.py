import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from wallpaper_studio.backend import NativeBackend,BackendError,prepare_environment


class FakeGNOME:
    def __init__(self):
        self.calls=[];self.values={"picture-uri":"'file:///old.jpg'","picture-uri-dark":"'file:///dark.jpg'","picture-options":"'scaled'"}
        self.locked=set();self.fail_once=None;self.warn_once=None
    def __call__(self,args,**kwargs):
        self.calls.append((args,kwargs.get("env",{})))
        code=0;out="";err=""
        if args[0]=="systemctl":
            if "show" in args:out="0\n"
        elif args[1]=="writable":out="false" if args[-1] in self.locked else "true"
        elif args[1]=="get":out=self.values[args[-1]]
        elif args[1]=="set":
            key,value=args[-2:]
            if key==self.fail_once:code=1;err="Operation not permitted";self.fail_once=None
            elif key==self.warn_once:err="failed to commit changes to dconf";self.warn_once=None
            else:self.values[key]=value
        return subprocess.CompletedProcess(args,code,out,err)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        patch=mock.patch.dict(os.environ,{"HOME":str(self.home),"XDG_CONFIG_HOME":str(self.home/".config"),"XDG_SESSION_TYPE":"x11"})
        patch.start();self.addCleanup(patch.stop)
        root=mock.patch("os.geteuid",return_value=1000);root.start();self.addCleanup(root.stop)
        self.profile=self.home/".config/dconf/wallpaper-profile";self.profile.parent.mkdir(parents=True)
        self.profile.write_bytes(b"# existing profile: keep exactly\nuser-db:user\n")
        self.override=self.home/".config/systemd/user/org.gnome.Shell@x11.service.d/wallpaper-profile.conf"
        self.override.parent.mkdir(parents=True)
        self.override.write_text(f'[Service]\n# working account\nEnvironment="DCONF_PROFILE={self.profile}"\nEnvironment=GSETTINGS_BACKEND=dconf\n')
        self.fake=FakeGNOME();self.backend=NativeBackend(self.fake)
        self.image=self.home/"a picture's name.png";self.image.write_bytes(b"test file")

    def test_preserve_working_profile_and_override(self):
        before=[p.read_bytes() for p in (self.profile,self.override)]
        prepare_environment();status=self.backend.apply_image(self.image)
        self.assertEqual(before,[p.read_bytes() for p in (self.profile,self.override)])
        self.assertIsNone(status.loaded)
        for args,env in self.fake.calls:
            self.assertEqual(env["DCONF_PROFILE"],str(self.profile));self.assertEqual(env["GSETTINGS_BACKEND"],"dconf")
            self.assertFalse(any(word in args for word in ("restart","start","stop","--replace","daemon-reload")))

    def test_light_only_preserves_dark_variant(self):
        self.backend.apply_image(self.image,"light","centered")
        self.assertEqual(self.fake.values["picture-uri-dark"],"'file:///dark.jpg'")
        self.assertIn("%20",self.fake.values["picture-uri"])
        self.assertEqual(self.fake.values["picture-options"],"'centered'")

    def test_preflight_prevents_partial_change(self):
        old=dict(self.fake.values);self.fake.locked.add("picture-uri-dark")
        with self.assertRaises(BackendError):self.backend.apply_image(self.image)
        self.assertEqual(old,self.fake.values)

    def test_failure_rolls_back_both_values(self):
        old=dict(self.fake.values);self.fake.fail_once="picture-uri-dark"
        with self.assertRaises(BackendError):self.backend.apply_image(self.image)
        self.assertEqual(old,self.fake.values)

    def test_zero_exit_dconf_warning_is_failure(self):
        old=dict(self.fake.values);self.fake.warn_once="picture-uri-dark"
        with self.assertRaisesRegex(BackendError,"dconf"):self.backend.apply_image(self.image)
        self.assertEqual(old,self.fake.values)

    def test_new_setup_requires_only_normal_login(self):
        self.override.unlink();status=self.backend.ensure_setup()
        self.assertIs(status.loaded,False)
        self.assertIn("daemon-reload",[args[-1] for args,_ in self.fake.calls])

    def test_unrelated_override_kept(self):
        self.override.write_text('[Service]\nEnvironment="DCONF_PROFILE=/other/profile"\n')
        before=self.override.read_bytes()
        with self.assertRaises(BackendError):self.backend.ensure_setup()
        self.assertEqual(before,self.override.read_bytes())

    def test_root_rejected(self):
        with mock.patch("os.geteuid",return_value=0),self.assertRaisesRegex(BackendError,"without sudo"):
            self.backend.ensure_setup()


if __name__=="__main__":unittest.main()
