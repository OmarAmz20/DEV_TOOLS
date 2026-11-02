"""Widgets, desktop controls and the full window-style editor for GTK 4."""
import copy
from datetime import datetime
from pathlib import Path
from gi.repository import Gtk,Gdk,Adw,Gio,GLib,Pango
from . import core,recipes,skins,desktop,assets,widget_control as widgets


def text(value,css=None,**props):
    item=Gtk.Label(label=value,xalign=0,**props)
    if css:item.add_css_class(css)
    return item


def action(title,callback):
    button=Gtk.Button(label=title);button.connect('clicked',lambda *_:callback());return button


class CustomizationPages:
    def window_style_options(self,page):
        group=Adw.PreferencesGroup(title='Window design',description='Borders, titlebars, controls and menus change too. Some apps need reopening.')
        self.window_design_group=group
        names=list(skins.SKINS)
        self.skin_combo=Adw.ComboRow(title='Window structure',model=Gtk.StringList.new([skins.SKINS[k][0] for k in names]))
        self.skin_combo.set_selected(names.index(self.config['skin']))
        self.skin_combo.connect('notify::selected',lambda c,_:self.save(skin=names[c.get_selected()]));group.add(self.skin_combo)
        group.add(self.switch_row('Pixel typeface','Use bundled Silkscreen in pixel window styles','pixel_font'))
        group.add(self.switch_row('Match pixel icons and cursor','Pixel recipes also select the included icon and cursor packs','theme_extras'))
        row=self.switch_row('Style the GNOME panel','Requires the User Themes extension to be installed and enabled','panel_theme')
        row.set_sensitive(desktop.panel_available());group.add(row)
        row=Adw.ActionRow(title='Try real controls',subtitle='Open a sample window with entries, buttons, switches and menus')
        row.add_suffix(action('Open sample',self.live_sample));group.add(row);page.append(group)
        self.custom_group=Adw.PreferencesGroup(title='Build your own palette',description='Editing a role selects My Custom Theme. Text contrast is adjusted for readability.')
        self.custom_entries={};self.custom_mode=None
        titles={'paper':'Window background','paper2':'Sidebar / secondary surface','sheet':'Cards and controls','ink':'Main text','muted':'Secondary text','accent':'Accent'}
        for key in recipes.COLOUR_KEYS:
            row=Adw.ActionRow(title=titles[key]);entry=Gtk.Entry(width_chars=10,max_length=7,valign=Gtk.Align.CENTER)
            entry.connect('changed',lambda item,k=key:self.custom_colour(k,item))
            row.add_suffix(entry);self.custom_group.add(row);self.custom_entries[key]=entry
        page.append(self.custom_group)
        self.saved_looks=Adw.PreferencesGroup(title='Your saved looks',description='Keep multiple personal themes here, or export them to share.')
        self.saved_rows=[]
        row=Adw.ActionRow(title='Save the current look')
        self.look_name=Gtk.Entry(text=self.config['custom_name'],max_length=48,width_chars=16,valign=Gtk.Align.CENTER)
        row.add_suffix(self.look_name);row.add_suffix(action('Save',self.save_current_look));self.saved_looks.add(row)
        page.append(self.saved_looks);self.load_saved_looks()

    def jump_to(self,widget):
        scroller=widget.get_ancestor(Gtk.ScrolledWindow)
        if scroller:scroller.get_vadjustment().set_value(widget.get_allocation().y)
        return False

    def edit_own_theme(self):
        self.select_recipe('custom');self.refresh_palette()
        GLib.timeout_add(160,lambda:self.jump_to(self.custom_group) if self.alive else False)

    def save_current_look(self):
        try:
            core.save_recipe(self.look_name.get_text());self.config=core.load_config();self.load_saved_looks();self.toast('Look saved in your personal library')
        except (OSError,ValueError) as error:self.toast(str(error))

    def load_saved_looks(self):
        for row in self.saved_rows:self.saved_looks.remove(row)
        self.saved_rows=[]
        for name,path in core.saved_recipes():
            row=Adw.ActionRow(title=GLib.markup_escape_text(name))
            def load(p=path):
                try:self.config=core.import_recipe(p);self.sync_controls();self.look_name.set_text(self.config['custom_name']);self.toast('Saved look loaded for preview')
                except (OSError,ValueError) as error:self.toast(str(error))
            def remove(p=path):
                try:core.delete_recipe(p);self.load_saved_looks()
                except (OSError,ValueError) as error:self.toast(str(error))
            row.add_suffix(action('Load',load));row.add_suffix(action('Remove',remove));self.saved_looks.add(row);self.saved_rows.append(row)

    def custom_colour(self,key,entry):
        if self.syncing:return
        value=entry.get_text().strip();valid=recipes.valid_hex(value)
        (entry.remove_css_class if valid else entry.add_css_class)('error')
        if valid:
            mode=core.effective_mode(self.config);palette=dict(self.config['custom_'+mode]);palette[key]=value.upper()
            self.save(preset='custom',**{'custom_'+mode:palette})

    def update_custom_controls(self):
        if not hasattr(self,'custom_group'):return
        self.custom_group.set_visible(self.config['preset']=='custom')
        mode=core.effective_mode(self.config)
        if mode!=self.custom_mode:
            self.custom_mode=mode;values=dict(zip(recipes.COLOUR_KEYS,recipes.PRESETS['custom'][3 if mode=='dark' else 2]))
            values.update(self.config['custom_'+mode]);self.syncing=True
            try:
                for key,entry in self.custom_entries.items():entry.set_text(values[key])
            finally:self.syncing=False

    def live_sample(self):
        window=Gtk.Window(title='A real window in your preview style',transient_for=self,default_width=600,default_height=420)
        header=Gtk.HeaderBar();header.set_title_widget(text('Window design preview'));window.set_titlebar(header)
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18,margin_top=24,margin_bottom=24,margin_start=24,margin_end=24)
        root.append(text('Make your desktop yours','title-1'))
        root.append(text('These are real GTK controls. Close this sample to keep editing.',wrap=True))
        root.append(Gtk.Entry(placeholder_text='An entry in the selected window style'))
        row=Gtk.Box(spacing=12)
        primary=Gtk.Button(label='Primary action');primary.add_css_class('suggested-action');row.append(primary)
        row.append(Gtk.Button(label='A normal button'));row.append(Gtk.Switch(active=True,valign=Gtk.Align.CENTER));root.append(row)
        root.append(Gtk.ProgressBar(fraction=.68,show_text=True,text='68% complete'))
        root.append(Gtk.CheckButton(label='Pixel borders, menus and controls',active=True))
        root.append(Gtk.DropDown.new_from_strings(['Menu option one','Menu option two','Menu option three']))
        window.set_child(root);self.sample_window=window;window.present()

    def widgets_page(self):
        self.widget_draft=widgets.load();self.widget_selected='clock';self.widget_rects={}
        self.widget_common={}
        page=self.page('Your desktop, with extras','Drag widgets in the preview. Apply the layout, or move them directly in desktop edit mode.')
        controls=Gtk.Box(spacing=10)
        controls.append(action('Minimal clock',lambda:self.widget_preset('minimal')))
        controls.append(action('Study desk',lambda:self.widget_preset('study')))
        controls.append(action('Pixel HUD',lambda:self.widget_preset('hud')))
        controls.append(Gtk.Box(hexpand=True))
        button=action('Apply widgets',self.apply_widgets);button.add_css_class('suggested-action');controls.append(button);page.append(controls)
        self.widget_canvas=Gtk.DrawingArea(content_height=350,hexpand=True)
        self.widget_canvas.add_css_class('studio-preview');self.widget_canvas.set_draw_func(self.draw_widget_preview)
        drag=Gtk.GestureDrag();drag.connect('drag-begin',self.widget_drag_begin);drag.connect('drag-update',self.widget_drag_update)
        self.widget_canvas.add_controller(drag);page.append(self.widget_canvas)
        group=Adw.PreferencesGroup(title='Widget layout',description='Widgets use small desktop windows on X11. They never replace your native wallpaper.')
        row=Adw.ActionRow(title='Show desktop widgets');self.widgets_enabled=Gtk.Switch(active=self.widget_draft['enabled'],valign=Gtk.Align.CENTER)
        self.widgets_enabled.connect('notify::active',lambda item,_:self.widget_change('enabled',item.get_active()));row.add_suffix(self.widgets_enabled);group.add(row)
        row=Adw.ActionRow(title='Move widgets on the desktop',subtitle='Edit puts them above windows for dragging. Lock puts them back on the desktop.')
        row.add_suffix(action('Edit',lambda:self.desktop_widget_edit(True)));row.add_suffix(action('Lock',lambda:self.desktop_widget_edit(False)));group.add(row)
        displays=Gdk.Display.get_default().get_monitors();monitors=[f'Monitor {i+1}' for i in range(displays.get_n_items())] or ['Monitor 1']
        row=Adw.ComboRow(title='Monitor',model=Gtk.StringList.new(monitors));row.set_selected(min(len(monitors)-1,self.widget_draft['monitor']))
        self.widget_monitor=row
        row.connect('notify::selected',lambda c,_:self.widget_change('monitor',c.get_selected()));group.add(row)
        row=Adw.ComboRow(title='Window layer',subtitle='If a desktop-icons extension covers widgets, try Above desktop icons.',model=Gtk.StringList.new(['Desktop layer','Above desktop icons']))
        row.set_selected(0 if self.widget_draft['layer']=='desktop' else 1)
        self.widget_layer=row
        row.connect('notify::selected',lambda c,_:self.widget_change('layer',['desktop','above-icons'][c.get_selected()]));group.add(row)
        row=Adw.ActionRow(title='Widget opacity');opacity=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,55,100,1);opacity.set_value(self.widget_draft['opacity']*100);opacity.set_size_request(180,-1);opacity.set_valign(Gtk.Align.CENTER)
        opacity.connect('value-changed',lambda item:self.widget_change('opacity',item.get_value()/100));row.add_suffix(opacity);group.add(row);self.widget_opacity=opacity
        self.widget_toggles={}
        for kind,(title,description,_) in widgets.TYPES.items():
            row=Adw.ActionRow(title=title,subtitle=description)
            switch=Gtk.Switch(active=self.widget_draft['items'][kind]['enabled'],valign=Gtk.Align.CENTER)
            switch.connect('notify::active',lambda item,_,k=kind:self.widget_item(k,'enabled',item.get_active()))
            row.add_suffix(switch);row.add_suffix(action('Edit',lambda k=kind:self.widget_select(k)))
            group.add(row);self.widget_toggles[kind]=switch
        page.append(group)
        self.widget_editor=Adw.PreferencesGroup(title='Clock position',description='Positions are percentages of the space available on your chosen monitor.')
        self.widget_spins={}
        for key,title,low,high,step in [('x','Horizontal position',0,100,1),('y','Vertical position',0,100,1),('scale','Size',65,160,5)]:
            row=Adw.ActionRow(title=title);spin=Gtk.SpinButton.new_with_range(low,high,step);spin.set_valign(Gtk.Align.CENTER)
            spin.connect('value-changed',lambda item,k=key:self.widget_spin(k,item.get_value()/100));row.add_suffix(spin);self.widget_editor.add(row);self.widget_spins[key]=spin
        page.append(self.widget_editor)
        notes=Adw.PreferencesGroup(title='Sticky note',description='This text stays on your computer and is never included in theme exports.')
        self.note_buffer=Gtk.TextBuffer();self.note_buffer.set_text(self.widget_draft['note'])
        editor=Gtk.TextView(buffer=self.note_buffer,wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=100,left_margin=12,right_margin=12,top_margin=12,bottom_margin=12)
        notes.add(editor);page.append(notes)
        options=Adw.PreferencesGroup(title='Clock and focus timer')
        for key,title in [('hour24','24-hour clock'),('seconds','Show seconds')]:
            row=Adw.ActionRow(title=title);switch=Gtk.Switch(active=self.widget_draft[key],valign=Gtk.Align.CENTER)
            self.widget_common[key]=switch
            switch.connect('notify::active',lambda item,_,k=key:self.widget_change(k,item.get_active()));row.add_suffix(switch);options.add(row)
        row=Adw.ActionRow(title='Focus session minutes');minutes=Gtk.SpinButton.new_with_range(1,180,1);minutes.set_value(self.widget_draft['focus_minutes']);minutes.set_valign(Gtk.Align.CENTER)
        self.widget_minutes=minutes
        minutes.connect('value-changed',lambda item:self.widget_change('focus_minutes',item.get_value_as_int()));row.add_suffix(minutes);options.add(row);page.append(options)
        share=Gtk.Box(spacing=10);share.append(action('Export layout',lambda:self.widget_layout_file(False)));share.append(action('Import layout',lambda:self.widget_layout_file(True)));page.append(share)
        self.widget_select('clock');return page

    def widget_change(self,key,value):self.widget_draft[key]=value;self.widget_canvas.queue_draw()
    def widget_item(self,kind,key,value):self.widget_draft['items'][kind][key]=value;self.widget_canvas.queue_draw()
    def widget_spin(self,key,value):
        if not getattr(self,'widget_syncing',False):self.widget_item(self.widget_selected,key,value)

    def widget_select(self,kind):
        self.widget_selected=kind;self.widget_editor.set_title(widgets.TYPES[kind][0]+' position');self.widget_syncing=True
        try:
            for key,spin in self.widget_spins.items():spin.set_value(self.widget_draft['items'][kind][key]*100)
        finally:self.widget_syncing=False
        self.widget_canvas.queue_draw()

    def widget_preset(self,name):
        self.widget_draft=widgets.preset(name,self.widget_draft)
        self.widgets_enabled.set_active(self.widget_draft['enabled'])
        for kind,item in self.widget_toggles.items():item.set_active(self.widget_draft['items'][kind]['enabled'])
        self.widget_select(self.widget_selected);self.widget_canvas.queue_draw()

    def widget_snapshot(self):
        self.widget_draft['note']=self.note_buffer.get_text(self.note_buffer.get_start_iter(),self.note_buffer.get_end_iter(),True)[:4000]
        return copy.deepcopy(self.widget_draft)

    def widget_layout_file(self,importing):
        dialog=Gtk.FileChooserNative(title='Import widget layout' if importing else 'Export widget layout',transient_for=self,action=Gtk.FileChooserAction.OPEN if importing else Gtk.FileChooserAction.SAVE)
        if not importing:dialog.set_current_name('my-widget-layout.json')
        formats=Gtk.FileFilter(name='Widget layout JSON');formats.add_pattern('*.json');dialog.add_filter(formats)
        def response(item,result):
            if result==Gtk.ResponseType.ACCEPT:
                try:
                    path=item.get_file().get_path()
                    if importing:
                        self.widget_draft=widgets.import_layout(path,self.widget_snapshot())
                        for kind,switch in self.widget_toggles.items():switch.set_active(self.widget_draft['items'][kind]['enabled'])
                        for key,switch in self.widget_common.items():switch.set_active(self.widget_draft[key])
                        self.widget_minutes.set_value(self.widget_draft['focus_minutes']);self.widget_opacity.set_value(self.widget_draft['opacity']*100)
                        self.widget_layer.set_selected(0 if self.widget_draft['layer']=='desktop' else 1)
                        monitor=min(self.widget_draft['monitor'],self.widget_monitor.get_model().get_n_items()-1);self.widget_monitor.set_selected(monitor);self.widget_change('monitor',monitor)
                        self.widget_select(self.widget_selected);self.toast('Widget layout loaded for preview. Apply when ready.')
                    else:widgets.export_layout(path,self.widget_snapshot());self.toast('Layout exported without your private note')
                except (OSError,ValueError) as error:self.toast(str(error))
            item.destroy();self.dialog=None
        dialog.connect('response',response);self.dialog=dialog;dialog.show()

    def apply_widgets(self):
        draft=self.widget_snapshot();draft['editing']=False
        self.run(lambda:widgets.apply(draft),'Widget layout applied')

    def desktop_widget_edit(self,editing):
        draft=self.widget_snapshot()
        if not editing:
            latest=widgets.load()
            if latest['editing']:
                for kind,item in draft['items'].items():
                    for key in ('x','y'):item[key]=latest['items'][kind][key]
        draft.update(enabled=True,editing=editing);self.widget_draft=draft;self.widgets_enabled.set_active(True);self.widget_select(self.widget_selected)
        self.run(lambda:widgets.apply(draft),'Drag widget headings to move them. Click Lock when ready.' if editing else 'Widget positions locked')

    def draw_widget_preview(self,_area,cr,width,height):
        p=self.palette[core.effective_mode(self.config)];factor=min(width/1440,height/850);offset_x=(width-1440*factor)/2;offset_y=(height-850*factor)/2
        def colour(value):
            rgba=Gdk.RGBA();rgba.parse(value);cr.set_source_rgb(rgba.red,rgba.green,rgba.blue)
        def rect(x,y,w,h,c,alpha=1):
            rgba=Gdk.RGBA();rgba.parse(c);cr.set_source_rgba(rgba.red,rgba.green,rgba.blue,alpha);cr.rectangle(x,y,w,h);cr.fill()
        def caption(x,y,value,c,size=12):colour(c);cr.select_font_face('Sans',0,0);cr.set_font_size(size);cr.move_to(x,y);cr.show_text(value)
        rect(0,0,width,height,p['paper2']);cr.save();cr.translate(offset_x,offset_y);cr.scale(factor,factor)
        rect(0,0,1440,850,p['paper2']);rect(0,0,1440,28,p['sheet']);caption(22,20,'DESKTOP PREVIEW',p['muted'],11)
        self.widget_rects={}
        samples={'clock':datetime.now().strftime('%H:%M'),'calendar':datetime.now().strftime('%B %Y'),'stats':'CPU   /   RAM   /   DISK','notes':'Your sticky note','player':'Music & playback','timer':f"{self.widget_draft['focus_minutes']:02}:00",'shortcuts':'Home  ·  Browser  ·  Terminal'}
        for kind,item in self.widget_draft['items'].items():
            if not item['enabled']:continue
            x,y,w,h=widgets.geometry(item,kind,1440,850);self.widget_rects[kind]=(x*factor+offset_x,y*factor+offset_y,w*factor,h*factor)
            rect(x,y,w,h,p['paper'],self.widget_draft['opacity']);colour(p['accent'] if kind==self.widget_selected else p['muted']);cr.set_line_width(3 if skins.pixel_style(self.config) else 1);cr.rectangle(x,y,w,h);cr.stroke()
            caption(x+15,y+25,widgets.TYPES[kind][0].upper(),p['accent'],11)
            caption(x+15,y+65,samples[kind],p['ink'],25 if kind in ('clock','timer') else 13)
            if kind in ('clock','timer'):caption(x+15,y+94,'Drag to position',p['muted'],11)
        cr.restore()

    def widget_drag_begin(self,_gesture,x,y):
        self.widget_drag=None
        for kind,(left,top,w,h) in reversed(list(self.widget_rects.items())):
            if left<=x<=left+w and top<=y<=top+h:
                self.widget_select(kind);self.widget_drag=(kind,self.widget_draft['items'][kind]['x'],self.widget_draft['items'][kind]['y']);break

    def widget_drag_update(self,_gesture,dx,dy):
        if not self.widget_drag:return
        kind,x,y=self.widget_drag;item=self.widget_draft['items'][kind];factor=min(self.widget_canvas.get_width()/1440,self.widget_canvas.get_height()/850)
        _,_,w,h=widgets.geometry(item,kind,1440,850)
        item['x']=max(0,min(1,x+dx/max(1,(1440-w)*factor)));item['y']=max(0,min(1,y+dy/max(1,(850-h)*factor)))
        self.widget_select(kind)

    def desktop_page(self):
        page=self.page('More than colours','Fonts, icons, cursors, window controls and your installed GNOME dock. Changes apply only when you choose.')
        self.desktop_changes={};self.desktop_fields={};self.desktop_options={};available=desktop.values()
        controls=Gtk.Box(spacing=10)
        controls.append(action('Pixel desktop',lambda:self.desktop_preset(True)));controls.append(action('Clean desktop',lambda:self.desktop_preset(False)))
        controls.append(Gtk.Box(hexpand=True));button=action('Apply desktop changes',self.apply_desktop);button.add_css_class('suggested-action');controls.append(button);page.append(controls)
        fonts=Adw.PreferencesGroup(title='Fonts, icons and cursors')
        windows=Adw.PreferencesGroup(title='Windows and motion')
        panel=Adw.PreferencesGroup(title='Top bar and workspaces')
        dock=Adw.PreferencesGroup(title='Dock',description='Controls the installed Ubuntu Dock or Dash to Dock extension.')
        choices={'icons':desktop.themes(),'cursor':desktop.themes(True),'buttons':[':minimize,maximize,close','close,minimize,maximize:',':close'],'focus':['click','sloppy','mouse'],'dock_position':['BOTTOM','LEFT','RIGHT','TOP']}
        titles={'font':'Interface font','mono':'Monospace font','icons':'Icon pack','cursor':'Cursor pack','cursor_size':'Cursor size','text_scale':'Text scale','animations':'Window animations','buttons':'Titlebar buttons','focus':'Focus behaviour','center':'Centre new windows','clock_seconds':'Clock seconds','clock_date':'Clock date','clock_weekday':'Clock weekday','hot_corner':'Activities hot corner','battery':'Battery percentage','dynamic_workspaces':'Dynamic workspaces','workspaces':'Workspace count','dock_position':'Dock position','dock_size':'Dock icon size','dock_autohide':'Dock auto-hide','dock_extend':'Extend dock along screen edge'}
        for name,spec in available.items():
            value=spec['value'];row=Adw.ActionRow(title=titles[name]);field=None
            if name in choices:
                values=list(choices[name])
                if value not in values:values.insert(0,value)
                self.desktop_options[name]=values;field=Gtk.DropDown.new_from_strings(values);field.set_selected(values.index(value))
                field.connect('notify::selected',lambda item,_,k=name:self.desktop_changes.update({k:self.desktop_options[k][item.get_selected()]}))
            elif isinstance(value,bool):
                field=Gtk.Switch(active=value);field.connect('notify::active',lambda item,_,k=name:self.desktop_changes.update({k:item.get_active()}))
            elif isinstance(value,(int,float)):
                low,high,step={'cursor_size':(16,96,8),'text_scale':(.75,2,.05),'workspaces':(1,36,1),'dock_size':(16,64,4)}[name]
                field=Gtk.SpinButton.new_with_range(low,high,step);field.set_value(value)
                field.connect('value-changed',lambda item,k=name,is_float=isinstance(value,float):self.desktop_changes.update({k:item.get_value() if is_float else item.get_value_as_int()}))
            else:
                field=Gtk.Entry(text=str(value),width_chars=18,max_length=128)
                field.connect('changed',lambda item,k=name:self.desktop_changes.update({k:item.get_text()}))
                if name in ('font','mono'):row.add_suffix(action('Choose',lambda k=name:self.desktop_font(k)))
            field.set_valign(Gtk.Align.CENTER);field.set_sensitive(spec['writable']);row.add_suffix(field);self.desktop_fields[name]=field
            group=fonts if name in ('font','mono','icons','cursor','cursor_size','text_scale') else windows if name in ('animations','buttons','focus','center') else dock if name.startswith('dock_') else panel
            group.add(row)
        for group in (fonts,windows,panel):page.append(group)
        if any(name.startswith('dock_') for name in available):page.append(dock)
        else:page.append(text('Dock controls appear when Ubuntu Dock or Dash to Dock is installed.', 'dim-label',wrap=True))
        page.append(action('Restore desktop controls',lambda:self.run(desktop.restore_all,'Original desktop controls restored')))
        page.append(text('GTK apps can adopt the full window design. Apps that draw their own interfaces and sandboxed apps may keep their own controls.', 'caption',wrap=True))
        return page

    def desktop_preset(self,pixel):
        values={'font':'Silkscreen 10' if pixel else 'Sans 11','mono':'Monospace 11','icons':assets.ICON_THEME if pixel else 'Adwaita','cursor':'Studio Pixel Gold' if pixel else 'Adwaita','cursor_size':24}
        for name,value in values.items():
            item=self.desktop_fields.get(name)
            if item is None or not item.get_sensitive():continue
            if name in self.desktop_options:item.set_selected(self.desktop_options[name].index(value))
            elif isinstance(item,Gtk.Entry):item.set_text(value)
            else:item.set_value(value)

    def desktop_font(self,name):
        dialog=Gtk.FontChooserDialog(title='Choose a font',transient_for=self,modal=True)
        dialog.set_font(self.desktop_fields[name].get_text())
        def response(item,result):
            if result==Gtk.ResponseType.OK:self.desktop_fields[name].set_text(item.get_font())
            item.destroy()
        dialog.connect('response',response);dialog.present()

    def apply_desktop(self):
        changes=dict(self.desktop_changes)
        def apply():assets.install_assets();return desktop.apply(changes)
        self.run(apply,'Desktop controls updated')
