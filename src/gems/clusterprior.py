"""Empirical geometric prior from the clustering of mapped faults, with its own validation.

The question (user brief, 2026-10-02): do faults cluster around larger faults strongly enough that a
candidate pixel lying near a known larger fault should be preferred to an equally scored isolated one?
This module *measures* the answer instead of assuming it:

* ``enrichment_profile``  - density of a target fault population at distance r from the known long faults,
  relative to the density expected if targets ignored the long faults (1 = no effect), with a spatial-block
  bootstrap interval so that the clustering of the residuals themselves is respected.
* ``blocked_auc``         - out-of-fold discrimination: the profile is fitted on three geographic quadrants
  and used to rank the pixels of the fourth, with AUC against the held-out targets.
* ``lift_map`` / ``tiebreak_bonus`` - the fitted profile as a pixel field and as a deliberately small
  re-ranking term that can only separate near-equal scores.

Two target populations are used because they answer different questions:
  (a) the catalogue's own short traces - how known faults are arranged around known larger faults;
  (b) SGMC faults that the catalogue does not capture (> 300 m from any catalogue pixel) - an independent
      sample of faults *missing from the catalogue*, the population the prize is actually about.
The lift for (b) is the evidence-based one; (a) is an upper bound because mapping effort itself clusters.

None of this is validated against the hidden labels.  A prior that ranks held-out *known* faults is not a
prior that finds *unknown* ones; the live-score calibration in docs/data/prediction-audit.json is the only
evidence on the latter and it does not reward concentration near known faults.
"""
from __future__ import annotations

from typing import Dict, Sequence

import numpy as np
from scipy import ndimage as ndi

DEFAULT_EDGES_M = np.array([0, 200, 400, 600, 1000, 1500, 2500, 4000, 7000, 12000, 20000, 1e9], float)


def _band(dist: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return (dist > lo) & (dist <= hi) if lo > 0 else (dist <= hi)


def enrichment_profile(target: np.ndarray, dist_m: np.ndarray, eligible: np.ndarray,
                       edges_m: Sequence[float] = DEFAULT_EDGES_M, tile: int = 500, n_boot: int = 300,
                       seed: int = 0) -> Dict:
    """E(band) = [targets / eligible pixels in the band] / [targets / eligible pixels overall].

    ``dist_m`` is the distance (m) to the nearest source pixel (e.g. a long known fault), ``eligible`` the
    pixels where a target could occur.  The bootstrap resamples ``tile`` x ``tile`` pixel blocks (default
    50 km) with replacement."""
    edges = np.asarray(edges_m, float)
    H, W = target.shape
    tiles = [(r, c) for r in range(0, H, tile) for c in range(0, W, tile)]
    nb = len(edges) - 1
    ct = np.zeros((len(tiles), nb))
    cd = np.zeros_like(ct)
    for k, (r, c) in enumerate(tiles):
        sl = (slice(r, r + tile), slice(c, c + tile))
        el = eligible[sl]
        if not el.any():
            continue
        db, tg = dist_m[sl], target[sl]
        for j in range(nb):
            m = el & _band(db, edges[j], edges[j + 1])
            cd[k, j] = m.sum()
            ct[k, j] = (tg & m).sum()

    def ratio(idx):
        t, d = ct[idx].sum(0), cd[idx].sum(0)
        tot = ct[idx].sum() / max(cd[idx].sum(), 1)
        return (t / np.maximum(d, 1)) / max(tot, 1e-12)

    rng = np.random.default_rng(seed)
    E = ratio(np.arange(len(tiles)))
    B = np.array([ratio(rng.integers(0, len(tiles), len(tiles))) for _ in range(n_boot)])
    lo, hi = np.nanpercentile(B, [2.5, 97.5], axis=0)
    E = np.where(cd.sum(0) > 0, E, np.nan)
    return dict(edges_m=[float(e) for e in edges], enrichment=[float(v) for v in E], lo=[float(v) for v in lo],
                hi=[float(v) for v in hi], n_eligible=[int(v) for v in cd.sum(0)], n_target=[int(v) for v in ct.sum(0)])


def lift_map(dist_m: np.ndarray, profile: Dict, floor: float = 0.0) -> np.ndarray:
    """Interpolate a fitted profile to a pixel field (log-distance interpolation between band mid-points).
    Bands with no eligible pixels are skipped; the first band (0-200 m) is excluded because distinct
    8-connected traces cannot be closer than 200 m, which makes its value structural."""
    e = np.asarray(profile["edges_m"], float)
    v = np.asarray(profile["enrichment"], float)
    mids = np.where(np.isfinite(e[1:]) & (e[1:] < 1e8), np.sqrt(np.maximum(e[:-1], 100.0) * e[1:]), np.nan)
    ok = np.isfinite(v) & np.isfinite(mids) & (np.arange(len(v)) >= 1)
    x = np.log(mids[ok])
    y = v[ok]
    out = np.interp(np.log(np.maximum(dist_m, 1.0)), x, y)
    return np.maximum(out, floor).astype(np.float32)


def tiebreak_bonus(lift: np.ndarray, weight: float, cap: float | None = None) -> np.ndarray:
    """Additive rank-score bonus in [0, weight]: only lift above 1 earns a bonus (never a penalty), scaled so
    the largest lift in the profile earns exactly ``weight`` (rank units).  With weight ~ 1e-3 .. 1e-2 the
    term can only reorder pixels whose scores differ by less than ``weight``."""
    top = float(np.max(lift) if cap is None else cap)
    if top <= 1.0:
        return np.zeros_like(lift, np.float32)
    return (weight * np.clip((lift - 1.0) / (top - 1.0), 0.0, 1.0)).astype(np.float32)


def _auc_from_scores(score_pos: np.ndarray, score_neg: np.ndarray) -> float:
    """AUC with ties counted as 0.5, computed from the few distinct score values."""
    vals = np.unique(np.concatenate([score_pos, score_neg]))
    if vals.size < 2:
        return 0.5
    ip = np.searchsorted(vals, score_pos)
    ineg = np.searchsorted(vals, score_neg)
    cp = np.bincount(ip, minlength=vals.size).astype(float)
    cn = np.bincount(ineg, minlength=vals.size).astype(float)
    cum_n = np.cumsum(cn) - cn
    auc = (cp * (cum_n + 0.5 * cn)).sum() / (cp.sum() * cn.sum())
    return float(auc)


def blocked_auc(target: np.ndarray, dist_m: np.ndarray, eligible: np.ndarray,
                edges_m: Sequence[float] = DEFAULT_EDGES_M, folds: int = 2) -> Dict:
    """Out-of-fold AUC of the fitted enrichment profile for ``target`` pixels.

    The footprint is cut into ``folds`` x ``folds`` geographic blocks; for each block the profile is fitted
    on the other blocks only (no bootstrap) and applied to the held-out block.  Also reported: the AUC of
    a parameter-free baseline, score = 1 / (1 + d / 1 km), to show how much of the discrimination is simply
    'closer is better'."""
    H, W = target.shape
    rb = np.linspace(0, H, folds + 1).astype(int)
    cb = np.linspace(0, W, folds + 1).astype(int)
    edges = np.asarray(edges_m, float)
    res, base = [], []
    for i in range(folds):
        for j in range(folds):
            te = np.zeros_like(target, bool)
            te[rb[i]:rb[i + 1], cb[j]:cb[j + 1]] = True
            tr_el = eligible & ~te
            prof = enrichment_profile(target, dist_m, tr_el, edges, n_boot=2)
            lm = lift_map(dist_m, prof)
            pos = lm[target & eligible & te]
            neg = lm[~target & eligible & te]
            if pos.size < 50 or neg.size < 50:
                continue
            res.append(_auc_from_scores(pos, neg))
            b = 1.0 / (1.0 + dist_m / 1000.0)
            base.append(_auc_from_scores(np.round(b[target & eligible & te], 3), np.round(b[~target & eligible & te], 3)))
    return dict(auc_folds=[float(a) for a in res], auc_mean=float(np.mean(res)) if res else float("nan"),
                baseline_inverse_distance_mean=float(np.mean(base)) if base else float("nan"), n_folds=len(res))


# ------------------------------------------------------------------------------------------------
# along-strike geometry: continuation beyond tips vs flanks
# ------------------------------------------------------------------------------------------------
def trace_endpoints(labels: np.ndarray, ids: Sequence[int], tip_radius_px: int = 6):
    """Endpoints of the given 8-connected traces and the outward unit direction of each (row, col space).

    An endpoint is a pixel with exactly one 8-neighbour of the same label.  The outward direction points from
    the mean of the trace's pixels within ``tip_radius_px`` (Chebyshev) of the endpoint to the endpoint.
    Returns arrays (rows, cols, urow, ucol, trace_id)."""
    ids = np.asarray(list(ids), int)
    out = []
    objs = ndi.find_objects(labels)
    for tid in ids:
        sl = objs[tid - 1]
        if sl is None:
            continue
        sub = labels[sl] == tid
        nb = ndi.convolve(sub.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - sub.astype(np.uint8)
        ends = np.argwhere(sub & (nb == 1))
        pts = np.argwhere(sub)
        for er, ec in ends:
            near = pts[(np.abs(pts[:, 0] - er) <= tip_radius_px) & (np.abs(pts[:, 1] - ec) <= tip_radius_px)]
            near = near[~((near[:, 0] == er) & (near[:, 1] == ec))]
            if len(near) == 0:
                continue
            m = near.mean(0)
            v = np.array([er - m[0], ec - m[1]], float)
            n = np.hypot(*v)
            if n < 1e-9:
                continue
            out.append((er + sl[0].start, ec + sl[1].start, v[0] / n, v[1] / n, tid))
    if not out:
        z = np.zeros(0)
        return z.astype(int), z.astype(int), z, z, z.astype(int)
    a = np.array(out)
    return a[:, 0].astype(int), a[:, 1].astype(int), a[:, 2], a[:, 3], a[:, 4].astype(int)


WEDGES = {"continuation (<= 25 deg of strike, beyond the tip)": (0.0, 25.0), "oblique forward (25-65 deg)": (25.0, 65.0),
          "lateral (65-115 deg)": (65.0, 115.0)}


def tip_wedge_profile(labels: np.ndarray, ids: Sequence[int], target: np.ndarray, eligible: np.ndarray,
                      edges_m: Sequence[float] = (300, 600, 1000, 1500, 2000, 3000), pixel_m: float = 100.0,
                      n_boot: int = 300, seed: int = 0) -> Dict:
    """Enrichment of ``target`` in angular wedges around the tips of the long traces ``ids``.

    For every endpoint and every eligible pixel at distance rho in the band, the angle theta between the
    pixel's offset and the outward strike direction assigns it to the continuation, oblique-forward or lateral
    wedge.  E = [targets / eligible] in (wedge, band) divided by [targets / eligible] over all three wedges and
    all bands, so 1 means the wedge is no richer than the tip neighbourhood as a whole.  Pairs are counted per
    endpoint (a pixel near two tips counts twice); the bootstrap resamples endpoints."""
    H, W = target.shape
    rows, cols, ur, uc, tid = trace_endpoints(labels, ids)
    n_e = len(rows)
    rmax = int(np.ceil(edges_m[-1] / pixel_m))
    dy, dx = np.mgrid[-rmax:rmax + 1, -rmax:rmax + 1]
    rho = np.hypot(dy, dx) * pixel_m
    ok = (rho >= edges_m[0]) & (rho <= edges_m[-1])
    dy, dx, rho = dy[ok], dx[ok], rho[ok]
    band = np.digitize(rho, edges_m) - 1                     # 0 .. len(edges)-2
    nb = len(edges_m) - 1
    wnames = list(WEDGES)
    cnt_t = np.zeros((n_e, len(wnames), nb))
    cnt_d = np.zeros_like(cnt_t)
    for i in range(n_e):
        y, x = rows[i] + dy, cols[i] + dx
        inb = (y >= 0) & (y < H) & (x >= 0) & (x < W)
        yy, xx, bb = y[inb], x[inb], band[inb]
        e = eligible[yy, xx]
        t = target[yy, xx] & e
        cos = (dy[inb] * ur[i] + dx[inb] * uc[i]) / np.maximum(rho[inb] / pixel_m, 1e-9)
        theta = np.degrees(np.arccos(np.clip(cos, -1, 1)))
        for w, (lo, hi) in enumerate(WEDGES.values()):
            m = (theta >= lo) & (theta < hi) if lo == 0 else (theta > lo) & (theta <= hi)
            cnt_d[i, w] = np.bincount(bb[m & e], minlength=nb)[:nb]
            cnt_t[i, w] = np.bincount(bb[m & t], minlength=nb)[:nb]

    def ratio(idx):
        t, d = cnt_t[idx].sum(0), cnt_d[idx].sum(0)
        tot = t.sum() / max(d.sum(), 1)
        return (t / np.maximum(d, 1)) / max(tot, 1e-12)

    rng = np.random.default_rng(seed)
    E = ratio(np.arange(n_e))
    B = np.array([ratio(rng.integers(0, n_e, n_e)) for _ in range(n_boot)])
    lo, hi = np.nanpercentile(B, [2.5, 97.5], axis=0)
    # wedge-level summary over bands (pooled counts) and continuation / lateral contrast
    t_w, d_w = cnt_t.sum((0, 2)), cnt_d.sum((0, 2))
    pooled = (t_w / np.maximum(d_w, 1)) / max(t_w.sum() / max(d_w.sum(), 1), 1e-12)
    contrast = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_e, n_e)
        tw, dw = cnt_t[idx].sum((0, 2)), cnt_d[idx].sum((0, 2))
        p = (tw / np.maximum(dw, 1))
        contrast.append(p[0] / max(p[2], 1e-12))
    p0 = (t_w / np.maximum(d_w, 1))
    return dict(n_endpoints=int(n_e), n_traces=int(len(set(tid.tolist()))), edges_m=[float(e) for e in edges_m], wedges=wnames,
                enrichment=[[float(v) for v in row] for row in E], lo=[[float(v) for v in row] for row in lo],
                hi=[[float(v) for v in row] for row in hi], pooled_enrichment=[float(v) for v in pooled],
                continuation_over_lateral=float(p0[0] / max(p0[2], 1e-12)),
                continuation_over_lateral_ci95=[float(v) for v in np.percentile(contrast, [2.5, 97.5])],
                n_target_by_wedge=[int(v) for v in t_w], n_eligible_by_wedge=[int(v) for v in d_w])


def wedge_union_mask(labels: np.ndarray, ids: Sequence[int], wedge_deg=(0.0, 25.0), band_m=(300.0, 1000.0),
                     pixel_m: float = 100.0) -> np.ndarray:
    """Union over all tips of the pixels inside one angular wedge and distance band (see ``tip_wedge_profile``)."""
    H, W = labels.shape
    rows, cols, ur, uc, _ = trace_endpoints(labels, ids)
    rmax = int(np.ceil(band_m[1] / pixel_m))
    dy, dx = np.mgrid[-rmax:rmax + 1, -rmax:rmax + 1]
    rho = np.hypot(dy, dx) * pixel_m
    ok = (rho >= band_m[0]) & (rho <= band_m[1])
    dy, dx, rho = dy[ok], dx[ok], rho[ok]
    out = np.zeros((H, W), bool)
    lo, hi = wedge_deg
    for i in range(len(rows)):
        y, x = rows[i] + dy, cols[i] + dx
        inb = (y >= 0) & (y < H) & (x >= 0) & (x < W)
        cos = (dy[inb] * ur[i] + dx[inb] * uc[i]) / np.maximum(rho[inb] / pixel_m, 1e-9)
        theta = np.degrees(np.arccos(np.clip(cos, -1, 1)))
        m = (theta >= lo) & (theta < hi) if lo == 0 else (theta > lo) & (theta <= hi)
        out[y[inb][m], x[inb][m]] = True
    return out
