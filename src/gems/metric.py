"""Competition distance-weighted Tversky index (DTI).

The equations and alpha/beta/radius defaults follow the official problem page.
The implementation uses the same triangular distance kernel. It intentionally
fails if SciPy/NumPy are not installed rather than substituting an approximate
metric.
"""

from __future__ import annotations

from typing import Any


def distance_weighted_tversky(
    predictions: Any,
    truth: Any,
    *,
    mask: Any | None = None,
    pixel_size_m: float = 100.0,
    radius_m: float = 300.0,
    alpha: float = 0.2,
    beta: float = 0.8,
    epsilon: float = 1e-12,
) -> dict[str, float]:
    """Compute the official distance-weighted Tversky score for one raster.

    For each ground-truth pixel, TP is the maximum nearby prediction weighted
    by `max(1 - distance/radius, 0)`; FN is its residual. FP is the prediction
    weight times one minus its nearest-ground-truth kernel weight. Distances are
    Euclidean in map units. Pixels outside `mask` are ignored.

    The returned dictionary includes score and the three weighted components so
    validation reports remain auditable.
    """
    try:
        import numpy as np
        from scipy.ndimage import distance_transform_edt
    except ImportError as exc:  # pragma: no cover - exercised in data environment
        raise RuntimeError("DTI requires numpy and scipy; install requirements.txt") from exc

    if pixel_size_m <= 0 or radius_m <= 0:
        raise ValueError("pixel_size_m and radius_m must be positive")
    if alpha < 0 or beta < 0:
        raise ValueError("alpha and beta must be non-negative")
    p = np.asarray(predictions, dtype=np.float64)
    g = np.asarray(truth, dtype=bool)
    if p.ndim != 2 or g.ndim != 2 or p.shape != g.shape:
        raise ValueError("predictions and truth must be matching 2-D arrays")
    valid = np.ones(p.shape, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if valid.shape != p.shape:
        raise ValueError("mask must match the raster shape")
    if not np.isfinite(p[valid]).all():
        raise ValueError("Predictions must be finite inside the scoring mask")
    if ((p[valid] < 0.0) | (p[valid] > 1.0)).any():
        raise ValueError("Predictions must be in [0, 1]")
    if not g[valid].any():
        raise ValueError("DTI is undefined for a fold with no positive ground-truth pixels")

    p = np.where(valid, p, 0.0)
    g = g & valid

    # The nearest ground-truth distance gives max_g k(distance(x, g)) for each x.
    dist_to_truth = distance_transform_edt(~g, sampling=(pixel_size_m, pixel_size_m))
    gt_kernel_at_prediction = np.clip(1.0 - dist_to_truth / radius_m, 0.0, 1.0)
    fp = float(np.sum(p[valid] * (1.0 - gt_kernel_at_prediction[valid]), dtype=np.float64))

    # For each truth pixel, maximize p(x) * k(distance(x, g)) over x within R.
    h, w = p.shape
    max_offset = int(radius_m // pixel_size_m) + 1
    match = np.zeros(p.shape, dtype=np.float64)
    for dy in range(-max_offset, max_offset + 1):
        for dx in range(-max_offset, max_offset + 1):
            distance = ((dy * pixel_size_m) ** 2 + (dx * pixel_size_m) ** 2) ** 0.5
            if distance > radius_m:
                continue
            kernel = max(1.0 - distance / radius_m, 0.0)
            if dy >= 0:
                dst_y = slice(0, h - dy)
                src_y = slice(dy, h)
            else:
                dst_y = slice(-dy, h)
                src_y = slice(0, h + dy)
            if dx >= 0:
                dst_x = slice(0, w - dx)
                src_x = slice(dx, w)
            else:
                dst_x = slice(-dx, w)
                src_x = slice(0, w + dx)
            np.maximum(
                match[dst_y, dst_x],
                p[src_y, src_x] * kernel,
                out=match[dst_y, dst_x],
            )
    match = np.where(g, match, 0.0)
    tp = float(np.sum(match[g], dtype=np.float64))
    fn = float(np.sum(1.0 - match[g], dtype=np.float64))
    denominator = tp + alpha * fp + beta * fn + epsilon
    return {
        "dti": tp / denominator,
        "tp_weighted": tp,
        "fp_weighted": fp,
        "fn_weighted": fn,
        "alpha": float(alpha),
        "beta": float(beta),
        "radius_m": float(radius_m),
        "pixel_size_m": float(pixel_size_m),
    }
