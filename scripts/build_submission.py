#!/usr/bin/env python3
"""Build a uniquely named GeoTIFF only after a spatial-holdout gate passes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_current_best_record(record: dict) -> None:
    """Require an auditable registry entry for the current spatial-holdout incumbent."""
    if record.get("status") != "VERIFIED":
        raise ValueError("No verified current holdout best is registered; submission release is blocked")
    if record.get("truth_semantics") != "independent_uncatalogued_faults":
        raise ValueError("Current holdout best must use independent uncatalogued-fault truth")
    if record.get("folds") != [0, 1, 2, 3]:
        raise ValueError("Current holdout best must be registered on four spatial folds")
    for key in ("holdout_id", "candidate_id"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Current holdout best is missing {key}")
    for key in ("candidate_spec_sha256", "oof_prediction_sha256", "validation_report_sha256", "truth_sha256"):
        value = record.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"Current holdout best is missing a valid {key}")


def validate_gate_report(gate: dict, current_best: dict) -> None:
    """Recompute the four-fold gate and bind it to the registered current best.

    A proxy-only, withdrawn, missing, or stale comparison must never authorize a weekly
    submission. The candidate must beat the exact OOF map registered in current-best.json.
    """
    validate_current_best_record(current_best)
    if gate.get("status") != "PASSED":
        raise ValueError("Holdout report status must be PASSED; proxy-only or withdrawn reports cannot release a submission")
    if gate.get("eligible_for_submission") is not True:
        raise ValueError("Holdout report does not explicitly set eligible_for_submission=true")
    if gate.get("truth_semantics") != current_best["truth_semantics"]:
        raise ValueError("Candidate and current-best reports do not use the registered independent truth semantics")
    if gate.get("truth_sha256") != current_best["truth_sha256"]:
        raise ValueError("Candidate report truth does not match the registered current-best truth")
    if gate.get("incumbent_id") != current_best["candidate_id"]:
        raise ValueError("Candidate was not compared against the registered current holdout best")
    if gate.get("incumbent_spec_sha256") != current_best["candidate_spec_sha256"]:
        raise ValueError("Incumbent spec does not match the registered current holdout best")
    if gate.get("incumbent_prediction_sha256") != current_best["oof_prediction_sha256"]:
        raise ValueError("Incumbent OOF prediction does not match the registered current holdout best")
    if gate.get("current_best_holdout_id") != current_best["holdout_id"]:
        raise ValueError("Candidate report does not reference the registered holdout ID")

    stats = gate.get("gate")
    folds = gate.get("fold_results")
    design = gate.get("spatial_design")
    if not isinstance(stats, dict) or not isinstance(folds, list) or not isinstance(design, dict):
        raise ValueError("Gate report is missing its gate statistics, fold results, or spatial design")
    if design.get("folds") != 4 or design.get("prediction_type") != "out_of_fold":
        raise ValueError("Submission gate must use four spatial out-of-fold predictions")
    if len(folds) != 4 or [row.get("fold_id") for row in folds] != [0, 1, 2, 3]:
        raise ValueError("Submission gate must contain exactly folds 0, 1, 2, and 3")
    deltas = [float(row["delta"]) for row in folds]
    if not all(math.isfinite(value) for value in deltas):
        raise ValueError("Gate fold deltas must be finite")
    mean_delta = sum(deltas) / len(deltas)
    fold_wins = sum(value > 0.0 for value in deltas)
    minimum_delta = float(stats.get("minimum_mean_delta", float("nan")))
    minimum_wins = int(stats.get("minimum_fold_wins", -1))
    if not math.isfinite(minimum_delta) or minimum_wins < 1 or minimum_wins > 4:
        raise ValueError("Gate thresholds are missing or invalid")
    if not math.isclose(float(stats.get("mean_delta", float("nan"))), mean_delta, rel_tol=1e-7, abs_tol=1e-10):
        raise ValueError("Reported gate mean delta does not match its fold results")
    if int(stats.get("fold_wins", -1)) != fold_wins:
        raise ValueError("Reported gate fold wins do not match its fold results")
    if mean_delta < minimum_delta or fold_wins < minimum_wins:
        raise ValueError("Gate report claims eligibility but its recorded thresholds are not met")
    if stats.get("eligible_for_submission") is not True:
        raise ValueError("Nested gate status is not explicitly eligible")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probabilities", type=Path, required=True, help="2-D .npy of final ensemble-mean scores in [0,1]")
    parser.add_argument("--template", type=Path, required=True, help="Official sample_submission.tif")
    parser.add_argument("--config", type=Path, required=True, help="Same candidate config used for the holdout and final full-data model")
    parser.add_argument("--inference-report", type=Path, required=True, help="uncertainty-report.json from final full-data ensemble inference")
    parser.add_argument("--gate-report", type=Path, required=True, help="Spatially blocked validation JSON with eligible_for_submission=true")
    parser.add_argument("--current-best-report", type=Path, default=Path("docs/data/current-holdout-best.json"),
                        help="Verified registry record for the current best spatial holdout (release fails closed unless VERIFIED)")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/submissions"))
    parser.add_argument("--strategy", default="ensemble", help="Short strategy slug included in the filename")
    parser.add_argument("--note", default=None, help="Short DrivenData note; otherwise generated from strategy and hash")
    args = parser.parse_args()
    try:
        import numpy as np
        from gems.submission import validate_submission, write_submission_raster

        gate = json.loads(args.gate_report.read_text(encoding="utf-8"))
        current_best = json.loads(args.current_best_report.read_text(encoding="utf-8"))
        config = json.loads(args.config.read_text(encoding="utf-8"))
        inference = json.loads(args.inference_report.read_text(encoding="utf-8"))
        config_hash = hashlib.sha256(args.config.read_bytes()).hexdigest()
        validate_gate_report(gate, current_best)
        candidate_id = config.get("candidate_id", "unnamed")
        expected_slug = re.sub(r"[^a-z0-9-]+", "-", candidate_id.lower()).strip("-")
        if gate.get("candidate_id") != candidate_id:
            raise ValueError("Gate report candidate_id differs from final model config")
        if gate.get("candidate_spec_sha256") != config_hash:
            raise ValueError("Gate report config hash differs from final model config")
        if (inference.get("candidate_id") != candidate_id
                or inference.get("candidate_spec_sha256") != config_hash
                or inference.get("candidate_spec") != config):
            raise ValueError("Final inference report candidate/config does not match the validated candidate")
        if inference.get("training_mode") != "full-data":
            raise ValueError("Submission predictions must come from the final full-data model, not a held-out fold")
        if inference.get("member_count") != config.get("ensemble_size"):
            raise ValueError("Final inference member count does not match the candidate config ensemble_size")
        if inference.get("files", {}).get("mean_probability_sha256") != sha256(args.probabilities):
            raise ValueError("Probability array does not match the mean raster recorded by the final inference report")
        if re.sub(r"[^a-z0-9-]+", "-", args.strategy.lower()).strip("-") != expected_slug:
            raise ValueError("--strategy must identify the validated candidate ID")
        values = np.load(args.probabilities, mmap_mode="r")
        if values.ndim != 2:
            raise ValueError(f"Expected a 2-D probability raster; got shape {values.shape}")
        slug = re.sub(r"[^a-z0-9-]+", "-", args.strategy.lower()).strip("-") or "candidate"
        created_at = datetime.now(timezone.utc)
        timestamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        temp = args.out_dir / f".pending-{slug}-{timestamp}.tif"
        write_submission_raster(values, args.template, temp)
        report = validate_submission(temp, args.template)
        if not report["passed"]:
            temp.unlink(missing_ok=True)
            raise ValueError(f"Written GeoTIFF failed validation: {report.get('hard_failures')}")
        digest = sha256(temp)
        base_name = f"gemsdoe23-{slug}-{timestamp}-{digest[:8]}"
        final = args.out_dir / f"{base_name}.tif"
        collision = 1
        while final.exists() or final.with_suffix(".json").exists():
            final = args.out_dir / f"{base_name}-{collision:02d}.tif"
            collision += 1
        temp.rename(final)
        note = args.note or f"GEMSDOE23 {slug} | independent four-fold holdout gate passed vs registered current best | artifact {digest[:8]}"
        manifest = {
            "file": final.name,
            "sha256": digest,
            "bytes": final.stat().st_size,
            "strategy": slug,
            "created_utc": created_at.isoformat(),
            "note": note,
            "calibrated": inference.get("calibrated"),
            "calibration_report": inference.get("calibration_report"),
            "probabilities_sha256": sha256(args.probabilities),
            "template_sha256": sha256(args.template),
            "candidate_spec": {
                "candidate_id": candidate_id,
                "config_path": str(args.config),
                "config_sha256": config_hash,
                "config": config,
                "ensemble_size": inference.get("member_count"),
                "training_mode": inference.get("training_mode"),
            },
            "gate_report": str(args.gate_report),
            "gate_report_sha256": sha256(args.gate_report),
            "current_best_report": str(args.current_best_report),
            "current_best_report_sha256": sha256(args.current_best_report),
            "current_holdout_best": {
                "holdout_id": current_best["holdout_id"],
                "candidate_id": current_best["candidate_id"],
                "candidate_spec_sha256": current_best["candidate_spec_sha256"],
                "oof_prediction_sha256": current_best["oof_prediction_sha256"],
                "validation_report_sha256": current_best["validation_report_sha256"],
                "truth_sha256": current_best["truth_sha256"],
            },
            "release_status": "APPROVED_BY_SPATIAL_HOLDOUT_GATE",
            "candidate_spec_sha256": config_hash,
            "inference_report": str(args.inference_report),
            "inference_report_sha256": sha256(args.inference_report),
            "validation": report,
            "warning": "Public/private leaderboard performance is unknown until the competition evaluates the upload.",
        }
        manifest_path = final.with_suffix(".json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 0
    except Exception as exc:
        print(f"build_submission: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
