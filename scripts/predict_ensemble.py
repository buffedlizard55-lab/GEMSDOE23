#!/usr/bin/env python3
"""Deterministic full-grid inference and law-of-total-variance sidecars."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.json")
    parser.add_argument("--features", type=Path, default=None)
    parser.add_argument("--footprint", type=Path, default=None)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--calibration-report", type=Path, default=None)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()
    try:
        import numpy as np
        import torch
        import torch.nn.functional as F
        from gems.model import UNetFaultNet

        if args.tile_size < 32 or args.tile_size % 8:
            raise ValueError("tile-size must be >=32 and divisible by 8")
        if args.temperature <= 0:
            raise ValueError("temperature must be positive")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        config_hash = hashlib.sha256(args.config.read_bytes()).hexdigest()
        feature_path = args.features or Path(config["features_file"])
        footprint_path = args.footprint or Path(config["footprint_file"])
        training_meta_path = args.model_dir / "fold-metadata.json"
        if not training_meta_path.is_file():
            raise FileNotFoundError(f"Missing training provenance: {training_meta_path}")
        training_meta = json.loads(training_meta_path.read_text(encoding="utf-8"))
        if training_meta.get("config_sha256") != config_hash:
            raise ValueError("Inference config hash does not match the model training config")
        if training_meta.get("candidate_id") != config.get("candidate_id", "unnamed"):
            raise ValueError("Inference candidate ID does not match model training metadata")
        x = np.load(feature_path, mmap_mode="r")
        footprint = np.asarray(np.load(footprint_path, mmap_mode="r"), dtype=bool)
        if x.ndim != 3 or x.shape[1:] != footprint.shape:
            raise ValueError("Feature cube and footprint shapes do not align")
        checkpoints = sorted(args.model_dir.glob("member-*.pt"))
        expected_members = int(config.get("ensemble_size", 0))
        if expected_members < 2 or len(checkpoints) != expected_members:
            raise ValueError(
                f"Expected exactly config ensemble_size={expected_members} member checkpoints in {args.model_dir}; found {len(checkpoints)}"
            )
        recorded_members = training_meta.get("members")
        if not isinstance(recorded_members, list) or len(recorded_members) != expected_members:
            raise ValueError("Training provenance member list does not match config ensemble_size")
        calibration = None
        if args.calibration_report:
            calibration = json.loads(args.calibration_report.read_text(encoding="utf-8"))
            if calibration.get("out_of_fold") is not True or calibration.get("temperature") != args.temperature:
                raise ValueError("Calibration report must be out-of-fold and match --temperature")
            if calibration.get("candidate_spec_sha256") != config_hash:
                raise ValueError("Calibration report candidate config hash does not match inference config")
        device_name = args.device if args.device not in (None, "auto") else ("cuda" if torch.cuda.is_available() else "cpu")
        device = torch.device(device_name)
        h, w = footprint.shape
        args.out_dir.mkdir(parents=True, exist_ok=True)
        mean_path = args.out_dir / "mean_probability.npy"
        epi_path = args.out_dir / "epistemic_variance.npy"
        alea_path = args.out_dir / "aleatoric_variance.npy"
        total_path = args.out_dir / "predictive_variance.npy"
        mean = np.lib.format.open_memmap(mean_path, mode="w+", dtype=np.float32, shape=(h, w))
        m2 = np.lib.format.open_memmap(args.out_dir / ".ensemble-m2.npy", mode="w+", dtype=np.float32, shape=(h, w))
        alea_sum = np.lib.format.open_memmap(args.out_dir / ".ensemble-alea.npy", mode="w+", dtype=np.float32, shape=(h, w))
        mean[:] = 0.0
        m2[:] = 0.0
        alea_sum[:] = 0.0

        observed_seeds: set[int] = set()
        for member_index, checkpoint_path in enumerate(checkpoints, start=1):
            checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
            if checkpoint.get("member_index") != member_index - 1 or checkpoint.get("ensemble_size") != expected_members:
                raise ValueError(f"Checkpoint {checkpoint_path.name} has inconsistent member index/count metadata")
            seed = checkpoint.get("seed")
            if not isinstance(seed, int) or seed in observed_seeds:
                raise ValueError(f"Checkpoint {checkpoint_path.name} has a missing or duplicated seed")
            observed_seeds.add(seed)
            model = UNetFaultNet(in_channels=int(x.shape[0])).to(device)
            model.load_state_dict(checkpoint["state_dict"], strict=True)
            model.eval()  # model has no dropout; inference is deterministic
            if checkpoint.get("dropout_at_inference") is not False:
                raise ValueError(f"Checkpoint {checkpoint_path.name} does not assert dropout_at_inference=false")
            with torch.inference_mode():
                for row in range(0, h, args.tile_size):
                    for col in range(0, w, args.tile_size):
                        th = min(args.tile_size, h - row)
                        tw = min(args.tile_size, w - col)
                        tile = np.asarray(x[:, row:row + th, col:col + tw], dtype=np.float32).copy()
                        tensor = torch.from_numpy(tile[None]).to(device)
                        pad_h = (-th) % 8
                        pad_w = (-tw) % 8
                        if pad_h or pad_w:
                            tensor = F.pad(tensor, (0, pad_w, 0, pad_h), mode="replicate")
                        probs = torch.sigmoid(model(tensor) / args.temperature)[0, 0, :th, :tw]
                        p = probs.cpu().numpy().astype(np.float32, copy=False)
                        region = (slice(row, row + th), slice(col, col + tw))
                        if member_index == 1:
                            mean[region] = p
                            alea_sum[region] = p * (1.0 - p)
                        else:
                            old = np.asarray(mean[region], dtype=np.float32)
                            delta = p - old
                            new_mean = old + delta / member_index
                            m2[region] = np.asarray(m2[region], dtype=np.float32) + delta * (p - new_mean)
                            mean[region] = new_mean
                            alea_sum[region] = np.asarray(alea_sum[region], dtype=np.float32) + p * (1.0 - p)
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()

        mean.flush()
        m2.flush()
        alea_sum.flush()
        epi = np.lib.format.open_memmap(epi_path, mode="w+", dtype=np.float32, shape=(h, w))
        alea = np.lib.format.open_memmap(alea_path, mode="w+", dtype=np.float32, shape=(h, w))
        total = np.lib.format.open_memmap(total_path, mode="w+", dtype=np.float32, shape=(h, w))
        count = len(checkpoints)
        for row in range(0, h, args.tile_size):
            for col in range(0, w, args.tile_size):
                ys = slice(row, min(row + args.tile_size, h))
                xs = slice(col, min(col + args.tile_size, w))
                p = np.asarray(mean[ys, xs], dtype=np.float32)
                e = np.asarray(m2[ys, xs], dtype=np.float32) / count
                a = np.asarray(alea_sum[ys, xs], dtype=np.float32) / count
                t = p * (1.0 - p)
                # Outside the official footprint is represented as NaN in all outputs.
                valid = footprint[ys, xs]
                epi_block, alea_block, total_block = e.copy(), a.copy(), t.copy()
                p_block = p.copy()
                for block in (epi_block, alea_block, total_block, p_block):
                    block[~valid] = np.nan
                mean[ys, xs] = p_block
                epi[ys, xs], alea[ys, xs], total[ys, xs] = epi_block, alea_block, total_block
        mean.flush(); epi.flush(); alea.flush(); total.flush()
        (args.out_dir / ".ensemble-m2.npy").unlink(missing_ok=True)
        (args.out_dir / ".ensemble-alea.npy").unlink(missing_ok=True)
        report = {
            "candidate_id": config.get("candidate_id", "unnamed"),
            "candidate_spec_sha256": config_hash,
            "candidate_spec": config,
            "training_mode": training_meta.get("mode"),
            "calibration_status": "out-of-fold temperature scaling applied" if calibration is not None else "uncalibrated; temperature scaling not evidenced",
            "calibration_report_sha256": None if args.calibration_report is None else sha256(args.calibration_report),
            "footprint_sha256": sha256(footprint_path),
            "training_metadata_sha256": sha256(training_meta_path),
            "member_count": count,
            "checkpoints": [{"path": p.name, "sha256": sha256(p)} for p in checkpoints],
            "temperature": args.temperature,
            "calibrated": calibration is not None,
            "calibration_report": None if args.calibration_report is None else str(args.calibration_report),
            "inference": "eval/inference_mode; model contains no dropout; same raster grid for each independently trained member",
            "uncertainty": {
                "epistemic_variance": "population variance across member probabilities (ddof=0)",
                "aleatoric_variance": "mean member-conditional Bernoulli p(1-p); interpretation requires calibration and a defensible label model",
                "predictive_variance": "ensemble_mean * (1 - ensemble_mean)",
                "identity": "predictive = epistemic + aleatoric, up to float32 tolerance",
            },
            "files": {
                "mean_probability": mean_path.name,
                "mean_probability_sha256": sha256(mean_path),
                "epistemic_variance": epi_path.name,
                "epistemic_variance_sha256": sha256(epi_path),
                "aleatoric_variance": alea_path.name,
                "aleatoric_variance_sha256": sha256(alea_path),
                "predictive_variance": total_path.name,
                "predictive_variance_sha256": sha256(total_path),
            },
            "footprint_pixels": int(footprint.sum()),
        }
        (args.out_dir / "uncertainty-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        print(f"predict_ensemble: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
