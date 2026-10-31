# Wallpaper Lite

A small, fast wallpaper picker: choose a picture, get its colours on your GTK
desktop. It is a clean reimplementation of `wallpaper-studio`, with the network,
hooks and heavy theme machinery removed.

- **One click:** click a thumbnail; the wallpaper and colours apply together.
- **Light or dark:** two palettes are made from every picture.
- **Small surface:** one GTK 3 window and one optional helper, no libadwaita,
  no theme copies, no video stack.
- **Offline:** `install.sh` copies local files. It never downloads anything.
- **Private:** config, cache and runtime files are `0700`/`0600`.
- **Bounded:** pictures are checked for file size, pixel count and aspect ratio
  before they are decoded.
- **No hooks, no videos, no terminal profile, no auto-rotation.** Those are in
  the original if you need them.

This is not a patched copy of the original. The security review of the original
is in [`../SECURITY-AUDIT.md`](../SECURITY-AUDIT.md).

## Requirements

- Python 3 with PyGObject (`python3-gi`, `python3-gi-cairo`)
- GTK 3 and GdkPixbuf (`gir1.2-gtk-3.0`)
- X11 for the fallback wallpaper window. On Wayland, GNOME's own background
  setting must be writable.

On Ubuntu 22.04:

```sh
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

No sudo is needed to install or run the app.

## Install

```sh
cd simple
./install.sh
```

Open **Wallpaper Lite** from your apps, or run:

```sh
wallpaper-lite
```

The installer puts the app in `~/.local/share/wallpaper-lite`, creates a launcher
in `~/.local/bin` and an autostart entry for the optional X11 desktop helper.
The helper exits immediately on sessions where GNOME's own wallpaper can be set.

Run `./install.sh` again to update. Your folder and colours are kept.

## Use

1. Choose a folder with the folder button, or open a single file.
2. Click a picture. The app writes a light and a dark palette from it.
3. Use **Light** / **Dark** to change the colours.
4. Use **Restore original look** to put the old theme, colour scheme and
   wallpaper back.

The first time you apply a picture, the original settings are saved in
`~/.config/wallpaper-lite/originals.json` so Restore can be exact.

## How it works

| File | What it does |
|---|---|
| `wallpaper_lite/core.py` | Paths, image checks, palette, GTK CSS, settings, restore, helper lifecycle |
| `wallpaper_lite/app.py` | The GTK 3 window |
| `wallpaper_lite/desktop.py` | Optional X11 desktop window when GNOME's picture is locked |
| `wallpaper_lite/__main__.py` | Small command line |

The palette is built from at most 64 × 64 pixels in one pass: the dominant tint
becomes the neutrals, the most vivid common hue becomes the accent, then the
accent is nudged until it has enough contrast against the paper. Light and dark
palettes are generated together.

`theme.css` defines both GTK 3 names (`@theme_bg_color`) and GTK 4/libadwaita
names (`@window_bg_color`, `@accent_bg_color`). The app adds one import line at
the top of `~/.config/gtk-3.0/gtk.css` and `~/.config/gtk-4.0/gtk.css`, keeping
the rest of those files intact. On Restore it removes only that exact import.

For live recolouring of open GTK 3 apps, it also writes two tiny themes,
`Wallpaper Lite A` and `Wallpaper Lite B`, under `~/.local/share/themes`. Each
imports the built-in Adwaita stylesheet and `theme.css`; each recolour flips the
theme name, which is what makes GTK 3 reload the CSS. The original theme is
saved and restored. Open libadwaita/GTK 4 apps pick up the new palette the next
time they start (they do follow light/dark live through `color-scheme`).

### Why the X11 helper exists

At 42, `org.gnome.desktop.background` is locked. When GNOME's keys are writable,
the app uses the normal setting and does not start anything. When they are
locked, it starts a single GTK 3 window of type `_NET_WM_WINDOW_TYPE_DESKTOP`
behind all windows and above the root window, which draws the saved picture.
There is no raw Xlib and no video player. The helper exits when GNOME can draw
the wallpaper itself and when there is no saved picture.

### Your own GTK style

`theme.css` also exposes stable names you can use in your own CSS:

`@ws_paper`, `@ws_paper2`, `@ws_sheet`, `@ws_ink`, `@ws_muted`, `@ws_accent`,
`@ws_accent_text`, `@ws_on_accent`, `@ws_shadow`.

## Command line

```
wallpaper-lite                  open the window
wallpaper-lite set FILE         use a picture
wallpaper-lite next             a random different picture from your folder
wallpaper-lite light|dark       choose the colour mode
wallpaper-lite apply            re-apply the current picture and mode
wallpaper-lite restore          undo theme, colours and wallpaper
wallpaper-lite stop             stop the X11 desktop helper
```

## Tests

```sh
cd simple
python3 -m unittest discover -s tests -v
```

The tests never touch your real GSettings; they use temporary paths and stubbed
settings calls.

## Limits

- Pictures only (JPG, PNG, WebP, GIF, BMP, TIFF). No videos.
- No GNOME Terminal profile, lock-screen picture, or automatic rotation.
- GTK 4/libadwaita apps read `gtk-4.0/gtk.css` at startup, not while running
  (light/dark still follows `color-scheme`).
- The fallback desktop window is X11-only.
- A malicious image still reaches GdkPixbuf in-process. The size/pixel/aspect
  checks stop the easy decompression bombs, but they are not a sandbox.
- The app changes global settings while it is active: `gtk-theme`,
  `color-scheme`, and the GNOME background URI. Restore puts them back.

## Uninstall

```sh
cd simple
./uninstall.sh
```

It restores the original look first, stops the helper, and removes the app,
config, cache, launcher and autostart entry. Your pictures are not touched.
