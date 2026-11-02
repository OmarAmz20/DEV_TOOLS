# Wallpaper Studio Video — working notes

## Python packages

- Use **Pixi** (`pixi.toml` + `pixi.lock`) for development and tests:
  `pixi add <package>`, `pixi add --pypi <package>`, `pixi run test`.
- On goinfre machines, `source scripts/env.sh` before `pixi install`/`pixi run`
  so Pixi packages and detached environments stay in goinfre.
- Do not pip-install into the development environment.
- The Ubuntu installer intentionally uses the system Python/GTK because the
  app must integrate with the host dconf/GSettings database and the optional
  user-local GTK runtime.  That is the one runtime exception to the Pixi rule.

## Caches

When `$HOME/goinfre` exists and is writable, Pixi packages/environments,
pip/uv downloads and the app cache belong under
`$HOME/goinfre/wallpaper-studio-video`:

- `pixi-cache/`, `pixi-home/`
- `pip-cache/`, `uv-cache/`
- `cache/` for thumbnails, video frames and `video.log`

`scripts/env.sh` sets the Pixi variables.  The app itself also checks goinfre
in `wallpaper_studio/core.py` and `video_wallpaper.py` via
`WALLPAPER_STUDIO_GOINFRE` / `WALLPAPER_STUDIO_CACHE_DIR`.  Never hard-code a
user's home path.

## Dock

- `wallpaper_studio/dock.py` — config, app entries, styling, process manager.
- `wallpaper_studio/dock_daemon.py` — GTK4/layer-shell dock host.
- `wallpaper_studio/dock_page.py` — Dock page and app editor.
- Dock config lives beside the studio config as `dock.json`; state/PID are
  managed inside `core.CONFIG_DIR`/runtime cache. Do not enable it automatically
  without the user's page toggle.

## Video wallpaper

- `video_wallpaper.py` — state, process control, extension helpers.
- `video_engine.py` — supervisor; restarts the renderer with backoff.
- `video_renderer.py` — chooses GTK 4 (Wayland) or GTK 3 (X11) and dispatches.
- `video_renderer_gtk3.py`, `video_renderer_gtk4.py` — GStreamer renderers.
- `video_extension/` — GNOME Shell Wayland bridge (Clutter.Clone).
- On X11 the renderer is a desktop-type window; on Wayland the extension
  reparents the GTK 3 actor or clones the GTK 4 actor into the background
  group. Wayland needs one logout/login after installing the extension.
