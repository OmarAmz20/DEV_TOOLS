"""GTK 4 / libadwaita interface, compatible with Ubuntu 22.04's GTK 4.6."""
import concurrent.futures
import os
from pathlib import Path
import threading
import gi
gi.require_version("Gtk","4.0")
gi.require_version("Adw","1")
gi.require_version("GdkPixbuf","2.0")
from gi.repository import Adw,Gdk,GdkPixbuf,Gio,GLib,Gtk,Pango
from . import core,recipes,skins,assets,widget_control
from . import video_wallpaper as video
from .custom_pages import CustomizationPages
from .backend import NativeBackend

APP_ID=core.APP_ID
ROTATIONS=[(0,"Off"),(.25,"Every 15 minutes"),(1,"Every hour"),(3,"Every 3 hours"),(6,"Every 6 hours"),(12,"Every 12 hours"),(24,"Once a day")]
FITS=[("zoom","Fill / crop"),("scaled","Fit whole image"),("stretched","Stretch"),("centered","Center"),("wallpaper","Tile"),("spanned","Span monitors")]
TARGETS=[("both","Light + dark"),("light","Light only"),("dark","Dark only")]
CSS=b"""
window.studio-plus { background-color: @window_bg_color; }
.studio-sidebar { background-color: alpha(@headerbar_bg_color,.72); border-right: 1px solid alpha(@window_fg_color,.08); }
.studio-brand { font-weight: 800; font-size: 19px; letter-spacing: -.4px; }
.studio-kicker { font-size: 10px; font-weight: 800; letter-spacing: 1.7px; }
.studio-nav { background: transparent; }
.studio-nav row { border-radius: 10px; padding: 4px; margin: 2px 12px; }
.studio-nav row:selected { background-color: alpha(@accent_bg_color,.16); color: @accent_color; }
.studio-nav row:hover { background-color: alpha(@window_fg_color,.06); }
.studio-method { border-radius: 12px; background-color: alpha(@accent_bg_color,.10); padding: 12px; }
.studio-heading { font-weight: 800; font-size: 28px; letter-spacing: -.8px; }
.studio-hero { border-radius: 18px; background-color: @card_bg_color; border: 1px solid alpha(@window_fg_color,.08); padding: 16px; }
.studio-photo { border-radius: 12px; background-color: @headerbar_bg_color; }
.studio-pill { border-radius: 20px; padding: 4px 10px; font-size: 10px; font-weight: 700; background: alpha(@accent_bg_color,.12); color: @accent_color; }
.studio-toolbar { border-radius: 12px; background-color: alpha(@headerbar_bg_color,.45); padding: 8px; }
.studio-thumb { padding: 0; border-radius: 13px; border: 2px solid transparent; background-color: @card_bg_color; }
.studio-thumb:hover { border-color: alpha(@accent_bg_color,.55); }
.studio-thumb.selected { border-color: @accent_bg_color; }
.studio-thumb.current { box-shadow: 0 0 0 1px alpha(@accent_bg_color,.32); }
.studio-thumb-label { padding: 9px 11px; font-size: 11px; font-weight: 600; }
.studio-favorite { margin: 7px; min-height: 24px; min-width: 24px; background: alpha(@window_bg_color,.92); border-radius: 20px; }
.studio-badge { background: rgba(14,18,25,.82); color: white; border-radius: 6px; padding: 3px 7px; margin: 8px; font-size: 9px; font-weight: bold; }
.studio-recipe { background-color: @card_bg_color; border-radius: 13px; border: 2px solid transparent; padding: 14px; }
.studio-recipe.selected { border-color: @accent_bg_color; }
.studio-recipe:hover { border-color: alpha(@accent_bg_color,.5); }
.studio-section { font-size: 15px; font-weight: 750; }
.studio-preview { border-radius: 15px; border: 1px solid alpha(@window_fg_color,.08); }
.studio-swatch { border-radius: 7px; }
.studio-muted { color: @ws_muted; }
.studio-divider { min-height: 1px; background: alpha(@window_fg_color,.09); }
.studio-primary { padding: 10px 20px; border-radius: 11px; font-weight: 700; }
"""


def label(text,css=None,**kwargs):
    item=Gtk.Label(label=text,xalign=0,**kwargs)
    if css:item.add_css_class(css)
    return item


def button(text=None,icon=None,callback=None,classes=()):
    item=Gtk.Button(label=text) if text else Gtk.Button(icon_name=icon)
    for name in classes:item.add_css_class(name)
    if callback:item.connect("clicked",callback)
    return item


def cover(path,width,height):
    _,w,h=GdkPixbuf.Pixbuf.get_file_info(path)
    if not w or not h:raise ValueError("This image cannot be decoded")
    scale=max(width/w,height/h)
    pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,max(width,round(w*scale)),max(height,round(h*scale)),False)
    return pixbuf.new_subpixbuf((pixbuf.get_width()-width)//2,(pixbuf.get_height()-height)//2,width,height)


def thumbnail(path):
    out=Path(core.CACHE_DIR)/"thumbs"/core._cache_name(path,".png")
    if out.is_file():return GdkPixbuf.Pixbuf.new_from_file(str(out))
    pb=cover(core.still_of(path),480,290)
    out.parent.mkdir(parents=True,exist_ok=True)
    pb.savev(str(out),"png",[],[])
    return pb


def swatch(hexcolour,size=24):
    area=Gtk.DrawingArea(content_width=size,content_height=size,tooltip_text=hexcolour)
    rgba=Gdk.RGBA();rgba.parse(hexcolour)
    def draw(_a,cr,w,h):
        cr.set_source_rgb(rgba.red,rgba.green,rgba.blue);cr.rectangle(0,0,w,h);cr.fill()
    area.set_draw_func(draw);area.add_css_class("studio-swatch");area.set_overflow(Gtk.Overflow.HIDDEN)
    return area


class CoverPicture(Gtk.DrawingArea):
    """Cropped thumbnails, including on GTK 4.6 without Picture.content-fit."""
    def __init__(self):
        super().__init__(content_width=230,content_height=139,hexpand=True)
        self.pixbuf=None
        self.set_draw_func(self.draw)

    def set_pixbuf(self,pixbuf):
        self.pixbuf=pixbuf;self.queue_draw()

    def draw(self,_area,cr,width,height):
        if self.pixbuf is None:return
        w,h=self.pixbuf.get_width(),self.pixbuf.get_height();scale=max(width/w,height/h)
        cr.translate((width-w*scale)/2,(height-h*scale)/2);cr.scale(scale,scale)
        Gdk.cairo_set_source_pixbuf(cr,self.pixbuf,0,0);cr.paint()


from .session_page import SessionPage


class Window(Adw.ApplicationWindow,CustomizationPages,SessionPage):
    def __init__(self,app,page="library"):
        super().__init__(application=app,title="Wallpaper Studio Video",default_width=1160,default_height=880)
        self.add_css_class("studio-plus")
        self.config=core.load_config();self.alive=True;self.busy=False
        self.switches={};self.syncing=False
        self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.preview_pool=concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.futures=[];self.preview_future=None;self.library_generation=0;self.selection_generation=0
        self.selected=None;self.base_palette=core.load_state().get("base_palette") or recipes.sample_base()
        self.palette=recipes.resolve(self.base_palette,self.config)
        self.cards={};self.recipe_buttons={};self.pending_monitor=0;self.filter_timer=0;self.preview_timer=0
        self.query="";self.only_favorites=False;self.kind="all";self.page_limit=48
        self.toasts=Adw.ToastOverlay()
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header=Adw.HeaderBar();header.set_title_widget(label("Wallpaper Studio Video"))
        self.spinner=Gtk.Spinner();header.pack_start(self.spinner)
        menu=Gio.Menu()
        for title,action in (("Open an image…","open"),("Undo wallpaper","undo"),("Import a theme…","import"),("Export this theme…","export"),
                             ("Restore window style only","restore-style"),("Restore wallpaper only","restore-wallpaper"),("Restore all Plus changes","restore-all"),("About & credits","about")):
            menu.append(title,"win."+action)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic",menu_model=menu))
        root.append(header)
        split=Gtk.Box(vexpand=True)
        self.stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=150,hexpand=True,vexpand=True)
        split.append(self.sidebar());split.append(self.stack)
        self.stack.add_named(self.scroll(self.library_page()),"library")
        self.stack.add_named(self.scroll(self.appearance_page()),"appearance")
        self.stack.add_named(self.scroll(self.widgets_page()),"widgets")
        self.stack.add_named(self.scroll(self.video_page()),"video")
        self.stack.add_named(self.scroll(self.desktop_page()),"desktop")
        self.stack.add_named(self.scroll(self.session_page()),"session")
        self.stack.add_named(self.scroll(self.history_page()),"history")
        self.stack.add_named(self.scroll(self.preferences_page()),"preferences")
        root.append(split);self.toasts.set_child(root);self.set_content(self.toasts)
        self.install_actions()
        drop=Gtk.DropTarget.new(Gio.File,Gdk.DragAction.COPY)
        drop.connect("drop",lambda _t,file,*_:self.select(file.get_path()) or True);self.add_controller(drop)
        self.connect("close-request",self.closed)
        os.makedirs(core.CONFIG_DIR,exist_ok=True)
        self.monitor=Gio.File.new_for_path(core.CONFIG_DIR).monitor_directory(Gio.FileMonitorFlags.NONE,None)
        self.monitor.connect("changed",self.state_event)
        self.folder_monitor=None
        self.set_page(page);self.refresh_palette();self.load_library();self.load_history();self.check_backend()
        initial=core.load_state().get("source") or core.load_state().get("wallpaper")
        if initial and os.path.isfile(initial):self.select(initial)
        else:
            def current():
                result=NativeBackend().current_image(core.effective_mode()=="dark")
                def selected():
                    if self.alive and result:self.select(result)
                    return False
                GLib.idle_add(selected)
            self.pool.submit(current)

    def sidebar(self):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,width_request=204)
        box.add_css_class("studio-sidebar")
        brand=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_top=28,margin_start=22,margin_end=12,margin_bottom=26)
        brand.append(label("STUDIO / PLUS","studio-kicker"));brand.append(label("A little more you.","studio-brand"))
        brand.append(label("Wallpaper & colour","dim-label"));box.append(brand)
        self.nav=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE);self.nav.add_css_class("studio-nav")
        for key,title,icon in (("library","Library","view-grid-symbolic"),("appearance","Appearance","applications-graphics-symbolic"),
                               ("widgets","Widgets","view-app-grid-symbolic"),("video","Video wallpaper","media-playback-start-symbolic"),
                               ("desktop","Desktop controls","preferences-desktop-display-symbolic"),
                               ("session","Session","system-lock-screen-symbolic"),("history","Recent choices","document-open-recent-symbolic"),("preferences","Preferences","preferences-system-symbolic")):
            row=Gtk.ListBoxRow();row.page_name=key
            content=Gtk.Box(spacing=12,margin_top=10,margin_bottom=10,margin_start=12,margin_end=10)
            content.append(Gtk.Image(icon_name=icon));content.append(label(title));row.set_child(content);self.nav.append(row)
        self.nav.connect("row-selected",lambda _l,row:self.set_page(row.page_name) if row else None)
        box.append(self.nav);box.append(Gtk.Box(vexpand=True))
        footer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7,margin_start=14,margin_end=14,margin_bottom=18)
        footer.add_css_class("studio-method")
        footer.append(label("NATIVE GNOME","studio-kicker"))
        self.setup_label=label("Checking your setup…","caption",wrap=True)
        footer.append(self.setup_label)
        footer.append(button("Setup details",callback=lambda *_:self.set_page("preferences"),classes=("flat",)))
        box.append(footer);return box

    def scroll(self,child):
        scroller=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(child);return scroller

    def page(self,title,description):
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=22,margin_top=25,margin_bottom=30,margin_start=26,margin_end=26)
        head=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        head.append(label(title,"studio-heading"));head.append(label(description,"studio-muted",wrap=True));box.append(head)
        return box

    def set_page(self,name):
        if hasattr(self,"stack") and self.stack.get_child_by_name(name):self.stack.set_visible_child_name(name)
        for i in range(8):
            row=self.nav.get_row_at_index(i)
            if row and row.page_name==name and self.nav.get_selected_row()!=row:self.nav.select_row(row)
        if name=="history" and hasattr(self,"history_group"):self.load_history()
        if name=="video" and hasattr(self,"video_status_label"):self.refresh_video_status()

    def library_page(self):
        page=self.page("Wallpaper library","Preview a picture, make it a favourite, then apply it to your desktop.")
        hero=Gtk.Box(spacing=20);hero.add_css_class("studio-hero")
        self.hero=Gtk.Picture(can_shrink=True,keep_aspect_ratio=True,width_request=430,height_request=248)
        self.hero.add_css_class("studio-photo");self.hero.set_overflow(Gtk.Overflow.HIDDEN);hero.append(self.hero)
        info=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=11,hexpand=True,valign=Gtk.Align.CENTER)
        self.preview_badge=label("PREVIEW","studio-pill",halign=Gtk.Align.START);info.append(self.preview_badge)
        self.selected_title=label("Choose a wallpaper","title-2",wrap=True,max_width_chars=28)
        self.selected_meta=label("Your current wallpaper setup stays in place.","studio-muted",wrap=True,max_width_chars=30)
        info.append(self.selected_title);info.append(self.selected_meta)
        self.hero_swatches=Gtk.Box(spacing=6);info.append(self.hero_swatches)
        choices=Gtk.Box(spacing=8)
        self.target_combo=Gtk.DropDown.new_from_strings([title for _,title in TARGETS])
        self.target_combo.set_selected([key for key,_ in TARGETS].index(self.config["target"]))
        self.target_combo.connect("notify::selected",lambda combo,_:self.save(target=TARGETS[combo.get_selected()][0]))
        self.target_combo.set_tooltip_text("Which wallpaper variant to change")
        self.fit_combo=Gtk.DropDown.new_from_strings([title for _,title in FITS])
        self.fit_combo.set_selected([key for key,_ in FITS].index(self.config["fit"]))
        self.fit_combo.connect("notify::selected",lambda combo,_:self.save(fit=FITS[combo.get_selected()][0]))
        choices.append(self.target_combo);choices.append(self.fit_combo);info.append(choices)
        self.apply_button=button("Apply wallpaper",callback=self.apply_wallpaper,classes=("suggested-action","studio-primary"))
        self.apply_button.set_sensitive(False);info.append(self.apply_button)
        self.apply_hint=label("Also applies your selected colour recipe","caption",wrap=True);info.append(self.apply_hint)
        hero.append(info);page.append(hero)
        toolbar=Gtk.Box(spacing=8);toolbar.add_css_class("studio-toolbar")
        self.search=Gtk.SearchEntry(hexpand=True)
        self.search.set_tooltip_text("Search wallpapers by name")
        self.search.connect("search-changed",self.search_changed);toolbar.append(self.search)
        favorites=Gtk.ToggleButton(icon_name="starred-symbolic",tooltip_text="Show favourites only")
        favorites.connect("toggled",lambda b:self.favorite_filter(b.get_active()));toolbar.append(favorites)
        sort=Gtk.DropDown.new_from_strings(["Name","Newest","Favourites first"])
        sort.set_selected(["name","newest","favorites"].index(self.config.get("sort","name")))
        sort.connect("notify::selected",lambda c,_:self.change_sort(["name","newest","favorites"][c.get_selected()]));toolbar.append(sort)
        toolbar.append(button(icon="folder-open-symbolic",callback=lambda *_:self.choose_folder(),classes=("flat",)))
        toolbar.append(button(icon="list-add-symbolic",callback=lambda *_:self.choose_file(),classes=("flat",)))
        page.append(toolbar)
        top=Gtk.Box(spacing=8);self.folder_label=label("", "caption",hexpand=True,ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.count_label=label("","caption");top.append(self.folder_label);top.append(self.count_label);page.append(top)
        self.grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=2,max_children_per_line=3,
            row_spacing=14,column_spacing=14)
        page.append(self.grid)
        self.empty=Adw.StatusPage(icon_name="folder-pictures-symbolic",title="No pictures here yet",description="Choose another folder or drop an image onto this window.")
        self.empty.add_css_class("compact");page.append(self.empty)
        self.load_more=button("Show more",callback=lambda *_:self.more(),classes=("pill",));page.append(self.load_more)
        return page

    def video_page(self):
        page=self.page("Video wallpaper","Play a real video behind your desktop icons. GNOME keeps a still frame as a fallback, and the video engine starts again at login.")
        hero=Gtk.Box(spacing=20);hero.add_css_class("studio-hero")
        self.video_hero=Gtk.Picture(can_shrink=True,keep_aspect_ratio=True,width_request=430,height_request=248)
        self.video_hero.add_css_class("studio-photo");self.video_hero.set_overflow(Gtk.Overflow.HIDDEN);hero.append(self.video_hero)
        info=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=11,hexpand=True,valign=Gtk.Align.CENTER)
        self.video_status_label=label("Checking…","studio-pill",halign=Gtk.Align.START)
        info.append(self.video_status_label)
        info.append(label("Desktop video","title-2"))
        self.video_path_label=label("No video selected","studio-muted",wrap=True,max_width_chars=34)
        info.append(self.video_path_label)
        self.video_detail_label=label("","caption",wrap=True,max_width_chars=42)
        info.append(self.video_detail_label)
        self.video_selected=video.load().get("path") or None
        actions=Gtk.Box(spacing=8)
        actions.append(button("Choose video…",callback=lambda *_:self.choose_video(),classes=("pill",)))
        self.video_play_button=button("Set video wallpaper",callback=lambda *_:self.apply_video(),classes=("suggested-action","studio-primary"))
        actions.append(self.video_play_button)
        self.video_stop_button=button("Stop",callback=lambda *_:self.stop_video(),classes=("destructive-action",))
        actions.append(self.video_stop_button)
        info.append(actions)
        hero.append(info);page.append(hero)

        options=Adw.PreferencesGroup(title="Playback",description="Changes apply to the running video immediately.")
        mute_row=Adw.ActionRow(title="Mute the video",subtitle="Recommended for a desktop wallpaper")
        self.video_mute_switch=Gtk.Switch(active=bool(video.load().get("mute",True)),valign=Gtk.Align.CENTER)
        self.video_mute_switch.connect("notify::active",lambda b,_:self.save_video_option(mute=b.get_active()))
        mute_row.add_suffix(self.video_mute_switch);mute_row.set_activatable_widget(self.video_mute_switch);options.add(mute_row)
        fit_row=Adw.ComboRow(title="Scaling",subtitle="Cover crops to fill the screen; contain shows the whole frame")
        self.video_fit_combo=Gtk.DropDown.new_from_strings(["Cover / crop","Contain / fit"])
        self.video_fit_combo.set_selected(0 if video.load().get("fit","cover")=="cover" else 1)
        self.video_fit_combo.connect("notify::selected",lambda c,_:self.save_video_option(fit="cover" if c.get_selected()==0 else "contain"))
        fit_row.add_suffix(self.video_fit_combo);options.add(fit_row)
        monitor_row=Adw.ActionRow(title="Monitor",subtitle="0 is the primary monitor")
        self.video_monitor_spin=Gtk.SpinButton.new_with_range(0,7,1)
        self.video_monitor_spin.set_value(int(video.load().get("monitor",0)))
        self.video_monitor_spin.connect("value-changed",lambda s:self.save_video_option(monitor=int(s.get_value())))
        monitor_row.add_suffix(self.video_monitor_spin);options.add(monitor_row)
        page.append(options)

        support=Adw.PreferencesGroup(title="Session support")
        self.video_extension_label=label("","caption",wrap=True)
        self.video_extension_row=Adw.ActionRow(title="GNOME Shell extension",subtitle="Needed on Wayland only")
        self.video_extension_row.add_suffix(self.video_extension_label)
        self.video_extension_button=button("Install / enable",callback=lambda *_:self.install_video_extension(),classes=("flat",))
        self.video_extension_row.add_suffix(self.video_extension_button)
        support.add(self.video_extension_row)
        support.add(Adw.ActionRow(title="Autostart",subtitle="The engine restores the video when you log in"))
        page.append(support)
        self.video_timer=GLib.timeout_add_seconds(2,self.refresh_video_status)
        self.refresh_video_status()
        self.load_video_preview(self.video_selected)
        return page

    def refresh_video_status(self):
        if not self.alive:return False
        info=video.status()
        if info["running"]:
            self.video_status_label.set_text("PLAYING")
            self.video_detail_label.set_text(f"PID {info['renderer_pid']} · {info['session']} · {info['fit']} · {'muted' if info['mute'] else 'audio on'}")
        elif info["enabled"]:
            self.video_status_label.set_text("WAITING FOR RENDERER")
            self.video_detail_label.set_text(info.get("error") or f"Session: {info['session']} · see {info['log']}")
        else:
            self.video_status_label.set_text("OFF")
            self.video_detail_label.set_text("Choose a video and press Set video wallpaper.")
        path=info.get("path") or self.video_selected or ""
        self.video_path_label.set_text(Path(path).name if path else "No video selected")
        self.video_play_button.set_sensitive(bool(self.video_selected))
        self.video_stop_button.set_sensitive(info["running"] or info["enabled"])
        extension=info["extension"]
        if info["session"]=="wayland":
            state="enabled" if extension["enabled"] else "installed, not enabled" if extension["installed"] else "not installed"
            self.video_extension_label.set_text(state)
            self.video_extension_button.set_visible(True)
        else:
            self.video_extension_label.set_text("not needed on X11")
            self.video_extension_button.set_visible(False)
        return True

    def save_video_option(self,**changes):
        video.save(**changes)
        info=video.status()
        if info["enabled"] and not info["running"]:video.start(wait=False)

    def choose_video(self):
        dialog=Gtk.FileChooserNative(title="Choose a video wallpaper",transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        formats=Gtk.FileFilter(name="Videos")
        for ext in core.VIDEO_EXT:formats.add_suffix(ext[1:])
        dialog.add_filter(formats)
        videos=Path.home()/"Videos"
        if videos.is_dir():dialog.set_current_folder(Gio.File.new_for_path(str(videos)))
        def response(d,result):
            if result==Gtk.ResponseType.ACCEPT:
                self.video_selected=d.get_file().get_path()
                self.select(self.video_selected)
                self.load_video_preview(self.video_selected)
            d.destroy();self.dialog=None
        dialog.connect("response",response);self.dialog=dialog;dialog.show()

    def load_video_preview(self,path):
        if not path:return
        def work():
            try:
                still=core.still_of(path);pb=cover(still,860,496);error=None
            except Exception as exc:pb,error=None,str(exc)
            def done():
                if self.alive and pb is not None and self.video_selected==path:self.video_hero.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
                elif error and self.alive and self.video_selected==path:self.video_detail_label.set_text(error)
                return False
            GLib.idle_add(done)
        self.preview_pool.submit(work)

    def apply_video(self):
        if not self.video_selected:self.toast("Choose a video first");return
        self.run(lambda:core.set_wallpaper(self.video_selected),"Video wallpaper applied")

    def stop_video(self):
        self.run(video.stop,"Video wallpaper stopped")

    def install_video_extension(self):
        self.run(lambda:(video.install_extension(),video.enable_extension()),"Video extension installed. Log out once on Wayland if it is not active yet.")

    def appearance_page(self):
        page=self.page("Change the whole look","Pixel windows, retro desktops and custom colours. Choose a look, preview it, then apply.")
        controls=Gtk.Box(spacing=8)
        self.mode_buttons={};first=None
        group=Gtk.Box(css_classes=["linked"])
        for mode,title in (("light","Light"),("dark","Dark"),("auto","Auto")):
            item=Gtk.ToggleButton(label=title,group=first,active=self.config["mode"]==mode)
            first=first or item;item.connect("toggled",lambda b,m=mode:self.mode_changed(b,m))
            group.append(item);self.mode_buttons[mode]=item
        controls.append(group);controls.append(Gtk.Box(hexpand=True))
        controls.append(button("Live window preview",callback=lambda *_:self.live_sample()))
        self.style_button=button("Apply style only",callback=lambda *_:self.apply_style(),classes=("suggested-action","studio-primary"))
        controls.append(self.style_button);page.append(controls)
        sections=Gtk.Box(spacing=8)
        for title,callback in [('Themes',lambda:self.jump_to(self.appearance_themes)),('Window design',lambda:self.jump_to(self.window_design_group)),('My own theme',self.edit_own_theme),('Saved looks',lambda:self.jump_to(self.saved_looks)),('Fine-tune',lambda:self.jump_to(self.tuning_group))]:
            sections.append(button(title,callback=lambda _b,cb=callback:cb(),classes=('pill',)))
        page.append(sections)
        self.style_scene=Gtk.DrawingArea(content_height=236,hexpand=True)
        self.style_scene.add_css_class("studio-preview");self.style_scene.set_overflow(Gtk.Overflow.HIDDEN)
        self.style_scene.set_draw_func(self.draw_scene);page.append(self.style_scene)
        self.contrast_label=label("","caption");page.append(self.contrast_label)
        grid=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=2,max_children_per_line=2,row_spacing=10,column_spacing=10)
        self.appearance_themes=grid
        for key,(title,description,light,dark) in recipes.PRESETS.items():
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7,hexpand=True)
            row=Gtk.Box(spacing=9)
            for colour in (dark[0],dark[2],dark[5]) if dark else ("#263247","#384967","#8AB4F8"):
                row.append(swatch(colour,20))
            row.append(label(title,"heading",hexpand=True));content.append(row)
            content.append(label(description,"caption",wrap=True))
            item=Gtk.Button(child=content);item.add_css_class("studio-recipe")
            item.connect("clicked",lambda _b,p=key:self.select_recipe(p));grid.append(item);self.recipe_buttons[key]=item
        page.append(grid)
        self.window_style_options(page)
        options=Adw.PreferencesGroup(title="Fine-tune your recipe",description="These controls edit the preview. Apply style to update other apps.")
        self.tuning_group=options
        accent_row=Adw.ActionRow(title="Accent colour",subtitle="Leave empty to use the selected recipe")
        self.accent_entry=Gtk.Entry(placeholder_text="#89B4FA",text=self.config.get("accent",""),width_chars=10,max_length=7,valign=Gtk.Align.CENTER)
        self.accent_entry.connect("changed",self.accent_changed);accent_row.add_suffix(self.accent_entry)
        accent_row.add_suffix(button(icon="color-select-symbolic",callback=lambda *_:self.choose_accent(),classes=("flat",)))
        options.add(accent_row)
        tint_row=Adw.ActionRow(title="Wallpaper tint",subtitle="How much colour to keep in the Wallpaper recipe's surfaces")
        self.tint=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,1,.05);self.tint.set_value(float(self.config["tint"]))
        self.tint.set_size_request(180,-1);self.tint.set_draw_value(False);self.tint.set_valign(Gtk.Align.CENTER)
        self.tint.connect("value-changed",lambda scale:self.save(tint=round(scale.get_value(),2)));tint_row.add_suffix(self.tint);options.add(tint_row)
        shape=Adw.ComboRow(title="Corner style",model=Gtk.StringList.new(["Soft","Crisp","Square"]));self.shape_combo=shape
        shape.set_selected(["soft","crisp","square"].index(self.config["shape"]))
        shape.connect("notify::selected",lambda c,_:self.save(shape=["soft","crisp","square"][c.get_selected()]));options.add(shape)
        options.add(self.switch_row("Stronger text contrast","Raise main text to a 7:1 contrast target","high_contrast"))
        options.add(self.switch_row("Subtle glass","Light transparency; menus and reading surfaces stay mostly solid","glass"))
        options.add(self.switch_row("GNOME Terminal palette","Use a Plus profile for new Terminal windows","terminal"))
        page.append(options)
        share=Gtk.Box(spacing=8)
        share.append(button("Export recipe…",callback=lambda *_:self.theme_file(False),classes=("pill",)))
        share.append(button("Import recipe…",callback=lambda *_:self.theme_file(True),classes=("pill",)))
        page.append(share);return page

    def history_page(self):
        page=self.page("Recent choices","Your last 30 wallpaper choices, with one-click undo.")
        actions=Gtk.Box(spacing=8);actions.append(button("Undo last wallpaper",callback=lambda *_:self.run(core.undo_wallpaper,"Previous wallpaper restored"),classes=("pill",)))
        actions.append(button("Random from folder",callback=lambda *_:self.run(core.next_wallpaper,"Another wallpaper applied"),classes=("pill",)))
        page.append(actions);self.history_group=Adw.PreferencesGroup();page.append(self.history_group)
        self.history_empty=label("Your choices will appear here after applying a wallpaper.","dim-label",wrap=True)
        page.append(self.history_empty);self.history_rows=[];return page

    def preferences_page(self):
        page=self.page("Preferences","Keep the useful bits automatic, and the rest under your control.")
        behavior=Adw.PreferencesGroup(title="Wallpaper behaviour")
        behavior.add(self.switch_row("Match colours when applying a wallpaper","Switch this off to change pictures without changing your theme","auto_style"))
        rotation=Adw.ComboRow(title="Rotate wallpapers",subtitle="Choose a different image from your folder; pauses while GNOME is locked",model=Gtk.StringList.new([title for _,title in ROTATIONS]))
        hours=[h for h,_ in ROTATIONS];rotation.set_selected(hours.index(self.config["rotate_hours"]) if self.config["rotate_hours"] in hours else 0)
        rotation.connect("notify::selected",lambda c,_:self.save(rotate_hours=hours[c.get_selected()]));behavior.add(rotation)
        folder=Adw.ActionRow(title="Wallpaper folder",subtitle=str(self.config["folder"]).replace(core.HOME,"~",1))
        folder.add_suffix(button("Choose…",callback=lambda *_:self.choose_folder(),classes=("flat",)));behavior.add(folder);page.append(behavior)
        native=Adw.PreferencesGroup(title="Your existing GNOME setup")
        self.native_details=Adw.ActionRow(title="Native wallpaper",subtitle="Checking…")
        self.native_details.add_suffix(button("Check",callback=lambda *_:self.check_backend(),classes=("flat",)));native.add(self.native_details)
        setup=Adw.ActionRow(title="Set up this account",subtitle="Reuses your existing profile; new accounts may need one normal logout/login")
        setup.add_suffix(button("Set up",callback=lambda *_:self.run(lambda:NativeBackend().ensure_setup(),"Native setup checked"),classes=("flat",)))
        native.add(setup);page.append(native)
        presentation=Adw.PreferencesGroup(title="Keep awake and activity guard")
        awake=Adw.ActionRow(title="Session controls",subtitle="Keep the screen awake or request a lock on the next input")
        awake.add_suffix(button("Open",callback=lambda *_:self.set_page('session')))
        presentation.add(awake);page.append(presentation)
        advanced=Adw.PreferencesGroup(title="Storage and advanced")
        cache=Adw.ActionRow(title="Clear preview cache",subtitle="Keeps your applied wallpaper copies and saved choices")
        cache.add_suffix(button("Clear",callback=lambda *_:self.run(core.clear_preview_cache,"Preview cache cleared"),classes=("flat",)));advanced.add(cache)
        advanced.add(self.switch_row("Run local colour hooks","Run executable files you place in your own hooks folder after applying a style","run_hooks"))
        pause=Adw.ActionRow(title="Pause automation",subtitle="Stops rotation and colour following; keeps your native wallpaper")
        pause.add_suffix(button("Pause",callback=lambda *_:self.run(core.stop,"Automation paused"),classes=("flat",)));advanced.add(pause)
        if core.original_app_present():
            old=Adw.ActionRow(title="Original Wallpaper Studio detected",subtitle="Its desktop window can cover GNOME's native wallpaper. Stop it from the original app before using Plus.")
            advanced.add(old)
        page.append(advanced)
        restore=Adw.PreferencesGroup(title="Restore")
        row=Adw.ActionRow(title="Restore changes made by Plus",subtitle="Your working wallpaper profile and GNOME login setup are kept")
        row.add_suffix(button("Restore…",callback=lambda *_:self.ask_restore("all"),classes=("destructive-action",)));restore.add(row);page.append(restore)
        return page

    def switch_row(self,title,subtitle,key):
        row=Adw.ActionRow(title=title,subtitle=subtitle)
        item=Gtk.Switch(active=bool(self.config[key]),valign=Gtk.Align.CENTER)
        self.switches[key]=item
        item.connect("notify::active",lambda b,_:self.save(**{key:b.get_active()}));row.add_suffix(item);row.set_activatable_widget(item)
        return row

    def install_actions(self):
        handlers={"open":lambda *_:self.choose_file(),"undo":lambda *_:self.run(core.undo_wallpaper,"Previous wallpaper restored"),
            "apply":self.apply_wallpaper,"import":lambda *_:self.theme_file(True),"export":lambda *_:self.theme_file(False),
            "restore-style":lambda *_:self.ask_restore("style"),"restore-wallpaper":lambda *_:self.ask_restore("wallpaper"),
            "restore-all":lambda *_:self.ask_restore("all"),"about":self.about,"search":lambda *_:self.focus_search(),
            "preferences":lambda *_:self.set_page("preferences")}
        for name,handler in handlers.items():
            action=Gio.SimpleAction.new(name,None);action.connect("activate",handler);self.add_action(action)
        for action,keys in {"win.open":["<Primary>o"],"win.search":["<Primary>f"],"win.apply":["<Primary>Return"],
                            "win.undo":["<Primary>z"],"win.preferences":["<Primary>comma"]}.items():self.get_application().set_accels_for_action(action,keys)

    def focus_search(self):self.set_page("library");self.search.grab_focus()

    def refresh_palette(self):
        if not self.alive:return False
        self.palette=recipes.resolve(self.base_palette,self.config);mode=core.effective_mode(self.config);p=self.palette[mode]
        manager=Adw.StyleManager.get_default();manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK if mode=="dark" else Adw.ColorScheme.FORCE_LIGHT)
        provider=self.get_application().preview_css
        provider.load_from_data(recipes.gtk_css(p,mode=="dark",{**self.config,"glass":False}).encode())
        for key,item in self.recipe_buttons.items():
            (item.add_css_class if key==self.config["preset"] else item.remove_css_class)("selected")
        while child:=self.hero_swatches.get_first_child():self.hero_swatches.remove(child)
        for key in ("paper","paper2","sheet","muted","ink","accent"):self.hero_swatches.append(swatch(p[key],23))
        values=recipes.metrics(p)
        self.contrast_label.set_text(f"Text {values['text']:.1f}:1   ·   Secondary {values['secondary']:.1f}:1   ·   Accent label {values['accent']:.1f}:1")
        self.style_scene.queue_draw()
        self.update_custom_controls()
        if hasattr(self,'widget_canvas'):self.widget_canvas.queue_draw()
        self.apply_hint.set_text("Plays the video on your desktop" if self.selected and core.is_video(self.selected)
            else "Also applies your selected colour recipe" if self.config["auto_style"] else "Changes only the wallpaper")
        return False

    def save(self,**changes):
        if self.syncing:return
        try:self.config=core.save_config(**changes)
        except (ValueError,OSError) as exc:self.toast(str(exc));return
        if self.preview_timer:GLib.source_remove(self.preview_timer)
        def update():
            self.preview_timer=0
            return self.refresh_palette()
        self.preview_timer=GLib.timeout_add(100,update)

    def select_recipe(self,key):self.save(preset=key)
    def sync_controls(self):
        self.syncing=True
        try:
            self.accent_entry.set_text(self.config["accent"]);self.tint.set_value(self.config["tint"])
            self.shape_combo.set_selected(["soft","crisp","square"].index(self.config["shape"]))
            self.skin_combo.set_selected(list(skins.SKINS).index(self.config['skin']));self.custom_mode=None
            self.mode_buttons[self.config["mode"]].set_active(True)
            for key,widget in self.switches.items():widget.set_active(self.config[key])
        finally:self.syncing=False
        self.refresh_palette()
    def mode_changed(self,item,mode):
        if item.get_active() and self.config["mode"]!=mode:self.save(mode=mode)
    def accent_changed(self,entry):
        value=entry.get_text().strip()
        valid=not value or recipes.valid_hex(value)
        (entry.remove_css_class if valid else entry.add_css_class)("error")
        if valid:self.save(accent=value.upper())

    def select(self,path):
        if not path or not self.alive:return False
        path=os.path.realpath(os.path.expanduser(path))
        if os.path.isdir(path):self.save(folder=path);self.page_limit=48;self.load_library();return True
        if not os.path.isfile(path) or not core.is_wallpaper(path):self.toast("Choose an existing picture or video");return False
        self.selected=path;self.selection_generation+=1;generation=self.selection_generation
        if core.is_video(path):
            self.video_selected=path
            if hasattr(self,"video_path_label"):self.video_path_label.set_text(Path(path).name)
        self.selected_title.set_text("Current wallpaper" if len(Path(path).stem)==64 else Path(path).stem.replace("_"," "))
        self.selected_meta.set_text("Loading preview…");self.apply_button.set_sensitive(False);self.update_selected()
        if self.preview_future:self.preview_future.cancel()
        def work():
            try:
                still=core.still_of(path);pb=cover(still,860,496);base=core.palette.from_image(still)
                _,w,h=GdkPixbuf.Pixbuf.get_file_info(still);error=None
            except Exception as exc:pb=base=None;w=h=0;error=str(exc)
            GLib.idle_add(self.preview_done,generation,pb,base,w,h,error)
        self.preview_future=self.preview_pool.submit(work);return True

    def preview_done(self,generation,pb,base,w,h,error):
        if not self.alive or generation!=self.selection_generation:return False
        if error:self.selected_meta.set_text(error);self.toast(error);return False
        self.hero.set_paintable(Gdk.Texture.new_for_pixbuf(pb));self.base_palette=base
        if core.is_video(self.selected):
            kind="Video"
            self.apply_button.set_label("Set video wallpaper")
            self.video_selected=self.selected
            if hasattr(self,"video_path_label"):
                self.video_path_label.set_text(Path(self.selected).name)
                self.load_video_preview(self.selected)
        else:
            kind="Picture"
            self.apply_button.set_label("Apply wallpaper")
        self.selected_meta.set_text(f"{kind} · {w:,} × {h:,}")
        self.apply_button.set_sensitive(not self.busy);self.refresh_palette();return False

    def update_selected(self):
        current=core.load_state().get("source") or core.load_state().get("wallpaper")
        self.preview_badge.set_text("CURRENT" if self.selected==current else "PREVIEW")
        for path,item in self.cards.items():
            (item.add_css_class if path==self.selected else item.remove_css_class)("selected")
            (item.add_css_class if path==current else item.remove_css_class)("current")

    def search_changed(self,entry):
        self.query=entry.get_text()
        if self.filter_timer:GLib.source_remove(self.filter_timer)
        self.filter_timer=GLib.timeout_add(160,self.load_library)
    def favorite_filter(self,value):self.only_favorites=value;self.load_library()
    def change_sort(self,value):self.save(sort=value);self.load_library()
    def more(self):self.page_limit+=48;self.load_library()

    def load_library(self):
        if not self.alive:return False
        self.filter_timer=0;self.library_generation+=1;generation=self.library_generation
        for future in self.futures:future.cancel()
        self.futures=[]
        while child:=self.grid.get_first_child():self.grid.remove(child)
        self.cards={}
        files=core.filtered_wallpapers(self.query,self.only_favorites,self.kind,self.config.get("sort","name"))
        self.count_label.set_text(f"{len(files)} wallpapers")
        self.folder_label.set_text("Included collection" if self.config["folder"]==core.BUILT_IN else self.config["folder"].replace(core.HOME,"~",1))
        self.empty.set_visible(not files);self.grid.set_visible(bool(files));self.load_more.set_visible(len(files)>self.page_limit)
        for path in files[:self.page_limit]:
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            picture=CoverPicture()
            overlay=Gtk.Overlay(child=picture)
            if core.is_video(path):overlay.add_overlay(label("VIDEO FRAME","studio-badge",halign=Gtk.Align.START,valign=Gtk.Align.END))
            favorite=Gtk.ToggleButton(icon_name="starred-symbolic" if path in self.config["favorites"] else "non-starred-symbolic",
                active=path in self.config["favorites"],halign=Gtk.Align.END,valign=Gtk.Align.START,tooltip_text="Favourite")
            favorite.add_css_class("studio-favorite")
            favorite.connect("toggled",lambda item,p=path:self.favorite_clicked(item,p));overlay.add_overlay(favorite)
            content.append(overlay)
            content.append(label(Path(path).stem.replace("_"," "),"studio-thumb-label",ellipsize=Pango.EllipsizeMode.END,max_width_chars=24))
            item=Gtk.Button(child=content,tooltip_text=Path(path).name);item.add_css_class("studio-thumb");item.set_overflow(Gtk.Overflow.HIDDEN)
            item.connect("clicked",lambda _b,p=path:self.select(p));self.grid.append(item);self.cards[path]=item
            self.futures.append(self.pool.submit(self.load_thumb,path,picture,generation))
        self.update_selected();return False

    def load_thumb(self,path,picture,generation=None):
        try:pb=thumbnail(path)
        except Exception:pb=None
        def done():
            if self.alive and pb is not None and (generation is None or generation==self.library_generation):
                if isinstance(picture,CoverPicture):picture.set_pixbuf(pb)
                else:picture.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
            return False
        GLib.idle_add(done)

    def favorite_clicked(self,item,path):
        values=core.toggle_favorite(path);self.config["favorites"]=values
        item.set_icon_name("starred-symbolic" if path in values else "non-starred-symbolic")

    def load_history(self):
        for row in self.history_rows:self.history_group.remove(row)
        self.history_rows=[];entries=list(reversed(core.history()))
        self.history_empty.set_visible(not entries)
        for index,entry in enumerate(entries):
            path=(entry.get("source") if entry.get("video") else entry.get("wallpaper")) or entry.get("source")
            if not path:continue
            title=Path(entry.get("source") or path).stem
            if len(title)==64:title="Saved wallpaper"
            row=Adw.ActionRow(title=title,subtitle="Most recent" if index==0 else f"Earlier choice · {entry.get('target','both')}")
            picture=Gtk.Picture(can_shrink=True,width_request=84,height_request=52,keep_aspect_ratio=True)
            row.add_prefix(picture)
            row.add_suffix(button("Use",callback=lambda _b,p=path:self.run(lambda:core.set_wallpaper(p),"Wallpaper restored"),classes=("flat",)))
            self.history_group.add(row);self.history_rows.append(row);self.pool.submit(self.load_thumb,path,picture)

    def apply_wallpaper(self,*_):
        if not self.selected:return
        path=self.selected
        self.run(lambda:core.set_wallpaper(path),"Video wallpaper applied" if core.is_video(path) else "Wallpaper applied with native GNOME")

    def apply_style(self):
        path=self.selected
        self.run(lambda:core.apply_theme(path),"Desktop colours updated")

    def run(self,job,message=None):
        if self.busy:return
        self.busy=True;self.spinner.start();self.apply_button.set_sensitive(False);self.style_button.set_sensitive(False)
        def worker():
            try:result,error=job(),None
            except Exception as exc:result,error=None,str(exc)
            GLib.idle_add(done,result,error)
        def done(result,error):
            if not self.alive:return False
            self.busy=False;self.spinner.stop();self.apply_button.set_sensitive(bool(self.selected));self.style_button.set_sensitive(True)
            if error:self.toast(error)
            elif getattr(result,"warning",""):self.toast(result.warning)
            elif hasattr(result,"loaded") and result.loaded is False:self.toast("Saved. Log out normally once and sign back in to load this account's native setup.")
            elif message:self.toast(message)
            self.update_selected();self.load_history();self.check_backend()
            if hasattr(self,"video_status_label"):self.refresh_video_status()
            return False
        threading.Thread(target=worker,daemon=True).start()

    def check_backend(self):
        def work():
            try:status=NativeBackend().status();error=None
            except Exception as exc:status=None;error=str(exc)
            def done():
                if not self.alive:return False
                text=status.summary if status else error
                self.setup_label.set_text(text)
                if hasattr(self,"native_details"):self.native_details.set_subtitle(text)
                return False
            GLib.idle_add(done)
        self.pool.submit(work)

    def state_event(self,_monitor,file,*_):
        if file.get_basename()!="state.json":return
        if self.pending_monitor:GLib.source_remove(self.pending_monitor)
        self.pending_monitor=GLib.timeout_add(200,self.state_changed)

    def state_changed(self):
        self.pending_monitor=0
        if self.alive:self.update_selected();self.load_history()
        return False

    def toast(self,message):
        if self.alive:self.toasts.add_toast(Adw.Toast(title=str(message)[:280],timeout=6))

    def choose_file(self):self.file_dialog(False,lambda path:self.select(path))
    def choose_folder(self):
        def selected(path):
            self.save(folder=path);self.page_limit=48;self.load_library()
        self.file_dialog(True,selected)

    def file_dialog(self,folder,callback):
        dialog=Gtk.FileChooserNative(title="Choose a wallpaper folder" if folder else "Choose a picture or video frame",transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
        if not folder:
            formats=Gtk.FileFilter(name="Pictures and videos")
            for ext in core.IMAGE_EXT+core.VIDEO_EXT:formats.add_suffix(ext[1:])
            dialog.add_filter(formats)
        if os.path.isdir(self.config["folder"]):dialog.set_current_folder(Gio.File.new_for_path(self.config["folder"]))
        def response(d,result):
            if result==Gtk.ResponseType.ACCEPT:callback(d.get_file().get_path())
            d.destroy();self.dialog=None
        dialog.connect("response",response);self.dialog=dialog;dialog.show()

    def choose_accent(self):
        dialog=Gtk.ColorChooserDialog(title="Choose an accent",transient_for=self,modal=True,use_alpha=False)
        rgba=Gdk.RGBA();rgba.parse(self.config.get("accent") or self.palette[core.effective_mode(self.config)]["accent"]);dialog.set_rgba(rgba)
        def response(d,result):
            if result==Gtk.ResponseType.OK:
                value=d.get_rgba();self.accent_entry.set_text("#"+"".join(f"{round(c*255):02X}" for c in (value.red,value.green,value.blue)))
            d.destroy()
        dialog.connect("response",response);dialog.present()

    def theme_file(self,importing):
        dialog=Gtk.FileChooserNative(title="Import a theme" if importing else "Export your theme",transient_for=self,
            action=Gtk.FileChooserAction.OPEN if importing else Gtk.FileChooserAction.SAVE)
        if not importing:dialog.set_current_name("my-studio-theme.json")
        filefilter=Gtk.FileFilter(name="Theme JSON");filefilter.add_pattern("*.json");dialog.add_filter(filefilter)
        def response(d,result):
            if result==Gtk.ResponseType.ACCEPT:
                try:
                    path=d.get_file().get_path()
                    if importing:
                        self.config=core.import_recipe(path);self.sync_controls();self.toast("Recipe loaded for preview")
                    else:core.export_recipe(path);self.toast("Theme exported without private image paths")
                except Exception as exc:self.toast(str(exc))
            d.destroy();self.dialog=None
        dialog.connect("response",response);self.dialog=dialog;dialog.show()

    def ask_restore(self,scope):
        description={"all":"Restore wallpapers, window styles, desktop controls and Terminal defaults, and hide Plus widgets?",
            "style":"Restore window styles, theme icons/cursors and Terminal defaults? Your wallpaper will stay as it is.",
            "wallpaper":"Restore your previous native wallpaper settings? Your colour recipe stays as it is."}[scope]
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,text="Restore previous settings?",secondary_text=description)
        dialog.add_button("Cancel",Gtk.ResponseType.CANCEL);dialog.add_button("Restore",Gtk.ResponseType.ACCEPT)
        def response(d,result):
            d.destroy()
            if result==Gtk.ResponseType.ACCEPT:self.run(lambda:core.restore(scope),"Previous settings restored")
        dialog.connect("response",response);dialog.present()

    def about(self,*_):
        Gtk.AboutDialog(transient_for=self,modal=True,program_name="Wallpaper Studio Video",version="2.2",
            logo_icon_name=APP_ID,comments="Your native wallpaper setup, full window designs and desktop widgets.",
            authors=["Adil Asselman (yuxev) — original Wallpaper Studio","Wallpaper Studio Video contributors"],
            website="https://github.com/yuxev/wallpaper-studio",license_type=Gtk.License.MIT_X11).present()

    def draw_scene(self,_area,cr,w,h):
        p=self.palette[core.effective_mode(self.config)]
        skin=skins.selected(self.config);pixel=skins.pixel_style(self.config)
        def colour(value):
            rgba=Gdk.RGBA();rgba.parse(value);cr.set_source_rgb(rgba.red,rgba.green,rgba.blue)
        def rect(x,y,width,height,c):colour(c);cr.rectangle(x,y,width,height);cr.fill()
        def text(x,y,string,c,size=12,mono=False):
            colour(c);cr.select_font_face("Monospace" if mono else "Silkscreen" if pixel and self.config['pixel_font'] else "Sans",0,0);cr.set_font_size(size);cr.move_to(x,y);cr.show_text(string)
        rect(0,0,w,h,p["paper2"])
        left=18;top=18;width=w*.57;height=h-36
        rect(left,top,width,height,p["paper"]);rect(left,top,width,32,'#894526' if skin=='kingdom' else p["accent"] if skin=='classic' else p["sheet"])
        if skin=='kingdom':
            for row in range(4):
                rect(left,top+row*8,width,1,'#4B2B1E')
                for x0 in range(0,int(width),24):rect(left+x0+(12 if row%2 else 0),top+row*8,1,8,'#4B2B1E')
        for i,c in enumerate([p["accent"],p["muted"],p["ink"]]):
            colour(c);cr.arc(left+15+i*13,top+16,3,0,6.283);cr.fill()
        text(left+width*.42,top+21,"Preferences",p["muted"],11)
        rect(left,top+32,92,height-32,p["paper2"])
        for i,title in enumerate(["General","Appearance","Keyboard"]):
            if i==1:rect(left+8,top+67,76,25,p["accent"])
            text(left+16,top+54+i*29,title,p["on_accent"] if i==1 else p["muted"],10)
        text(left+112,top+60,"A calmer desktop",p["ink"],15)
        text(left+112,top+83,"Surfaces with room to breathe.",p["muted"],10)
        rect(left+112,top+104,width-132,29,p["sheet"])
        text(left+123,top+123,"Readable by default",p["ink"],10)
        rect(left+112,top+148,106,28,p["accent"]);text(left+129,top+166,"Apply style",p["on_accent"],10)
        x=w*.63;rect(x,top,w-x-18,height,p["paper"])
        text(x+16,top+24,"TERMINAL",p["muted"],9,True)
        text(x+16,top+56,"~ studio-plus",p["accent"],11,True)
        text(x+16,top+81,"theme: "+recipes.PRESETS[self.config["preset"]][0],p["ink"],10,True)
        text(x+16,top+106,"native background",p["ansi"][2],10,True)
        for i,c in enumerate(p["ansi"][1:7]):rect(x+16+i*22,top+136,17,23,c)

    def closed(self,*_):
        self.alive=False
        if self.monitor:self.monitor.cancel()
        for identifier in (self.pending_monitor,self.filter_timer,self.preview_timer,getattr(self,"video_timer",0)):
            if identifier:
                try:GLib.source_remove(identifier)
                except GLib.Error:pass
        self.pool.shutdown(wait=False,cancel_futures=True);self.preview_pool.shutdown(wait=False,cancel_futures=True)
        return False


class App(Adw.Application):
    def __init__(self,page="library"):
        super().__init__(application_id=APP_ID,flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.page=page
    def do_startup(self):
        assets.register_font()
        Adw.Application.do_startup(self)
        provider=Gtk.CssProvider();provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.preview_css=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.preview_css,Gtk.STYLE_PROVIDER_PRIORITY_USER+1)
        action=Gio.SimpleAction.new("quit",None);action.connect("activate",lambda *_:self.quit());self.add_action(action)
        core.start()
        if widget_control.load()['enabled']:
            def resume():
                try:widget_control.start()
                except (ValueError,OSError) as error:
                    message=str(error)
                    def show():
                        window=self.get_active_window()
                        if window:window.toast(message)
                        return False
                    GLib.idle_add(show)
            threading.Thread(target=resume,daemon=True).start()
    def do_activate(self):
        window=self.get_active_window() or Window(self,self.page);window.present()


def main(page="library"):
    GLib.set_prgname(APP_ID);GLib.set_application_name("Wallpaper Studio Video")
    return App(page).run(None)
