#!/usr/bin/env python3
"""Rewrite absolute paths inside a Pixi environment after the project moved.

Pixi refuses to start an environment whose recorded prefix no longer matches
the current project directory.  Moving a checkout (or moving .pixi into
~/goinfre) is common, so instead of downloading GTK again we rewrite the old
prefix in the text files of the environment.  Binary files are left alone.
"""
from __future__ import annotations

import json
import os
import sys


def _read_prefix(env):
    path = os.path.join(env, "conda-meta", "pixi_env_prefix")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            recorded = handle.read().strip()
    except OSError:
        return ""
    if recorded.endswith("/conda-meta"):
        recorded = recorded[:-len("/conda-meta")]
    return recorded


def _read_manifest(env):
    path = os.path.join(env, "conda-meta", "pixi")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return ""
    return value.get("manifest_path", "") if isinstance(value, dict) else ""


def _project_root(env):
    # <project>/.pixi/envs/default -> <project>
    return os.path.dirname(os.path.dirname(os.path.dirname(env)))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.path.abspath(argv[0]) if argv else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".pixi", "envs", "default")
    expected = os.path.abspath(env)
    new_root = _project_root(expected)
    if len(new_root) < 2:
        return 0

    recorded = _read_prefix(expected)
    manifest = _read_manifest(expected)
    old_root = ""
    if recorded and _project_root(recorded) != new_root:
        old_root = _project_root(recorded)
    elif manifest and os.path.dirname(manifest) != new_root:
        old_root = os.path.dirname(manifest)
    if len(old_root) < 2:
        return 0

    old_bytes = old_root.encode("utf-8", "surrogateescape")
    new_bytes = new_root.encode("utf-8", "surrogateescape")
    changed = 0
    for root, _directories, files in os.walk(expected):
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            try:
                with open(path, "rb") as handle:
                    data = handle.read()
            except OSError:
                continue
            if old_bytes not in data or b"\0" in data:
                continue
            try:
                with open(path, "wb") as handle:
                    handle.write(data.replace(old_bytes, new_bytes))
                changed += 1
            except OSError:
                continue

    print(f"aura-studio: repaired {changed} Pixi environment files "
          f"for {new_root}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
