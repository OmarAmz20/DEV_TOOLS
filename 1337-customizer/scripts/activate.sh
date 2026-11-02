# Pixi activation for 1337-Customizer.
#
# The Pixi environment carries its own GTK/GLib stack.  Connect it to the
# host's dconf backend so Gio.Settings reads and writes the user's real desktop
# settings instead of an isolated configuration database.
for modules in /usr/lib/*/gio/modules /usr/lib64/gio/modules /usr/lib/gio/modules; do
    if [ -f "$modules/libdconfsettings.so" ]; then
        case ":${GIO_EXTRA_MODULES:-}:" in
            *":$modules:"*) ;;
            *) export GIO_EXTRA_MODULES="${GIO_EXTRA_MODULES:+$GIO_EXTRA_MODULES:}$modules" ;;
        esac
        if [ -z "${GSETTINGS_BACKEND:-}" ]; then
            export GSETTINGS_BACKEND=dconf
        fi
        break
    fi
done

# Prefer the host's schemas over the older conda-forge copy: desktop
# distributions ship newer keys such as org.gnome.desktop.interface
# accent-color.  Fall back to the Pixi schemas when the host has none.
for schemas in /usr/share/glib-2.0/schemas /usr/local/share/glib-2.0/schemas; do
    if [ -f "$schemas/org.gnome.desktop.interface.gschema.xml" ]; then
        export GSETTINGS_SCHEMA_DIR="$schemas"
        break
    fi
done

# Keep the environment's typelibs ahead of the system ones so GTK and
# gtk4-layer-shell come from the same stack.
if [ -n "${CONDA_PREFIX:-}" ]; then
    for typelibs in "$CONDA_PREFIX/lib/girepository-1.0" \
                    "$CONDA_PREFIX/lib64/girepository-1.0"; do
        if [ -d "$typelibs" ]; then
            case ":${GI_TYPELIB_PATH:-}:" in
                *":$typelibs:"*) ;;
                *) export GI_TYPELIB_PATH="$typelibs${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}" ;;
            esac
        fi
    done
fi

# Some distributions install gtk4-layer-shell outside the default typelib
# search path.  Keep the system directories available after the Pixi ones.
for typelibs in \
    /usr/lib/girepository-1.0 \
    /usr/lib64/girepository-1.0 \
    /usr/lib/x86_64-linux-gnu/girepository-1.0 \
    /usr/local/lib/girepository-1.0; do
    if [ -d "$typelibs" ]; then
        case ":${GI_TYPELIB_PATH:-}:" in
            *":$typelibs:"*) ;;
            *) export GI_TYPELIB_PATH="${GI_TYPELIB_PATH:+$GI_TYPELIB_PATH:}$typelibs" ;;
        esac
    fi
done
