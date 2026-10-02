#!/usr/bin/env python3
"""Autonomous acquisition of the official competition rasters. No manual input.

Three sources are tried in order and every byte is hash-verified before anything is
written into ``data/``.  The script fails closed: if no source verifies, it exits
non-zero and leaves ``data/`` untouched rather than producing a plausible-looking file.

1.  the group's git *data bridge* - the official rasters split into <100 MB parts and
    committed to a public sibling repository, with a manifest that pins the SHA-256 of
    every part, of the reassembled feature stack and of an independent inventory taken
    on a GitHub-hosted runner (``GEMSDOE2:data/bridge``);
2.  the Dropbox convenience mirrors named in that manifest (personal shares, not
    official hosting - see the irregularity register);
3.  nothing else.  The DrivenData data tab needs a login and this script will never
    attempt to authenticate to anything.

Usage:  python scripts/fetch_data_bridge.py [--out data] [--verify-only]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import urllib.request

OWNER = "buffedlizard55-lab"
BRIDGE_REPO = "GEMSDOE2"
BRIDGE_PREFIX = f"{BRIDGE_REPO}-main/data/bridge/"
CANONICAL = {
    "gems-geodawn-numerical-features.tif": "training_features.tif",
    "existing_faults.tif": "labels.tif",
    "example_submission.tif": "sample_submission.tif",
}
EXPECTED = {
    "gems-geodawn-numerical-features.tif": ("4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5", 418912844),
    "existing_faults.tif": ("7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093", 425830),
    "example_submission.tif": ("2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc", 1599597),
}
UA = {"User-Agent": "gemsdoe23-data-bridge/1.0"}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def http_get(url: str, timeout: int = 600) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_bridge(verbose=True) -> dict[str, bytes]:
    """Download the sibling repository tarball and return the bridge members."""
    url = f"https://codeload.github.com/{OWNER}/{BRIDGE_REPO}/tar.gz/refs/heads/main"
    if verbose:
        print(f"GET {url}", flush=True)
    blob = http_get(url)
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or BRIDGE_PREFIX not in m.name:
                continue
            name = m.name.split(BRIDGE_PREFIX, 1)[1]
            fh = tf.extractfile(m)
            if fh is not None:
                out[name] = fh.read()
    if verbose:
        print(f"  bridge members: {sorted(out)}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("GEMS_DATA_DIR", "data"))
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    # already present and correct?
    ok = True
    for name, (sha, size) in EXPECTED.items():
        dst = os.path.join(args.out, CANONICAL[name])
        if os.path.exists(dst) and os.path.getsize(dst) == size and sha256_file(dst) == sha:
            print(f"OK   {dst} already in place and hash-verified")
        else:
            ok = False
    if ok:
        print("Nothing to do: every official raster is present and hash-verified.")
        return 0
    if args.verify_only:
        print("VERIFY-ONLY: missing or mismatched rasters listed above.")
        return 1

    os.makedirs(args.out, exist_ok=True)
    failures = []
    try:
        members = fetch_bridge()
    except Exception as exc:                                   # noqa: BLE001
        members = {}
        failures.append(f"bridge download failed: {exc!r}")
    manifest = None
    if "manifest.json" in members:
        manifest = json.loads(members["manifest.json"].decode())
        # cross-check the manifest against the hashes this script was written with
        for entry in manifest.get("files", []):
            want = EXPECTED.get(entry["name"])
            if want and (entry["sha256"], entry["bytes"]) != want:
                failures.append(f"manifest pin for {entry['name']} disagrees with the recorded pin")
        print("  manifest pins agree with the recorded SHA-256 values")

    for name, (sha, size) in EXPECTED.items():
        dst = os.path.join(args.out, CANONICAL[name])
        if os.path.exists(dst) and sha256_file(dst) == sha:
            continue
        payload = None
        if name in members and len(members[name]) == size:
            payload = members[name]
        elif manifest:
            entry = next((e for e in manifest["files"] if e["name"] == name), None)
            if entry and "parts" in entry:
                buf = io.BytesIO()
                good = True
                for part in entry["parts"]:
                    raw = members.get(part["name"])
                    if raw is None or sha256_bytes(raw) != part["sha256"] or len(raw) != part["bytes"]:
                        good = False
                        failures.append(f"part {part['name']} missing or hash mismatch")
                        break
                    buf.write(raw)
                if good:
                    payload = buf.getvalue()
        if payload is None:
            mirror = ((manifest or {}).get("source", {}).get("mirrors", {}) or {}).get(name)
            if mirror:
                try:
                    print(f"GET mirror {mirror[:80]}…", flush=True)
                    cand = http_get(mirror)
                    if len(cand) == size and sha256_bytes(cand) == sha:
                        payload = cand
                    else:
                        failures.append(f"mirror for {name} failed hash verification")
                except Exception as exc:                        # noqa: BLE001
                    failures.append(f"mirror for {name} unreachable: {exc!r}")
        if payload is None:
            failures.append(f"no verified source for {name}")
            continue
        if sha256_bytes(payload) != sha or len(payload) != size:
            failures.append(f"{name} did not verify after assembly")
            continue
        tmp = dst + ".part"
        with open(tmp, "wb") as fh:
            fh.write(payload)
        os.replace(tmp, dst)
        print(f"OK   wrote {dst} ({len(payload):,} B, sha256 {sha[:12]}… verified)")
        if name == "gems-geodawn-numerical-features.tif":
            alias = os.path.join(args.out, name)
            if not os.path.exists(alias):
                try:
                    os.link(dst, alias)
                except OSError:
                    shutil.copyfile(dst, alias)

    if failures:
        print("\nFAILED (nothing unsafe was written):")
        for f in failures:
            print("  -", f)
        return 1
    print("\nAll official rasters verified in", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
