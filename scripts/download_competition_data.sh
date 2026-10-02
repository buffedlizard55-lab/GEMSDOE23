#!/usr/bin/env bash
set -euo pipefail

# DrivenData serves the GEMS files only to registered/authenticated competitors.
# This script intentionally does not accept passwords, cookies, or tokens and
# never attempts to bypass that access control.
DATA_DIR="${1:-data}"
required=(labels.tif sample_submission.tif)
missing=()
feature_files=("${DATA_DIR}/training_features.tif" "${DATA_DIR}/numeric_features.tif")
present_features=()
for path in "${feature_files[@]}"; do
  [[ -s "$path" ]] && present_features+=("$path")
done

if ((${#present_features[@]} > 1)); then
  printf 'Ambiguous feature inputs: both training_features.tif and numeric_features.tif are present. Choose the file verified against the official data inventory.\n' >&2
  exit 2
elif ((${#present_features[@]} == 0)); then
  missing+=("training_features.tif or numeric_features.tif")
fi
for name in "${required[@]}"; do
  [[ -s "${DATA_DIR}/${name}" ]] || missing+=("${name}")
done

if ((${#missing[@]} == 0)); then
  printf 'Competition rasters are already present in %s.\n' "$DATA_DIR"
  printf 'Run: python scripts/prepare_data.py --data-dir %q --out-dir %q/processed\n' "$DATA_DIR" "$DATA_DIR"
  exit 0
fi

cat >&2 <<EOF
Cannot download the missing competition files automatically.
The official data page redirects unauthenticated visitors to DrivenData login:
  https://www.drivendata.org/competitions/306/competition-doe-gems/data/
Missing from ${DATA_DIR}: ${missing[*]}

No credentials were supplied to this environment. Download the files through an
authorized competition account and place them in ${DATA_DIR}/; then rerun this
script and scripts/prepare_data.py. Never put account passwords, session cookies,
or access tokens in this repository or in chat.
EOF
exit 2
