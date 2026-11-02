# Shared storage setup for 1337-Customizer.
#
# Source this from the installer and launcher.  When the 42-school goinfre
# mount exists, Pixi packages, detached environments, pip/uv downloads and the
# app's thumbnail cache all live there instead of in the home quota.
# Override the mount with LEET_GOINFRE.

leet_find_goinfre_root() {
    base=${LEET_GOINFRE:-"$HOME/goinfre"}
    if [ -n "$base" ] && [ -d "$base" ] && [ -w "$base" ]; then
        resolved=$(cd -- "$base" 2>/dev/null && pwd -P) || return 1
        printf '%s/%s\n' "$resolved" "1337-customizer"
        return 0
    fi
    return 1
}

LEET_GOINFRE_ROOT=$(leet_find_goinfre_root 2>/dev/null || true)
if [ -n "$LEET_GOINFRE_ROOT" ]; then
    mkdir -p \
        "$LEET_GOINFRE_ROOT/pixi-cache" \
        "$LEET_GOINFRE_ROOT/pixi-home" \
        "$LEET_GOINFRE_ROOT/pip-cache" \
        "$LEET_GOINFRE_ROOT/uv-cache" \
        "$LEET_GOINFRE_ROOT/cache"
    : "${PIXI_HOME:=$LEET_GOINFRE_ROOT/pixi-home}"
    : "${PIXI_CACHE_DIR:=$LEET_GOINFRE_ROOT/pixi-cache}"
    : "${RATTLER_CACHE_DIR:=$PIXI_CACHE_DIR}"
    : "${PIP_CACHE_DIR:=$LEET_GOINFRE_ROOT/pip-cache}"
    : "${UV_CACHE_DIR:=$LEET_GOINFRE_ROOT/uv-cache}"
    : "${LEET_CACHE_DIR:=$LEET_GOINFRE_ROOT/cache}"
    export PIXI_HOME PIXI_CACHE_DIR RATTLER_CACHE_DIR
    export PIP_CACHE_DIR UV_CACHE_DIR LEET_CACHE_DIR
fi
export LEET_GOINFRE_ROOT

# Point Pixi at the goinfre cache and keep its environments detached from the
# checkout, so `.pixi` contains only a small config file and an environment
# symlink.  A user-supplied config file is never overwritten.
leet_prepare_pixi_config() {
    root=$1
    config="$root/.pixi/config.toml"
    marker="# Managed by 1337-customizer"
    if [ -n "$LEET_GOINFRE_ROOT" ]; then
        mkdir -p "$root/.pixi"
        if [ -f "$config" ] && ! head -n 1 "$config" 2>/dev/null | grep -qF "$marker"; then
            return 0
        fi
        cat > "$config" <<EOF
$marker: keep environments and packages in goinfre.
detached-environments = true

[cache]
root = "$PIXI_CACHE_DIR"
EOF
    else
        if [ -f "$config" ] && head -n 1 "$config" 2>/dev/null | grep -qF "$marker"; then
            rm -f "$config"
        fi
        if [ -L "$root/.pixi/envs" ] && [ ! -e "$root/.pixi/envs" ]; then
            rm -f "$root/.pixi/envs"
        fi
    fi
}

leet_find_pixi() {
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
