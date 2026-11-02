import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    with mock.patch("wallpaper_studio.backend.prepare_environment"):
        from wallpaper_studio import core
    HAVE_GI=True
except ImportError:HAVE_GI=False


@unittest.skipUnless(HAVE_GI,"Core tests need PyGObject; pure backend/palette tests still run")
class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        paths={key:str(self.root/key.lower()) for key in ("CONFIG_DIR","CACHE_DIR","DATA_DIR","THEMES_DIR")}
        paths.update({key:str(self.root/"config_dir"/(key.lower()+".json")) for key in ("CONFIG","STATE","ORIGINALS","HISTORY")})
        paths["THEME_CSS"]=str(self.root/"config_dir/theme.css")
        patch=mock.patch.multiple(core,**paths);patch.start();self.addCleanup(patch.stop)
        home=mock.patch.dict(os.environ,{"XDG_CONFIG_HOME":str(self.root/"personal-config")})
        home.start();self.addCleanup(home.stop)

    def test_malformed_config_recovers_without_crashing(self):
        core._json(core.CONFIG,{"preset":[],"tint":"NaN","favorites":[{}],"glass":"yes","folder":None})
        config=core.load_config()
        self.assertEqual(config["preset"],"wallpaper");self.assertFalse(config["glass"]);self.assertEqual(config["favorites"],[])

    def test_import_rejects_invalid_types_and_never_enables_hooks(self):
        path=self.root/"theme.json"
        for settings in ([],{"preset":[]},{"tint":float('nan')},{"glass":"false"},{'preset':'custom','custom_dark':{'paper':'#000000','sheet':'#FFFFFF'}}):
            path.write_text(json.dumps({"format":"wallpaper-studio-video-theme","version":1,"settings":settings}))
            with self.assertRaises(ValueError):core.import_recipe(path)
        path.write_text(json.dumps({"format":"wallpaper-studio-video-theme","version":1,"settings":{"preset":"nord","run_hooks":True,"folder":"/private"}}))
        config=core.import_recipe(path)
        self.assertEqual(config["preset"],"nord");self.assertFalse(config["run_hooks"]);self.assertNotEqual(config["folder"],"/private")

    def test_export_has_no_private_paths_or_hooks(self):
        core.save_config(preset="rose",folder="/private",favorites=["/private/image.png"],run_hooks=True)
        path=self.root/"theme.json";core.export_recipe(path)
        text=path.read_text();self.assertNotIn("/private",text);self.assertNotIn("run_hooks",text)

    def test_named_looks_round_trip_and_stay_inside_their_library(self):
        core.save_config(preset='custom',skin='pixel',custom_dark={'paper':'#171419','accent':'#C6A77A'})
        path=core.save_recipe('Pixel Coffee')
        core.save_config(preset='nord');core.import_recipe(path)
        self.assertEqual(core.load_config()['preset'],'custom');self.assertEqual(core.load_config()['custom_name'],'Pixel Coffee')
        self.assertEqual(len(core.saved_recipes()),1)
        core.save_recipe('Pixel Coffee');self.assertEqual(len(core.saved_recipes()),1)
        with self.assertRaises(ValueError):core.delete_recipe(self.root/'outside.json')
        core.delete_recipe(path);self.assertEqual(core.saved_recipes(),[])

    def test_existing_user_css_survives_apply_and_restore(self):
        path=core._css_file();path.parent.mkdir(parents=True);original="/* my CSS */\nlabel { font-size: 12px; }\n";path.write_text(original)
        core._add_import();core._add_import()
        self.assertEqual(path.read_text().count(core.CSS_MARKER),1)
        core._remove_import();self.assertEqual(path.read_text(),original)

    def test_video_wallpaper_engine_is_used(self):
        video_path=self.root/"clip.mp4";video_path.write_bytes(b"video")
        image_path=self.root/"picture.png";image_path.write_bytes(b"image")
        status=mock.Mock(warning="")
        patchers=[
            mock.patch.object(core,"still_of",side_effect=lambda _p:str(self.root/"frame.jpg")),
            mock.patch.object(core.palette,"from_image",return_value={}),
            mock.patch.object(core,"_keep_image",return_value=str(self.root/"still.jpg")),
            mock.patch.object(core.NativeBackend,"apply_image",return_value=status),
            mock.patch.object(core,"apply_theme"),
            mock.patch.object(core,"start"),
        ]
        for patcher in patchers:patcher.start();self.addCleanup(patcher.stop)
        with mock.patch.object(core.video,"start") as starter,mock.patch.object(core.video,"stop") as stopper:
            core.set_wallpaper(video_path)
            starter.assert_called_once_with(str(video_path),mute=None,fit=None,monitor=None)
            stopper.assert_not_called()
            core.set_wallpaper(image_path)
            stopper.assert_called_once()

    def test_applied_copy_survives_cache_clearing(self):
        source=self.root/"picture.png";source.write_bytes(b"durable image")
        copy=Path(core._keep_image(source));source.unlink()
        frames=Path(core.CACHE_DIR)/"frames";frames.mkdir(parents=True);(frames/"temp.jpg").write_bytes(b"cache")
        core.clear_preview_cache();self.assertEqual(copy.read_bytes(),b"durable image");self.assertFalse(frames.exists())

    def test_undo_uses_saved_copy_and_removes_only_last_entry(self):
        entries=[{"wallpaper":"/old.png","source":"/original.png","target":"dark","fit":"scaled"},{"wallpaper":"/new.png","source":"/new.png"}]
        core._json(core.HISTORY,entries)
        with mock.patch.object(core,"set_wallpaper",return_value="ok") as setter:
            self.assertEqual(core.undo_wallpaper(),"ok")
        setter.assert_called_once_with("/old.png","dark","scaled",record=False,still_only=True)
        self.assertEqual(core.history(),entries[:1])

    def test_restoring_terminal_keeps_profiles_added_later(self):
        class Profiles:
            values={"list":["old","ours","added-later"],"default":"ours"}
            def get_strv(self,key):return self.values[key]
            def get_string(self,key):return self.values[key]
            def set_strv(self,key,value):self.values[key]=value
            def set_string(self,key,value):self.values[key]=value
        profiles=Profiles();core._json(Path(core.CONFIG_DIR)/"terminal-profile.json",{"uuid":"ours","previous_default":"old"})
        with mock.patch.object(core,"_settings",side_effect=lambda schema,*_:profiles if schema.endswith("ProfilesList") else None):core._restore_terminal()
        self.assertEqual(profiles.values,{"list":["old","added-later"],"default":"old"})

    def test_failed_restore_retains_backup_and_theme(self):
        core._json(core.ORIGINALS,{"org.gnome.desktop.interface gtk-theme":"'Previous'"})
        core._write(core.THEME_CSS,"/* keep until restored */")
        settings=mock.Mock();settings.is_writable.return_value=False
        with mock.patch.object(core,"_settings",return_value=settings),self.assertRaisesRegex(ValueError,"backups were kept"):
            core.restore("style")
        self.assertTrue(Path(core.THEME_CSS).exists())
        self.assertIn("org.gnome.desktop.interface gtk-theme",core._read_json(core.ORIGINALS,{}))


if __name__=="__main__":unittest.main()
