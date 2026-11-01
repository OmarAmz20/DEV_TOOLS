#!/bin/sh
# Build the optional Rust core and place it next to the Python package.
# Run this through `pixi run build-rust` so cargo comes from the project env.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET_DIR=${CARGO_TARGET_DIR:-"$ROOT/target"}

cd "$ROOT"
cargo build --release -p aura-py

library=""
for candidate in \
    "$TARGET_DIR/release/libaura_core.so" \
    "$TARGET_DIR/release/libaura_core.dylib" \
    "$TARGET_DIR/release/aura_core.dll"; do
    if [ -f "$candidate" ]; then
        library=$candidate
        break
    fi
done

if [ -z "$library" ]; then
    echo "build-rust: could not find the compiled aura_core library" >&2
    exit 1
fi

cp "$library" "$ROOT/aura_core.abi3.so"
chmod 755 "$ROOT/aura_core.abi3.so"
printf 'Rust core built: %s\n' "$ROOT/aura_core.abi3.so"
