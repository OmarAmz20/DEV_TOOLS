# Wallpaper Studio Video 2.2 — quick start

Your working native wallpaper method is preserved. This fork of Wallpaper Studio Plus keeps window designs, seven desktop widgets, desktop controls and adds a real video wallpaper engine for X11 and GNOME Wayland.

## Download and open

1. Download **Wallpaper-Studio-Video.run** (Ubuntu Intel/AMD 64-bit).
2. Right-click it → **Properties → Permissions → Allow executing file as program**.
3. Double-click it. Setup and launch happen automatically. No terminal or manual extraction.
4. Next time, open **Wallpaper Studio Video** from Applications or double-click the same download.

This permission is a one-time Linux requirement for downloaded executables. No sudo or FUSE is needed. First setup may download missing GTK dependencies from official Ubuntu packages. Updates preserve settings, notes, themes, images and your existing wallpaper setup.

## Video wallpaper

1. Open **Video wallpaper** in the sidebar.
2. Choose an MP4, WebM, MKV, MOV, M4V or AVI file.
3. Pick **Cover** or **Contain**, mute if wanted, and press **Set video wallpaper**.
4. On **GNOME Wayland** (GNOME Shell 45+), press **Install / enable** on the extension row, then log out and back in once. On X11 no extension is needed. On Ubuntu 22.04/GNOME 42, use the X11 session for video.
5. Press **Stop** to return to the still frame; applying a picture also stops the engine.

Video playback needs GStreamer GTK support:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gtk-4.0 \
  gstreamer1.0-gtk3 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-libav
# Optional on Ubuntu 25.10+ (GTK4 sink); 22.04/24.04 use the GTK3 sink above:
sudo apt install gstreamer1.0-gtk4
```

## Keep awake and lock on activity

Open **Session**. Choose a keep-awake duration, or use **Lock on next activity**:

- **Lock now** tests your system's real locker.
- **Arm · 10 seconds** starts the countdown. Move away before it ends.
- The next keyboard or mouse activity requests a system lock, then ends keep awake.
- The guard never automatically arms at login or after a helper restart.

The first input may reach an app before the lock activates. If no working system locker is detected, the activity option is disabled and explains why; the LightDM login screen alone is not secure locking. Normal keep awake remains available.

**A school logout timer can still end your session.** This app cannot guarantee an unlimited login and does not change administrator timers.

## Make windows look different

1. Open **Appearance**.
2. Select **Mushroom Kingdom** for Mario-inspired brick titlebars, gold controls and pixel fonts. Or try Pixel Arcade, Pocket Console, Retro Desktop 95, Neon Grid, Paper & Ink, Ocean Glass or Terminal CRT.
3. Click **Live window preview** to try real controls.
4. Click **Apply style only**. Reopen other apps if they have not refreshed yet.

Use **Window design** to combine a different window structure with any palette. Switch off **Pixel typeface** if you want normal fonts. **Match pixel icons and cursor** controls the theme's extra icon/cursor changes.

The six original colour themes and wallpaper-matched colours are still available. Light, Dark and Auto are supported.

## Add your own themes

Click **My own theme** to edit six colour roles for the current light/dark variant. Pick a window structure and fine-tune the accent, tint, corners or contrast. Under **Saved looks**, name it and click **Save**. You can keep multiple looks.

Use **Export recipe / Import recipe** to share. Import loads a preview; Apply makes it active. Editable examples are in the archive's `examples/` folder.

## Put widgets on your desktop

1. Open **Widgets** and click **Study desk** or **Pixel HUD**.
2. Drag the boxes in the preview. Choose sizes, monitor, opacity and which widgets you want.
3. Edit your sticky note in the studio, then click **Apply widgets**.
4. For direct movement, click **Edit**, drag the widget headings on the desktop, then click **Lock**.

You get a clock, calendar, CPU/RAM/disk stats, sticky note, now-playing controls, focus timer and quick-launch buttons. They keep running when you close the studio.

Switch off **Show desktop widgets** and apply to hide them. If desktop icons cover the widgets, select **Window layer → Above desktop icons**. Widgets require X11; your session is already X11.

Export/import layouts to share positions and options. Your note is excluded. Widgets follow the last applied theme, not unfinished colour edits.

## Fonts, icons and the rest

Open **Desktop controls** for fonts, icons, cursor size, text scale, window buttons, motion, clock details and workspaces. Dock controls appear when Ubuntu Dock or Dash to Dock is installed. Click **Apply desktop changes** after editing.

The GNOME panel can use the look when the **User Themes** extension is already installed and enabled. The app does not restart GNOME or install Shell extensions automatically.

## Wallpapers and recovery

**Library → choose picture → Apply wallpaper** still uses your existing method. Disable **Preferences → Match colours when applying a wallpaper** to change the picture on its own.

Use **Recent choices → Undo** for wallpaper history. The menu restores window styles, wallpaper or all Plus changes. A full restore also restores desktop controls and hides widgets; it keeps your notes and saved looks.

If you need to restore from Terminal:

```bash
"$HOME/.local/bin/wallpaper-studio-video" restore --scope all
```

GTK apps have the broadest window-style support. Qt, Electron, games and sandboxed apps may retain their own internal interface. Use **Video wallpaper** for motion; **Stop** returns to the still frame. This release does not change the lock-screen background; LightDM/Codam uses its own greeter.

Open **Wallpaper Studio Video** from your apps next time. Your already-configured account should not need another login to change wallpapers. Friends setting up a new account may need one normal logout/login once.

Full instructions and source details are in `README.md`; test results are in `VALIDATION.md`.
