#!/usr/bin/env bash
# Acquire the official competition rasters with no manual input, then verify them.
#
# Order of attempts (every byte hash-verified, fails closed):
#   1. the group's public git data bridge   (scripts/fetch_data_bridge.py)
#   2. the Dropbox convenience mirrors named in that bridge's manifest
#   3. the DrivenData data tab              -- NOT attempted: it requires a login and
#                                             this project never authenticates to anything.
#
# The previous version of this script hard-coded Dropbox URLs whose rlkey/st values did
# not match the shares the project owner supplied, so it 404'd even with network access.
# That is recorded as an irregularity; the URLs now come from the bridge manifest, which
# pins the SHA-256 of every file it names.
set -euo pipefail
cd "$(dirname "$0")/.."
DATA_DIR="${GEMS_DATA_DIR:-data}"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

echo "== acquiring official rasters into ${DATA_DIR} =="
if "$PY" scripts/fetch_data_bridge.py --out "$DATA_DIR"; then
  echo "== acquisition verified =="
else
  echo "!! acquisition failed; see the messages above. Nothing was written." >&2
  exit 1
fi

echo "== preparing derived arrays =="
"$PY" scripts/prepare_data.py
