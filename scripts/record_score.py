#!/usr/bin/env python3
"""Record a live public score and turn it into a NEW ANCHOR for the habitat refit.

    python scripts/record_score.py --score 0.2341 --id 38539dc6 [--name h30] [--family h24-dispersed] [--note "..."]

Why this matters: every live score is an observation of the hidden truth (it tightens |G|, q and the habitat
weights), and one slot is worth more than any amount of further offline work.

What it does
  1. finds the uploaded file by the first 8 hex of its SHA-256 (docs/data/candidates.json, the submission manifest,
     then every raster in docs/downloads);
  2. appends {content_id, name, public_dti, file, family, recorded_utc} to docs/data/score-log.json;
  3. with the default rebuild: scripts/restore_workspace.py --anchors reads that log and adds the file to
     .cache/sib/anchors/ (identified by its own emitted-pixel count and mass; family = the same family as the other
     emissions built from the H24 ranking, so leave-one-family-out CV does not see near-duplicates as independent), then
     scripts/fit_habitat_model.py refits into docs/data/habitat-model-refit.json and outputs/habitat_score_refit.npy.
     The COMMITTED model (docs/data/habitat-model.json) is not overwritten, so the shipped H24 stays reproducible;
     promote the refit deliberately after reading flag I-20 (anchor order / tie handling).
Before 2026-10-02 this script wrote the log but nothing read it, and the 'refit' re-ran on the same 24 anchors.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_REL = os.path.join("docs", "data", "score-log.json")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_file(content_id: str, root: str = ROOT):
    """Return (relative path, full sha256) of the raster whose SHA-256 starts with ``content_id``."""
    cid = content_id.lower()
    seen = []
    cand = os.path.join(root, "docs", "data", "candidates.json")
    if os.path.exists(cand):
        for c in json.load(open(cand)).get("candidates", []):
            for key in ("nan", "allfinite"):
                f = c.get(key) or {}
                if f.get("sha256", "").startswith(cid):
                    seen.append(("docs/" + f["href"], f["sha256"]))
    man = os.path.join(root, "docs", "data", "submission-manifest.json")
    if os.path.exists(man):
        for key in ("primary", "compatibility"):
            f = json.load(open(man)).get(key) or {}
            if f.get("sha256", "").startswith(cid):
                seen.append(("docs/" + f["href"], f["sha256"]))
    for path in sorted(glob.glob(os.path.join(root, "docs", "downloads", "*.tif"))):
        full = sha256_file(path)
        if full.startswith(cid):
            seen.append((os.path.relpath(path, root), full))
    uniq = sorted(set(seen))
    if len({s[1] for s in uniq}) > 1:
        raise SystemExit(f"id {content_id} is ambiguous: {uniq}")
    return uniq[0] if uniq else (None, None)


def add_entry(log_path: str, entry: dict) -> dict:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = json.load(open(log_path)) if os.path.exists(log_path) else dict(entries=[])
    log["entries"] = [e for e in log["entries"] if e.get("content_id") != entry["content_id"]] + [entry]
    log["generated_utc"] = entry["recorded_utc"]
    json.dump(log, open(log_path, "w"), indent=1)
    return log


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score", type=float, required=True)
    ap.add_argument("--id", required=True, help="first 8 hex of the submission's sha256")
    ap.add_argument("--name", default="", help="anchor id, e.g. h30 (default: the file's stem)")
    ap.add_argument("--family", default="h24-dispersed", help="cross-validation family of this emission")
    ap.add_argument("--note", default="")
    ap.add_argument("--no-rebuild", action="store_true")
    a = ap.parse_args()
    if not (0.0 <= a.score <= 1.0):
        sys.exit("score must be in [0, 1]")
    if len(a.id) < 6:
        sys.exit("--id must be at least 6 hex characters of the file's SHA-256")
    rel, full = find_file(a.id)
    if rel is None:
        sys.exit(f"no raster under docs/ has a SHA-256 starting with {a.id}; the refit needs the file itself")
    name = a.name or os.path.splitext(os.path.basename(rel))[0]
    entry = dict(recorded_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), content_id=a.id, sha256=full, name=name,
                 file=rel, family=a.family, public_dti=a.score, note=a.note)
    add_entry(os.path.join(ROOT, LOG_REL), entry)
    print("recorded", json.dumps(entry))
    if not a.no_rebuild:
        os.chdir(ROOT)
        for cmd in ([sys.executable, "scripts/restore_workspace.py", "--anchors"],
                    [sys.executable, "scripts/fit_habitat_model.py", "--out", "docs/data/habitat-model-refit.json",
                     "--score-out", "outputs/habitat_score_refit.npy"],
                    [sys.executable, "scripts/build_site.py"]):
            print("$", " ".join(cmd))
            subprocess.run(cmd, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
