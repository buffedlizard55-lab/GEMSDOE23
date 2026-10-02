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


def multiline_corroborated_fault_consensus(
    features: object,
    valid_mask: object,
    *,
    base_edge_consensus: object | None = None,
    external_dir: object | None = None,
) -> tuple[object, object | None]:
    """Compute a 100% label-free multi-line corroborated physical consensus feature and survey coverage proxy.

    Integrates three independent physical families without touching `labels.tif`:
    1. Topographic / Neotectonic Scarp Family:
       - USGS 1 m 3DEP lidar tectonic-vs-fluvial ratio, piedmont step height,
         Laplacian dipole, antithetic scarp ratio, and 1 m openness / LRM gradient
       - USGS 10 m 3DEP seamless DEM one-sided directional slope / 20 m HGM /
         profile curvature with quantile-matched CDF bridging across the 24.6%
         1 m lidar survey gap (eliminating survey-boundary step seams).
    2. Subsurface Potential-Field & Conductive-Basement Contact Family:
       - 5-band multi-scale structure-tensor edge consensus (`base_edge_consensus`)
       - True Miller & Singh (1994) Magnetic & Gravity Tilt-Angle horizontal
         contact gradients (`arctan2(tmi_vg, tmi_hg)` and `arctan2(grav_vg, grav_slope)`),
         replacing the mislabeled Band 6 (`tc`) radiometric total-count channel
       - Conductive basement step gradient and 150 m upward-continued TMI gradient.
    3. Radiometric Alteration & Hydrothermal Conduit Family:
       - USGS GeoDAWN potassium-metasomatism anomaly (`K/Th` and `U/K` local
         2.1 km high-pass anomalies + `grad(TC)`)
       - OpenEI GDR 1391 silica/cation geothermometer & thermal-spring conduit
         field (`temp_c`, `geothermquartz_c`, `geothermchalc_c`, `geothermcat_c`).

    Returns `(consensus_feature, survey_coverage_proxy)` where both are float32
    2-D arrays in `[0, 1]` inside `valid_mask` and `NaN` outside `valid_mask`.
    """
    import csv
    import gc
    from pathlib import Path
    import numpy as np
    from scipy.ndimage import gaussian_filter, uniform_filter

    mask = np.asarray(valid_mask, dtype=bool)
    if mask.ndim != 2 or not mask.any():
        raise ValueError("valid_mask must be a non-empty 2-D array")
    H, W = mask.shape
    fp_idx = np.flatnonzero(mask.ravel())

    def norm01(arr2d: np.ndarray) -> np.ndarray:
        vals = arr2d[mask & np.isfinite(arr2d)]
        if vals.size == 0:
            return np.zeros((H, W), dtype=np.float32)
        p05, p99 = np.percentile(vals, [5.0, 99.0])
        denom = max(float(p99 - p05), 1e-5)
        out = np.where(mask, np.clip((arr2d - p05) / denom, 0.0, 1.0), 0.0)
        return out.astype(np.float32, copy=False)

    def from_fp(v_fp: np.ndarray) -> np.ndarray:
        out = np.zeros((H, W), dtype=np.float32)
        out.ravel()[fp_idx] = np.asarray(v_fp, dtype=np.float32)
        return out

    x = np.asarray(features) if not hasattr(features, "shape") else features
    if base_edge_consensus is not None:
        edge_base = np.nan_to_num(np.asarray(base_edge_consensus, dtype=np.float32), nan=0.0)
    else:
        edge_base = np.zeros((H, W), dtype=np.float32)

    ext_path = Path(external_dir) if external_dir is not None else None
    has_external = (
        ext_path is not None
        and (ext_path / "lidar_scarp_features_u8.tif").is_file()
        and (ext_path / "dem10_slope_max.f32.npy").is_file()
        and (ext_path / "geodawn_rad_u8.tif").is_file()
        and (ext_path / "geodawn_extensions_u8.tif").is_file()
    )

    if not has_external or x.shape[0] < 19:
        score = np.clip(edge_base, 0.0, 1.0).astype(np.float32)
        score[~mask] = np.nan
        return score, None

    import rasterio

    with rasterio.open(ext_path / "lidar_scarp_features_u8.tif") as lds:
        lid_cov = (lds.read(12).astype(np.float32) / 255.0)
        lid_ok = (lid_cov > 0.5) & mask
        down = lds.read(6).astype(np.float32) / 255.0
        up = lds.read(7).astype(np.float32) / 255.0
        cross = lds.read(8).astype(np.float32) / 255.0
        coh = lds.read(10).astype(np.float32) / 255.0
        tect_fluv = norm01((np.maximum(down, 1.35 * up) * (0.3 + coh)) / (cross + 0.08))
        anti_1m = norm01(up * (0.25 + coh) / (cross + 0.10))
        del down, up, cross, coh
        step = lds.read(3).astype(np.float32) / 255.0
        rel = lds.read(9).astype(np.float32)
        pied_1m = norm01(step / np.sqrt(rel * (100.0 / 255.0) + 9.0))
        del step, rel
        lneg = lds.read(4).astype(np.float32) / 255.0
        lpos = lds.read(5).astype(np.float32) / 255.0
        dipole_1m = norm01(np.sqrt(np.maximum(lneg * lpos, 0.0)))
        del lneg, lpos

    op_path = ext_path / "dem1m_high_prior_openness_lrm.npz"
    if op_path.is_file():
        op_npz = np.load(op_path)
        op_2d = np.zeros((H, W), dtype=np.float32)
        op_2d.ravel()[op_npz["cov_fp_indices"]] = (
            0.35 * op_npz["openness_dipole_max"].astype(np.float32) / 255.0
            + 0.35 * op_npz["openness_asymm_max"].astype(np.float32) / 255.0
            + 0.30 * op_npz["lrm_grad_max"].astype(np.float32) / 255.0
        )
        lid1m_scarp = (
            0.28 * tect_fluv + 0.28 * pied_1m + 0.14 * dipole_1m + 0.12 * anti_1m + 0.18 * norm01(op_2d)
        ).astype(np.float32)
        del op_2d, op_npz
    else:
        lid1m_scarp = (0.35 * tect_fluv + 0.35 * pied_1m + 0.15 * dipole_1m + 0.15 * anti_1m).astype(np.float32)
    del tect_fluv, pied_1m, dipole_1m, anti_1m
    gc.collect()

    s_max10 = from_fp(np.load(ext_path / "dem10_slope_max.f32.npy"))
    one3_10 = from_fp(np.load(ext_path / "dem10_onesided3.f32.npy"))
    d10_scarp = 0.45 * norm01((1.0 - one3_10) * s_max10)
    del s_max10, one3_10
    hgm20_10 = from_fp(np.load(ext_path / "dem10_hgm20_max.f32.npy"))
    one1_10 = from_fp(np.load(ext_path / "dem10_onesided.f32.npy"))
    d10_scarp += 0.35 * norm01((1.0 - one1_10) * np.sqrt(np.clip(hgm20_10, 0.0, None)))
    del hgm20_10, one1_10
    curv_10 = from_fp(np.load(ext_path / "dem10_curv_absmax.f32.npy"))
    d10_scarp += 0.20 * norm01(curv_10)
    del curv_10
    gc.collect()

    comb_lid = 0.72 * lid1m_scarp + 0.28 * d10_scarp
    q_grid = np.linspace(0.0, 1.0, 1001)
    gap_mask = mask & (~lid_ok)
    scarp_seamfree = comb_lid.copy()
    if gap_mask.any() and lid_ok.any():
        scarp_seamfree[gap_mask] = np.interp(
            d10_scarp[gap_mask],
            np.quantile(d10_scarp[gap_mask], q_grid),
            np.quantile(comb_lid[lid_ok], q_grid),
        )
    del lid1m_scarp, d10_scarp, comb_lid, gap_mask
    gc.collect()

    def clean_band(idx: int) -> np.ndarray:
        b = np.asarray(x[idx], dtype=np.float32)
        ok = mask & np.isfinite(b) & (np.abs(b) < 1e30)
        med = float(np.median(b[ok])) if ok.any() else 0.0
        return np.where(ok, b, med).astype(np.float32, copy=False)

    tmi_hg = clean_band(2)
    tmi_vg = clean_band(8)
    grav_slope = clean_band(4)
    grav_vg = clean_band(10)
    depth_base = clean_band(14)

    theta_mag = np.arctan2(tmi_vg, np.maximum(tmi_hg - float(tmi_hg[mask].min()), 1e-3)).astype(np.float32)
    theta_grav = np.arctan2(grav_vg, np.maximum(grav_slope - float(grav_slope[mask].min()), 1e-3)).astype(np.float32)
    del tmi_hg, tmi_vg, grav_slope, grav_vg
    gy_m, gx_m = np.gradient(gaussian_filter(theta_mag, sigma=1.5))
    grad_tmag = np.hypot(gy_m, gx_m).astype(np.float32)
    del theta_mag, gy_m, gx_m
    gy_g, gx_g = np.gradient(gaussian_filter(theta_grav, sigma=1.5))
    grad_tgrav = np.hypot(gy_g, gx_g).astype(np.float32)
    del theta_grav, gy_g, gx_g
    gy_d, gx_d = np.gradient(gaussian_filter(depth_base, sigma=1.5))
    grad_dbase = np.hypot(gy_d, gx_d).astype(np.float32)
    del depth_base, gy_d, gx_d

    with rasterio.open(ext_path / "geodawn_extensions_u8.tif") as eds:
        uk = eds.read(2).astype(np.float32) / 255.0
        up150 = eds.read(4).astype(np.float32) / 255.0
    gy_u, gx_u = np.gradient(gaussian_filter(up150, sigma=1.5))
    grad_up150 = np.hypot(gy_u, gx_u).astype(np.float32)
    del up150, gy_u, gx_u

    geophys_line = (
        0.35 * edge_base
        + 0.25 * norm01(np.sqrt(grad_tmag * grad_tgrav))
        + 0.20 * norm01(grad_dbase)
        + 0.20 * norm01(grad_up150)
    ).astype(np.float32)
    del grad_tmag, grad_tgrav, grad_dbase, grad_up150
    gc.collect()

    with rasterio.open(ext_path / "geodawn_rad_u8.tif") as rds:
        r_k = rds.read(1).astype(np.float32) / 255.0
        r_th = rds.read(2).astype(np.float32) / 255.0
        r_tc = rds.read(4).astype(np.float32) / 255.0
    k_th = (r_k + 0.02) / (r_th + 0.05)
    del r_k, r_th
    k_th_anom = np.maximum(k_th - uniform_filter(k_th, size=21), 0.0)
    del k_th
    uk_anom = np.maximum(uk - uniform_filter(uk, size=21), 0.0)
    del uk
    gy_r, gx_r = np.gradient(gaussian_filter(r_tc, sigma=1.5))
    rad_grad = np.hypot(gy_r, gx_r).astype(np.float32)
    del r_tc, gy_r, gx_r

    therm_imp = np.zeros((H, W), dtype=np.float32)
    well_density_imp = np.zeros((H, W), dtype=np.float32)
    ws_csv = ext_path / "gdr_wellspring_in_footprint.csv"
    if ws_csv.is_file():
        with ws_csv.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                r, c = int(row["row"]), int(row["col"])
                if 0 <= r < H and 0 <= c < W and mask[r, c]:
                    well_density_imp[r, c] = 1.0
                    t = float(row["temp_c"]) if row.get("temp_c") else 20.0
                    tq = float(row["geothermquartz_c"]) if row.get("geothermquartz_c") else 0.0
                    tc_ = float(row["geothermchalc_c"]) if row.get("geothermchalc_c") else 0.0
                    tcat = float(row["geothermcat_c"]) if row.get("geothermcat_c") else 0.0
                    w = float(np.clip((max(t, tq * 0.75, tc_ * 0.75, tcat * 0.65) - 25.0) / 100.0, 0.05, 2.5))
                    if w > therm_imp[r, c]:
                        therm_imp[r, c] = w
    therm_conduit = norm01(0.6 * gaussian_filter(therm_imp, sigma=8.0) + 0.4 * gaussian_filter(therm_imp, sigma=22.0))
    well_survey = norm01(gaussian_filter(well_density_imp, sigma=45.0))
    del therm_imp, well_density_imp

    rad_therm_line = (
        0.35 * norm01(k_th_anom)
        + 0.25 * norm01(uk_anom)
        + 0.25 * norm01(rad_grad)
        + 0.15 * therm_conduit
    ).astype(np.float32)
    del k_th_anom, uk_anom, rad_grad, therm_conduit
    gc.collect()

    second_best = np.minimum(
        np.maximum(scarp_seamfree, geophys_line),
        np.maximum(np.minimum(scarp_seamfree, geophys_line), rad_therm_line),
    )
    corrob_gate = np.clip(second_best / 0.18, 0.45, 1.0)
    consensus = ((0.56 * scarp_seamfree + 0.28 * geophys_line + 0.16 * rad_therm_line) * corrob_gate).astype(np.float32)
    consensus = np.clip(consensus, 0.0, 1.0)
    consensus[~mask] = np.nan

    # Survey coverage proxy in [0, 1] from 1m 3DEP lidar survey footprint + field well/spring sampling density
    survey_coverage = np.clip(0.75 * np.clip(lid_cov, 0.0, 1.0) + 0.25 * well_survey, 0.0, 1.0).astype(np.float32)
    survey_coverage[~mask] = np.nan
    return consensus, survey_coverage
