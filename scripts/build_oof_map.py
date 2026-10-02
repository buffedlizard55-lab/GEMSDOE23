#!/usr/bin/env python3
"""Combine four held-out-quadrant predictions into one strict OOF raster."""
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
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold-runs", type=Path, nargs=4, required=True, help="four model run dirs in fold order 0,1,2,3")
    parser.add_argument("--footprint", type=Path, default=Path("data/processed/footprint.npy"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    args = parser.parse_args()
    try:
        import numpy as np
        from gems.holdout import four_quadrant_folds

        footprint = np.asarray(np.load(args.footprint, mmap_mode="r"), dtype=bool)
        folds = four_quadrant_folds(footprint, buffer_m=0.0)
        h, w = footprint.shape
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        oof = np.lib.format.open_memmap(args.output, mode="w+", dtype=np.float32, shape=(h, w))
        oof[:] = np.nan
        provenance = []
        config_hashes = set()
        for expected_fold, run_dir in enumerate(args.fold_runs):
            run_dir = run_dir.resolve()
            fold_meta_path = run_dir / "fold-metadata.json"
            prediction_path = run_dir / "predictions" / "mean_probability.npy"
            inference_report_path = run_dir / "predictions" / "uncertainty-report.json"
            if not fold_meta_path.is_file() or not prediction_path.is_file() or not inference_report_path.is_file():
                raise FileNotFoundError(f"Missing fold metadata, prediction, or inference report under {run_dir}")
            fold_meta = json.loads(fold_meta_path.read_text(encoding="utf-8"))
            inference_report = json.loads(inference_report_path.read_text(encoding="utf-8"))
            if fold_meta.get("mode") != "spatially-blocked" or fold_meta.get("holdout_fold") != expected_fold:
                raise ValueError(f"Run {run_dir} does not identify as spatial holdout fold {expected_fold}")
            if fold_meta.get("effective_buffer_m", 0) <= 0:
                raise ValueError(f"Fold {expected_fold} has no spatial training buffer")
            if fold_meta.get("candidate_id") != args.candidate_id:
                raise ValueError(f"Fold {expected_fold} candidate ID does not match {args.candidate_id}")
            if inference_report.get("candidate_id") != args.candidate_id:
                raise ValueError(f"Fold {expected_fold} inference candidate ID does not match {args.candidate_id}")
            if inference_report.get("candidate_spec_sha256") != fold_meta.get("config_sha256"):
                raise ValueError(f"Fold {expected_fold} inference config hash does not match training metadata")
            if inference_report.get("training_mode") != "spatially-blocked":
                raise ValueError(f"Fold {expected_fold} inference report is not from a spatial holdout run")
            if inference_report.get("footprint_sha256") != sha256(args.footprint):
                raise ValueError(f"Fold {expected_fold} inference used a different footprint")
            if inference_report.get("files", {}).get("mean_probability_sha256") != sha256(prediction_path):
                raise ValueError(f"Fold {expected_fold} prediction hash does not match its inference report")
            config_hashes.add(fold_meta.get("config_sha256"))
            prediction = np.load(prediction_path, mmap_mode="r")
            if prediction.shape != footprint.shape:
                raise ValueError(f"Fold {expected_fold} prediction shape mismatch")
            valid = folds[expected_fold]["validation_mask"]
            values = np.asarray(prediction[valid], dtype=np.float32)
            if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
                raise ValueError(f"Fold {expected_fold} has invalid probabilities in its validation region")
            oof[valid] = values
            provenance.append({
                "fold_id": expected_fold,
                "run_dir": str(run_dir),
                "fold_metadata_sha256": sha256(fold_meta_path),
                "inference_report_sha256": sha256(inference_report_path),
                "prediction_sha256": sha256(prediction_path),
                "validation_pixels": int(valid.sum()),
            })
        if len(config_hashes) != 1 or None in config_hashes:
            raise ValueError("All four fold runs must use the same recorded candidate config hash")
        oof.flush()
        for fold in folds:
            valid = fold["validation_mask"]
            if not np.isfinite(oof[valid]).all():
                raise ValueError(f"OOF map has missing/non-finite values in fold {fold['fold_id']}")
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "candidate_id": args.candidate_id,
            "prediction_type": "out_of_fold",
            "training_exclusion_verified": True,
            "folds": [0, 1, 2, 3],
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "oof_prediction_sha256": sha256(args.output),
            "candidate_spec_sha256": next(iter(config_hashes)),
            "footprint_sha256": sha256(args.footprint),
            "fold_provenance": provenance,
            "verification_note": "The script checked each run's fold id/mode, positive buffer, and full finite [0,1] prediction coverage in its held-out quadrant. The model code/data hashes remain available in each run directory.",
        }
        args.metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(metadata, indent=2))
        return 0
    except Exception as exc:
        print(f"build_oof_map: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
