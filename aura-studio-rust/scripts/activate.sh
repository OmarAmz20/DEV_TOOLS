# Make the host's dconf settings backend available to the Pixi GLib/GTK stack.
# Without this, Gio.Settings inside the Pixi environment sees schema defaults
# instead of the user's real GNOME/GTK settings.
for modules in /usr/lib/*/gio/modules /usr/lib64/gio/modules /usr/lib/gio/modules; do
    if [ -f "$modules/libdconfsettings.so" ]; then
        case ":${GIO_EXTRA_MODULES:-}:" in
            *":$modules:"*) ;;
            *) export GIO_EXTRA_MODULES="${modules}${GIO_EXTRA_MODULES:+:$GIO_EXTRA_MODULES}" ;;
        esac
        if [ -z "${GSETTINGS_BACKEND:-}" ]; then
            export GSETTINGS_BACKEND=dconf
        fi
        break
    fi
done
