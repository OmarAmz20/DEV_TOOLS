import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import hashlib

spec=importlib.util.spec_from_file_location('studio_bootstrap',Path(__file__).resolve().parent.parent/'packaging/run_bundle.py')
bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)


class BundleTests(unittest.TestCase):
    def test_payload_tampering_and_truncation_are_rejected(self):
        payload=b'example payload';stub=b'native stub'
        trailer=struct.pack('<8sQQ32s',bundle.MAGIC,len(stub),len(payload),hashlib.sha256(payload).digest())
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'app.run';path.write_bytes(stub+payload+trailer)
            self.assertEqual(bundle.inspect_bundle(path)[:2],(len(stub),len(payload)))
            path.write_bytes(stub+b'X'+payload[1:]+trailer)
            with self.assertRaisesRegex(RuntimeError,'checksum'):bundle.inspect_bundle(path)
            path.write_bytes((stub+payload+trailer)[:-3])
            with self.assertRaises(RuntimeError):bundle.inspect_bundle(path)

    def test_archive_cannot_escape_or_install_symlinks(self):
        for name,kind in [('../outside',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('wallpaper-studio-video/link',tarfile.SYMTYPE)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                root=Path(td);archive=root/'app'
                with tarfile.open(archive,'w:gz') as tar:
                    info=tarfile.TarInfo(name);info.type=kind;info.linkname='/etc/passwd';tar.addfile(info)
                with self.assertRaises(RuntimeError):bundle.unpack_bundle(archive,0,root/'out')

    def test_regular_files_extract_including_space_paths(self):
        with tempfile.TemporaryDirectory(prefix='studio space ') as td:
            root=Path(td);archive=root/'app';payload=b'hello'
            with tarfile.open(archive,'w:gz') as tar:
                info=tarfile.TarInfo('wallpaper-studio-video/name with spaces.txt');info.size=len(payload)
                tar.addfile(info,io.BytesIO(payload))
            source=bundle.unpack_bundle(archive,0,root/'out')
            self.assertEqual((source/'name with spaces.txt').read_bytes(),payload)

    def test_repeated_launch_uses_installed_app_without_setup(self):
        from unittest import mock
        import json,os,sys
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data=root/'data';parent=data/'wallpaper-studio-video';(parent/'app').mkdir(parents=True)
            (parent/'launch.sh').write_text('launcher');(parent/'app/wallpaper-studio-video').write_text('app')
            (parent/'bundle.json').write_text(json.dumps({'sha256':'abc'}))
            with mock.patch.object(bundle,'inspect_bundle',return_value=(0,1,'abc')),mock.patch.object(bundle,'launch') as launch,mock.patch.object(bundle,'unpack_bundle') as unpack,mock.patch.object(bundle.os,'geteuid',return_value=1000),mock.patch.dict(os.environ,{'DISPLAY':':test','XDG_DATA_HOME':str(data),'XDG_CACHE_HOME':str(root/'cache')}),mock.patch.object(sys,'argv',['-c','download.run']):
                self.assertEqual(bundle.main(),0)
            launch.assert_called_once();unpack.assert_not_called()


if __name__=='__main__':unittest.main()
