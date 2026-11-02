# Pixi development activation: use the host's dconf/GSettings database and keep
# the Pixi typelibs ahead of system ones.
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

for schemas in /usr/share/glib-2.0/schemas /usr/local/share/glib-2.0/schemas; do
    if [ -f "$schemas/org.gnome.desktop.interface.gschema.xml" ]; then
        export GSETTINGS_SCHEMA_DIR="$schemas"
        break
    fi
done

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
