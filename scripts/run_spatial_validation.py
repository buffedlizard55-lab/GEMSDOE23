#!/usr/bin/env python3
"""Score out-of-fold predictions against known catalogue labels as a diagnostic only.

The supplied training labels are already-mapped faults, not the competition's target of
uncatalogued faults. This script can screen for gross spatial generalisation failures, but it
never authorizes a submission slot. Release approval requires a separate, documented comparison
against the current best on an independent uncatalogued-fault holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True, help="2-D .npy of OOF candidate probabilities")
    parser.add_argument("--incumbent", type=Path, required=True, help="2-D .npy of OOF incumbent probabilities")
    parser.add_argument("--truth", type=Path, default=Path("data/processed/labels.npy"))
    parser.add_argument("--label-observed", type=Path, default=Path("data/processed/label_observed.npy"))
    parser.add_argument("--footprint", type=Path, default=Path("data/processed/footprint.npy"))
    parser.add_argument("--metadata", type=Path, required=True, help="Candidate metadata asserting OOF predictions by matching spatial fold")
    parser.add_argument("--incumbent-metadata", type=Path, required=True, help="Incumbent metadata asserting OOF predictions on the same folds")
    parser.add_argument("--output", type=Path, default=Path("outputs/validation-report.json"))
    parser.add_argument("--radius-m", type=float, default=300.0)
    parser.add_argument("--pixel-size-m", type=float, default=100.0)
    parser.add_argument("--min-mean-delta", type=float, default=0.002)
    parser.add_argument("--minimum-fold-wins", type=int, default=3)
    args = parser.parse_args()
    try:
        import numpy as np
        from scipy.ndimage import distance_transform_edt
        from gems.holdout import four_quadrant_folds
        from gems.metric import distance_weighted_tversky

        meta = json.loads(args.metadata.read_text(encoding="utf-8"))
        incumbent_meta = json.loads(args.incumbent_metadata.read_text(encoding="utf-8"))
        expected_folds = [0, 1, 2, 3]
        for label, record in (("candidate", meta), ("incumbent", incumbent_meta)):
            if record.get("prediction_type") != "out_of_fold":
                raise ValueError(f"{label} metadata must declare prediction_type='out_of_fold'")
            if record.get("training_exclusion_verified") is not True:
                raise ValueError(f"{label} metadata must assert training_exclusion_verified=true")
            if record.get("folds") != expected_folds:
                raise ValueError(f"{label} OOF metadata must cover folds exactly {expected_folds}")
        footprint_hash = sha256(args.footprint)
        for label, record, prediction_path in (
            ("candidate", meta, args.candidate),
            ("incumbent", incumbent_meta, args.incumbent),
        ):
            if record.get("footprint_sha256") != footprint_hash:
                raise ValueError(f"{label} OOF metadata footprint hash does not match the scoring footprint")
            if record.get("oof_prediction_sha256") != sha256(prediction_path):
                raise ValueError(f"{label} OOF prediction hash does not match its metadata")
            if not isinstance(record.get("candidate_spec_sha256"), str) or len(record["candidate_spec_sha256"]) != 64:
                raise ValueError(f"{label} OOF metadata has no valid candidate config SHA-256")
            provenance = record.get("fold_provenance")
            if not isinstance(provenance, list) or [item.get("fold_id") for item in provenance] != expected_folds:
                raise ValueError(f"{label} OOF metadata lacks provenance for all four ordered folds")
        if meta.get("footprint_sha256") != incumbent_meta.get("footprint_sha256"):
            raise ValueError("Candidate and incumbent OOF maps were not built on the same footprint")

        candidate = np.asarray(np.load(args.candidate, mmap_mode="r"), dtype=np.float32)
        incumbent = np.asarray(np.load(args.incumbent, mmap_mode="r"), dtype=np.float32)
        truth = np.asarray(np.load(args.truth, mmap_mode="r"), dtype=bool)
        label_observed = np.asarray(np.load(args.label_observed, mmap_mode="r"), dtype=bool)
        footprint = np.asarray(np.load(args.footprint, mmap_mode="r"), dtype=bool)
        if candidate.ndim != 2 or any(a.shape != candidate.shape for a in (incumbent, truth, label_observed, footprint)):
            raise ValueError("Candidate, incumbent, truth, label_observed, and footprint must be matching 2-D arrays")
        for label, prediction in (("candidate", candidate), ("incumbent", incumbent)):
            values = prediction[footprint]
            if not np.isfinite(values).all() or (values < 0.0).any() or (values > 1.0).any():
                raise ValueError(f"{label} OOF map has non-finite or out-of-range values inside the footprint")
            if not np.isnan(prediction[~footprint]).all():
                raise ValueError(f"{label} OOF map must contain NaN outside the official footprint")
        folds = four_quadrant_folds(footprint, buffer_m=0.0, pixel_size_m=args.pixel_size_m)
        results = []
        for fold in folds:
            validation = fold["validation_mask"]
            # Remove the scoring collar so this fold's DTI does not depend on
            # labels or predictions across a fold boundary.
            interior_distance = distance_transform_edt(
                validation,
                sampling=(args.pixel_size_m, args.pixel_size_m),
            )
            score_mask = validation & label_observed & (interior_distance > args.radius_m)
            if not (truth & score_mask).any():
                raise ValueError(f"Fold {fold['fold_id']} has no positive known-fault pixels after the scoring collar")
            ys, xs = np.nonzero(score_mask)
            y_slice = slice(int(ys.min()), int(ys.max()) + 1)
            x_slice = slice(int(xs.min()), int(xs.max()) + 1)
            local_mask = score_mask[y_slice, x_slice]
            local_truth = truth[y_slice, x_slice]
            c = distance_weighted_tversky(
                candidate[y_slice, x_slice],
                local_truth,
                mask=local_mask,
                pixel_size_m=args.pixel_size_m,
                radius_m=args.radius_m,
            )
            b = distance_weighted_tversky(
                incumbent[y_slice, x_slice],
                local_truth,
                mask=local_mask,
                pixel_size_m=args.pixel_size_m,
                radius_m=args.radius_m,
            )
            results.append(
                {
                    "fold_id": fold["fold_id"],
                    "scored_pixels": int(score_mask.sum()),
                    "truth_positive_pixels": int((truth & score_mask).sum()),
                    "candidate_dti": c["dti"],
                    "incumbent_dti": b["dti"],
                    "delta": c["dti"] - b["dti"],
                    "candidate_components": c,
                }
            )

        deltas = [r["delta"] for r in results]
        mean_delta = float(np.mean(deltas))
        fold_wins = sum(delta > 0.0 for delta in deltas)
        metric_screen_passed = mean_delta >= args.min_mean_delta and fold_wins >= args.minimum_fold_wins
        # This command scores the official *known-catalogue* label raster by default. Those
        # pixels are masked from the competition metric, so even a positive screen cannot
        # authorize spending a competition slot. Preserve the measured comparison, but make
        # release eligibility impossible at this stage.
        report = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PROXY_ONLY",
            "candidate_id": meta.get("candidate_id", "unnamed"),
            "candidate_spec_sha256": meta.get("candidate_spec_sha256"),
            "candidate_metadata_sha256": sha256(args.metadata),
            "candidate_prediction_sha256": sha256(args.candidate),
            "incumbent_id": incumbent_meta.get("candidate_id", "unnamed"),
            "incumbent_spec_sha256": incumbent_meta.get("candidate_spec_sha256"),
            "incumbent_metadata_sha256": sha256(args.incumbent_metadata),
            "incumbent_prediction_sha256": sha256(args.incumbent),
            "truth_semantics": "known_catalogue_faults; proxy-only and excluded from competition scoring",
            "truth_sha256": sha256(args.truth),
            "metric": "official distance-weighted Tversky index; alpha=0.2, beta=0.8",
            "spatial_design": {
                "folds": 4,
                "layout": "four geographic quadrants",
                "scoring_collar_m": args.radius_m,
                "pixel_size_m": args.pixel_size_m,
                "prediction_type": "out_of_fold",
                "provenance_note": "OOF semantics are asserted by checked metadata; this local check is not tamper-proof."
            },
            "gate": {
                "minimum_mean_delta": args.min_mean_delta,
                "minimum_fold_wins": args.minimum_fold_wins,
                "mean_delta": mean_delta,
                "fold_wins": fold_wins,
                "screen_passed": bool(metric_screen_passed),
                "eligible_for_submission": False,
                "reason": "known-catalogue truth is not the hidden uncatalogued-fault target and cannot release a competition submission",
            },
            "eligible_for_submission": False,
            "fold_results": results,
            "warning": "This four-quadrant known-catalogue diagnostic is not submission validation. A candidate must separately beat the reproducible current holdout best on independent uncatalogued-fault truth before any weekly submission slot is used.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        print(f"run_spatial_validation: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
