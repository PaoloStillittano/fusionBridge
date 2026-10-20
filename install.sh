#!/usr/bin/env bash
# User-level symlink installation; the checkout must remain in place.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'ERROR: Python 3.9 or newer is required. See docs/installation.md.' >&2
  exit 1
fi
exec python3 "$ROOT/scripts/install.py" "$@"
