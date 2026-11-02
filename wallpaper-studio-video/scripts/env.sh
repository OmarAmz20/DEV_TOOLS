# Development-only Pixi storage setup for Wallpaper Studio Video.
#
# The Ubuntu installer intentionally uses the system Python/GTK so the app can
# use the host's desktop settings and the user-local GTK runtime.  This helper
# is for `pixi run ...` during development.  When ~/goinfre exists, Pixi
# packages, detached environments and pip/uv downloads live there.
# Override the mount with WALLPAPER_STUDIO_GOINFRE.

wallpaper_studio_find_goinfre() {
    base=${WALLPAPER_STUDIO_GOINFRE:-"$HOME/goinfre"}
    if [ -n "$base" ] && [ -d "$base" ] && [ -w "$base" ]; then
        resolved=$(cd -- "$base" 2>/dev/null && pwd -P) || return 1
        printf '%s/%s\n' "$resolved" "wallpaper-studio-video"
        return 0
    fi
    return 1
}

WALLPAPER_STUDIO_GOINFRE_ROOT=$(wallpaper_studio_find_goinfre 2>/dev/null || true)
if [ -n "$WALLPAPER_STUDIO_GOINFRE_ROOT" ]; then
    mkdir -p \
        "$WALLPAPER_STUDIO_GOINFRE_ROOT/pixi-cache" \
        "$WALLPAPER_STUDIO_GOINFRE_ROOT/pixi-home" \
        "$WALLPAPER_STUDIO_GOINFRE_ROOT/pip-cache" \
        "$WALLPAPER_STUDIO_GOINFRE_ROOT/uv-cache" \
        "$WALLPAPER_STUDIO_GOINFRE_ROOT/cache"
    : "${PIXI_HOME:=$WALLPAPER_STUDIO_GOINFRE_ROOT/pixi-home}"
    : "${PIXI_CACHE_DIR:=$WALLPAPER_STUDIO_GOINFRE_ROOT/pixi-cache}"
    : "${RATTLER_CACHE_DIR:=$PIXI_CACHE_DIR}"
    : "${PIP_CACHE_DIR:=$WALLPAPER_STUDIO_GOINFRE_ROOT/pip-cache}"
    : "${UV_CACHE_DIR:=$WALLPAPER_STUDIO_GOINFRE_ROOT/uv-cache}"
    : "${WALLPAPER_STUDIO_CACHE_DIR:=$WALLPAPER_STUDIO_GOINFRE_ROOT/cache}"
    export PIXI_HOME PIXI_CACHE_DIR RATTLER_CACHE_DIR
    export PIP_CACHE_DIR UV_CACHE_DIR WALLPAPER_STUDIO_CACHE_DIR
fi
export WALLPAPER_STUDIO_GOINFRE_ROOT

wallpaper_studio_prepare_pixi_config() {
    root=$1
    config="$root/.pixi/config.toml"
    marker="# Managed by wallpaper-studio-video"
    if [ -n "$WALLPAPER_STUDIO_GOINFRE_ROOT" ]; then
        mkdir -p "$root/.pixi"
        if [ -f "$config" ] && ! head -n 1 "$config" 2>/dev/null | grep -qF "$marker"; then
            return 0
        fi
        cat > "$config" <<CFG
$marker: keep environments and packages in goinfre.
detached-environments = true

[cache]
root = "$PIXI_CACHE_DIR"
CFG
    else
        if [ -f "$config" ] && head -n 1 "$config" 2>/dev/null | grep -qF "$marker"; then
            rm -f "$config"
        fi
        if [ -L "$root/.pixi/envs" ] && [ ! -e "$root/.pixi/envs" ]; then
            rm -f "$root/.pixi/envs"
        fi
    fi
}

wallpaper_studio_find_pixi() {
    candidate=$(command -v pixi 2>/dev/null || true)
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        printf '%s\n' "$candidate"
        return 0
    fi
    for candidate in \
        "$HOME/.local/bin/pixi" \
        "$HOME/.pixi/bin/pixi" \
        "${PIXI_HOME:-$HOME/.pixi}/bin/pixi"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}
