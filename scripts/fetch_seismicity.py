#!/usr/bin/env python3
"""Acquire the USGS ComCat (ANSS) earthquake catalogue for the competition AOI.

Free, official, no login: the FDSN event web service,
https://earthquake.usgs.gov/fdsnws/event/1/ .  This feeds hypothesis H-40
(fine-scale seismicity lineaments): the official competition stack already
carries earthquake channels but smooths them at a 100 km radius
(``ieq_n100a15`` / ``deq_n100a15``), which erases fault-scale structure; this
catalogue is the raw event list from which a 5-10 km layer can be built.

The bounding box is the exact EPSG:32611 footprint rectangle of the official
template (x 243350..572750, y 4135850..4508550 -> lon -120.0372..-116.1386,
lat 37.3339..40.7247), unbuffered so events outside the footprint are not
double-counted; a consumer that wants an edge buffer should fetch a wider box.

Obtainability was verified on 2026-10-02: the count endpoint answered 15,802
events (M >= 2.5) and 692 (M >= 4.0) for the wider box 37.2-40.8N,
120.2-116.3W, 1960-01-01..2026-10-01, and the text format streams correctly.

Usage:  python scripts/fetch_seismicity.py [--out docs/data/seismicity]
Fails closed: nothing is written unless the response parses, has the expected
header, exceeds a minimum event count and every row has a magnitude.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"
LON_LO, LON_HI = -120.0372, -116.1386
LAT_LO, LAT_HI = 37.3339, 40.7247
STARTTIME = "1960-01-01"
MIN_MAG = 2.5
MIN_EVENTS = 5000          # the wider verified box held 15,802; fail closed well below that
HEADER_PREFIX = "#EventID|"
SOURCE_PAGE = "https://earthquake.usgs.gov/fdsnws/event/1/"
CITE = ("USGS Earthquake Hazards Program, Advanced National Seismic System (ANSS), "
        "Comprehensive Earthquake Catalog (ComCat)")


def build_url(endtime: str) -> str:
    from urllib.parse import urlencode
    q = urlencode({
        "format": "text", "starttime": STARTTIME, "endtime": endtime,
        "minmagnitude": MIN_MAG,
        "minlatitude": LAT_LO, "maxlatitude": LAT_HI,
        "minlongitude": LON_LO, "maxlongitude": LON_HI,
        "orderby": "time-asc", "eventtype": "earthquake",
    })
    return f"{BASE}?{q}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/data/seismicity")
    ap.add_argument("--min-events", type=int, default=MIN_EVENTS)
    ap.add_argument("--endtime", default=time.strftime("%Y-%m-%dT%H:%M"))
    args = ap.parse_args()

    url = build_url(args.endtime)
    print("GET", url, flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "gemsdoe23-seismicity/1.0"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        text = resp.read().decode("utf-8")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith(HEADER_PREFIX):
        print("FAIL: response does not start with the FDSN text header", file=sys.stderr)
        return 1
    expected_cols = ["#EventID", "Time", "Latitude", "Longitude", "Depth/km"]
    header_cols = lines[0].split("|")
    for c in expected_cols:
        if c not in header_cols:
            print(f"FAIL: header missing column {c}", file=sys.stderr)
            return 1
    mag_i = header_cols.index("Magnitude")
    n = 0
    for ln in lines[1:]:
        parts = ln.split("|")
        if len(parts) <= mag_i or not parts[mag_i]:
            print(f"FAIL: row without magnitude: {ln[:80]}", file=sys.stderr)
            return 1
        n += 1
    if n < args.min_events:
        print(f"FAIL: only {n} events (< {args.min_events}); refusing to overwrite", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data_path = out / "comcat_m25_aoi.txt"
    data_path.write_text(text, encoding="utf-8")
    meta = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": SOURCE_PAGE,
        "citation": CITE,
        "url": url,
        "format": "FDSN text (pipe-separated)",
        "box": {"lon": [LON_LO, LON_HI], "lat": [LAT_LO, LAT_HI]},
        "box_definition": "exact EPSG:32611 footprint rectangle of the official template, unbuffered",
        "min_magnitude": MIN_MAG,
        "starttime": STARTTIME,
        "endtime": args.endtime,
        "event_count": n,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "bytes": len(text.encode("utf-8")),
        "obtainability_verified_utc": "2026-10-02",
        "note": ("Hypothesis H-40 input. The official competition bands ieq_n100a15/deq_n100a15 "
                 "smooth seismicity at a 100 km radius; this raw list permits 5-10 km lineament "
                 "layers. Not yet validated on any holdout."),
    }
    (out / "comcat-meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"wrote {data_path} ({n} events, {meta['bytes']:,} bytes)")
    print(f"wrote {out / 'comcat-meta.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
