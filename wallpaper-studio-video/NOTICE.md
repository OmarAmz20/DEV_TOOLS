# Sources and attribution

Wallpaper Studio Video is a fork of **Wallpaper Studio Plus 2.1** with an added video-wallpaper engine.

Wallpaper Studio Plus is a derivative of **Wallpaper Studio**, by **Adil Asselman (yuxev)**.

- Upstream: https://github.com/yuxev/wallpaper-studio
- Starting revision: `7db414f` on `main`, retrieved 29 October 2026.
- License: MIT. The original copyright and permission notice are included in `LICENSE`.
- The image palette algorithm and bundled wallpaper collection originate from that repository. The interface, wallpaper backend, session helper, editable recipes, installer and recovery behavior were adapted or rewritten for this distribution.
- This is an independent derivative, not an official upstream release or endorsement.

The unmodified **adw-gtk3 v6.5** theme assets in `vendor/adw-gtk3` and `vendor/adw-gtk3-dark` are used as an optional GTK 3 base.

- Project and source: https://github.com/lassekongo83/adw-gtk3/tree/v6.5
- Distributed release: https://github.com/lassekongo83/adw-gtk3/releases/tag/v6.5
- License: GNU Lesser General Public License, version 2.1; full text at `vendor/ADW-GTK3-LICENSE`.
- Copyright: the adw-gtk3 project contributors; retain the notices in the distributed assets.
- You can replace these theme files or install your own adw-gtk3 theme. The application imports their CSS by file path; the theme is not embedded into a compiled application.

The colour recipes are adaptations inspired by Catppuccin, Nord, Tokyo Night, Gruvbox, Dracula and Rosé Pine. These names identify palette inspiration. This archive does not bundle those projects' application themes or claim affiliation.

The pixel icons, cursor images, brick tile and additional window-style code are original assets distributed under the project's MIT license. Mushroom Kingdom is an original Mario-inspired style; it is not an official Nintendo theme and includes no Nintendo game assets.

The unmodified Silkscreen font in `data/fonts/Silkscreen-Regular.ttf` is Copyright 2001 The Silkscreen Project Authors (https://github.com/googlefonts/silkscreen), distributed under the SIL Open Font License 1.1. Its full license is `data/fonts/OFL.txt`. The font was obtained from https://github.com/google/fonts/tree/main/ofl/silkscreen. Its family name and binary data are unchanged.

The optional runtime downloader retrieves Ubuntu packages from official Ubuntu HTTPS archives, checks package-list and package SHA-256 checksums, and extracts them into the current user's application folder. Those downloaded packages retain their own copyright and licensing files under the runtime's `usr/share/doc/` tree. No runtime binaries are included in this source archive.

## Video wallpaper

The video engine (`wallpaper_studio/video_wallpaper.py`, `video_engine.py`, `video_renderer.py` and `video_extension/`) is original code distributed under this project's MIT license. Its GNOME Shell bridge uses the public technique of cloning a renderer window actor into GNOME Shell's background group, an approach also used by Hanabi and DING; no GPL source code from those projects is copied. Video playback uses the system GStreamer installation and GTK 3. The still-image fallback continues to use the native GNOME wallpaper backend.
