"""Original pixel icons and Xcursor files, plus the licensed Silkscreen font."""
from pathlib import Path
import os
import shutil
import struct
import subprocess

ICON_THEME='Studio Pixel'
CURSORS={'Studio Pixel Pearl':'#F3F1FA','Studio Pixel Violet':'#C79CF5','Studio Pixel Gold':'#F4C34D','Studio Pixel Lime':'#A9DF7C','Studio Pixel Ice':'#83DDEB'}
ARROW=['X...............','XX..............','XOX.............','XOOX............','XOOOX...........','XOOOOX..........','XOOOOOX.........','XOOOOOOX........','XOOOOOOOX.......','XOOOOXXXXX......','XOOXO X.........','XOX.XOX.........','XX..XOX.........','X....XOX........','.....XOX........','......X.........']
TEXT=['.XXXXXXX........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','...XOX..........','.XXXXXXX........']
HAND=['.....XX.........','....XOOX........','....XOOX........','....XOOX........','....XOOXXX......','....XOOXOOXX....','..XXXOOXOOXOX...','.XOOXOOOOOOOX...','.XOOOOOOOOOOX...','..XOOOOOOOOOX...','..XOOOOOOOOOX...','...XOOOOOOOX....','...XOOOOOOOX....','....XXXXXXX.....','................','................']


def cursor_bytes(rows,colour,sizes=(24,32,48,64),hotspot=(0,0)):
    """Xcursor image chunks, ARGB pixels and size-specific hotspots."""
    rgb=int(colour.lstrip('#'),16);chunks=[];toc=[];offset=16+12*len(sizes)
    for size in sizes:
        pixels=[]
        for y in range(size):
            row=rows[min(len(rows)-1,y*16//size)] if y*16//size<len(rows) else ''
            for x in range(size):
                c=row[x*16//size] if x*16//size<len(row) else '.'
                pixels.append((0xFF000000|rgb) if c=='O' else 0xFF15131F if c=='X' else 0)
        header=struct.pack('<9I',36,0xFFFD0002,size,1,size,size,hotspot[0]*size//16,hotspot[1]*size//16,0)
        chunk=header+struct.pack('<'+'I'*len(pixels),*pixels)
        toc.append(struct.pack('<3I',0xFFFD0002,size,offset));chunks.append(chunk);offset+=len(chunk)
    return struct.pack('<4I',0x72756358,16,0x10000,len(sizes))+b''.join(toc)+b''.join(chunks)


def pixel_svg(kind):
    colours={'folder':'#E4B955','home':'#85C9EE','trash':'#B6C0D4','terminal':'#95D98B','file':'#E3E9F4','settings':'#B69BE7','browser':'#87CEDB','music':'#E4A2BE','image':'#95C78C'}
    c=colours.get(kind,'#9ABBE5')
    shapes={
     'folder':'<path d="M2 5h5l2 2h5v7H2z"/><path fill="#FFF1BD" d="M3 8h10v1H3z"/>',
     'home':'<path d="m1 8 7-6 7 6h-2v6H3V8z"/><path fill="#263146" d="M7 10h3v4H7z"/>',
     'trash':'<path d="M4 6h8v9H4zM3 3h10v2H3zM6 1h4v2H6z"/><path fill="#526078" d="M6 8h1v5H6zm3 0h1v5H9z"/>',
     'terminal':'<path fill="#253043" d="M1 3h14v11H1z"/><path d="m3 5 3 3-3 3v-2l1-1-1-1zm5 5h4v1H8z"/>',
     'file':'<path d="M4 1h6l3 3v11H4z"/><path fill="#8A9CB6" d="M6 7h5v1H6zm0 3h5v1H6zM10 1v4h3z"/>',
     'settings':'<path d="M6 1h4v2h2v2h3v6h-3v2h-2v2H6v-2H4v-2H1V5h3V3h2z"/><path fill="#3C3155" d="M6 6h4v4H6z"/>',
     'browser':'<path d="M4 1h8v2h2v2h1v6h-1v2h-2v2H4v-2H2v-2H1V5h1V3h2z"/><path fill="#315E83" d="M7 2h2v12H7zM2 7h12v2H2z"/>',
     'music':'<path d="M7 2h6v9h-2V5H9v8H7zM3 11h4v3H3zm6-2h4v3H9z"/>',
     'image':'<path fill="#24334B" d="M1 2h14v12H1z"/><path d="m2 12 4-6 3 4 2-3 3 5z"/><path fill="#EFCE74" d="M10 4h2v2h-2z"/>',
    }
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 16 16" shape-rendering="crispEdges"><g fill="{c}">{shapes.get(kind,shapes["file"])}</g></svg>\n'


def install_assets():
    home=Path.home();data=Path(os.environ.get('XDG_DATA_HOME',home/'.local/share'))
    root=Path(__file__).resolve().parent.parent
    fontdir=data/'fonts/wallpaper-studio-video';fontdir.mkdir(parents=True,exist_ok=True)
    changed=False
    for name in ('Silkscreen-Regular.ttf','OFL.txt'):
        source=root/'data/fonts'/name;target=fontdir/name
        if source.is_file() and (not target.exists() or source.read_bytes()!=target.read_bytes()):shutil.copyfile(source,target);changed=True
    if changed and shutil.which('fc-cache'):
        subprocess.run(['fc-cache','-f',str(fontdir)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
    config=Path(os.environ.get('XDG_CONFIG_HOME',home/'.config'))/'fontconfig/conf.d/91-wallpaper-studio-video-pixel.conf'
    config.parent.mkdir(parents=True,exist_ok=True)
    config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><match target="font"><test name="family" compare="eq"><string>Silkscreen</string></test><edit name="antialias" mode="assign"><bool>false</bool></edit><edit name="hinting" mode="assign"><bool>true</bool></edit></match></fontconfig>\n')
    icons=data/'icons'/ICON_THEME;directory=icons/'scalable/apps';directory.mkdir(parents=True,exist_ok=True)
    (icons/'index.theme').write_text('[Icon Theme]\nName=Studio Pixel\nComment=Original pixel desktop icons\nInherits=Adwaita,hicolor\nDirectories=scalable/apps\n\n[scalable/apps]\nSize=48\nType=Scalable\nMinSize=16\nMaxSize=256\nContext=Applications\n')
    groups={'folder':['folder','folder-documents','folder-download','folder-pictures','folder-music','folder-videos','inode-directory','org.gnome.Nautilus','system-file-manager'],
     'home':['user-home','user-desktop'],'trash':['user-trash','user-trash-full'],
     'terminal':['utilities-terminal','org.gnome.Terminal','gnome-terminal'],
     'file':['text-x-generic','application-x-executable','text-x-python','text-x-csrc'],
     'settings':['preferences-system','org.gnome.Settings','preferences-desktop-theme'],
     'browser':['web-browser','firefox','firefox-esr','chromium','chromium-browser'],
     'music':['audio-x-generic','multimedia-player','org.gnome.Music'],
     'image':['image-x-generic','org.gnome.eog']}
    for kind,names in groups.items():
        for name in names:(directory/(name+'.svg')).write_text(pixel_svg(kind))
    for name,colour in CURSORS.items():
        path=data/'icons'/name;cursor_dir=path/'cursors';cursor_dir.mkdir(parents=True,exist_ok=True)
        (path/'index.theme').write_text(f'[Icon Theme]\nName={name}\nInherits=Adwaita\n')
        for shape,rows,names in [('arrow',ARROW,('left_ptr','default','top_left_arrow','arrow')),
                                 ('text',TEXT,('xterm','text','vertical-text')),
                                 ('hand',HAND,('hand1','hand2','pointer','pointing_hand'))]:
            payload=cursor_bytes(rows,colour,hotspot=(4,7) if shape=='text' else (5,1) if shape=='hand' else (0,0))
            for alias in names:(cursor_dir/alias).write_bytes(payload)


def register_font():
    """Expose the bundled font to the studio when running from source, too."""
    try:
        import ctypes,ctypes.util
        library=ctypes.CDLL(ctypes.util.find_library('fontconfig'))
        library.FcConfigAppFontAddFile.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        library.FcConfigAppFontAddFile(None,str(Path(__file__).resolve().parent.parent/'data/fonts/Silkscreen-Regular.ttf').encode())
    except (OSError,AttributeError,TypeError):pass
