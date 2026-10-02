#!/usr/bin/env python3
"""Export one uncertainty/survey-coverage record for every labeled candidate."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-labels", type=Path, required=True, help="2-D .npy; integer component ID per candidate pixel, 0=background")
    parser.add_argument("--mean", type=Path, required=True, help="2-D .npy ensemble-mean probabilities")
    parser.add_argument("--epistemic", type=Path, required=True, help="2-D .npy ensemble epistemic variance")
    parser.add_argument("--aleatoric", type=Path, required=True, help="2-D .npy mean conditional Bernoulli variance")
    parser.add_argument("--template", type=Path, required=True, help="official template for map coordinates")
    parser.add_argument("--survey-coverage", type=Path, default=None, help="optional 2-D .npy coverage proxy in [0,1]")
    parser.add_argument("--priority-strength", type=float, default=0.0, help="must be selected using spatially blocked validation")
    parser.add_argument("--calibration-status", default="not supplied")
    parser.add_argument("--survey-source", default="unavailable; no uncertainty adjustment unless a coverage raster is provided")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        import numpy as np
        import rasterio
        from gems.uncertainty import survey_gap_priority

        ids = np.asarray(np.load(args.candidate_labels, mmap_mode="r"))
        p = np.asarray(np.load(args.mean, mmap_mode="r"), dtype=np.float64)
        epi = np.asarray(np.load(args.epistemic, mmap_mode="r"), dtype=np.float64)
        alea = np.asarray(np.load(args.aleatoric, mmap_mode="r"), dtype=np.float64)
        if ids.ndim != 2 or any(a.shape != ids.shape for a in (p, epi, alea)):
            raise ValueError("Candidate ID and uncertainty maps must have matching 2-D shapes")
        if not np.issubdtype(ids.dtype, np.integer) or (ids < 0).any():
            raise ValueError("Candidate labels must be non-negative integer IDs")
        coverage = None if args.survey_coverage is None else np.asarray(np.load(args.survey_coverage, mmap_mode="r"), dtype=np.float64)
        if coverage is not None and coverage.shape != ids.shape:
            raise ValueError("Survey-coverage raster must match candidate map")
        with rasterio.open(args.template) as template:
            if (template.height, template.width) != ids.shape:
                raise ValueError("Candidate map does not match official template dimensions")
            transform, crs = template.transform, template.crs

        max_id = int(ids.max(initial=0))
        if max_id == 0:
            raise ValueError("No candidate component IDs (>0) found")
        flat_ids = ids.ravel().astype(np.int64, copy=False)
        candidate_mask = flat_ids > 0
        counts = np.bincount(flat_ids[candidate_mask], minlength=max_id + 1)
        if (counts[1:] == 0).any():
            # Sparse IDs are ambiguous for a handoff; require canonical 1..N IDs.
            raise ValueError("Candidate IDs must be contiguous positive integers 1..N")
        if not np.isfinite(p[candidate_mask.reshape(ids.shape)]).all():
            raise ValueError("Non-finite mean probability on candidate pixels")
        if not np.isfinite(epi[candidate_mask.reshape(ids.shape)]).all() or (epi[candidate_mask.reshape(ids.shape)] < 0).any():
            raise ValueError("Invalid epistemic variance on candidate pixels")
        if not np.isfinite(alea[candidate_mask.reshape(ids.shape)]).all() or (alea[candidate_mask.reshape(ids.shape)] < 0).any():
            raise ValueError("Invalid aleatoric variance on candidate pixels")

        rows, cols = np.indices(ids.shape)
        sums = {}
        for name, raster in (("p", p), ("epi", epi), ("alea", alea), ("total", p * (1.0 - p)), ("row", rows), ("col", cols)):
            sums[name] = np.bincount(flat_ids[candidate_mask], weights=np.asarray(raster).ravel()[candidate_mask], minlength=max_id + 1)
        coverage_means = None
        if coverage is not None:
            cov_values = coverage[candidate_mask.reshape(ids.shape)]
            if not np.isfinite(cov_values).all() or ((cov_values < 0) | (cov_values > 1)).any():
                raise ValueError("Survey coverage must be finite and in [0,1] for candidate pixels")
            coverage_sums = np.bincount(flat_ids[candidate_mask], weights=coverage.ravel()[candidate_mask], minlength=max_id + 1)
            coverage_means = coverage_sums[1:] / counts[1:]

        p_means = sums["p"][1:] / counts[1:]
        epi_means = sums["epi"][1:] / counts[1:]
        alea_means = sums["alea"][1:] / counts[1:]
        if coverage_means is None:
            priority = survey_gap_priority(p_means.tolist(), epi_means.tolist(), None, strength=args.priority_strength)
            adjustments = [0.0] * len(p_means)
            priority_scores = priority["priority_score"]
        else:
            priority = survey_gap_priority(p_means.tolist(), epi_means.tolist(), coverage_means.tolist(), strength=args.priority_strength)
            adjustments = priority["adjustment"]
            priority_scores = priority["priority_score"]

        args.output.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "candidate_id", "pixel_count", "centroid_row", "centroid_col", "easting_m", "northing_m",
            "mean_probability", "epistemic_variance", "aleatoric_variance", "predictive_variance",
            "survey_coverage_proxy", "survey_gap_adjustment", "review_priority_score",
            "uncertainty_interpretation", "calibration_status", "survey_source", "is_submission_probability",
        ]
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for i, candidate_id in enumerate(range(1, max_id + 1)):
                row = sums["row"][candidate_id] / counts[candidate_id]
                col = sums["col"][candidate_id] / counts[candidate_id]
                x, y = rasterio.transform.xy(transform, row, col, offset="center")
                if epi_means[i] > alea_means[i]:
                    interpretation = "higher ensemble disagreement; inspect evidence and mapped coverage"
                elif alea_means[i] > epi_means[i]:
                    interpretation = "members agree more; conditional Bernoulli ambiguity is larger"
                else:
                    interpretation = "epistemic and conditional variance are equal"
                if coverage_means is None:
                    interpretation += "; no coverage adjustment applied"
                writer.writerow({
                    "candidate_id": candidate_id,
                    "pixel_count": int(counts[candidate_id]),
                    "centroid_row": f"{row:.3f}",
                    "centroid_col": f"{col:.3f}",
                    "easting_m": f"{x:.3f}",
                    "northing_m": f"{y:.3f}",
                    "mean_probability": f"{p_means[i]:.8g}",
                    "epistemic_variance": f"{epi_means[i]:.8g}",
                    "aleatoric_variance": f"{alea_means[i]:.8g}",
                    "predictive_variance": f"{sums['total'][candidate_id] / counts[candidate_id]:.8g}",
                    "survey_coverage_proxy": "" if coverage_means is None else f"{coverage_means[i]:.8g}",
                    "survey_gap_adjustment": f"{float(adjustments[i]):.8g}",
                    "review_priority_score": f"{float(priority_scores[i]):.8g}",
                    "uncertainty_interpretation": interpretation,
                    "calibration_status": args.calibration_status,
                    "survey_source": args.survey_source if coverage_means is not None else "unknown; no coverage layer",
                    "is_submission_probability": "false",
                })
        print(json.dumps({"candidate_count": max_id, "rows_written": max_id, "output": str(args.output), "crs": None if crs is None else crs.to_string(), "coverage_adjustment_applied": coverage_means is not None, "note": "priority is review triage, not a calibrated probability"}, indent=2))
        return 0
    except Exception as exc:
        print(f"export_candidate_review: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
