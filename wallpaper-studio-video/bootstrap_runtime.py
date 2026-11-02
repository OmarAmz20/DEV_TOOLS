#!/usr/bin/env python3
"""Optional user-local GTK runtime from official Ubuntu packages.

Only regular dpkg-deb extraction is used: no apt install, sudo, maintainer
scripts, shell startup changes, or system library replacement.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

SEEDS=("python3-gi","python3-gi-cairo","python3-cairo","gir1.2-gtk-4.0",
       "gir1.2-adw-1","gir1.2-gdkpixbuf-2.0","gir1.2-gtk-3.0")


def runtime_environment(prefix,environment=None):
    env=dict(os.environ if environment is None else environment)
    arch=subprocess.check_output(["dpkg-architecture","-qDEB_HOST_MULTIARCH"],text=True).strip() if shutil.which("dpkg-architecture") else ("aarch64-linux-gnu" if os.uname().machine=="aarch64" else "x86_64-linux-gnu")
    lib=prefix/"usr/lib"/arch
    values={"LD_LIBRARY_PATH":str(lib)+":"+str(prefix/"lib"/arch),
            "PYTHONPATH":str(prefix/"usr/lib/python3/dist-packages"),
            "GI_TYPELIB_PATH":str(lib/"girepository-1.0"),
            "XDG_DATA_DIRS":str(prefix/"usr/share")}
    for key,value in values.items():
        previous=env.get(key,"")
        if key=="XDG_DATA_DIRS" and not previous:previous="/usr/local/share:/usr/share"
        env[key]=value+(":"+previous if previous else "")
    return env


def has_gtk(python,environment=None):
    probe='import gi,cairo;gi.require_version("Gtk","4.0");gi.require_version("Adw","1");gi.require_version("GdkPixbuf","2.0");from gi.repository import Gtk,Adw,GdkPixbuf'
    return subprocess.run([python,"-c",probe],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0


def has_widgets(python,environment=None):
    probe='import gi,cairo;gi.require_version("Gtk","3.0");from gi.repository import Gtk,Gdk'
    return subprocess.run([python,'-c',probe],env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0


def download_runtime(destination,python):
    info={}
    for line in Path("/etc/os-release").read_text().splitlines():
        key,_,value=line.partition("=");info[key]=value.strip('"')
    suites={"22.04":("jammy",(3,10)),"24.04":("noble",(3,12))}
    version=info.get("VERSION_ID")
    abi=tuple(json.loads(subprocess.check_output([python,"-c","import json,sys;print(json.dumps(list(sys.version_info[:2])))"],text=True)))
    if info.get("ID")!="ubuntu" or version not in suites or abi!=suites[version][1]:
        raise RuntimeError("Automatic runtime download supports Ubuntu 22.04 / Python 3.10 and Ubuntu 24.04 / Python 3.12. Use a system Python with GTK 4 and libadwaita on other systems.")
    if not shutil.which("dpkg-deb"):raise RuntimeError("dpkg-deb is required for the user-local runtime")
    arch=subprocess.check_output(["dpkg","--print-architecture"],text=True).strip()
    if arch not in ("amd64","arm64"):raise RuntimeError("Automatic runtime download supports amd64 and arm64")
    base="https://archive.ubuntu.com/ubuntu/" if arch=="amd64" else "https://ports.ubuntu.com/ubuntu-ports/"
    suite=suites[version][0];packages={};provides={}
    installed_text=subprocess.check_output(["dpkg-query","-W","-f=${binary:Package}\t${Version}\n"],text=True)
    installed={line.partition("\t")[0].split(":")[0]:line.partition("\t")[2] for line in installed_text.splitlines()}
    with tempfile.TemporaryDirectory(prefix="wallpaper-plus-runtime-") as temp:
        workspace=Path(temp)
        def get(url):
            request=urllib.request.Request(url,headers={"User-Agent":"Wallpaper-Studio-Plus/2.0"})
            with urllib.request.urlopen(request,timeout=60) as response:return response.read()
        release=get(base+f"dists/{suite}/Release").decode()
        hashes={}
        section=False
        for line in release.splitlines():
            if line=="SHA256:":section=True;continue
            if section and not line.startswith(" "):break
            if section:
                digest,size,path=line.split();hashes[path]=digest
        loaded=set()
        def load(component):
            if component in loaded:return
            print(f"Reading official Ubuntu {suite} {component} package list…",flush=True)
            path=f"{component}/binary-{arch}/Packages.xz"
            payload=get(base+f"dists/{suite}/"+path)
            if hashlib.sha256(payload).hexdigest()!=hashes.get(path):raise RuntimeError("Ubuntu package-list checksum did not match")
            for paragraph in lzma.decompress(payload).decode().split("\n\n"):
                record={};key=None
                for line in paragraph.splitlines():
                    if line.startswith(" ") and key:record[key]+=" "+line.strip()
                    elif ": " in line:key,value=line.split(": ",1);record[key]=value
                if "Package" not in record:continue
                packages.setdefault(record["Package"],record)
                for name in record.get("Provides","").split(","):
                    match=re.match(r"\s*([a-z0-9][a-z0-9+.-]*)",name)
                    if match:provides.setdefault(match.group(1),record)
            loaded.add(component)
        load("main");load("universe")
        chosen={};queue=list(SEEDS)
        def satisfied(item):
            match=re.match(r"\s*([a-z0-9][a-z0-9+.-]*)(?::[a-z0-9]+)?(?:\s*\((<<|<=|=|>=|>>)\s*([^)]+)\))?",item)
            if not match:return None,False
            name,operator,version=match.groups()
            if name in chosen:return name,True
            if name not in installed:return name,False
            return name,not operator or subprocess.run(["dpkg","--compare-versions",installed[name],operator,version],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        while queue:
            name=queue.pop();record=packages.get(name) or provides.get(name)
            if not record:raise RuntimeError("Ubuntu dependency not found: "+name)
            name=record["Package"]
            if name in chosen:continue
            # Extracting glibc or a different system Python would not be a safe
            # partial runtime. These are prerequisites of the matching Ubuntu.
            if name in ("libc6","libc-bin","python3","python3-minimal") or re.fullmatch(r"(?:lib)?python3\.\d+.*",name):
                raise RuntimeError("This Ubuntu needs updated system prerequisites. Ask its administrator to provide GTK 4 and libadwaita.")
            chosen[name]=record
            for group in (record.get("Pre-Depends","")+","+record.get("Depends","")).split(","):
                alternatives=[satisfied(item) for item in group.split("|")]
                if any(ok for _,ok in alternatives):continue
                candidate=next((n for n,_ in alternatives if n and (n in packages or n in provides)),None)
                if candidate:queue.append(candidate)
                elif any(n for n,_ in alternatives):raise RuntimeError("Could not resolve runtime dependency: "+group)
        print(f"Downloading {len(chosen)} verified packages into your account…",flush=True)
        def fetch(record):
            payload=get(base+record["Filename"])
            if hashlib.sha256(payload).hexdigest()!=record["SHA256"]:raise RuntimeError("Package checksum did not match: "+record["Package"])
            path=workspace/Path(record["Filename"]).name;path.write_bytes(payload);return path
        with ThreadPoolExecutor(max_workers=4) as pool:archives=list(pool.map(fetch,chosen.values()))
        destination.parent.mkdir(parents=True,exist_ok=True)
        staged=Path(tempfile.mkdtemp(prefix=".runtime-",dir=destination.parent))
        try:
            for archive in archives:subprocess.run(["dpkg-deb","-x",str(archive),str(staged)],check=True)
            if not has_gtk(python,runtime_environment(staged)) or not has_widgets(python,runtime_environment(staged)):
                raise RuntimeError("The downloaded runtime could not load GTK. Existing files were kept.")
            (staged/"packages.json").write_text(json.dumps({n:r["Version"] for n,r in chosen.items()},indent=2)+"\n")
            if destination.exists():shutil.rmtree(destination)
            staged.rename(destination)
        finally:
            if staged.exists():shutil.rmtree(staged)
    return destination


if __name__=="__main__":
    print("This helper is used by install.sh; run that instead.",file=sys.stderr)
    raise SystemExit(2)
