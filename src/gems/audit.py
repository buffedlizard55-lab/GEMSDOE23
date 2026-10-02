"""Post-hoc audit of a predicted raster against the measured regional fault statistics.

The audit asks two different questions and keeps them apart, because a pattern can be *designed* (a
declared emission rule such as a hard-core 400 m dot spacing) or *inherited* (an artefact of how the input
data were acquired).  Only the second is evidence of a spurious detection.

1. ``describe_emission``  - the same spatial statistics that ``faultstats`` fits on the known catalogue
   (normalised correlation sum at 0.5-30 km, enrichment near long known faults, trace/dot structure,
   coverage), so the arrangement of a prediction can be compared with the arrangement of real faults.
2. ``survey_line_test``   - spectral line detector at the *verified* GeoDAWN acquisition geometry:
   Area 2 traverse lines every 400 m (east-west, so period 4 px along y) and tie lines every 4000 m
   (north-south, so period 40 px along x); Area 1: 200 m / 2000 m.  A sharp spectral line is compared with
   control frequencies drawn from the same spectrum, so the verdict is a rank p-value, not a threshold
   picked by eye.  The same detector is run on the official feature bands to establish whether the survey
   lines are visible in the 100 m inputs at all.
3. ``edge_jump``          - density ratio across an acquisition / coverage boundary (footprint edge,
   lidar-validity edge, Area 1 / Area 2 edge) relative to the same ratio for the known catalogue.

Verified geometry (USGS GeoDAWN metadata, sibling mirror data/external/audit_sources/GeoDAWN Metadata
FINAL.csv; DOI 10.5066/P93LGLVQ): traverse_line_spacing_meters "Area 1: 200m  Area 2: 400m",
traverse_line_direction_degCCW_fromN 90, tie_line_spacing_meters "Area 1: 2000m  Area 2: 4000m",
tie_line_direction_degCCW_fromN 180.
"""
from __future__ import annotations

import io
import zipfile
from typing import Dict, Optional, Sequence

import numpy as np
from scipy import ndimage as ndi

from . import faultstats as fs

PIXEL_M = 100.0
AREA2_LINE_PX = 4.0      # 400 m traverse spacing
AREA2_TIE_PX = 40.0      # 4000 m tie spacing
AREA1_LINE_PX = 2.0
AREA1_TIE_PX = 20.0


# ------------------------------------------------------------------------------------------------
# geometry helpers
# ------------------------------------------------------------------------------------------------
def rasterize_polygon_zip(zip_path: str, transform, shape) -> np.ndarray:
    """Rasterise the single polygon of a zipped shapefile (EPSG:32611 coordinates) onto the grid."""
    import shapefile
    from rasterio import features
    zf = zipfile.ZipFile(zip_path)
    shp = [n for n in zf.namelist() if n.lower().endswith(".shp")][0]
    dbf = [n for n in zf.namelist() if n.lower().endswith(".dbf")]
    rd = shapefile.Reader(shp=io.BytesIO(zf.read(shp)), dbf=io.BytesIO(zf.read(dbf[0])) if dbf else None)
    geoms = [s.__geo_interface__ for s in rd.shapes()]
    return features.rasterize([(g, 1) for g in geoms], out_shape=shape, transform=transform, fill=0,
                              dtype="uint8", all_touched=False).astype(bool)


def distance_to_boundary_km(region: np.ndarray, pixel_m: float = PIXEL_M) -> np.ndarray:
    """Signed distance (km) to the boundary of ``region``: positive inside, negative outside."""
    inside = ndi.distance_transform_edt(region) * pixel_m / 1000.0
    outside = ndi.distance_transform_edt(~region) * pixel_m / 1000.0
    return np.where(region, inside, -outside)


# ------------------------------------------------------------------------------------------------
# spectral line detector
# ------------------------------------------------------------------------------------------------
def _detrend(profile: np.ndarray, window: int) -> np.ndarray:
    k = np.ones(window) / window
    pad = window // 2
    p = np.pad(profile, pad, mode="edge")
    sm = np.convolve(p, k, mode="same")[pad:-pad if pad else None]
    return profile - sm[:len(profile)]


def line_strength(profile: np.ndarray, f0: float, guard: float = 0.0015, band: float = 0.012,
                  detrend_window: int = 61) -> float:
    """Peak power within +-guard of f0 divided by the median power of the surrounding band."""
    x = np.asarray(profile, float)
    x = _detrend(x, detrend_window)
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    fr = np.fft.rfftfreq(len(x))
    near = np.abs(fr - f0) <= guard
    ring = (np.abs(fr - f0) > guard) & (np.abs(fr - f0) <= band)
    if not near.any() or not ring.any() or np.median(spec[ring]) <= 0:
        return float("nan")
    return float(spec[near].max() / np.median(spec[ring]))


def periodicity_test(profile: np.ndarray, f0: float, n_controls: int = 60, seed: int = 0,
                     f_lo: float = 0.04, f_hi: float = 0.45, exclude: float = 0.02,
                     harmonics: Sequence[float] = (1.0,)) -> Dict:
    """Is there a spectral line at f0?  The statistic is compared with ``n_controls`` control frequencies
    chosen uniformly in [f_lo, f_hi] away from f0 and its harmonics (rank p-value)."""
    rng = np.random.default_rng(seed)
    s0 = line_strength(profile, f0)
    bad = [f0 * h for h in harmonics]
    ctrl = []
    tries = 0
    while len(ctrl) < n_controls and tries < 10000:
        tries += 1
        f = rng.uniform(f_lo, f_hi)
        if all(abs(f - b) > exclude for b in bad) and f > 0.012 + 0.0015:
            ctrl.append(line_strength(profile, f))
    ctrl = np.array([c for c in ctrl if np.isfinite(c)])
    p = float((np.sum(ctrl >= s0) + 1) / (len(ctrl) + 1)) if np.isfinite(s0) else float("nan")
    return dict(f0=float(f0), strength=float(s0), control_median=float(np.median(ctrl)) if ctrl.size else float("nan"),
                control_p95=float(np.percentile(ctrl, 95)) if ctrl.size else float("nan"), p_rank=p, n_controls=int(ctrl.size))


def survey_line_test(raster: np.ndarray, region: np.ndarray, area1: Optional[np.ndarray] = None) -> Dict:
    """Run the detector on the traverse (period 4 px along y) and tie-line (period 40 px along x) frequencies
    using row / column means of ``raster`` inside ``region`` (Area 2 = footprint minus Area 1)."""
    reg = region if area1 is None else (region & ~area1)
    r = np.where(reg, raster, 0.0).astype(np.float64)
    cnt_y = reg.sum(1).astype(float)
    cnt_x = reg.sum(0).astype(float)
    rows = np.where(cnt_y > 200, r.sum(1) / np.maximum(cnt_y, 1), np.nan)
    cols = np.where(cnt_x > 200, r.sum(0) / np.maximum(cnt_x, 1), np.nan)
    # use only the longest contiguous run of valid rows / columns so the FFT sees a clean series
    def longest(v):
        ok = np.isfinite(v)
        best = (0, 0, 0)
        i = 0
        while i < len(ok):
            if ok[i]:
                j = i
                while j < len(ok) and ok[j]:
                    j += 1
                if j - i > best[0]:
                    best = (j - i, i, j)
                i = j
            else:
                i += 1
        return v[best[1]:best[2]]
    ry, cx = longest(rows), longest(cols)
    out = {}
    if ry.size > 200:
        out["traverse_400m_along_y"] = periodicity_test(ry, 1.0 / AREA2_LINE_PX, harmonics=(1.0, 2.0))
    if cx.size > 200:
        out["tie_4km_along_x"] = periodicity_test(cx, 1.0 / AREA2_TIE_PX, f_lo=0.006, f_hi=0.08, exclude=0.003)
    return out


# ------------------------------------------------------------------------------------------------
# edge / boundary jump
# ------------------------------------------------------------------------------------------------
def density_across_boundary(mask: np.ndarray, domain: np.ndarray, signed_km: np.ndarray,
                            edges_km: Sequence[float] = (-10, -5, -2, -1, 0, 1, 2, 5, 10)) -> Dict:
    """Emitted-pixel density (per domain pixel) in signed-distance bands across a boundary."""
    rows = []
    for lo, hi in zip(edges_km[:-1], edges_km[1:]):
        band = domain & (signed_km > lo) & (signed_km <= hi)
        n = int(band.sum())
        rows.append(dict(lo_km=float(lo), hi_km=float(hi), n_domain=n,
                         density=float((mask & band).sum() / n) if n else float("nan")))
    return dict(bands=rows)


def edge_jump(mask: np.ndarray, domain: np.ndarray, region: np.ndarray, reference: np.ndarray,
              ref_domain: Optional[np.ndarray] = None, width_km: float = 3.0) -> Dict:
    """Density ratio inside/outside ``region`` within ``width_km`` of its boundary, for the prediction
    (measured over ``domain``) and for the reference mask (measured over ``ref_domain``; the known catalogue
    lives *outside* the scored domain by construction, so its density must be taken over the footprint).
    ``jump_index`` = ratio_pred / ratio_ref; 1 means the boundary affects the prediction no more than it
    affects the real faults."""
    ref_domain = domain if ref_domain is None else ref_domain
    sd = distance_to_boundary_km(region)
    inn, out = domain & (sd > 0) & (sd <= width_km), domain & (sd <= 0) & (sd > -width_km)
    rin, rout = ref_domain & (sd > 0) & (sd <= width_km), ref_domain & (sd <= 0) & (sd > -width_km)
    if min(inn.sum(), out.sum(), rin.sum(), rout.sum()) < 1000:
        return dict(note="boundary bands too small", n_in=int(inn.sum()), n_out=int(out.sum()))
    dp_in, dp_out = float(mask[inn].mean()), float(mask[out].mean())
    dr_in, dr_out = float(reference[rin].mean()), float(reference[rout].mean())
    rp = dp_in / dp_out if dp_out > 0 else float("nan")
    rr = dr_in / dr_out if dr_out > 0 else float("nan")
    return dict(width_km=float(width_km), n_in=int(inn.sum()), n_out=int(out.sum()),
                pred_density_in=dp_in, pred_density_out=dp_out, ratio_pred=float(rp),
                ref_density_in=dr_in, ref_density_out=dr_out, ratio_ref=float(rr),
                jump_index=float(rp / rr) if np.isfinite(rp) and np.isfinite(rr) and rr > 0 else float("nan"))


# ------------------------------------------------------------------------------------------------
# arrangement descriptors
# ------------------------------------------------------------------------------------------------
NCC_R_M = np.array([500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000], float)


def ncc_pixels(mask: np.ndarray, footprint: np.ndarray, n_null: int = 25, seed: int = 0,
               max_points: int = 30000, r_m: np.ndarray = NCC_R_M) -> Dict:
    rr, cc = np.nonzero(mask)
    pts = np.column_stack([cc, rr]).astype(float) * PIXEL_M
    return fs.ncc_2d(pts, footprint, r_m, n_null=n_null, seed=seed, max_points=max_points)


def near_long_enrichment(mask: np.ndarray, domain: np.ndarray, dist_long_m: np.ndarray,
                         bands_m: Sequence[Sequence[float]] = ((200, 1000), (1000, 2500), (2500, 7000), (7000, 1e9))) -> Dict:
    """Fraction of emitted pixels in each distance band from long known faults divided by the fraction of
    the domain in that band (1 = placement independent of the known long faults)."""
    out = {}
    tot_e = max(int(mask[domain].sum()), 1)
    for lo, hi in bands_m:
        zone = domain & (dist_long_m > lo) & (dist_long_m <= hi)
        out[f"{int(lo)}-{int(min(hi, 99999))}m"] = float(((mask & zone).sum() / tot_e) / (zone.sum() / domain.sum()))
    return out


def structure_summary(mask: np.ndarray) -> Dict:
    """How the emitted pixels are organised: component count, size quantiles, share in components of
    >= 5 px (line-like) versus isolated dots, and the isolation fraction at 4 px (400 m)."""
    lab, n = ndi.label(mask, structure=fs.STRUCT8)
    sizes = np.bincount(lab.ravel())[1:] if n else np.zeros(0, int)
    d_other = ndi.distance_transform_edt(~mask, return_indices=False)
    # nearest *other* emitted pixel: distance transform of mask minus self is not available directly, so
    # use a 3x3 erosion proxy: pixels with no emitted neighbour in the 8-neighbourhood are 'isolated dots'
    nb = ndi.convolve(mask.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - mask.astype(np.uint8)
    isolated = mask & (nb == 0)
    return dict(n_pixels=int(mask.sum()), n_components=int(n),
                size_median=float(np.median(sizes)) if n else 0.0,
                size_p90=float(np.percentile(sizes, 90)) if n else 0.0,
                share_in_components_ge5=float(sizes[sizes >= 5].sum() / max(sizes.sum(), 1)) if n else 0.0,
                share_isolated_dots=float(isolated.sum() / max(mask.sum(), 1)))


def log_divergence(sum_ratio_pred: Sequence[float], sum_ratio_ref: Sequence[float],
                   idx: Optional[Sequence[int]] = None) -> float:
    """RMS difference of log NCC-sum over the chosen scales."""
    a = np.log(np.clip(np.asarray(sum_ratio_pred, float), 1e-3, None))
    b = np.log(np.clip(np.asarray(sum_ratio_ref, float), 1e-3, None))
    if idx is not None:
        a, b = a[list(idx)], b[list(idx)]
    ok = np.isfinite(a) & np.isfinite(b)
    return float(np.sqrt(np.mean((a[ok] - b[ok]) ** 2))) if ok.any() else float("nan")


# ------------------------------------------------------------------------------------------------
# verdicts and remediation
# ------------------------------------------------------------------------------------------------
def survey_flags(line_tests: Dict, alpha: float = 0.05) -> Dict[str, bool]:
    """True where the rank p-value of a spectral line at the verified survey period is <= alpha.
    With 60 control frequencies the smallest attainable p is 1/61 = 0.016, so a flag means 'the line is
    stronger than every control frequency tried', not an asymptotic significance claim."""
    out = {}
    for k, v in (line_tests or {}).items():
        p = v.get("p_rank", float("nan"))
        out[k] = bool(np.isfinite(p) and p <= alpha)
    return out


def row_phase_hist(mask: np.ndarray, period: int = 4) -> np.ndarray:
    rows, _ = np.nonzero(mask)
    return np.bincount(rows % period, minlength=period) / max(len(rows), 1)


def _disc_offsets(r: float):
    rc = int(np.ceil(r))
    return [(dy, dx) for dy in range(-rc, rc + 1) for dx in range(-rc, rc + 1)
            if (dy or dx) and dy * dy + dx * dx < r * r]


def equalize_row_phase(mask: np.ndarray, domain: np.ndarray, period: int = 4, block: int = 300,
                       min_sep_px: float = 4.0, max_shift: int = 2, seed: int = 0, tol: float = 0.005,
                       min_dots: int = 40, forbid: Optional[np.ndarray] = None) -> Dict:
    """Remove a systematic row preference at the survey-line period with the fewest possible moves.

    Inside every ``block`` x ``block`` window the dots are counted by row phase (row % period).  Dots are moved
    from over-represented to under-represented phases by the smallest vertical shift (<= ``max_shift`` px) that
    keeps the dot inside the window, inside ``domain``, off ``forbid`` and at least ``min_sep_px`` from every
    other dot.  Only the *excess* moves, so with a 5-8 % excess roughly that share of dots shifts by 100 m.
    Returns the new mask and the move statistics."""
    rng = np.random.default_rng(seed)
    new = mask.copy()
    H, W = mask.shape
    offs = _disc_offsets(min_sep_px)
    moved, shifts, blocks_done = 0, [], 0

    def free(r, c):
        if r < 0 or c < 0 or r >= H or c >= W or not domain[r, c] or new[r, c]:
            return False
        if forbid is not None and forbid[r, c]:
            return False
        for dy, dx in offs:
            rr, cc = r + dy, c + dx
            if 0 <= rr < H and 0 <= cc < W and new[rr, cc]:
                return False
        return True

    for r0 in range(0, H, block):
        for c0 in range(0, W, block):
            sub = new[r0:r0 + block, c0:c0 + block]
            rr, cc = np.nonzero(sub)
            n = len(rr)
            if n < min_dots:
                continue
            blocks_done += 1
            rr = rr + r0
            cc = cc + c0
            ph = rr % period
            counts = np.bincount(ph, minlength=period).astype(float)
            target = n / period
            dead = set()
            for _ in range(10 * n):
                exc = counts - target
                order_p = [p for p in np.argsort(-exc) if exc[p] > max(1.0, tol * n) and p not in dead]
                if not order_p:
                    break
                p = order_p[0]
                q = int(np.argmin(exc))
                if exc[q] >= -0.5:
                    break
                idx = np.flatnonzero(ph == p)
                rng.shuffle(idx)
                did = False
                for i in idx[:300]:
                    r, c = int(rr[i]), int(cc[i])
                    cand = sorted((d for d in range(-max_shift, max_shift + 1) if d and (r + d) % period == q), key=abs)
                    for d in cand:
                        r2 = r + d
                        if not (r0 <= r2 < min(r0 + block, H)):
                            continue
                        new[r, c] = False
                        if free(r2, c):
                            new[r2, c] = True
                            rr[i] = r2
                            ph[i] = q
                            counts[p] -= 1
                            counts[q] += 1
                            moved += 1
                            shifts.append(abs(d))
                            did = True
                            break
                        new[r, c] = True
                    if did:
                        break
                if not did:
                    dead.add(int(p))
    return dict(mask=new, n_moved=int(moved), share_moved=float(moved / max(mask.sum(), 1)),
                mean_abs_shift_px=float(np.mean(shifts)) if shifts else 0.0, blocks=int(blocks_done),
                hist_before=[float(v) for v in row_phase_hist(mask, period)],
                hist_after=[float(v) for v in row_phase_hist(new, period)])


def signed_log_divergence(sum_ratio_pred: Sequence[float], sum_ratio_ref: Sequence[float],
                          idx: Optional[Sequence[int]] = range(2, 10)) -> float:
    """Mean of log NCC_pred - log NCC_ref over the chosen scales (default 2-30 km).  Negative = less clustered than
    the reference (the known catalogue), positive = more clustered.  The symmetric RMS ``log_divergence`` cannot tell a
    flat lattice from a catalogue-hugging detector; the sign can."""
    a = np.log(np.clip(np.asarray(sum_ratio_pred, float), 1e-3, None))
    b = np.log(np.clip(np.asarray(sum_ratio_ref, float), 1e-3, None))
    if idx is not None:
        a, b = a[list(idx)], b[list(idx)]
    ok = np.isfinite(a) & np.isfinite(b)
    return float((a[ok] - b[ok]).mean()) if ok.any() else float("nan")


# Bins are DESCRIPTIVE and were defined after looking at the 23 live-scored emissions (docs/data/prediction-audit.json);
# they summarise where the live scores fell, they are not a validated rule.
ARRANGEMENT_BINS = (
    (-9.0, -0.55, "lattice-like (flat, Poisson-like at >= 1 km)"),
    (-0.55, -0.15, "mildly less clustered than the catalogue (the bin holding the best live scores)"),
    (-0.15, 0.20, "catalogue-like"),
    (0.20, 9.0, "over-clustered (catalogue-hugging)"),
)


def arrangement_bin(signed: float) -> str:
    if not np.isfinite(signed):
        return "unclassified"
    for lo, hi, name in ARRANGEMENT_BINS:
        if lo <= signed < hi:
            return name
    return "unclassified"
