#!/usr/bin/env python3
"""Record a live public score the moment it appears, then rebuild the evidence and site.

    python scripts/record_score.py --score 0.2341 --id 3fa9c2d1 [--note "..."]

Every live score is an observation that tightens the |G| bound and the habitat
regression, so recording it is the highest-value action after an upload.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time

LOG = "docs/data/score-log.json"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", type=float, required=True)
    ap.add_argument("--id", required=True, help="first 8 hex of the submission's sha256")
    ap.add_argument("--name", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--no-rebuild", action="store_true")
    a = ap.parse_args()
    if not (0.0 <= a.score <= 1.0):
        sys.exit("score must be in [0, 1]")
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log = json.load(open(LOG)) if os.path.exists(LOG) else dict(entries=[])
    entry = dict(recorded_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 content_id=a.id, name=a.name, public_dti=a.score, note=a.note)
    log["entries"] = [e for e in log["entries"] if e.get("content_id") != a.id] + [entry]
    log["generated_utc"] = entry["recorded_utc"]
    json.dump(log, open(LOG, "w"), indent=1)
    print("recorded", entry)
    if not a.no_rebuild:
        for cmd in (["python", "scripts/fit_habitat_model.py"], ["python", "scripts/build_site.py"]):
            print("$", " ".join(cmd))
            subprocess.run(cmd, check=False)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
