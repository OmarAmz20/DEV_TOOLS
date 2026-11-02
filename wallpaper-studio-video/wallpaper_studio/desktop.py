"""Explicit desktop controls, original-value backups and owned theme extras."""
import os
from pathlib import Path
import subprocess
from functools import lru_cache
from gi.repository import Gio,GLib
from . import core,assets,skins

I='org.gnome.desktop.interface';W='org.gnome.desktop.wm.preferences';M='org.gnome.mutter'
D='org.gnome.shell.extensions.dash-to-dock';U='org.gnome.shell.extensions.user-theme'
USER_THEME_UUID='user-theme@gnome-shell-extensions.gcampax.github.com'
FIELDS={
 'font':(I,'font-name'),'mono':(I,'monospace-font-name'),'icons':(I,'icon-theme'),
 'cursor':(I,'cursor-theme'),'cursor_size':(I,'cursor-size'),'text_scale':(I,'text-scaling-factor'),
 'animations':(I,'enable-animations'),'clock_seconds':(I,'clock-show-seconds'),
 'clock_date':(I,'clock-show-date'),'clock_weekday':(I,'clock-show-weekday'),
 'battery':(I,'show-battery-percentage'),'hot_corner':(I,'enable-hot-corners'),
 'buttons':(W,'button-layout'),'focus':(W,'focus-mode'),'workspaces':(W,'num-workspaces'),
 'center':(M,'center-new-windows'),'dynamic_workspaces':(M,'dynamic-workspaces'),
 'dock_position':(D,'dock-position'),'dock_size':(D,'dash-max-icon-size'),
 'dock_autohide':(D,'autohide'),'dock_extend':(D,'extend-height'),
}


@lru_cache(maxsize=32)
def _schema(schema):
    base=Gio.SettingsSchemaSource.get_default()
    found=base.lookup(schema,True) if base else None
    if found:return found,None
    for parent in (Path.home()/'.local/share/gnome-shell/extensions',Path('/usr/share/gnome-shell/extensions')):
        if not parent.is_dir():continue
        for path in parent.glob('*/schemas'):
            if not (path/'gschemas.compiled').is_file():continue
            try:
                source=Gio.SettingsSchemaSource.new_from_directory(str(path),base,False)
                found=source.lookup(schema,True)
                if found:return found,str(path)
            except GLib.Error:pass
    return None,None


def _setting(schema):
    found,_=_schema(schema)
    return Gio.Settings.new_full(found,None,None) if found else None


def values():
    result={}
    for name,(schema,key) in FIELDS.items():
        settings=_setting(schema)
        if settings and settings.props.settings_schema.has_key(key):
            result[name]={'value':settings.get_value(key).unpack(),'writable':settings.is_writable(key)}
    return result


def panel_available():
    settings=core._settings('org.gnome.shell')
    return bool(_setting(U) and settings and USER_THEME_UUID in settings.get_strv('enabled-extensions') and not settings.get_boolean('disable-user-extensions'))


def themes(cursors=False):
    values=set(assets.CURSORS if cursors else [assets.ICON_THEME,'Adwaita','hicolor'])
    data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
    for root in (data/'icons',Path.home()/'.icons',Path('/usr/share/icons')):
        if not root.is_dir():continue
        for item in root.iterdir():
            if item.is_dir() and ((item/'cursors').is_dir() if cursors else (item/'index.theme').is_file() and (item/'scalable').is_dir() or (item/'index.theme').is_file() and not (item/'cursors').is_dir()):values.add(item.name)
    return sorted(values,key=str.casefold)


def _paths():return Path(core.CONFIG_DIR)/'desktop-originals.json',Path(core.CONFIG_DIR)/'look-state.json'


def _environment(schema):
    _,directory=_schema(schema)
    env={**os.environ}
    if directory:env['GSETTINGS_SCHEMA_DIR']=directory
    return env


def _current(schema,key):
    result=subprocess.run(['gsettings','get',schema,key],env=_environment(schema),capture_output=True,text=True,timeout=6)
    if result.returncode or result.stderr.strip():raise ValueError(result.stderr.strip() or f'Could not read {key}')
    return GLib.Variant.parse(None,result.stdout.strip(),None,None)


def _cli(schema,key,raw=None,reset=False):
    args=['gsettings','reset',schema,key] if reset else ['gsettings','set',schema,key,raw]
    result=subprocess.run(args,env=_environment(schema),capture_output=True,text=True,timeout=6)
    if result.returncode or result.stderr.strip():raise ValueError(result.stderr.strip() or f'Could not change {key}')
    actual=_current(schema,key)
    if not reset and not actual.equal(GLib.Variant.parse(None,raw,None,None)):raise ValueError(f'{key} could not be saved')


def apply(changes,owned=False):
    """Preflight every field; preserve first originals and roll back a failed batch."""
    pending={}
    for name,value in changes.items():
        schema,key=FIELDS.get(name,(U,'name')) if name=='panel' or name in FIELDS else (None,None)
        if not schema:raise ValueError('Unknown desktop control')
        settings=_setting(schema)
        if not settings or not settings.props.settings_schema.has_key(key) or not settings.is_writable(key):raise ValueError(f'{name.replace("_"," ")} is unavailable or locked')
        spec=settings.props.settings_schema.get_key(key)
        variant=GLib.Variant(spec.get_value_type().dup_string(),value)
        if not spec.range_check(variant):raise ValueError(f'Value outside the supported range for {name}')
        original=settings.get_user_value(key)
        pending[name]=(schema,key,variant,None if original is None else original.print_(True))
    with core.locked():
        backup_path,look_path=_paths();backup=core._read_json(backup_path,{})
        look=core._read_json(look_path,{})
        completed=[]
        try:
            for name,(schema,key,value,previous) in pending.items():
                backup.setdefault(name,previous)
                core._json(backup_path,backup)
                completed.append(name);_cli(schema,key,value.print_(True))
                if owned:look.setdefault(name,{'previous':previous})['last']=value.unpack()
                else:look.pop(name,None)
        except Exception:
            for name in reversed(completed):
                schema,key,_,previous=pending[name]
                try:_cli(schema,key,previous,reset=previous is None)
                except Exception:pass
            raise
        core._json(look_path,look)
    return 'Desktop settings applied'


def restore_look(keep=()):
    with core.locked():
        _,path=_paths();look=core._read_json(path,{});failed=[]
        for name,data in list(look.items()):
            if name in keep:continue
            schema,key=FIELDS.get(name,(U,'name'));settings=_setting(schema)
            try:
                if settings and _current(schema,key).unpack()==data['last']:
                    if not settings.is_writable(key):raise ValueError(f'{name} is locked')
                    _cli(schema,key,data['previous'],reset=data['previous'] is None)
                del look[name]
            except (ValueError,OSError,subprocess.SubprocessError) as error:failed.append(str(error))
        core._json(path,look)
        if failed:raise ValueError('; '.join(failed))


def restore_all():
    with core.locked():
        backup_path,look_path=_paths();backup=core._read_json(backup_path,{});failed=[]
        for name,raw in list(backup.items()):
            schema,key=FIELDS.get(name,(U,'name'));settings=_setting(schema)
            try:
                if not settings or not settings.is_writable(key):raise ValueError(f'{name} is locked')
                _cli(schema,key,raw,reset=raw is None);del backup[name]
            except (ValueError,OSError,subprocess.SubprocessError) as error:failed.append(str(error))
        core._json(backup_path,backup)
        if not failed:core._json(look_path,{})
        else:raise ValueError('Some desktop settings could not be restored; backups were kept. '+'; '.join(failed))


def apply_look(config,theme):
    chosen=skins.selected(config);changes={}
    if config.get('theme_extras',True) and skins.pixel_style(config):
        cursor='Gold' if chosen=='kingdom' else 'Lime' if chosen in ('handheld','crt') else 'Violet'
        changes.update(icons=assets.ICON_THEME,cursor='Studio Pixel '+cursor)
    if config.get('panel_theme') and panel_available():changes['panel']=theme
    restore_look(keep=changes)
    if changes:apply(changes,owned=True)


def shell_css(p,config):
    radius=0 if skins.pixel_style(config) else 12
    font='font-family: "Silkscreen";' if skins.pixel_style(config) and config.get('pixel_font',True) else ''
    return f'''/* Wallpaper Studio Video panel theme */
#panel {{ background-color: {p['paper2']}; color: {p['ink']}; {font} border-bottom: 2px solid {p['accent']}; }}
#panel .panel-button:hover, #panel .panel-button:active {{ background-color: {p['sheet']}; }}
.popup-menu-content, .modal-dialog {{ background-color: {p['paper']}; color: {p['ink']}; border: 2px solid {p['accent']}; border-radius: {radius}px; }}
.popup-menu-item:active, .popup-menu-item:selected {{ background-color: {p['accent']}; color: {p['on_accent']}; }}
.dash-background {{ background-color: {p['paper2']}; border: 2px solid {p['accent']}; border-radius: {radius}px; }}
.workspace-switcher, .switcher-list {{ background-color: {p['paper']}; color: {p['ink']}; border: 2px solid {p['accent']}; }}
'''
