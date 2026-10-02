"""Label-independent geological feature transforms proposed for blocked testing."""

from __future__ import annotations

from typing import Mapping, Sequence


REQUIRED_EDGE_CHANNELS = (
    "tmi",
    "reduced_to_pole",
    "isostatic_gravity",
    "surface_conductivity",
    "conductive_base_depth",
)


def multiscale_geophysical_edge_consensus(
    layers: Mapping[str, object],
    valid_mask: object,
    *,
    scales_pixels: Sequence[float] = (1.0, 2.0, 4.0),
) -> object:
    """Compute a bounded cross-family edge-normal concordance feature.

    Expected layer keys are `tmi`, `reduced_to_pole`, `isostatic_gravity`,
    `surface_conductivity`, and `conductive_base_depth`. These labels must be
    mapped from the actual GeoTIFF band descriptions after data placement; this
    function refuses silently guessed band indices.

    At each Gaussian scale, gradient magnitudes are robustly scaled to their
    in-footprint 95th percentile. The score averages pairwise products of edge
    strengths across independent magnetic, geopotential, and conductive groups,
    weighted by absolute gradient-normal alignment (0 to 1). It is a feature,
    not a fault probability, and must be evaluated against a matched baseline.
    """
    try:
        import numpy as np
        from scipy.ndimage import gaussian_filter
    except ImportError as exc:  # pragma: no cover - data environment only
        raise RuntimeError("Geophysical edge transforms require numpy and scipy") from exc

    missing = [key for key in REQUIRED_EDGE_CHANNELS if key not in layers]
    if missing:
        raise ValueError(f"Missing named feature layers (do not guess band indexes): {missing}")
    mask = np.asarray(valid_mask, dtype=bool)
    if mask.ndim != 2 or not mask.any():
        raise ValueError("valid_mask must be a non-empty 2-D array")
    arrays = {}
    for key in REQUIRED_EDGE_CHANNELS:
        value = np.asarray(layers[key], dtype=np.float32)
        if value.shape != mask.shape:
            raise ValueError(f"Layer {key!r} has shape {value.shape}; expected {mask.shape}")
        valid = mask & np.isfinite(value) & (np.abs(value) < 1e30)
        if not valid.any():
            raise ValueError(f"Layer {key!r} has no finite in-footprint pixels")
        fill = float(np.median(value[valid]))
        arrays[key] = np.where(valid, value, fill).astype(np.float32, copy=False)
    if not scales_pixels or any(float(s) <= 0 for s in scales_pixels):
        raise ValueError("scales_pixels must contain positive values")

    groups = {
        "magnetic": ("tmi", "reduced_to_pole"),
        "geopotential": ("isostatic_gravity",),
        "conductive": ("surface_conductivity", "conductive_base_depth"),
    }
    group_vectors = []
    for sigma in scales_pixels:
        per_channel = {}
        for name, image in arrays.items():
            smooth = gaussian_filter(image, sigma=float(sigma), mode="nearest")
            gy, gx = np.gradient(smooth)
            magnitude = np.hypot(gx, gy)
            good = magnitude[mask & np.isfinite(magnitude)]
            scale = float(np.percentile(good, 95.0)) if good.size else 0.0
            if not np.isfinite(scale) or scale <= 1e-12:
                strength = np.zeros(mask.shape, dtype=np.float32)
            else:
                strength = np.clip(magnitude / scale, 0.0, 1.0).astype(np.float32)
            norm = np.maximum(magnitude, 1e-12)
            per_channel[name] = (strength, gx / norm, gy / norm)

        family = {}
        for group, members in groups.items():
            member_strengths = [per_channel[name][0] for name in members]
            member_gx = [per_channel[name][1] for name in members]
            member_gy = [per_channel[name][2] for name in members]
            # Edge normals are unoriented: use doubled-angle structure tensors
            # so opposite gradient polarity does not cancel the same boundary.
            strength_stack = np.stack(member_strengths, axis=0)
            gx_stack = np.stack(member_gx, axis=0)
            gy_stack = np.stack(member_gy, axis=0)
            weights = strength_stack
            c2 = np.sum(weights * (gx_stack * gx_stack - gy_stack * gy_stack), axis=0)
            s2 = np.sum(weights * (2.0 * gx_stack * gy_stack), axis=0)
            magnitude = np.hypot(c2, s2)
            theta = 0.5 * np.arctan2(s2, c2)
            coherence = np.clip(magnitude / np.maximum(np.sum(weights, axis=0), 1e-12), 0.0, 1.0)
            family[group] = (
                np.mean(strength_stack, axis=0),
                np.cos(theta),
                np.sin(theta),
                coherence,
            )
        pair_scores = []
        family_names = tuple(family)
        for i, first in enumerate(family_names):
            for second in family_names[i + 1:]:
                a_s, a_x, a_y, a_coherence = family[first]
                b_s, b_x, b_y, b_coherence = family[second]
                alignment = np.clip(np.abs(a_x * b_x + a_y * b_y), 0.0, 1.0)
                source_coherence = np.sqrt(a_coherence * b_coherence)
                pair_scores.append(np.sqrt(a_s * b_s) * alignment * source_coherence)
        group_vectors.append(np.mean(pair_scores, axis=0))

    score = np.mean(group_vectors, axis=0).astype(np.float32)
    score = np.clip(score, 0.0, 1.0)
    score[~mask] = np.nan
    return score
