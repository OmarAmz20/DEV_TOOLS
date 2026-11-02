#!/usr/bin/env bash
# Restore Plus changes and remove its app. Keep saved images and recovery data.
set -euo pipefail
studio_data="${XDG_DATA_HOME:-$HOME/.local/share}"
studio_config="${XDG_CONFIG_HOME:-$HOME/.config}"
studio_parent="$studio_data/wallpaper-studio-video"
studio_launcher="$studio_parent/launch.sh"
if [ "$(id -u)" = 0 ]; then
    echo 'Run as your normal desktop user, without sudo.' >&2
    exit 1
fi
if [ -x "$studio_launcher" ]; then
    "$studio_launcher" video stop >/dev/null 2>&1 || true
    "$studio_launcher" dock stop >/dev/null 2>&1 || true
    "$studio_launcher" widgets stop
    "$studio_launcher" stop
    "$studio_launcher" restore --scope all
fi
if [ -L "$HOME/.local/bin/wallpaper-studio-video" ] && [ "$(readlink -- "$HOME/.local/bin/wallpaper-studio-video")" = "$studio_launcher" ]; then
    rm -f -- "$HOME/.local/bin/wallpaper-studio-video"
fi
rm -f -- "$studio_data/applications/io.github.WallpaperStudioVideo.desktop" \
    "$studio_data/icons/hicolor/scalable/apps/io.github.WallpaperStudioVideo.svg" \
    "$studio_config/autostart/wallpaper-studio-video-session.desktop" \
    "$studio_config/autostart/wallpaper-studio-video-widgets.desktop" \
    "$studio_config/autostart/wallpaper-studio-video-video.desktop" \
    "$studio_config/autostart/wallpaper-studio-video-dock.desktop"
rm -rf -- "$studio_data/gnome-shell/extensions/wallpaper-studio-video@local"
rm -f -- "$studio_config/video-runtime.json"
# The wallpaper images, backup, profile and working Shell override stay intact.
rm -rf -- "$studio_parent/app" "$studio_parent/runtime"
rm -f -- "$studio_launcher"
rm -f -- "$studio_parent/bundle.json"
rm -f -- "$studio_config/fontconfig/conf.d/91-wallpaper-studio-video-pixel.conf"
rm -rf -- "$studio_data/fonts/wallpaper-studio-video" "$studio_data/icons/Studio Pixel" \
    "$studio_data/icons/Studio Pixel Pearl" "$studio_data/icons/Studio Pixel Violet" \
    "$studio_data/icons/Studio Pixel Gold" "$studio_data/icons/Studio Pixel Lime" "$studio_data/icons/Studio Pixel Ice"
echo 'Wallpaper Studio Video removed. Saved pictures, recovery settings and your working native wallpaper setup were kept.'
