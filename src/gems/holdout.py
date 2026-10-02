"""Spatially blocked holdout utilities; no random-pixel split is allowed."""

from __future__ import annotations

from typing import Any


def four_quadrant_folds(
    footprint: Any,
    *,
    buffer_m: float = 1500.0,
    pixel_size_m: float = 100.0,
) -> list[dict[str, Any]]:
    """Return four quadrant validation folds and buffered training masks.

    The buffer is a configurable leakage-control distance, not a geological
    constant. Freeze it before comparing candidates and report sensitivity to
    alternate buffers. Each fold validates exactly one quadrant and excludes
    training centers within `buffer_m` of that validation quadrant.
    """
    try:
        import numpy as np
        from scipy.ndimage import distance_transform_edt
    except ImportError as exc:  # pragma: no cover - data environment only
        raise RuntimeError("Spatial folds require numpy and scipy") from exc
    if buffer_m < 0 or pixel_size_m <= 0:
        raise ValueError("buffer_m must be non-negative and pixel_size_m positive")
    fp = np.asarray(footprint, dtype=bool)
    if fp.ndim != 2 or not fp.any():
        raise ValueError("footprint must be a non-empty 2-D mask")
    h, w = fp.shape
    ym, xm = h // 2, w // 2
    regions = [
        (slice(0, ym), slice(0, xm)),
        (slice(0, ym), slice(xm, w)),
        (slice(ym, h), slice(0, xm)),
        (slice(ym, h), slice(xm, w)),
    ]
    folds = []
    for fold_id, (ys, xs) in enumerate(regions):
        validation = np.zeros(fp.shape, dtype=bool)
        validation[ys, xs] = fp[ys, xs]
        distance_to_validation = distance_transform_edt(
            ~validation,
            sampling=(pixel_size_m, pixel_size_m),
        )
        training = fp & ~validation & (distance_to_validation > buffer_m)
        if np.any(training & validation):
            raise AssertionError("Training and validation masks overlap")
        if buffer_m > 0 and np.any(
            training & (distance_to_validation <= buffer_m)
        ):
            raise AssertionError("Spatial training buffer was not enforced")
        folds.append(
            {
                "fold_id": fold_id,
                "validation_mask": validation,
                "training_mask": training,
                "buffer_m": float(buffer_m),
                "validation_pixels": int(validation.sum()),
                "training_pixels": int(training.sum()),
            }
        )
    return folds
