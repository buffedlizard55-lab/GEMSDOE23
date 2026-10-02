#!/usr/bin/env python3
"""Fail-closed preflight for the official one-band GeoTIFF submission contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True, help="Official sample_submission.tif")
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    try:
        from gems.submission import validate_submission
        report = validate_submission(args.prediction, args.template)
        serialized = json.dumps(report, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(serialized + "\n", encoding="utf-8")
        print(serialized)
        return 0 if report["passed"] else 2
    except Exception as exc:
        print(f"validate_submission: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
