#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${1:-data}"
CACHE_DIR=".cache/gems_data"
mkdir -p "$DATA_DIR"

# Link from local cache if available and not yet present in DATA_DIR
if [[ -d "$CACHE_DIR" ]]; then
  for item in training_features.tif labels.tif sample_submission.tif dem_links.json external processed; do
    if [[ -e "${CACHE_DIR}/${item}" && ! -e "${DATA_DIR}/${item}" ]]; then
      ln -s "../${CACHE_DIR}/${item}" "${DATA_DIR}/${item}"
    fi
  done
fi

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
  missing+=("training_features.tif")
fi
for name in "${required[@]}"; do
  [[ -s "${DATA_DIR}/${name}" ]] || missing+=("${name}")
done

# Attempt direct download from user-supplied official Dropbox links or GitHub mirror if missing
if ((${#missing[@]} > 0)); then
  mkdir -p "$CACHE_DIR"
  declare -A DROPBOX_URLS=(
    ["sample_submission.tif"]="https://www.dropbox.com/scl/fi/492cf54eb52b552651c26/example_submission.tif?rlkey=6ec338c4c38e42f1a71587d89&st=dsbe1b5a&dl=1"
    ["labels.tif"]="https://www.dropbox.com/scl/fi/53c0673221d46e8f274e5/existing_faults.tif?rlkey=95324e1c4a9c4690927d03185&st=yv8s5v9a&dl=1"
    ["training_features.tif"]="https://www.dropbox.com/scl/fi/f8fb9d67eb7399d8e5f9c/gems-geodawn-numerical-features.tif?rlkey=63cb2e849093496f98143066e&st=2ybc3d5v&dl=1"
  )
  for fname in "${missing[@]}"; do
    url="${DROPBOX_URLS[$fname]:-}"
    if [[ -n "$url" ]]; then
      echo "Attempting download of ${fname}..."
      if curl -fsSL --connect-timeout 10 "$url" -o "${CACHE_DIR}/${fname}"; then
        ln -sf "../${CACHE_DIR}/${fname}" "${DATA_DIR}/${fname}"
      fi
    fi
  done
fi

# Re-check after download attempt
missing=()
present_features=()
for path in "${feature_files[@]}"; do
  [[ -s "$path" ]] && present_features+=("$path")
done
((${#present_features[@]} == 0)) && missing+=("training_features.tif")
for name in "${required[@]}"; do
  [[ -s "${DATA_DIR}/${name}" ]] || missing+=("${name}")
done

if ((${#missing[@]} == 0)); then
  printf 'Competition rasters are present and verified in %s:\n' "$DATA_DIR"
  sha256sum "${DATA_DIR}/training_features.tif" "${DATA_DIR}/labels.tif" "${DATA_DIR}/sample_submission.tif"
  printf 'Run: .venv/bin/python scripts/prepare_data.py --data-dir %q --out-dir %q/processed\n' "$DATA_DIR" "$DATA_DIR"
  exit 0
fi

cat >&2 <<EOF
Cannot download the missing competition files automatically.
Missing from ${DATA_DIR}: ${missing[*]}
EOF
exit 2
