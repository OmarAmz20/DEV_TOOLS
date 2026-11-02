# Validation — Wallpaper Studio Video 2.2

Checks performed on 30 October 2026. The original wallpaper backend is unchanged byte-for-byte from the previously delivered 2.0 source.

## New checks in 2.1

- **51 unit checks passed on Python 3.10 and Python 3.12**, including activity timing, ignoring the arming click, continuous motion, one-shot locking, rejecting dead proxies, lock-confirmation failures, releasing inhibition, rejecting requests from a previous helper, archive corruption and path/symlink validation.
- The real GTK editor rendered the new Session page. Page/control/dialog checks passed against GTK 4.14/libadwaita 1.5 and the extracted Ubuntu 22.04 GTK 4.6/libadwaita 1.1 runtime. All seven pages were visited. The older mixed test runtime still emits nonfatal GtkImage finalization warnings during rapid dialog tests.
- The delivered native ELF launcher verified its embedded checksum and automatically extracted, installed and opened the GUI from a download path containing spaces. Reopening the same file skipped setup. An update preserved the profile and override byte-for-byte, private notes, and a durable applied image. The Applications launcher was created.
- The executor cannot switch to an unprivileged UID. Only the normal-user UID guard was mocked for this installation test; filesystem, extraction, installer, desktop entry and launcher operations ran for real in a disposable home. The delivered launcher still rejects root execution.
- Native X11 idle reads and a private test display exercise keyboard and mouse activity. The guard uses real calls to a private test D-Bus service for inhibit flags 13, a single lock request, activation readback and uninhibit. No real desktop or authentication service is controlled by that test.
- Bash syntax and Python compilation passed. The single-file build needs no FUSE and uses a statically linked launcher around the system Python 3 bootstrap.

These checks do not certify real password authentication on the recipient's school desktop. Automatic locking is offered only when an actual supported locker is running. A GNOME forwarding proxy with no ScreenShield, or a LightDM greeter switch alone, is rejected. Administrator logout timers remain in force; the app cannot promise an unlimited login. The first input is observed after it occurs and may reach an app before the lock activates.

## Video wallpaper checks in 2.2

- **55 unit checks passed** (Python 3.14 in this development environment), including the new video state, extension lookup, undo-with-video and CLI parsing paths.
- The video engine was exercised with a disposable config/cache directory and a fake renderer: it started, wrote the runtime PID file, was detected as running, and stopped both renderer and supervisor cleanly.
- The video renderer reports a clear missing-sink error when neither GStreamer GTK sink is present. The GTK 3 and GTK 4 renderer modules both import cleanly in separate processes; the dispatcher chooses GTK 4 on Wayland and GTK 3 on X11 when available.
- `extension.js` passed a JavaScript module syntax check.
- The single-file installer extracted, installed the app, copied the GNOME Shell extension, and created the video autostart entry in a disposable home.
- The GNOME Shell extension was **not** runtime-tested inside a live GNOME Shell in this development environment (the host session is Hyprland). It must be validated on the target Ubuntu GNOME session after installing `gstreamer1.0-gtk3` and logging out/in once.

## Previous 2.0 validation

Checks performed on 29 October 2026. This is a source release adapted from upstream revision `7db414f`.

## Automated checks

**33 unit checks passed with both Python 3.10 and Python 3.12.** They cover:

- Preserving the existing personal dconf profile and GNOME service override byte-for-byte.
- Light-only changes preserving the dark variant; wallpaper setting preflight and rollback.
- Detecting dconf commit warnings even when `gsettings` exits with status zero.
- One normal login for a newly created override; refusing an unrelated override and root execution.
- All seven colour recipes in light/dark, stronger contrast, and varied custom accents. Main text meets 4.5:1, secondary text meets 4.5:1, and the stronger main-text option meets 7:1 on the tested opaque surfaces. Accent button labels meet 4.5:1.
- Malformed configuration recovery; rejecting invalid theme imports; excluding private paths and hooks from exports.
- Keeping existing custom CSS, durable image copies and Terminal profiles added after installation.
- Undo using the retained image copy; failed restore retaining recovery data and theme files.
- Automatic colour following using the last applied recipe instead of draft edits.

Python compilation and Bash syntax checks passed.

## Version 2 additions

- Every colour recipe in both modes, and every window structure, loaded without CSS parser errors in the actual GTK 4 editor, including GTK 4.6. The same recipe CSS was also loaded by GTK 3.
- The live window sample, saved named looks, desktop presets, widget layout controls and layout import/export dialogs were exercised.
- Seven real GTK 3 widgets ran in the test display. Checks covered desktop/taskbar hints, CPU updates, timer completion and the edit → move → save → lock cycle.
- Generated cursor files loaded successfully with the native Xcursor library at all four bundled sizes.
- Actual dconf integration verified pixel icon/cursor application, switching back, manual-choice ownership and restoring desktop controls.
- Widget layout exports exclude notes, and importing a layout does not write settings or enable widgets.
- The delivered 1.0 wallpaper backend was compared byte-for-byte with the 2.0 source: it is unchanged.

## Real GTK interface

The actual application was rendered in a private X11 test display using:

| Runtime | Result |
| --- | --- |
| GTK 4.14 / libadwaita 1.5 / Python 3.12 | Gallery/editor rendered; page and dialog checks passed |
| Ubuntu 22.04 GTK 4.6 / libadwaita 1.1 / Python 3.10 packages | Application opened; the same editor and dialog checks passed |

The GUI checks exercised all six pages, recipe selection, accent editing, control synchronization after import, image/folder/theme file pickers, the colour picker, and the restore confirmation's cancel path. They verified that preview interactions did not call wallpaper or theme application. Initial wallpaper discovery selected the picture once, without a repeating idle callback.

The older GTK runtime was extracted into a test prefix on an Ubuntu 24.04 host, using the host's newer GLib and some system libraries. It emitted GTK image finalization warnings during rapid dialog/control tests. This checks the older GTK/libadwaita APIs; it is not a full Ubuntu 22.04 desktop certification.

## Dconf and installation integration

Against a real dconf service and session D-Bus in a disposable account directory:

- Native `gsettings` wallpaper writes were read back successfully.
- Set, second set, undo, theme application, draft/applied recipe isolation, and full restore passed.
- Existing custom GTK CSS was recovered exactly after restore.
- Existing profile and service override bytes were unchanged.
- Installation and an update completed; applied image copies survived both.
- The installed launcher ran successfully.
- The uninstall body was executed against a disposable account directory with its UID guard mocked. It removed the application, private runtime, launcher, fonts and icon assets, while preserving native-profile bytes, saved image copies and private notes.

The GNOME Shell service's active/loaded status and the test process's root check were mocked for those integration checks. No real GNOME Shell process was restarted or controlled.

The optional runtime downloader retrieved and verified 28 official Ubuntu 24.04 packages, extracted them without system installation, and successfully loaded GTK 3, GTK 4 and libadwaita. Installation using that private runtime also passed with spaces in the account path. The Ubuntu 22.04 package family was separately exercised for GUI compatibility; its download fallback was not tested inside a full Ubuntu 22.04 installation.

Video testing extracted a frame from a generated MP4 with FFmpeg, derived light/dark palettes, and verified that the applied-image copy survived preview-cache removal.

## Practical limits

No access to the recipient's school computer or live GNOME 42 session was available. The native wallpaper method is the one already reported working by the recipient; the checks here validate the client behavior around it. Normal GNOME presentation inhibition, a real screen lock, a long-running rotation schedule, physical multi-monitor behavior, the optional User Themes panel stylesheet and interaction with desktop-icons extensions need verification in that actual GNOME session. The widgets were exercised in a test X11 display, not inside a running GNOME Shell window manager.

Videos use still frames. Lock-screen appearance remains GNOME's native blurred wallpaper. Applications vary in their response to theme changes, and some need reopening.
