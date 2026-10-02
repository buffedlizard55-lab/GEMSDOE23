"""Single-band GeoTIFF writing and strict template-based preflight checks."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def validate_submission(prediction_path: str | Path, template_path: str | Path) -> dict[str, Any]:
    """Validate the competition's one-band float32 raster contract against a template."""
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:  # pragma: no cover - geospatial environment only
        raise RuntimeError("Submission validation requires numpy and rasterio") from exc

    prediction_path, template_path = Path(prediction_path), Path(template_path)
    if not prediction_path.is_file() or not template_path.is_file():
        raise FileNotFoundError("Both prediction and sample-submission template files must exist")
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str, kind: str = "hard requirement") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail, "kind": kind})

    with rasterio.open(template_path) as template, rasterio.open(prediction_path) as pred:
        record("single band", pred.count == 1, f"count={pred.count}")
        record("float32", pred.count == 1 and pred.dtypes[0] == "float32", f"dtypes={pred.dtypes}")
        record("CRS matches template", pred.crs == template.crs, f"prediction={pred.crs}; template={template.crs}")
        record(
            "dimensions match template",
            (pred.width, pred.height) == (template.width, template.height),
            f"prediction={(pred.width, pred.height)}; template={(template.width, template.height)}",
        )
        record("affine transform matches template", pred.transform == template.transform, f"prediction={pred.transform}; template={template.transform}")
        record("EPSG:32611", pred.crs is not None and pred.crs.to_epsg() == 32611, f"EPSG={None if pred.crs is None else pred.crs.to_epsg()}")

        # Avoid reading the prediction twice and only count cells the official
        # template identifies as inside the scoring footprint.
        template_values = template.read(1, masked=False)
        template_mask = template.read_masks(1) > 0
        footprint = np.isfinite(template_values) & template_mask
        prediction_values = pred.read(1, masked=False)
        same_shape = prediction_values.shape == footprint.shape
        if not same_shape:
            record("footprint finite and in range", False, "prediction/template arrays differ in shape")
            record("outside-footprint is null/NaN", False, "prediction/template arrays differ in shape")
            return {
                "passed": False,
                "prediction_path": str(prediction_path),
                "template_path": str(template_path),
                "checks": checks,
            }
        inside = prediction_values[footprint]
        finite_inside = bool(np.isfinite(inside).all())
        range_inside = bool(finite_inside and inside.size > 0 and (inside.min() >= 0.0) and (inside.max() <= 1.0))
        record(
            "finite values in [0, 1] over footprint",
            finite_inside and range_inside,
            f"valid_pixels={int(footprint.sum())}; finite={finite_inside}; min={float(inside.min()) if inside.size and finite_inside else None}; max={float(inside.max()) if inside.size and finite_inside else None}",
        )
        outside = prediction_values[~footprint]
        outside_is_null = bool(np.isnan(outside).all()) if outside.size else True
        record(
            "outside-footprint is null/NaN",
            outside_is_null,
            f"outside_pixels={int(outside.size)}; non_nan_outside={int(np.count_nonzero(~np.isnan(outside)))}",
        )
        nodata = pred.nodata
        nodata_is_nan = nodata is not None and isinstance(nodata, (int, float)) and math.isnan(float(nodata))
        record(
            "NaN nodata tag",
            nodata_is_nan,
            f"nodata={nodata}",
            kind="advisory format convention",
        )
        record(
            "no infinity anywhere",
            not bool(np.isinf(prediction_values).any()),
            f"infinite_pixels={int(np.isinf(prediction_values).sum())}",
        )

    hard_failures = [check for check in checks if check["kind"] == "hard requirement" and not check["passed"]]
    return {
        "passed": not hard_failures,
        "hard_failures": [check["check"] for check in hard_failures],
        "prediction_path": str(prediction_path),
        "template_path": str(template_path),
        "checks": checks,
    }


def write_submission_raster(
    probabilities: Any,
    template_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write one float32 probability band using the sample raster's exact profile."""
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:  # pragma: no cover - geospatial environment only
        raise RuntimeError("GeoTIFF writing requires numpy and rasterio") from exc

    template_path, output_path = Path(template_path), Path(output_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"Missing official template: {template_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(probabilities, dtype=np.float32)
    with rasterio.open(template_path) as template:
        if values.shape != (template.height, template.width):
            raise ValueError(f"Prediction shape {values.shape} does not match template {(template.height, template.width)}")
        base = template.read(1, masked=False)
        footprint = np.isfinite(base) & (template.read_masks(1) > 0)
        inside = values[footprint]
        if not np.isfinite(inside).all():
            raise ValueError("Cannot write: prediction contains NaN/Inf inside the official footprint")
        if inside.size == 0 or inside.min() < 0.0 or inside.max() > 1.0:
            raise ValueError("Cannot write: predicted values must be in range [0, 1]")
        output = values.copy()
        output[~footprint] = np.nan
        profile = template.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype="float32",
            nodata=np.nan,
            compress="lzw",
            predictor=1,
        )
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(output, 1)
            dst.set_band_description(1, "ensemble_mean_fault_probability")
    return output_path
