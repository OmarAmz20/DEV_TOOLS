# Wallpaper Studio Video 2.2

A GNOME desktop studio with full window designs, desktop widgets, fonts, icons, cursors and native wallpapers, adapted from [Wallpaper Studio by Adil Asselman (yuxev)](https://github.com/yuxev/wallpaper-studio). This fork adds a **real video wallpaper engine** for X11 and GNOME Wayland while keeping the native GNOME image setup as a fallback.

**Your working wallpaper method stays the same:** the personal `wallpaper-profile`, the existing GNOME Shell service override, and native GNOME image settings. Video adds a renderer on top, and stopping it returns to the still image.

## Download and open

Download **Wallpaper-Studio-Video.run** for Ubuntu on Intel/AMD 64-bit computers.
Right-click the download → **Properties → Permissions → Allow executing file as program**, then double-click it.
Linux requires that permission once for a downloaded executable; a website cannot set it for you.

The launcher shows a setup window, installs to your own account, and opens the studio. No terminal, ZIP extraction, sudo, FUSE or AppImage runtime is needed. Afterwards open **Wallpaper Studio Video** from Applications, or open the same downloaded file again. You can delete the download after setup, or share it with friends; no personal settings are embedded in it.

Opening a newer download updates the same app and retains settings, notes, saved looks, applied images and your working GNOME profile. If an old app window is open, the update asks to close it first. Missing GTK dependencies can be downloaded from verified official Ubuntu packages on Ubuntu 22.04/24.04; internet may be needed for that first setup. Existing matching dependencies are reused.

The optional source checkout is for editing/development. Its `install.sh --launch` remains available, but the single-file launcher is the normal installation method. Build it with `python3 packaging/build_bundle.py dist/Wallpaper-Studio-Video.run`. The installed app is also available at `$HOME/.local/bin/wallpaper-studio-video`.

## Change a wallpaper

1. Open **Library**. Use the folder button to choose your pictures, or the **+** button for a single file. Dropping an image or folder onto the window also works.
2. Click a picture or video to preview it. Selecting one does not change your desktop.
3. Choose **Light + dark**, **Light only** or **Dark only**, and a fit such as **Fill / crop**.
4. Click **Apply wallpaper**. When the selection is a video, the button becomes **Set video wallpaper** and the video engine starts.
5. Use **Video wallpaper** in the sidebar to choose a video, change mute/scaling/monitor, install the Wayland extension, or stop playback.

Use the star to save favourites. Search filters filenames; the sort menu supports name, newest and favourites first. **Recent choices** keeps up to 30 applied choices and has Undo. Video entries are remembered with their source path, so Undo can start the previous video again.

Plus keeps a durable copy of applied images. Moving the original, clearing thumbnails, or updating the app will not remove that copy. With separate light/dark wallpapers, the visible variant follows GNOME's light/dark preference; use **Appearance → Auto** if you want to follow it.

## Change the full window design

**Appearance** now changes window structures as well as colours: titlebars, borders, buttons, entries, menus, scrollbars and fonts. The built-in looks include:

| Look | Window design |
| --- | --- |
| Mushroom Kingdom | Original Mario-inspired brick titlebars, coin-gold buttons and pixel fonts |
| Pixel Arcade | Square controls, chunky outlines and hard shadows |
| Pocket Console | Green handheld-console surfaces and inset controls |
| Retro Desktop 95 | Raised bevels, compact titlebars and classic blue |
| Neon Grid | Angular cyberpunk controls with luminous borders |
| Paper & Ink | Ink outlines and offset paper shadows |
| Ocean Glass | Rounded ocean-blue controls and soft glass surfaces |
| Terminal CRT | Sharp phosphor-green console windows |

The original Catppuccin, Nord, Tokyo Night, Gruvbox, Dracula, Rosé Pine and Wallpaper palettes remain available. **Window design → Window structure** lets you combine a different structure with any palette. **Live window preview** opens real GTK controls in your draft style.

Pixel styles can use the bundled **Silkscreen** font and included pixel icons/cursors. The font option affects the theme's GTK text; Desktop controls also lets you choose a global interface font. The icon pack includes common folders, files, desktop actions and selected apps; other icons inherit Adwaita. The cursor packs include pixel arrows, text cursors and pointing hands; other shapes inherit Adwaita.

Pixel icons and cursors are applied with the look when **Match pixel icons and cursor** is enabled. Switching back restores the extras owned by that look, while preserving a manual icon/cursor choice you made later. **Style the GNOME panel** is available when the **User Themes** extension is already installed and enabled. Plus does not install or enable Shell extensions automatically.

## Edit colours and add your own themes

Open **Appearance** and choose one of:

| Recipe | Character |
| --- | --- |
| Wallpaper | A palette sampled from the selected picture |
| Catppuccin | Pastel accents and soft surfaces |
| Nord | Cool slate and frost blue |
| Tokyo Night | Indigo and electric blue |
| Gruvbox | Warm charcoal, amber and olive |
| Dracula | Violet charcoal and bright highlights |
| Rosé Pine | Muted plum and rose gold |

Every recipe has light and dark variants. These are desktop colour adaptations inspired by the named palettes, not official theme distributions.

Click **My own theme** at the top of Appearance to edit the window background, secondary surface, cards, main text, secondary text and accent for the currently previewed light/dark variant. Choose a window structure, give the result a name under **Saved looks**, and save it. You can keep multiple personal looks and load them for preview later. Saving the same name updates that saved look.

The top shortcuts jump directly to Themes, Window design, My own theme, Saved looks and Fine-tune, so you do not have to scroll through every option. Three editable example recipes are included in `examples/`.

Scroll down for a custom accent, wallpaper tint, corner style, stronger text contrast, subtle transparency and GNOME Terminal colours. The live preview shows the result and contrast ratios. Clear the accent field to follow the recipe again. Tint controls the Wallpaper recipe's surfaces.

Click **Apply style only** to update colours while keeping your desktop picture. **Apply wallpaper** also applies your selected recipe by default. Turn off **Preferences → Match colours when applying a wallpaper** to change pictures on their own.

Editing a recipe affects the preview until you click Apply. Automatic light/dark following uses the last applied recipe. Export/import a theme JSON to share those controls with a friend; exported recipes do not contain your image paths, history or hooks. Import loads a preview; you still choose when to apply it.

GTK 3 apps use two alternating theme names to pick up colour updates. Many GTK 4/libadwaita apps need reopening after a style change. GNOME Shell's panel, every third-party app, browser web pages and sandboxed apps are not guaranteed to adopt these colours. GNOME Terminal uses a separate Plus profile for new windows; your previous profiles remain available.

| Application type | Expected coverage |
| --- | --- |
| Native GTK 3 apps | Broadest coverage: controls, window design, colours and fonts |
| GTK 4 / libadwaita apps | Custom CSS import; reopening may be needed; app-specific drawing can remain unchanged |
| GNOME top panel and menus | Optional, with the enabled User Themes extension |
| Qt / Electron / browsers / games | Icons, cursor and supported window decorations may change; their internal interfaces generally use their own styling |
| Sandboxed apps | Access to user themes/fonts varies with sandbox permissions |

This is a desktop customizer, not a renderer that turns every program's graphics into pixel art. Restore controls are included because application styles vary.

## Desktop widgets

Open **Widgets**, select **Minimal clock**, **Study desk** or **Pixel HUD**, then click **Apply widgets**. The seven widget types are:

- Clock and date, with optional seconds and 12/24-hour time.
- Current-month calendar.
- CPU, RAM and home-filesystem disk usage.
- A sticky note, edited inside the studio.
- Now playing and playback controls for MPRIS-compatible media players.
- A focus timer with start/pause, reset and a completion notification.
- Home, default browser and terminal shortcuts.

Drag the boxes in the preview to arrange them. Each widget has its own enable switch, position and size controls. Select a monitor and opacity. Click **Apply widgets** when ready.

To move actual widgets, click **Edit**, drag their headings on the desktop, then click **Lock**. Lock keeps the positions you just dragged. Edit mode raises widgets temporarily; locked widgets return to their desktop layer. If a desktop-icons extension covers them, try **Window layer → Above desktop icons**. That alternative remains below normal apps but can be hidden by Show Desktop, depending on the window manager.

Widgets follow the last applied theme. Draft colour edits do not alter the running widgets. Closing the studio leaves enabled widgets running. Switch off **Show desktop widgets** and apply to hide them. The layout is restored at the next login when enabled.

**Export layout** shares positions and widget options without the sticky note. **Import layout** loads a preview, preserves your note, and does not automatically enable widgets. The timer runs while the widget host is running and resets when that host exits. No weather service, account or internet access is needed for the local widgets.

## Dock

Open **Dock** to run a dock that belongs to this app rather than the GNOME
Shell extension. It is a separate GTK process with a native layer-shell surface
on wlroots/Hyprland and a normal-window fallback elsewhere.

- Start, stop and re-apply from the page, or use:
  `wallpaper-studio-video dock start`, `dock stop`, `dock status`.
- Put it on the **bottom, top, left or right** edge.
- Choose a monitor or show it on all monitors.
- Change alignment, icon size, spacing, edge padding, corner radius, opacity,
  accent colour and one of six skins.
- Show or hide app labels.
- Reserve screen space so maximized windows do not sit under the dock.
- Add installed desktop applications or custom commands.
- Add separators to group apps, then reorder or remove any entry.
- Reorder apps with the arrow buttons, edit their labels/icons/commands, or
  remove them.
- Toggle **Start at login** to create a per-user autostart entry.
- The live preview updates while you change settings; **Apply dock** commits and
  starts it.

The dock launches desktop files through `Gio.DesktopAppInfo` and custom
commands through `/bin/sh`. It does not collect or send anything.

## Desktop controls

The **Desktop controls** page can edit:

- Interface and monospace fonts, icon pack, cursor pack and cursor size.
- Text scale and window animations.
- Titlebar button positions, focus behaviour and centring new windows.
- Top-bar date, weekday, seconds and battery percentage, where supported.
- Hot corners, dynamic workspaces and workspace count.
- Dock position, icon size, auto-hide and screen-edge extension, when Ubuntu Dock or Dash to Dock is installed.

**Pixel desktop** and **Clean desktop** fill in a few common choices for preview. Click **Apply desktop changes** to commit edited fields. Unavailable controls are omitted; locked controls are disabled. **Restore desktop controls** recovers the original values saved before Plus first changed them.

## Existing native setup

Plus reuses these files and leaves existing matching files unchanged:

```text
~/.config/dconf/wallpaper-profile
~/.config/systemd/user/org.gnome.Shell@x11.service.d/wallpaper-profile.conf
```

The profile is selected before loading GNOME settings. Image changes use `gsettings` with that same profile and `GSETTINGS_BACKEND=dconf`; Plus checks writability, verifies saved values, and attempts rollback if an image-setting write fails.

For your already-configured account, changing wallpapers should not require another login. A friend's newly configured GNOME account may need **one normal logout/login** after setup so GNOME Shell loads the profile. Plus never replaces or restarts GNOME Shell or forces a logout. **Preferences → Native wallpaper → Check** shows the current status.

If GNOME reports a read-only runtime directory or a D-Bus permission error, that session problem is separate from a wallpaper lock. Open Plus in your regular graphical GNOME session. A different existing service override is left intact and reported for inspection.

## Session: keep awake and lock on activity

Open **Session** for keep-awake durations of 30 minutes, one hour, two hours or the rest of this session. The helper requests idle/suspend inhibition through GNOME. It never moves the mouse or creates fake input. Your normal settings resume when the request ends or the helper exits.

**Lock on next activity** is a one-shot X11 option:

1. The app checks for a real screen locker and reads X11 idle time.
2. Click **Lock now** to test the system locker, then unlock normally.
3. Click **Arm · 10 seconds** and move away before the countdown ends.
4. After arming, a key press, mouse movement or mouse click requests a screen lock.
5. The helper checks whether the locker activated and ends its keep-awake request. It reports a failure if activation cannot be confirmed.

The first input can reach an application before the lock activates; this is an activity-triggered lock request, not an input shield. It reads idle duration only, never records keys, and does not automatically arm after login or helper restart. Closing the editor leaves an armed helper running. **Stop** cancels a pending countdown; once armed, moving to the Stop button is itself activity and can trigger the lock.

GNOME ScreenShield and recognized running Light Locker/MATE/Cinnamon/Xfce lockers are supported. A dead GNOME proxy or `dm-tool switch-to-greeter` alone is not accepted as secure locking. On a LightDM school session with no real running locker, this control stays disabled with a reason; keep awake remains available.

**School logout timers may still end the session.** In particular, Codam's separate idle timer can terminate a user independently of GNOME inhibitors. This app does not alter school timers, reset their timestamps or promise an unlimited login.

## Rotation and video wallpaper

Choose wallpaper rotation in Preferences. Closing the studio leaves the helper running. **Pause automation** stops its rotation, colour following and any keep-awake/guard request, while keeping the native wallpaper. Opening the studio starts its normal helper again; it never rearms an old activity guard.

### Video wallpaper

Video is a real moving wallpaper, not just a still frame:

- **X11:** the renderer creates a borderless desktop-type window and stays below normal applications.
- **GNOME Wayland:** the bundled GNOME Shell extension places the renderer in the background layer, behind desktop icons. GTK 3 keeps the window mapped and reparents its actor; GTK 4 clones the paintable actor and minimises the original window.
- The still frame is still written to GNOME's native wallpaper settings, so locking, logging out or stopping the engine always leaves a correct desktop.
- The engine is supervised: if the renderer exits, it restarts; the login autostart entry restores it.
- Use **Video wallpaper → Stop** to return to the still image. Applying any picture also stops the video engine.

Requirements for video playback:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtk-4.0 \
  gstreamer1.0-gtk3 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-libav
# Optional on Ubuntu 25.10+ (GTK4 sink); 22.04/24.04 use the GTK3 sink above:
sudo apt install gstreamer1.0-gtk4
```

On GNOME Wayland (GNOME Shell 45+, Ubuntu 23.10 or newer), install/enable the extension from **Video wallpaper → Install / enable**, then **log out and back in once** so GNOME Shell loads it. The extension is copied to `~/.local/share/gnome-shell/extensions/wallpaper-studio-video@local`. On Ubuntu 22.04/GNOME 42, use the X11 session for video or keep the still-frame fallback.

This update does not change your lock-screen background. On standard GNOME it normally follows the blurred desktop image; LightDM/Codam uses its own greeter and wallpaper mechanism.

## Restore, update and remove

The menu provides **Restore window style only**, **Restore wallpaper only** and **Restore all Plus changes**. Backups are taken before Plus first changes each setting. Restore removes only Plus's marked CSS import and its own Terminal profile; other custom CSS and profiles added later are preserved. A full restore also recovers desktop controls and hides widgets, while keeping your notes and layouts. Your working native profile and service override are retained.

To update, close the Plus window and run the new archive's `install.sh --launch` again. Your preferences, applied image copies and backups live outside the application code.

To uninstall after closing the app:

```bash
bash "${XDG_DATA_HOME:-$HOME/.local/share}/wallpaper-studio-video/app/uninstall.sh"
```

This restores Plus changes before removing its app, launcher and autostart entry. It retains saved images, recovery data and your native wallpaper setup. If restoring fails, the uninstaller stops so you can recover first.

## Useful commands

Use `"$HOME/.local/bin/wallpaper-studio-video"` in place of `wallpaper-studio-video` if the command is not in PATH.

```bash
wallpaper-studio-video set "$HOME/Pictures/my wallpaper.jpg"
wallpaper-studio-video set "$HOME/Pictures/night.png" --target dark
wallpaper-studio-video set "$HOME/Videos/rain.mp4" --fit crop
wallpaper-studio-video set "$HOME/Videos/rain.mp4" --still
wallpaper-studio-video video set "$HOME/Videos/rain.mp4" --mute --fit cover --monitor 0
wallpaper-studio-video video start
wallpaper-studio-video video stop
wallpaper-studio-video video status
wallpaper-studio-video theme nord
wallpaper-studio-video light
wallpaper-studio-video dark
wallpaper-studio-video auto
wallpaper-studio-video next
wallpaper-studio-video undo
wallpaper-studio-video export-theme "$HOME/my-theme.json"
wallpaper-studio-video import-theme "$HOME/my-theme.json"
wallpaper-studio-video apply
wallpaper-studio-video awake 60
wallpaper-studio-video awake off
wallpaper-studio-video stop
wallpaper-studio-video start
wallpaper-studio-video doctor
wallpaper-studio-video restore --scope style
wallpaper-studio-video restore --scope desktop
wallpaper-studio-video widgets show
wallpaper-studio-video widgets edit
wallpaper-studio-video widgets lock
wallpaper-studio-video widgets hide
```

`set --no-theme` turns off automatic colour matching in your preferences. Re-enable it in Preferences when wanted. Running `set` on a video starts the video engine; add `--still` to use only a frame. `video stop` returns to the still image and keeps the last frame as the native wallpaper. For local automation, executable files in `~/.config/wallpaper-studio-video/hooks/` receive `WS_MODE`, `WS_STATE`, palette colours and ANSI colours only when **Run local colour hooks** is enabled. Theme imports cannot enable hooks.

## Source and checks

The full Python source is included. `backend.py` owns native wallpaper access. `recipes.py` and `skins.py` own colours and window designs. `desktop.py` owns reversible desktop controls; `widget_control.py` and `widgets.py` own widgets. `app.py` and `custom_pages.py` own the studio interface. `session.py` owns rotation and keep-awake requests. `screen_guard.py` owns X11 activity detection and verified locker discovery; `session_page.py` owns its GUI. `video_wallpaper.py` owns video state and process control, `video_engine.py` supervises the renderer, `video_renderer.py` dispatches to the GTK 3 (X11) or GTK 4 (Wayland) GStreamer process, and `video_extension/` is the GNOME Shell background bridge. `packaging/` builds the native single-file launcher.

### Development with Pixi

The Ubuntu installer uses the system Python and GTK so the app can talk to the host dconf database and the optional user-local GTK runtime. For development and tests, use the Pixi environment:

```bash
source scripts/env.sh    # optional: keeps Pixi and app caches in ~/goinfre
pixi install
pixi run test
pixi run lint
pixi run compile
```

Run the non-destructive unit checks from this folder with either Python:

```bash
pixi run test
# or
/usr/bin/python3 -m unittest discover -s tests -v
```

### 42-school machines and goinfre

When `~/goinfre` exists and is writable, the app cache (thumbnails, video
frames and `video.log`) moves to
`~/goinfre/wallpaper-studio-video/cache`. Pixi development caches move to
`~/goinfre/wallpaper-studio-video` after `source scripts/env.sh`. Set
`WALLPAPER_STUDIO_GOINFRE` to use a different mount. Without goinfre the
normal XDG cache locations are used.

Core/session tests require PyGObject. The backend tests use a fake GNOME client and do not change your real wallpaper. See `VALIDATION.md` for the tested environments and limits.

Original code is MIT-licensed; its copyright is retained in `LICENSE`. The bundled adw-gtk3 base has a separate LGPL-2.1 license. See `NOTICE.md` for sources and attribution. Sharing this archive lets friends install it for their own accounts; it does not edit other users' desktops.
