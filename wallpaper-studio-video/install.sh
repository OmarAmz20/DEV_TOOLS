#!/usr/bin/env bash
# Run as your normal Ubuntu user. No sudo and no GNOME restart.
set -euo pipefail
studio_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$studio_source/install_app.py" "$@"
