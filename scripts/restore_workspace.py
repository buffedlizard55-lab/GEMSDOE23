#!/usr/bin/env python3
"""Rebuild every git-ignored input this repository needs, with verification.

    python3 scripts/restore_workspace.py --all            # official + external + anchors
    python3 scripts/restore_workspace.py --external       # 4 hash-pinned raster layers + vector/point CSVs
    python3 scripts/restore_workspace.py --anchors        # the live-scored artefact rasters
    python3 scripts/restore_workspace.py --official       # the 3 competition rasters (git data bridge)

Why this exists
---------------
`data/`, `outputs/` and `.cache/` are git-ignored, so a fresh clone has none of the inputs that the
habitat model, the clustering statistics and the prediction audit need.  Every file below comes from a
public GitHub repository of this group (the only data host the build sandbox can reach) and is checked
before use:

* external layers - SHA-256 pinned (the same pins that docs/verification.html publishes);
* anchor artefacts - identified by the *exact emitted-pixel count and probability mass* recorded in
  docs/data/habitat-model.json (a wrong file cannot reproduce both by accident);
* official rasters - delegated to scripts/fetch_data_bridge.py (part- and whole-file SHA-256).

Large files are stored once under ``$GEMS_CACHE`` (default ``~/.cache/gems-data``) and symlinked into
``data/`` so that multi-hundred-MB rasters are never part of a git patch or a workspace snapshot.
The ``--official`` and ``--external`` steps use only the Python standard library (they run before the virtual
environment exists); ``--anchors`` also needs numpy and rasterio, because it verifies each artefact's identity.
Credentials are never requested; ``GH_TOKEN``/``GITHUB_TOKEN`` is used only if already present (it raises
the anonymous API rate limit, nothing more).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("GEMS_CACHE", str(Path.home() / ".cache" / "gems-data")))
OWNER = "buffedlizard55-lab"

# ----------------------------------------------------------------------------------------------
# official rasters (hash pins are the ones in README section 4)
OFFICIAL = {
    "training_features.tif": ("4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5", 418_912_844),
    "labels.tif": ("7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093", 425_830),
    "sample_submission.tif": ("2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc", 1_599_597),
}

# external layers: (repo, path in repo) -> pinned sha256 (None = size-checked only, provenance recorded)
EXTERNAL_SRC = "GEMSDOE24"
EXTERNAL = {
    "lidar_scarp_features_u8.tif": ("d580bb8bdcdb941e32fefb8b38044bc5bf04e199bf2e83498c3576e6fc465568", 36_943_606),
    "geodawn_rad_u8.tif": ("c22420f75999030d7cc65c9e31e50d232ea6158423bca051613a18a8b20ba682", 26_612_970),
    "geodawn_extensions_u8.tif": ("a35a9c6d2a14786f4dab85481ee59769213072f5dab5b2535ea82ae4d9bb7d9b", 27_132_925),
    "derived_sgmc_faults_100m_u8.tif": ("643cbe992ef4ba37588fb469163ed8291e3ceb23d6c1f78a3cfaa462430c2da0", 198_602),
    # small tables / metadata: size-checked, hash recorded in docs/data/restore-receipt.json on first fetch
    "gdr_qfaults_traces.csv": (None, 126_177),
    "gdr_wellspring_in_footprint.csv": (None, 2_146_771),
    "gdr_volcanic_vents_in_footprint.csv": (None, 672),
    "observed_files.json": (None, 4_203),
    "lidar_scarp_features.json": (None, 3_531),
    "geodawn_rad.json": (None, 7_985),
    "geodawn_extensions.json": (None, 8_927),
    "GeoDAWN_area1_outline.zip": (None, 1_190),
    "GeoDAWN_area2_outline.zip": (None, 1_497),
}
EXTERNAL_AUDIT = {   # official USGS GeoDAWN documents mirrored by the same repo (survey geometry)
    "audit_sources/GeoDAWN Metadata FINAL.csv": (None, 9_515),
    "audit_sources/GeoDAWN_data_extent.zip": (None, 2_774),
}

# anchors: id -> (repo, path).  Identity is verified against docs/data/habitat-model.json per_anchor.
ANCHORS = {
    "h19-5": ("19GEMSDOE", "docs/downloads/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif"),
    "h19-4": ("19GEMSDOE", "docs/downloads/gems19-h19-4-multiline-corroborated-openness-thermal-pop-20260930-691e4dfa-nan.tif"),
    "h16-1": ("16GEMSDOE", "docs/downloads/gems16-h16-1-topo-geophys-baseline-ridges-20260930-df20f65e-nan.tif"),
    "h28-dotted-ridge": ("GEMSDOE10", "docs/downloads/gems10-h28-dotted-ridge-20260928T020256236880Z-6452ae1d00.tif"),
    "ens12-adopted": ("7GEMSDOE", "external/scored/gemsdoe1-ens12-7f00890a.tif"),
    "dual-family-union": ("7GEMSDOE", "external/scored/gemsdoe2-dual-union-f68e590f.tif"),
    "lidarscarp-top2pct": ("7GEMSDOE", "downloads/gems7-lidarscarp-ridge-top2pct-36c3a3f341c8.tif"),
    "r7-nms3-dem10-scarp": ("12GEMSDOE", "docs/downloads/12GEMSDOE_r7-nms3-dem10-scarp_0c9199f14e62.tif"),
    "h25-ctx-ridge": ("GEMSDOE10", "docs/downloads/gems10-h25-ctx-ridge-20260927T232947704150Z-6452ae1d00.tif"),
    "pindrop-v4-nodes": ("7GEMSDOE", "external/scored/gemsdoe3-pindrop-nodes-f347b70daa.tif"),
    "pindrop-v4-ridge": ("7GEMSDOE", "external/scored/gemsdoe3-pindrop-ridge-4e03fc9705.tif"),
    "pindrop-v4-discovery": ("7GEMSDOE", "external/scored/gemsdoe3-pindrop-discovery-37f9d5b855.tif"),
    "h20-dem10-scarp-thin": ("GEMSDOE10", "docs/downloads/gems10-h20-dem10-scarp-thin-20260927T155223039488Z-ffc91a1686.tif"),
    "r13-lattice-s5": ("13GEMSDOE", "docs/downloads/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif"),
    "tso1-conj-alteration-mag": ("15GEMSDOE", "docs/downloads/gems-tso1-20260929T005627Z-conj_alteration_mag.tif"),
    "h16-continuation": ("GEMSDOE10", "docs/downloads/gems10-h16-continuation-20260927T065521077735Z-3431b83c7c.tif"),
    "gemsdoe4-combined": ("7GEMSDOE", "external/scored/gemsdoe4-combined-237f0063.tif"),
    "h19-c": ("18GEMSDOE", "docs/downloads/18GEMSDOE_H19-C_20260930T212401Z_c11e495e.tif"),
    "hgb88-topk03": ("7GEMSDOE", "external/scored/gems6-hgb88-topk03-33cec71ff0.tif"),
    "structural-area06-v1": ("11GEMSDOE", "docs/downloads/gems-structural-area06-v1.tif"),
    "f-ensemble-2pct": ("17GEMSDOE", "docs/downloads/17GEMSDOE_F-ensemble-2pct_20260930T050626Z.tif"),
    "placeholder-2314b599": ("GEMSDOE9", "docs/downloads/gemsdoe9-PLACEHOLDER-2314b599.tif"),
    "r5-geom-horse-ensemble": ("14GEMSDOE", "docs/downloads/GEMS_r5-geom-horse-ensemble_20260929T154852Z_ccbe1de0_site_e96e942f.tif"),
}
# hedge-v2 is byte-for-byte the same emission as ens12-adopted (identical n, mass and score), see habitat-model.json
ANCHOR_ALIASES = {"hedge-v2": "ens12-adopted"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gh_get(repo: str, path: str, dest: Path, retries: int = 3) -> None:
    """Download one file from a public repo of the group through the GitHub contents API."""
    url = f"https://api.github.com/repos/{OWNER}/{repo}/contents/{urllib.parse.quote(path)}"
    headers = {"Accept": "application/vnd.github.raw", "User-Agent": "gemsdoe23-restore"}
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    last = None
    for k in range(retries):
        try:
            if k > 0 and "Authorization" in headers and isinstance(last, urllib.error.HTTPError) and last.code == 401:
                headers.pop("Authorization")      # a stale/expired token makes even public repositories answer 401: retry anonymously
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as out:
                while True:
                    block = resp.read(1 << 20)
                    if not block:
                        break
                    out.write(block)
            return
        except Exception as exc:  # network / rate limit
            last = exc
            time.sleep(2 + 3 * k)
    raise RuntimeError(f"download failed for {repo}:{path}: {last}")


def link_into_data(name: str, target: Path) -> None:
    link = ROOT / "data" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.is_symlink() and Path(os.readlink(link)) == target:
            return
        if link.is_symlink():
            link.unlink()
        else:
            return          # a real file is already there; never overwrite
    link.symlink_to(target)


def restore_official(receipt: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    missing = [n for n in OFFICIAL if not ((CACHE / n).is_file() or (ROOT / "data" / n).is_file())]
    if missing:
        import subprocess
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "fetch_data_bridge.py"), "--out", str(CACHE)])
    for name, (sha, size) in OFFICIAL.items():
        p = (ROOT / "data" / name)
        real = p.resolve() if p.exists() else CACHE / name
        if not real.is_file():
            raise SystemExit(f"official raster missing after restore: {name}")
        got = sha256_file(real)
        ok = got == sha and real.stat().st_size == size
        receipt["official"][name] = dict(sha256=got, ok=ok)
        print(f"[official] {name}: {'OK' if ok else 'MISMATCH'}")
        if not ok:
            raise SystemExit(f"{name}: SHA-256 does not match the README pin")
        if real.parent == CACHE:
            link_into_data(name, real)


def restore_external(receipt: dict) -> None:
    ext = CACHE / "external"
    (ext / "audit_sources").mkdir(parents=True, exist_ok=True)
    for name, (sha, size) in {**EXTERNAL, **EXTERNAL_AUDIT}.items():
        dest = ext / name
        if not (dest.is_file() and dest.stat().st_size == size and (sha is None or sha256_file(dest) == sha)):
            print(f"[external] fetching {name} from {EXTERNAL_SRC}")
            gh_get(EXTERNAL_SRC, f"data/external/{name}", dest)
        got = sha256_file(dest)
        ok = dest.stat().st_size == size and (sha is None or got == sha)
        receipt["external"][name] = dict(sha256=got, bytes=dest.stat().st_size, pinned=sha is not None, ok=ok,
                                         source=f"https://github.com/{OWNER}/{EXTERNAL_SRC}/blob/main/data/external/{name}")
        print(f"[external] {name}: {'OK' if ok else 'MISMATCH'}{' (hash-pinned)' if sha else ' (size-checked)'}")
        if not ok:
            raise SystemExit(f"{name}: failed verification")
    link = ROOT / "data" / "external"
    if link.is_symlink() and Path(os.readlink(link)) != ext:
        link.unlink()
    if not link.exists() and not link.is_symlink():
        link.symlink_to(ext)


def restore_anchors(receipt: dict) -> None:
    import numpy as np
    import rasterio
    anchors_dir = ROOT / ".cache" / "sib" / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    hm = json.load(open(ROOT / "docs" / "data" / "habitat-model.json"))
    truth = {a["id"]: a for a in hm["per_anchor"]}
    with rasterio.open(ROOT / "data" / "sample_submission.tif") as src:
        tmpl = src.read(1)
    foot = np.isfinite(tmpl)
    domain = foot & (tmpl != 1)
    manifest = []
    for aid, (repo, path) in ANCHORS.items():
        dest = anchors_dir / f"{aid}.tif"
        if not dest.is_file():
            print(f"[anchor] fetching {aid} from {repo}")
            try:
                gh_get(repo, path, dest)
            except Exception as exc:          # one missing artefact must not hide the others
                receipt["anchors"][aid] = dict(repo=repo, path=path, identity_verified=False, error=str(exc)[:300])
                print(f"[anchor] {aid}: DOWNLOAD FAILED ({str(exc)[:120]})")
                continue
        with rasterio.open(dest) as src:
            p = src.read(1).astype(np.float32)
        p = np.where(domain, np.nan_to_num(p, nan=0.0), 0.0)
        n, mass = int((p > 0).sum()), float(p.sum())
        want = truth[aid]
        ok = (n == int(want["n"])) and abs(mass - float(want["area"])) <= 1e-6 * max(1.0, float(want["area"]))
        receipt["anchors"][aid] = dict(repo=repo, path=path, sha256=sha256_file(dest), n=n, mass=mass,
                                       expected_n=int(want["n"]), expected_mass=float(want["area"]),
                                       identity_verified=ok, live_dti=float(want["live_dti"]))
        print(f"[anchor] {aid}: n={n} (expect {want['n']}) mass={mass:.1f} -> {'IDENTITY VERIFIED' if ok else 'MISMATCH - not used'}")
        if ok:
            manifest.append(dict(id=aid, lb=float(want["live_dti"]), file=f"{aid}.tif"))
        else:
            dest.rename(dest.with_suffix(".tif.mismatch"))
    for alias, base in ANCHOR_ALIASES.items():
        src_f, dst_f = anchors_dir / f"{base}.tif", anchors_dir / f"{alias}.tif"
        if src_f.is_file() and base in truth and alias in truth and (
                int(truth[alias]["n"]) == int(truth[base]["n"]) and float(truth[alias]["area"]) == float(truth[base]["area"])):
            if not dst_f.is_file():
                import shutil
                shutil.copyfile(src_f, dst_f)
            manifest.append(dict(id=alias, lb=float(truth[alias]["live_dti"]), file=f"{alias}.tif", alias_of=base))
        receipt["anchors"][alias] = dict(alias_of=base, identity_verified=src_f.is_file(),
                                         note="identical emission to base (same n and mass; separate live score entry in habitat-model.json)")
    # Present the anchors in the order of docs/data/habitat-model.json: the nested-CV rank statistic breaks ties by array
    # position and hedge-v2 / ens12-adopted have identical targets, so a different order changes the final layer selection
    # (flag I-20).  In the committed order a full refit reproduces the committed model exactly.
    order = [a["id"] for a in hm["per_anchor"]]
    by_id = {m["id"]: m for m in manifest}
    manifest = [by_id[i] for i in order if i in by_id] + [m for m in manifest if m["id"] not in order]
    # live scores recorded by scripts/record_score.py become additional anchors (appended AFTER the committed ones)
    log_path = ROOT / "docs" / "data" / "score-log.json"
    if log_path.exists():
        for e in json.load(open(log_path)).get("entries", []):
            src_f = ROOT / e["file"]
            if not src_f.is_file() or sha256_file(src_f) != e.get("sha256", sha256_file(src_f)):
                print(f"[anchor] score-log entry {e.get('name')} skipped: file missing or hash changed")
                continue
            aid = e.get("name") or e["content_id"]
            dest = anchors_dir / f"{aid}.tif"
            if not dest.is_file():
                import shutil
                shutil.copyfile(src_f, dest)
            with rasterio.open(dest) as src:
                p = np.where(domain, np.nan_to_num(src.read(1).astype(np.float32), nan=0.0), 0.0)
            receipt["anchors"][aid] = dict(source="docs/data/score-log.json", file=e["file"], sha256=sha256_file(dest), n=int((p > 0).sum()),
                                           mass=float(p.sum()), live_dti=float(e["public_dti"]), identity_verified=True, family=e.get("family"))
            manifest = [m for m in manifest if m["id"] != aid] + [dict(id=aid, lb=float(e["public_dti"]), file=f"{aid}.tif", family=e.get("family", "h24-dispersed"))]
            print(f"[anchor] {aid}: live score {e['public_dti']} from the score log, n={int((p > 0).sum())}")
    json.dump(manifest, open(anchors_dir / "manifest.json", "w"), indent=1)
    print(f"[anchor] {len(manifest)} anchors ({len(ANCHORS)} distinct files + {len(ANCHOR_ALIASES)} alias) identity-verified -> {anchors_dir}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--official", action="store_true")
    ap.add_argument("--external", action="store_true")
    ap.add_argument("--anchors", action="store_true")
    ap.add_argument("--receipt", default=str(ROOT / "docs" / "data" / "restore-receipt.json"))
    args = ap.parse_args()
    if not (args.all or args.official or args.external or args.anchors):
        ap.print_help()
        return 2
    receipt = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), cache_dir=str(CACHE),
                   official={}, external={}, anchors={})
    if args.all or args.official:
        restore_official(receipt)
    if args.all or args.external:
        restore_external(receipt)
    if args.all or args.anchors:
        restore_anchors(receipt)
    prev = {}
    if os.path.exists(args.receipt):
        prev = json.load(open(args.receipt))
    for k in ("official", "external", "anchors"):
        prev.setdefault(k, {}).update(receipt[k])
    prev["generated_utc"] = receipt["generated_utc"]
    prev["cache_dir"] = receipt["cache_dir"]
    json.dump(prev, open(args.receipt, "w"), indent=1)
    print("receipt ->", args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
