import ctypes
import ctypes.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
from wallpaper_studio import assets,skins,recipes

try:
    with mock.patch('wallpaper_studio.backend.prepare_environment'):
        from wallpaper_studio import core,widget_control as widgets,desktop
    HAVE_GI=True
except ImportError:HAVE_GI=False


class AssetChecks(unittest.TestCase):
    def test_cursor_loads_in_native_xcursor_library(self):
        library=ctypes.util.find_library('Xcursor')
        if not library:self.skipTest('libXcursor unavailable')
        lib=ctypes.CDLL(library);lib.XcursorFilenameLoadImage.argtypes=[ctypes.c_char_p,ctypes.c_int];lib.XcursorFilenameLoadImage.restype=ctypes.c_void_p;lib.XcursorImageDestroy.argtypes=[ctypes.c_void_p]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cursor';path.write_bytes(assets.cursor_bytes(assets.ARROW,'#ECC34A'))
            for size in (24,32,48,64):
                image=lib.XcursorFilenameLoadImage(os.fsencode(path),size)
                self.assertTrue(image);lib.XcursorImageDestroy(image)

    def test_every_skin_resolves_and_has_actual_structural_css(self):
        for name in skins.SKINS:
            config={'preset':'kingdom','skin':name}
            p=recipes.resolve(recipes.sample_base(),config)['dark'];css=recipes.gtk_css(p,True,config)
            self.assertIn('border-radius',css)
            if name not in ('modern',):self.assertIn('titlebar',css)
        self.assertEqual(skins.selected({'preset':'kingdom'}),'kingdom')


@unittest.skipUnless(HAVE_GI,'PyGObject needed')
class WidgetChecks(unittest.TestCase):
    def test_invalid_layout_is_clamped_to_safe_defaults(self):
        result=widgets.validate({'enabled':'yes','opacity':float('nan'),'monitor':-2,'note':['oops'],'items':{'clock':{'x':99,'scale':0},'unknown':{}}})
        self.assertFalse(result['enabled']);self.assertEqual(result['opacity'],.96);self.assertNotIn('unknown',result['items'])
        self.assertEqual(result['items']['clock']['x'],widgets.DEFAULT['items']['clock']['x'])

    def test_geometry_stays_on_small_and_large_monitors(self):
        for width,height in ((640,480),(1920,1080),(3840,2160)):
            for kind in widgets.TYPES:
                x,y,w,h=widgets.geometry({'x':1,'y':1,'scale':1.6},kind,width,height)
                self.assertGreaterEqual(x,0);self.assertLessEqual(x+w,width);self.assertLessEqual(y+h,height)

    def test_layout_presets_enable_widgets_and_keep_private_note(self):
        data=widgets.validate({'note':'private text'})
        result=widgets.preset('hud',data)
        self.assertTrue(result['enabled']);self.assertEqual(result['note'],'private text')
        self.assertEqual(sum(item['enabled'] for item in result['items'].values()),7)
        self.assertFalse(data['enabled'])

    def test_cpu_uses_differences_and_handles_zero_interval(self):
        self.assertEqual(widgets.cpu_percent((100,40),(200,90)),50)
        self.assertIsNone(widgets.cpu_percent((100,40),(100,40)))
        self.assertIsNone(widgets.cpu_percent(None,(200,100)))

    def test_show_with_no_enabled_items_is_rejected_before_save(self):
        data=widgets.validate({'enabled':True})
        for item in data['items'].values():item['enabled']=False
        with mock.patch.object(widgets,'save') as save,self.assertRaises(ValueError):widgets.apply(data)
        save.assert_not_called()

    def test_layout_sharing_keeps_notes_private_and_import_does_not_apply(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'layout.json';data=widgets.preset('hud',widgets.validate({'note':'private secret'}))
            widgets.export_layout(path,data)
            self.assertNotIn('private secret',path.read_text());self.assertNotIn('"note"',path.read_text())
            with mock.patch.object(widgets,'save') as save:
                loaded=widgets.import_layout(path,widgets.validate({'note':'my own note','enabled':False}))
            self.assertFalse(loaded['enabled']);self.assertEqual(loaded['note'],'my own note');save.assert_not_called()


@unittest.skipUnless(HAVE_GI,'PyGObject needed')
class DesktopChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        patch=mock.patch.object(core,'CONFIG_DIR',self.temp.name);patch.start();self.addCleanup(patch.stop)

    def test_look_restore_keeps_a_later_manual_choice(self):
        _,path=desktop._paths();core._json(path,{'icons':{'previous':"'Adwaita'",'last':'Studio Pixel'}})
        with mock.patch.object(desktop,'_setting',return_value=mock.Mock()),mock.patch.object(desktop,'_current',return_value=core.GLib.Variant('s','Papirus')),mock.patch.object(desktop,'_cli') as commit:
            desktop.restore_look()
        commit.assert_not_called();self.assertEqual(core._read_json(path,{}),{})

    def test_look_restore_recovers_unset_value(self):
        _,path=desktop._paths();core._json(path,{'icons':{'previous':None,'last':'Studio Pixel'}})
        settings=mock.Mock();settings.is_writable.return_value=True
        with mock.patch.object(desktop,'_setting',return_value=settings),mock.patch.object(desktop,'_current',return_value=core.GLib.Variant('s','Studio Pixel')),mock.patch.object(desktop,'_cli') as commit:
            desktop.restore_look()
        commit.assert_called_once_with(desktop.I,'icon-theme',None,reset=True)

    def test_desktop_failed_restore_keeps_its_backup(self):
        path,_=desktop._paths();core._json(path,{'font':"'Sans 11'"})
        settings=mock.Mock();settings.is_writable.return_value=False
        with mock.patch.object(desktop,'_setting',return_value=settings),self.assertRaisesRegex(ValueError,'backups were kept'):desktop.restore_all()
        self.assertEqual(core._read_json(path,{}),{'font':"'Sans 11'"})
