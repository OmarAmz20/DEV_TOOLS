// Wallpaper Studio Video — GNOME Shell background bridge.
//
// The renderer is an ordinary GTK/GStreamer process.  On Wayland GNOME does
// not implement wlr-layer-shell, so this extension places the renderer in
// GNOME Shell's background group.  The GTK 3 widget sink keeps rendering while
// the window actor is reparented; the GTK 4 paintable sink is cloned and the
// original window is minimised.  This is the public GNOME live-wallpaper
// technique used by several extensions; no code is copied from them.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const CONFIG_DIR = GLib.build_filenamev([GLib.get_user_config_dir(), 'wallpaper-studio-video']);
const STATE_FILE = GLib.build_filenamev([CONFIG_DIR, 'video.json']);
const RUNTIME_FILE = GLib.build_filenamev([CONFIG_DIR, 'video-runtime.json']);
const SINK_FILE = GLib.build_filenamev([CONFIG_DIR, 'video-sink.json']);
const TITLE_PREFIX = '@wallpaper-studio-video!';
const TICK_MS = 1000;

function read_json(path) {
    try {
        const file = Gio.File.new_for_path(path);
        const [, contents] = file.load_contents(null);
        return JSON.parse(new TextDecoder().decode(contents));
    } catch (_error) {
        return {};
    }
}

export default class WallpaperStudioVideoExtension extends Extension {
    enable() {
        this._clones = new Map();
        this._hidden = new Set();
        this._reparented = new Map();
        this._sync();
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, TICK_MS, () => {
            this._sync();
            return GLib.SOURCE_CONTINUE;
        });
    }

    disable() {
        if (this._timer) {
            GLib.source_remove(this._timer);
            this._timer = 0;
        }
        this._clearClones();
        this._restoreReparented();
        for (const window of this._hidden) {
            try {
                window.unminimize();
            } catch (_error) {
                // The renderer may already be gone.
            }
        }
        this._hidden.clear();
        this._clones = null;
        this._hidden = null;
        this._reparented = null;
    }

    _sync() {
        const state = read_json(STATE_FILE);
        const runtime = read_json(RUNTIME_FILE);
        const sink = read_json(SINK_FILE);
        const pid = Number(runtime.renderer_pid ?? 0);
        const ready = runtime.ready !== false;
        const enabled = Boolean(state.enabled) && pid > 0 && ready;
        this._pruneReparented();
        const actor = enabled ? (this._findReparented(pid) || this._findRenderer(pid)) : null;

        if (!actor) {
            this._clearClones();
            this._restoreReparented();
            return;
        }

        const window = actor.get_meta_window();
        const useReparent = sink.sink === 'gtksink' && Number(sink.pid) === pid;
        if (useReparent) {
            this._clearClones();
            try {
                this._reparent(actor, window);
                return;
            } catch (error) {
                logError(error, 'Wallpaper Studio Video: reparent failed, using a clone');
                this._restoreReparented();
            }
        }
        this._restoreReparented();
        this._hideRenderer(window);
        this._ensureClones(actor);
    }

    _findReparented(pid) {
        for (const window of this._reparented.keys()) {
            try {
                if (window.get_pid() === pid)
                    return window.get_compositor_private();
            } catch (_error) {
                // Stale window.
            }
        }
        return null;
    }

    _pruneReparented() {
        for (const window of [...this._reparented.keys()]) {
            try {
                if (!window.get_compositor_private())
                    this._reparented.delete(window);
            } catch (_error) {
                this._reparented.delete(window);
            }
        }
    }

    _findRenderer(pid) {
        for (const actor of global.get_window_actors()) {
            const window = actor.get_meta_window();
            if (!window)
                continue;
            const title = window.get_title() ?? '';
            let windowPid = 0;
            try {
                windowPid = window.get_pid();
            } catch (_error) {
                windowPid = 0;
            }
            if (windowPid === pid || title.startsWith(TITLE_PREFIX))
                return actor;
        }
        return null;
    }

    _hideRenderer(window) {
        if (!window)
            return;
        try {
            window.skip_taskbar = true;
            window.skip_pager = true;
            window.stick();
            if (!window.minimized)
                window.minimize();
            this._hidden.add(window);
        } catch (error) {
            logError(error, 'Wallpaper Studio Video: could not hide the renderer');
        }
    }

    _reparent(actor, window) {
        const group = Main.layoutManager._backgroundGroup;
        if (!group || !window)
            return;
        if (!this._reparented.has(window))
            this._reparented.set(window, actor.get_parent());
        const parent = actor.get_parent();
        if (parent !== group) {
            if (parent)
                parent.remove_child(actor);
            group.add_child(actor);
        }
        const index = window.get_monitor();
        const monitor = Main.layoutManager.monitors[index] ?? Main.layoutManager.primaryMonitor;
        if (monitor) {
            try {
                window.move_resize_frame(true, monitor.x, monitor.y, monitor.width, monitor.height);
            } catch (_error) {
                // Some window managers ignore client moves.
            }
            actor.set_position(monitor.x, monitor.y);
            actor.set_size(monitor.width, monitor.height);
        }
        actor.set_reactive(false);
        window.skip_taskbar = true;
        window.skip_pager = true;
        window.stick();
        window.lower();
    }

    _restoreReparented() {
        if (!this._reparented)
            return;
        for (const [window, parent] of this._reparented) {
            try {
                const actor = window.get_compositor_private();
                if (actor && parent && actor.get_parent() !== parent) {
                    const current = actor.get_parent();
                    if (current)
                        current.remove_child(actor);
                    parent.add_child(actor);
                }
            } catch (_error) {
                // The renderer window may already be gone.
            }
        }
        this._reparented.clear();
    }

    _ensureClones(source) {
        const group = Main.layoutManager._backgroundGroup;
        if (!group)
            return;
        const actors = group.get_children().filter(child => child instanceof Meta.BackgroundActor);
        const targets = actors.length ? actors : [group];

        for (const [target, clone] of this._clones) {
            if (!targets.includes(target) || clone.source !== source) {
                try {
                    clone.destroy();
                } catch (_error) {
                    // The background actor already destroyed it.
                }
                this._clones.delete(target);
            }
        }

        for (const target of targets) {
            let clone = this._clones.get(target);
            if (!clone) {
                if (target instanceof Meta.BackgroundActor)
                    target.set_layout_manager(new Clutter.BinLayout());
                clone = new Clutter.Clone({ source });
                clone.set_reactive(false);
                target.add_child(clone);
                this._clones.set(target, clone);
            }
            clone.set_position(0, 0);
            clone.set_size(target.width, target.height);
        }
    }

    _clearClones() {
        if (!this._clones)
            return;
        for (const clone of this._clones.values()) {
            try {
                clone.destroy();
            } catch (_error) {
                // Already destroyed with the background group.
            }
        }
        this._clones.clear();
    }
}
