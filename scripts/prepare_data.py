#!/usr/bin/env python3
"""Validate official rasters and prepare robustly scaled, block-written arrays."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _grid_signature(ds):
    return (ds.width, ds.height, ds.count, ds.crs, ds.transform)


def prepare(data_dir: Path, out_dir: Path, block_size: int = 512, sample_stride: int = 8) -> dict:
    feature_candidates = [data_dir / "training_features.tif", data_dir / "numeric_features.tif"]
    present_features = [path for path in feature_candidates if path.is_file()]
    if len(present_features) > 1:
        raise ValueError(
            "Both training_features.tif and numeric_features.tif are present; choose the verified official file and remove the ambiguity"
        )
    required = {
        "features": present_features[0] if present_features else feature_candidates[0],
        "labels": data_dir / "labels.tif",
        "template": data_dir / "sample_submission.tif",
    }
    missing = [str(path) for key, path in required.items() if key != "features" and not path.is_file()]
    if not present_features:
        missing.insert(0, "one feature raster: " + " or ".join(str(path) for path in feature_candidates))
    if missing:
        raise FileNotFoundError(
            "Required competition inputs are missing: " + "; ".join(missing)
            + ". The official data tab requires DrivenData login; see data/README.md."
        )

    try:
        import numpy as np
        import rasterio
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt (numpy and rasterio) before preparation") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    feature_path, labels_path, label_observed_path, footprint_path = (
        out_dir / "features.npy",
        out_dir / "labels.npy",
        out_dir / "label_observed.npy",
        out_dir / "footprint.npy",
    )
    manifest_path = out_dir / "manifest.json"

    with rasterio.open(required["features"]) as features, \
            rasterio.open(required["labels"]) as labels, \
            rasterio.open(required["template"]) as template:
        if labels.count != 1 or template.count != 1:
            raise ValueError("labels.tif and sample_submission.tif must each have one band")
        if features.count < 1:
            raise ValueError("training_features.tif has no bands")
        ref = (template.width, template.height, template.crs, template.transform)
        for name, ds in (("training_features.tif", features), ("labels.tif", labels)):
            got = (ds.width, ds.height, ds.crs, ds.transform)
            if got != ref:
                raise ValueError(f"{name} grid does not exactly match sample_submission.tif")
        if template.crs is None or template.crs.to_epsg() != 32611:
            raise ValueError(f"Expected EPSG:32611 submission template; got {template.crs}")
        if template.transform.a <= 0 or abs(template.transform.a - 100.0) > 1e-6:
            raise ValueError(f"Expected 100 m pixel size; got transform {template.transform}")
        if abs(template.transform.e + 100.0) > 1e-6:
            raise ValueError(f"Expected north-up 100 m pixels; got transform {template.transform}")

        bands, height, width = features.count, features.height, features.width
        x_out = np.lib.format.open_memmap(
            feature_path, mode="w+", dtype=np.float32, shape=(bands, height, width)
        )
        y_out = np.lib.format.open_memmap(
            labels_path, mode="w+", dtype=np.uint8, shape=(height, width)
        )
        label_observed_out = np.lib.format.open_memmap(
            label_observed_path, mode="w+", dtype=np.uint8, shape=(height, width)
        )
        mask_out = np.lib.format.open_memmap(
            footprint_path, mode="w+", dtype=np.uint8, shape=(height, width)
        )
        sampled: list[list] = [[] for _ in range(bands)]
        footprint_count = 0
        positive_count = 0
        label_missing_count = 0

        # Pass 1: deterministic, spatially systematic samples for robust per-band
        # medians/IQR. This avoids retaining all 19 source bands in RAM.
        for row in range(0, height, block_size):
            h = min(block_size, height - row)
            for col in range(0, width, block_size):
                w = min(block_size, width - col)
                window = Window(col, row, w, h)
                t = template.read(1, window=window, out_dtype="float32")
                tmask = template.read_masks(1, window=window) > 0
                footprint = np.isfinite(t) & tmask
                footprint_count += int(footprint.sum())

                block = features.read(window=window, out_dtype="float32")
                for b in range(bands):
                    band_mask = features.read_masks(b + 1, window=window) > 0
                    values = block[b, ::sample_stride, ::sample_stride]
                    valid = (
                        footprint[::sample_stride, ::sample_stride]
                        & band_mask[::sample_stride, ::sample_stride]
                        & np.isfinite(values)
                        & (np.abs(values) < 1e30)
                    )
                    if valid.any():
                        # A systematic fixed stride is deterministic and bounded
                        # (about 1/64 of the 100 m raster).
                        sampled[b].append(values[valid].astype(np.float32, copy=True))

                lb = labels.read(1, window=window, out_dtype="float32")
                lmask = labels.read_masks(1, window=window) > 0
                lvalid = np.isfinite(lb) & lmask & (np.abs(lb) < 1e30)
                label_missing_count += int((footprint & ~lvalid).sum())
                positive_count += int((footprint & lvalid & (lb > 0)).sum())

        medians, scales, sample_counts = [], [], []
        for b, chunks in enumerate(sampled):
            if not chunks:
                raise ValueError(f"Feature band {b + 1} has no valid sample pixels")
            values = np.concatenate(chunks).astype(np.float64, copy=False)
            q25, median, q75 = np.percentile(values, [25.0, 50.0, 75.0])
            scale = float(q75 - q25)
            if not math.isfinite(scale) or scale < 1e-12:
                scale = 1.0
            medians.append(float(median))
            scales.append(scale)
            sample_counts.append(int(values.size))

        # Pass 2: normalize each block to median/IQR, clip extreme tails, and
        # write all arrays in a memory-bounded manner.
        for row in range(0, height, block_size):
            h = min(block_size, height - row)
            for col in range(0, width, block_size):
                w = min(block_size, width - col)
                window = Window(col, row, w, h)
                t = template.read(1, window=window, out_dtype="float32")
                tmask = template.read_masks(1, window=window) > 0
                footprint = np.isfinite(t) & tmask
                mask_out[row:row + h, col:col + w] = footprint.astype(np.uint8)

                lb = labels.read(1, window=window, out_dtype="float32")
                lmask = labels.read_masks(1, window=window) > 0
                lvalid = np.isfinite(lb) & lmask & (np.abs(lb) < 1e30) & footprint
                y_out[row:row + h, col:col + w] = (lvalid & (lb > 0)).astype(np.uint8)
                label_observed_out[row:row + h, col:col + w] = lvalid.astype(np.uint8)

                block = features.read(window=window, out_dtype="float32")
                for b in range(bands):
                    band_mask = features.read_masks(b + 1, window=window) > 0
                    good = (
                        footprint
                        & band_mask
                        & np.isfinite(block[b])
                        & (np.abs(block[b]) < 1e30)
                    )
                    normalized = np.zeros((h, w), dtype=np.float32)
                    normalized[good] = (
                        (block[b, good] - medians[b]) / scales[b]
                    ).astype(np.float32)
                    np.clip(normalized, -8.0, 8.0, out=normalized)
                    x_out[b, row:row + h, col:col + w] = normalized

        x_out.flush()
        y_out.flush()
        label_observed_out.flush()
        mask_out.flush()
        feature_band_tags = [features.tags(i + 1) for i in range(bands)]
        descriptions = []
        for i, description in enumerate(features.descriptions):
            tags = feature_band_tags[i]
            tagged_description = next(
                (value for key, value in tags.items() if key.casefold() == "description"),
                None,
            )
            descriptions.append(description or tagged_description or f"band_{i + 1:02d}")
        manifest = {
            "grid": {
                "width": width,
                "height": height,
                "crs": template.crs.to_string(),
                "transform": list(template.transform)[:6],
                "pixel_size_m": float(template.transform.a),
                "bands": bands,
            },
            "feature_descriptions": descriptions,
            "feature_band_tags": feature_band_tags,
            "normalization": {
                "method": "systematic sample median and interquartile range; clipped to [-8, 8]",
                "sample_stride_pixels": sample_stride,
                "sample_count_per_band": sample_counts,
                "median": medians,
                "iqr_scale": scales,
                "invalid_values": "non-finite, raster-mask-invalid, or abs(value) >= 1e30; filled with standardized zero",
            },
            "labels": {
                "positive_pixels": positive_count,
                "missing_inside_footprint_pixels": label_missing_count,
                "background_semantics": "unlabelled, not proven fault-free; training loss must downweight unlabeled pixels",
            },
            "footprint_pixels": footprint_count,
            "source_files": {
                key: {"path": str(path), "sha256": sha256_file(path)}
                for key, path in required.items()
            },
            "preparation": {
                "block_size_pixels": block_size,
                "sample_stride_pixels": sample_stride,
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        del x_out, y_out, label_observed_out, mask_out
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--sample-stride", type=int, default=8)
    args = parser.parse_args()
    try:
        manifest = prepare(args.data_dir, args.out_dir, args.block_size, args.sample_stride)
    except Exception as exc:
        print(f"prepare_data: ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
