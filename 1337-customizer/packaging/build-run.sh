#!/usr/bin/env bash
# Build dist/1337-Customizer.run — a self-extracting per-user installer.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
PAYLOAD="$DIST/1337-payload.tar.gz"
OUT="$DIST/1337-Customizer.run"
mkdir -p "$DIST"

tar -czf "$PAYLOAD" -C "$(dirname -- "$ROOT")" \
  --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='docs' --exclude='dist' --exclude='tests' \
  "1337-customizer"

python3 - "$PAYLOAD" "$OUT" <<'PY'
from pathlib import Path
import sys

payload = Path(sys.argv[1]).read_bytes()
out = Path(sys.argv[2])
header = '''#!/usr/bin/env bash
# 1337-Customizer — self-extracting installer
set -euo pipefail
TMP="$(mktemp -d "${TMPDIR:-/tmp}/1337-customizer.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT INT TERM
PAYLOAD_LINE=__PAYLOAD_LINE__
tail -n +"$PAYLOAD_LINE" "$0" | tar -xzf - -C "$TMP"
if [ "$#" -eq 0 ]; then
  "$TMP/1337-customizer/install.sh"
  cleanup
  trap - EXIT INT TERM
  exec "$HOME/.local/bin/1337-customizer"
fi
"$TMP/1337-customizer/install.sh" "$@"
exit 0
__PAYLOAD_BELOW__
'''
# Count lines including the final newline before the binary payload.
lines = header.replace("__PAYLOAD_LINE__", "0").count("\n") + 1
header = header.replace("__PAYLOAD_LINE__", str(lines))
out.write_bytes(header.encode() + payload)
out.chmod(0o755)
PY
rm -f "$PAYLOAD"
echo "Built $OUT"
