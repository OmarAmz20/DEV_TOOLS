#!/usr/bin/env python3
"""Build the Intel/AMD 64-bit single-file launcher using gcc and Python."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile


def build(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if os.uname().machine!='x86_64':raise RuntimeError('Build this launcher on Linux x86_64.')
    with tempfile.TemporaryDirectory(prefix='studio-bundle-build-') as td:
        td=Path(td)
        code=(source/'packaging/run_bundle.py').read_text()
        (td/'bootstrap_code.h').write_text('#define BOOTSTRAP_CODE '+json.dumps(code,ensure_ascii=True)+'\n')
        native=td/'launcher'
        subprocess.run(['gcc','-static','-Os','-s','-Wall','-Wextra','-I',str(td),str(source/'packaging/native_launcher.c'),'-o',str(native)],check=True)
        compressed=io.BytesIO()
        with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w|') as tar:
                for path in sorted(source.rglob('*')):
                    if not path.is_file() or any(p in ('__pycache__','.git','.pixi','dist','.pytest_cache') for p in path.parts) or path.suffix in ('.pyc','.run','.zip'):continue
                    if path.is_symlink():raise RuntimeError('Source archive cannot contain symlinks: '+str(path))
                    info=tar.gettarinfo(str(path),'wallpaper-studio-video/'+str(path.relative_to(source)))
                    info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                    with path.open('rb') as content:tar.addfile(info,content)
        payload=compressed.getvalue();stub=native.read_bytes()
        trailer=struct.pack('<8sQQ32s',b'WSPRUN21',len(stub),len(payload),hashlib.sha256(payload).digest())
        output.write_bytes(stub+payload+trailer);output.chmod(0o755)
    print(f'Built {output.name}: {output.stat().st_size/1024/1024:.1f} MiB')
    return output


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output')
    build(Path(__file__).resolve().parent.parent,parser.parse_args().output)
