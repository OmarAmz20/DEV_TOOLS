# 1337-Customizer — Command Reference

Every command in this file is run from the project root unless stated otherwise.
The installed command is `1337-customizer`; in the checkout you can use
`./1337-customizer` instead.

```text
Project root: /home/omar/Documents/tools/1337-customizer
Installed command: ~/.local/bin/1337-customizer
```

## 1. Run, install, version

```bash
# Run from the checkout
./1337-customizer

# Open the studio (same as above)
./1337-customizer --help
./1337-customizer --version

# Start enabled helpers without opening a window
./1337-customizer --background

# Install for the current user
./install.sh

# Install and launch
./install.sh --launch

# Build the self-extracting installer
./packaging/build-run.sh

# Run the self-extracting installer
chmod +x dist/1337-Customizer.run
./dist/1337-Customizer.run

# Install without auto-launching
./dist/1337-Customizer.run --no-launch
```

Installed launcher:

```bash
~/.local/bin/1337-customizer
```

## 2. Wallpapers

### Set a picture

```bash
1337-customizer set ~/Pictures/wallpapers/night.jpg
1337-customizer set ~/Pictures/wallpapers/night.jpg --monitor eDP-1
1337-customizer set ~/Pictures/wallpapers/night.jpg --fit crop
1337-customizer set ~/Pictures/wallpapers/night.jpg --fit fit
1337-customizer set ~/Pictures/wallpapers/night.jpg --monitor eDP-1 --fit stretch
1337-customizer set ~/Pictures/wallpapers/night.jpg --fit center --no-theme
```

`--fit` accepts:

```text
crop | fit | stretch | center
```

### Set a video or force a still frame

```bash
1337-customizer set ~/Videos/aurora.mp4
1337-customizer set ~/Videos/aurora.mp4 --video
1337-customizer set ~/Videos/aurora.mp4 --still
```

`--video` forces the video-wallpaper engine. `--still` extracts a frame and
applies it as a normal image.

### Rotate and undo

```bash
1337-customizer next
1337-customizer next --favorites
1337-customizer undo
```

### Inspect wallpapers

```bash
1337-customizer doctor
1337-customizer about
```

`doctor` prints JSON containing the session, monitors, detected backends,
tools, layer-shell support and current GTK settings. `about` prints the app
name, version, application ID and checkout path.

## 3. Themes and looks

```bash
# Apply a built-in look
1337-customizer theme midnight-aurora
1337-customizer theme catppuccin --mode dark
1337-customizer theme nord --mode light
1337-customizer theme gruvbox --mode auto

# List available presets
1337-customizer theme --list

# Derive colours from the current wallpaper
1337-customizer theme --wallpaper --mode dark

# Import a theme JSON and apply it
1337-customizer theme --file ~/my-theme.json

# Export the current resolved look
1337-customizer export-theme ~/my-theme.json

# Import a theme JSON
1337-customizer import-theme ~/my-theme.json
```

`--mode` accepts:

```text
auto | light | dark
```

### Restore

```bash
# Restore GTK, terminal, icon/cursor/font changes made by the app
1337-customizer restore --scope look

# Restore the previous wallpaper
1337-customizer restore --scope wallpaper

# Restore the look, wallpaper, widgets and video host
1337-customizer restore --scope all
```

## 4. Video wallpaper

```bash
# Start on all monitors using configured options
1337-customizer video start ~/Videos/aurora.mp4

# Start on one output
1337-customizer video start ~/Videos/aurora.mp4 --monitor eDP-1

# Crop or fit
1337-customizer video start ~/Videos/aurora.mp4 --fit crop
1337-customizer video start ~/Videos/aurora.mp4 --fit fit

# Status and stop
1337-customizer video status
1337-customizer video stop

# Rebuild the bundled mpvpaper engine
1337-customizer video build
```

Direct engine script:

```bash
# Use the existing bundled binary if it runs
engine/build-mpvpaper.sh

# Force a local rebuild from engine/mpvpaper-src.tar.gz
engine/build-mpvpaper.sh --force
```

## 5. Desktop widgets

```bash
# Start the widget host using the current config
1337-customizer widgets start

# Open the desktop widget editor (drag widgets, Save & lock)
1337-customizer widgets edit

# Stop the widget host and remove its layer surface
1337-customizer widgets stop

# Show runtime status as JSON
1337-customizer widgets status

# Add a widget by type without opening the GUI
1337-customizer widgets add clock
1337-customizer widgets add weather

# List widgets with index, id, type, monitor and enabled state
1337-customizer widgets list

# Remove by widget id or list index
1337-customizer widgets remove clock-a1b2c3
1337-customizer widgets remove 2

# Reset to the built-in four-widget starter layout
1337-customizer widgets reset
```

The widget host is a separate process with a single-instance lock. Starting or
editing always removes stale widget-host processes first. `add` and `remove`
save immediately; a running locked host reloads the new layout automatically.

Useful checks:

```bash
# List layer surfaces, including the widgets namespace
hyprctl layers -j

# Check that the host is running
1337-customizer widgets status
```

## 6. Slideshow and light/dark schedule

```bash
# Enable the slideshow helper and start it
1337-customizer slideshow start

# Stop the helper and disable the slideshow
1337-customizer slideshow stop

# Show helper status
1337-customizer slideshow status
```

The helper also handles the automatic light/dark schedule when enabled in
**Appearance → Light / dark schedule**.

## 7. Fonts and desktop controls

```bash
# Set the interface font
1337-customizer fonts --ui "Fira Sans 11"

# Set the monospace font
1337-customizer fonts --mono "Fira Code 11"

# Set the document font
1337-customizer fonts --doc "Noto Serif 11"

# Set text scale
1337-customizer fonts --scale 1.1

# Apply several at once
1337-customizer fonts --ui "Fira Sans 11" --mono "Fira Code 11" --scale 1.1
```

Icon themes, cursor themes, cursor size, titlebar buttons, animations and
scrollbars are configured from **Settings → Desktop controls** in the GUI.

## 8. Autostart

```bash
# Enable the login helper
1337-customizer autostart on

# Disable the login helper
1337-customizer autostart off

# Check status
1337-customizer autostart status
```

The autostart entry runs:

```bash
1337-customizer --background
```

## 9. Uninstall

Default uninstall restores the desktop and removes the app plus all app-owned
data.

```bash
./uninstall.sh
```

Keep the library, notes, saved looks and configuration:

```bash
./uninstall.sh --keep-data
```

Skip restoring the previous desktop state:

```bash
./uninstall.sh --no-restore
```

Compatibility aliases:

```bash
./uninstall.sh --restore
./uninstall.sh --purge
./uninstall.sh --all
```

The uninstaller removes:

- installed app code, launcher and menu entry
- desktop icon and autostart entry
- library database, saved layouts, notes and applied picture copies
- configuration, state, logs and caches
- generated `L33T-*` themes and legacy `Hamiid-*` themes
- GTK CSS blocks and terminal theme includes
- terminal theme files and fonts installed by the tool
- legacy Hamiid launcher/desktop/icon/data paths

## 10. Tests and development

```bash
# Compile-check Python
python3 -m compileall -q leet_customizer

# Run all tests
python3 -m unittest discover -s tests -v

# Quick undefined-name/lint check
flake8 leet_customizer --select=F821,F811,E9 --max-line-length=120
```

Run directly as a module:

```bash
python3 -m leet_customizer
python3 -m leet_customizer --version
python3 -m leet_customizer doctor
```

## 11. Environment variables

```bash
# Use a different Python executable
LEET_PYTHON=/usr/bin/python3 ./1337-customizer

# Install to a custom location
LEET_PREFIX="$HOME/.local/share/1337-customizer-custom" ./install.sh

# Uninstall from a custom location
LEET_PREFIX="$HOME/.local/share/1337-customizer-custom" ./uninstall.sh
```

XDG paths used by the app:

```text
Config:   ${XDG_CONFIG_HOME:-~/.config}/1337-customizer
Data:     ${XDG_DATA_HOME:-~/.local/share}/1337-customizer
State:    ${XDG_STATE_HOME:-~/.local/state}/1337-customizer
Cache:    ${XDG_CACHE_HOME:-~/.cache}/1337-customizer
```

## 12. Backend diagnostics

These are optional system commands, useful when a wallpaper backend is not
detected:

```bash
# Compositor outputs and layer surfaces
hyprctl monitors -j
hyprctl layers -j

# awww
awww query
awww img --help
awww restore
awww kill

# DankMaterialShell wallpaper state
dms ipc call wallpaper getFor eDP-1
dms ipc call wallpaper setFor eDP-1 /path/to/image.png
dms ipc call settings get wallpaperFillMode

# GNOME settings
gsettings get org.gnome.desktop.background picture-uri
gsettings get org.gnome.desktop.interface gtk-theme
gsettings get org.gnome.desktop.interface font-name

# mpvpaper
mpvpaper --help
engine/bin/mpvpaper --help
```

## 13. Complete top-level help

```bash
1337-customizer --help
```

```text
usage: 1337-customizer [-h] [--version] [--background]
                       {set,next,undo,theme,video,widgets,slideshow,fonts,restore,doctor,about,export-theme,import-theme,autostart} ...
```

## 14. Common examples

```bash
# Apply a wallpaper on the laptop panel and match the look
1337-customizer set ~/Pictures/wallpapers/night.jpg --monitor eDP-1 --fit crop

# Random next wallpaper from favourites
1337-customizer next --favorites

# Try a video wallpaper without opening the GUI
1337-customizer video start ~/Videos/aurora.mp4 --fit crop

# Start/stop the desktop widgets after editing
1337-customizer widgets start
1337-customizer widgets stop

# Start the slideshow and the login helper
1337-customizer slideshow start
1337-customizer autostart on

# Complete cleanup, including the library and saved looks
./uninstall.sh

# Remove the app but keep the library
./uninstall.sh --keep-data
```
