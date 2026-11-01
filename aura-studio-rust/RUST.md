# Rust core

This checkout is the hybrid version of Aura Studio:

- **Python** keeps the GTK 4 / libadwaita window and the desktop integration.
- **Rust** does the colour maths, image sampling, palette extraction and
  stylesheet/terminal theme generation.
- The Python modules in `aura_studio/color.py` and `aura_studio/palette.py`
  call the Rust extension when it is available and fall back to the original
  pure-Python implementation otherwise.

## Layout

```text
Cargo.toml                    Rust workspace
crates/aura-core/             pure Rust engine (no Python, no GTK)
  src/color.rs                sRGB, OKLab, OKLCH, WCAG contrast
  src/palette.rs              k-means, accents, accessible light/dark palettes
crates/aura-py/               PyO3 bindings, module name `aura_core`
aura_studio/color.py          Rust-first wrapper + Python fallback
aura_studio/palette.py        Rust-first wrapper + Python fallback
aura_studio/_color_py.py      original pure-Python colour engine
aura_studio/_palette_py.py    original pure-Python palette engine
scripts/build-rust.sh         builds and copies the extension
```

The extension is installed as `aura_core.abi3.so` in the project root. It is
built with the stable ABI for Python 3.12+, so the same file works with the
Pixi Python and with the system Python fallback.

## Build and run

```sh
cd ~/Downloads/aura-studio-rust
pixi run build-rust
pixi run run
```

Or use the normal launcher:

```sh
./aura-studio
```

`install.sh` builds the Rust core automatically after creating the Pixi
environment. If `cargo` is missing, it prints a warning and the app keeps
working with the Python fallback.

## Force the Python path

Useful for comparing results or debugging a binding problem:

```sh
AURA_FORCE_PYTHON=1 ./aura-studio
AURA_FORCE_PYTHON=1 pixi run test-python
```

## Tests

```sh
pixi run build-rust
pixi run test
pixi run test-python
```

`tests/test_rust_core.py` checks the Rust bindings directly and compares the
colour maths with `aura_studio/_color_py.py`.

## Performance

Extracting a palette from the bundled test picture:

| Backend | Time |
|---|---:|
| Rust | ~15 ms |
| Python | ~560 ms |

The rest of the app — GTK and wallpaper backends — is unchanged.

## Cargo builds and goinfre

On 42-school machines, the launcher and installer put build artefacts in
goinfre when it exists:

```sh
CARGO_HOME=$HOME/goinfre/aura-studio/cargo-home
CARGO_TARGET_DIR=$HOME/goinfre/aura-studio/cargo-target
```

Without goinfre, the default `target/` directory in this checkout is used.

## Next steps

The remaining Python work is intentionally kept for now: GTK pages, dialogs,
filesystem thumbnails and wallpaper/terminal backends. They can be moved to
Rust later without changing the public Python API.
