#!/usr/bin/env python3
"""Train M independently initialized U-Net members (no test-time dropout)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.json")
    parser.add_argument("--holdout-fold", type=int, choices=range(4), default=None)
    parser.add_argument("--device", default=None, help="cuda, cpu, or auto (default)")
    args = parser.parse_args()
    try:
        import numpy as np
        config = json.loads(args.config.read_text(encoding="utf-8"))
        from gems.holdout import four_quadrant_folds
        from gems.training import train_members

        footprint = np.asarray(np.load(config["footprint_file"], mmap_mode="r"), dtype=bool)
        if args.holdout_fold is None:
            train_mask = footprint.copy()
            output_dir = Path(config["output_dir"]) / "full-ensemble"
            fold_metadata = {"mode": "full-data", "holdout_fold": None}
        else:
            patch_extent_m = config["patch_size"] * config["pixel_size_m"] / math.sqrt(2.0)
            buffer_m = config["spatial_buffer_m"] + patch_extent_m
            fold = four_quadrant_folds(
                footprint,
                buffer_m=buffer_m,
                pixel_size_m=config["pixel_size_m"],
            )[args.holdout_fold]
            train_mask = fold["training_mask"]
            output_dir = Path(config["output_dir"]) / f"fold-{args.holdout_fold}"
            fold_metadata = {
                "mode": "spatially-blocked",
                "holdout_fold": args.holdout_fold,
                "configured_buffer_m": config["spatial_buffer_m"],
                "additional_patch_context_buffer_m": patch_extent_m,
                "effective_buffer_m": buffer_m,
                "training_pixels": fold["training_pixels"],
                "validation_pixels": fold["validation_pixels"],
            }

        members = train_members(
            feature_path=config["features_file"],
            label_path=config["labels_file"],
            label_observed_path=config["label_observed_file"],
            footprint_path=config["footprint_file"],
            training_mask=train_mask,
            output_dir=output_dir,
            ensemble_size=config["ensemble_size"],
            seed_base=config["seed_base"] + (0 if args.holdout_fold is None else 10000 * args.holdout_fold),
            patch_size=config["patch_size"],
            patches_per_epoch=config["patches_per_epoch"],
            batch_size=config["batch_size"],
            epochs=config["epochs"],
            learning_rate=config["learning_rate"],
            unlabeled_loss_weight=config["unlabeled_loss_weight"],
            device=None if args.device in (None, "auto") else args.device,
        )
        try:
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            revision = "unknown"
        fold_record = {
            **fold_metadata,
            "candidate_id": config.get("candidate_id", "unnamed"),
            "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
            "repository_revision": revision,
            "members": members,
        }
        (output_dir / "fold-metadata.json").write_text(
            json.dumps(fold_record, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Saved {len(members)} independent members to {output_dir}")
        return 0
    except Exception as exc:
        print(f"train_ensemble: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
