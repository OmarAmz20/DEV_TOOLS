# 1337-Customizer — working notes

## Python packages: Pixi only

- Manage every Python dependency with **Pixi** (`pixi.toml` + `pixi.lock`).
- Add packages with `pixi add <conda-package>` or `pixi add --pypi <package>`.
- Do **not** use pip, uv, poetry or virtualenv to install into this project.
- Run project commands through Pixi:
  - `pixi run run`
  - `pixi run test`
  - `pixi run compile`
  - `pixi run doctor`
- `requirements.txt` is a legacy compatibility file, not the source of truth.

## Caches: goinfre first

When `$HOME/goinfre` exists and is writable, all package and app caches must
live under `$HOME/goinfre/1337-customizer`:

- Pixi package cache and detached environments: `pixi-cache/`
- Pip downloads: `pip-cache/`
- uv downloads: `uv-cache/`
- Thumbnails, previews and other app caches: `cache/`

`scripts/env.sh` sets `PIXI_HOME`, `PIXI_CACHE_DIR`, `RATTLER_CACHE_DIR`,
`PIP_CACHE_DIR`, `UV_CACHE_DIR` and `LEET_CACHE_DIR` accordingly.  The app
itself also detects goinfre in `leet_customizer/constants.py`, so running the
Python module directly still uses the goinfre cache.  Run `./install.sh` or
`./1337-customizer` once so the project-local `.pixi/config.toml` points Pixi
at goinfre; later `pixi run ...` commands reuse it.

Use `LEET_GOINFRE=/some/mount` to point at a different goinfre mount.  Do not
hard-code `/home/<user>/goinfre` paths.  On machines without goinfre everything
falls back to the normal XDG locations.

## Quick checks

```bash
pixi run test
pixi run compile
pixi run lint
./1337-customizer --version
```
