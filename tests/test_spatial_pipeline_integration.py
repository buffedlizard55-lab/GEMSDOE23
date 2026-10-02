import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class SpatialPipelineIntegrationTests(unittest.TestCase):
    def test_oof_maps_gate_and_manifest_provenance_interoperate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shape = (64, 64)
            footprint = np.ones(shape, dtype=np.uint8)
            truth = np.zeros(shape, dtype=np.uint8)
            truth_points = [(10, 10), (10, 50), (50, 10), (50, 50)]
            for point in truth_points:
                truth[point] = 1
            observed = footprint.copy()
            footprint_path = root / "footprint.npy"
            truth_path = root / "labels.npy"
            observed_path = root / "label_observed.npy"
            np.save(footprint_path, footprint)
            np.save(truth_path, truth)
            np.save(observed_path, observed)

            config_paths = {}
            run_paths = {}
            for candidate_id, true_score in (("baseline-unet", 0.25), ("H1-edge-consensus", 0.95)):
                config_path = root / f"{candidate_id}-config.json"
                config = {"candidate_id": candidate_id, "ensemble_size": 5, "output_dir": str(root / candidate_id)}
                write_json(config_path, config)
                config_paths[candidate_id] = (config_path, sha256(config_path), config)
                runs = []
                for fold_id in range(4):
                    run_dir = root / candidate_id / f"fold-{fold_id}"
                    pred_dir = run_dir / "predictions"
                    pred_dir.mkdir(parents=True)
                    prediction = np.full(shape, 0.05, dtype=np.float32)
                    for point in truth_points:
                        prediction[point] = true_score
                    prediction_path = pred_dir / "mean_probability.npy"
                    np.save(prediction_path, prediction)
                    fold_meta = {
                        "mode": "spatially-blocked",
                        "holdout_fold": fold_id,
                        "effective_buffer_m": 1000.0,
                        "candidate_id": candidate_id,
                        "config_sha256": config_paths[candidate_id][1],
                        "members": [{"member_index": i, "seed": i + fold_id * 10} for i in range(5)],
                    }
                    write_json(run_dir / "fold-metadata.json", fold_meta)
                    inference_report = {
                        "candidate_id": candidate_id,
                        "candidate_spec_sha256": config_paths[candidate_id][1],
                        "training_mode": "spatially-blocked",
                        "member_count": 5,
                        "footprint_sha256": sha256(footprint_path),
                        "files": {"mean_probability_sha256": sha256(prediction_path)},
                    }
                    write_json(pred_dir / "uncertainty-report.json", inference_report)
                    runs.append(run_dir)
                run_paths[candidate_id] = runs

            oof_paths = {}
            for candidate_id in ("baseline-unet", "H1-edge-consensus"):
                prediction_path = root / f"{candidate_id}-oof.npy"
                metadata_path = root / f"{candidate_id}-oof.json"
                command = [
                    sys.executable, str(ROOT / "scripts/build_oof_map.py"),
                    "--candidate-id", candidate_id,
                    "--fold-runs", *[str(path) for path in run_paths[candidate_id]],
                    "--footprint", str(footprint_path),
                    "--output", str(prediction_path),
                    "--metadata", str(metadata_path),
                ]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                oof_paths[candidate_id] = (prediction_path, metadata_path)

            gate_path = root / "validation-report.json"
            command = [
                sys.executable, str(ROOT / "scripts/run_spatial_validation.py"),
                "--candidate", str(oof_paths["H1-edge-consensus"][0]),
                "--incumbent", str(oof_paths["baseline-unet"][0]),
                "--truth", str(truth_path),
                "--label-observed", str(observed_path),
                "--footprint", str(footprint_path),
                "--metadata", str(oof_paths["H1-edge-consensus"][1]),
                "--incumbent-metadata", str(oof_paths["baseline-unet"][1]),
                "--output", str(gate_path),
            ]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            self.assertTrue(gate["eligible_for_submission"])
            self.assertEqual(gate["spatial_design"]["prediction_type"], "out_of_fold")
            self.assertEqual(gate["gate"]["fold_wins"], 4)

            template_path = root / "sample_submission.tif"
            template_profile = {
                "driver": "GTiff", "width": shape[1], "height": shape[0],
                "count": 1, "dtype": "float32", "crs": "EPSG:32611",
                "transform": Affine(100, 0, 500000, 0, -100, 4200000),
                "nodata": np.nan,
            }
            with rasterio.open(template_path, "w", **template_profile) as dst:
                dst.write(np.zeros(shape, dtype=np.float32), 1)
            final_probabilities = np.full(shape, 0.05, dtype=np.float32)
            for point in truth_points:
                final_probabilities[point] = 0.95
            probability_path = root / "final-probabilities.npy"
            np.save(probability_path, final_probabilities)
            config_path, config_digest, config = config_paths["H1-edge-consensus"]
            inference_path = root / "final-inference-report.json"
            write_json(inference_path, {
                "candidate_id": "H1-edge-consensus",
                "candidate_spec_sha256": config_digest,
                "candidate_spec": config,
                "training_mode": "full-data",
                "member_count": 5,
                "calibrated": False,
                "files": {"mean_probability_sha256": sha256(probability_path)},
            })
            output_dir = root / "submissions"
            command = [
                sys.executable, str(ROOT / "scripts/build_submission.py"),
                "--strategy", "H1-edge-consensus",
                "--probabilities", str(probability_path),
                "--template", str(template_path),
                "--config", str(config_path),
                "--inference-report", str(inference_path),
                "--gate-report", str(gate_path),
                "--out-dir", str(output_dir),
            ]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = json.loads(result.stdout)
            self.assertIn("inference_report_sha256", manifest)
            self.assertIn("candidate_spec", manifest)
            self.assertEqual(manifest["candidate_spec"]["config_sha256"], config_digest)
            self.assertEqual(manifest["probabilities_sha256"], sha256(probability_path))
            self.assertEqual(manifest["template_sha256"], sha256(template_path))
            artifact_path = output_dir / manifest["file"]
            self.assertTrue(artifact_path.is_file())
            self.assertTrue(artifact_path.with_suffix(".json").is_file())


if __name__ == "__main__":
    unittest.main()
