"""Fault populations as a spatial statistic.

This module measures, on a raster of mapped fault traces, the scaling laws that relate how faults are
*sized* to how they are *arranged*, so that the same measurements can later be (i) fitted on the known
INGENIOUS / USGS catalogue before any model is touched, (ii) turned into a geometric prior and
(iii) re-computed on a predicted raster as an audit.

Primary sources (abstracts read and checked on 2026-10-02; see docs/research/knowledge_base.md)
------------------------------------------------------------------------------------------------
* Bour, O. & Davy, P. (1999), *Clustering and size distributions of fault patterns: Theory and
  measurements*, Geophys. Res. Lett. 26(13), 2001-2004, doi:10.1029/1999GL900419.  Abstract: the fractal
  dimension D of the fault pattern and the exponent a of the frequency-length distribution are related by
  x = (a - 1) / D, where x is the exponent of a scaling law for the *average distance from a fault to its
  nearest neighbour of larger length*; large faults have their nearest larger neighbour farther away.
* Marrett, R., Gale, J.F.W., Gomez, L.A. & Laubach, S.E. (2018), *Correlation analysis of fracture
  arrangement in space*, J. Struct. Geol. 108, 16-33, doi:10.1016/j.jsg.2017.06.012: the normalised
  correlation count (NCC) = observed correlation count / count expected for a random arrangement; NCC = 1
  random, > 1 clustered, < 1 anti-clustered / regular, evaluated scale by scale.  The slope of the
  normalised correlation *sum* on log-log axes equals the correlation dimension minus one.
* Wang, Q., Laubach, S.E., Gale, J.F.W. & Ramos, M.J. (2019), Petroleum Geoscience 25(4), 415-428,
  doi:10.1144/petgeo2018-146: worked application of the NCC to a fracture population.
* Clauset, A., Shalizi, C.R. & Newman, M.E.J. (2009), *Power-law distributions in empirical data*, SIAM
  Review 51(4), 661-703: maximum-likelihood exponent and KS-based choice of the lower cut-off.

Definitions used here (the abstract of Bour & Davy does not fix them, so they are declared, not assumed)
-----------------------------------------------------------------------------------------------------
* ``a`` is the exponent of the *density* n(l) ~ l**-a.  The cumulative exponent is a - 1.  With a fractal
  position set of dimension D independent of size, the nearest of the N(>l) ~ l**-(a-1) larger faults is at
  distance ~ N(>l)**(-1/D) ~ l**((a-1)/D), which reproduces the published x = (a - 1)/D only for the
  density exponent.  ``tests/test_faultstats.py`` checks this numerically on simulated populations.
* The "fault" is one 8-connected component of the raster.  Touching traces merge, so a component is a
  lower bound on the number of faults and an upper bound on fault length; this is stated wherever reported.
* "Length" is the maximum Feret diameter (largest centre-to-centre distance inside the component); the
  pixel count x pixel size (cumulative trace length) is reported alongside as a sensitivity check.
* Distance is reported two ways: between component centroids (the point-process reading used for D) and
  between the nearest pixels of two components (edge distance).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull, cKDTree

PIXEL_M = 100.0
STRUCT8 = np.ones((3, 3), dtype=bool)


# ------------------------------------------------------------------------------------------------
# trace extraction
# ------------------------------------------------------------------------------------------------
@dataclass
class Traces:
    """One row per 8-connected component (a 'trace').  Coordinates are in metres, x east, y north-up
    flipped to row/col space: ``cx`` is column * pixel, ``cy`` is row * pixel (row increases southward)."""
    labels: np.ndarray          # (H, W) int32 label image, 0 = background
    ids: np.ndarray             # (n,) component ids 1..n
    n_px: np.ndarray            # (n,) pixel count
    length_m: np.ndarray        # (n,) maximum Feret diameter + one pixel (a single pixel has length 1 px)
    cx: np.ndarray
    cy: np.ndarray
    strike_deg: np.ndarray      # principal-axis azimuth in image space, degrees from +col axis (0..180)
    pixel_m: float = PIXEL_M

    @property
    def n(self) -> int:
        return int(self.ids.size)

    @property
    def path_m(self) -> np.ndarray:
        """Cumulative trace length proxy (pixel count x pixel size)."""
        return self.n_px.astype(float) * self.pixel_m


def _feret(points_rc: np.ndarray) -> float:
    """Maximum centre-to-centre distance (in pixels) among a component's pixels."""
    n = len(points_rc)
    if n == 1:
        return 0.0
    if n == 2:
        return float(np.hypot(*(points_rc[0] - points_rc[1])))
    try:
        hull = points_rc[ConvexHull(points_rc.astype(float)).vertices]
    except Exception:                       # collinear points -> hull fails; the extremes are on a line
        hull = points_rc
    d = hull[:, None, :] - hull[None, :, :]
    return float(np.sqrt((d.astype(float) ** 2).sum(-1)).max())


def extract_traces(mask: np.ndarray, pixel_m: float = PIXEL_M) -> Traces:
    mask = np.asarray(mask).astype(bool)
    lab, n = ndi.label(mask, structure=STRUCT8)
    lab = lab.astype(np.int32)
    ids = np.arange(1, n + 1)
    if n == 0:
        z = np.zeros(0)
        return Traces(lab, ids, z.astype(int), z, z, z, z, pixel_m)
    objs = ndi.find_objects(lab)
    n_px = np.zeros(n, np.int64)
    length = np.zeros(n)
    cx = np.zeros(n)
    cy = np.zeros(n)
    strike = np.zeros(n)
    for k, sl in enumerate(objs):
        sub = lab[sl] == (k + 1)
        rr, cc = np.nonzero(sub)
        rr = rr + sl[0].start
        cc = cc + sl[1].start
        pts = np.column_stack([rr, cc])
        n_px[k] = len(pts)
        length[k] = (_feret(pts) + 1.0) * pixel_m
        cy[k] = rr.mean() * pixel_m
        cx[k] = cc.mean() * pixel_m
        if len(pts) >= 3:
            cov = np.cov(np.vstack([cc, rr]))
            w, v = np.linalg.eigh(cov)
            ax = v[:, np.argmax(w)]
            strike[k] = float(np.degrees(np.arctan2(ax[1], ax[0])) % 180.0)
    return Traces(lab, ids, n_px, length, cx, cy, strike, pixel_m)


# ------------------------------------------------------------------------------------------------
# (1) length-frequency exponent a  (density exponent)
# ------------------------------------------------------------------------------------------------
def powerlaw_mle(x: np.ndarray, xmin: float) -> Tuple[float, float, int]:
    """Continuous power-law MLE: alpha = 1 + n / sum ln(x / xmin), s.e. = (alpha - 1)/sqrt(n)."""
    t = np.asarray(x, float)
    t = t[t >= xmin]
    n = t.size
    if n < 3:
        return float("nan"), float("nan"), n
    s = float(np.log(t / xmin).sum())
    if s <= 0:
        return float("nan"), float("nan"), n
    a = 1.0 + n / s
    return a, (a - 1.0) / np.sqrt(n), n


def fit_length_distribution(lengths: np.ndarray, xmin_grid: Optional[Sequence[float]] = None,
                            n_boot: int = 200, seed: int = 0) -> Dict:
    """Power-law tail fit with the cut-off chosen by minimum KS distance (Clauset et al. 2009).

    Returns the *density* exponent ``a`` (n(l) ~ l**-a), the cumulative exponent ``a - 1``, the chosen
    ``xmin``, a bootstrap interval with xmin held fixed, and the KS distance.  A lognormal alternative is
    fitted on the same tail and the log-likelihood ratio is reported so that a power law is never assumed
    where the data prefer another shape.
    """
    L = np.asarray(lengths, float)
    L = L[np.isfinite(L) & (L > 0)]
    if L.size < 30:
        return dict(a_density=float("nan"), n=int(L.size), note="too few traces")
    if xmin_grid is None:
        xmin_grid = np.unique(np.quantile(L, np.linspace(0.05, 0.90, 35)))
    best = None
    for xm in xmin_grid:
        tail = L[L >= xm]
        if tail.size < 25:
            continue
        a, se, n = powerlaw_mle(L, xm)
        if not np.isfinite(a):
            continue
        t = np.sort(tail)
        emp = np.arange(1, t.size + 1) / t.size
        cdf = 1.0 - (t / xm) ** (1.0 - a)
        ks = float(np.max(np.maximum(np.abs(emp - cdf), np.abs(emp - 1.0 / t.size - cdf))))
        if best is None or ks < best[0]:
            best = (ks, float(xm), a, se, n)
    if best is None:
        return dict(a_density=float("nan"), n=int(L.size), note="no admissible xmin")
    ks, xmin, a, se, n = best
    tail = L[L >= xmin]
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        s = rng.choice(tail, size=tail.size, replace=True)
        ab, _, _ = powerlaw_mle(s, xmin)
        boots.append(ab)
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    # lognormal alternative on the same tail (truncated at xmin): MLE by moment matching on log-values
    # followed by a numerical truncation correction; the LR is the Vuong-style statistic.
    from scipy import optimize, stats
    lt = np.log(tail)

    def nll(theta):
        mu, ls = theta
        s = np.exp(ls)
        norm = stats.norm.sf((np.log(xmin) - mu) / s)
        if norm <= 1e-300:
            return 1e300
        ll = stats.norm.logpdf(lt, mu, s) - lt - np.log(norm)
        return -ll.sum()

    res = optimize.minimize(nll, x0=[lt.mean(), np.log(lt.std() + 1e-6)], method="Nelder-Mead")
    ll_ln = -float(res.fun)
    # power-law density above xmin: (a-1)/xmin * (x/xmin)**-a, so the log-likelihood is exact
    ll_i_pl = np.log((a - 1) / xmin) - a * np.log(tail / xmin)
    ll_pl = float(ll_i_pl.sum())
    mu, ls = res.x
    s = np.exp(ls)
    norm = stats.norm.sf((np.log(xmin) - mu) / s)
    ll_i_ln = stats.norm.logpdf(lt, mu, s) - lt - np.log(norm)
    d = ll_i_pl - ll_i_ln
    vuong = float(np.sqrt(d.size) * d.mean() / (d.std(ddof=1) + 1e-12))
    return dict(a_density=float(a), a_cumulative=float(a - 1.0), a_se=float(se), a_ci95=[float(lo), float(hi)],
                xmin_m=float(xmin), n_tail=int(n), n_all=int(L.size), ks=float(ks),
                lognormal=dict(mu=float(mu), sigma=float(s), loglik=float(ll_ln)),
                powerlaw_loglik=ll_pl, loglik_ratio_pl_minus_ln=float(ll_pl - ll_ln),
                vuong_z=vuong,
                preferred=("power-law" if vuong > 1.96 else "lognormal" if vuong < -1.96 else "indistinguishable"))


# ------------------------------------------------------------------------------------------------
# (2) nearest-larger-neighbour scaling  (Bour & Davy 1999)
# ------------------------------------------------------------------------------------------------
def nearest_larger_centroid(length: np.ndarray, cx: np.ndarray, cy: np.ndarray) -> np.ndarray:
    """Distance (m) from each trace centroid to the nearest centroid of a STRICTLY longer trace.
    The longest trace has none (NaN).  Ties are broken by array order so that every trace but one has a
    larger neighbour."""
    n = len(length)
    order = np.lexsort((np.arange(n), length))      # ascending length, stable
    rank = np.empty(n, int)
    rank[order] = np.arange(n)
    pts = np.column_stack([cx, cy])
    d = np.full(n, np.nan)
    # process in descending order, growing a KD-tree in blocks (exact: block-wise brute force + tree)
    desc = order[::-1]
    block = 256
    for s in range(0, n, block):
        idx = desc[s:s + block]
        larger_all = desc[:s]
        if larger_all.size:
            tree = cKDTree(pts[larger_all])
            dd, _ = tree.query(pts[idx], k=1)
            d[idx] = dd
        # within-block larger neighbours
        for j, i in enumerate(idx):
            prev = idx[:j]
            if prev.size:
                m = np.hypot(pts[prev, 0] - pts[i, 0], pts[prev, 1] - pts[i, 1]).min()
                d[i] = m if not np.isfinite(d[i]) else min(d[i], m)
    return d


def nearest_larger_edge(tr: Traces, length: Optional[np.ndarray] = None) -> np.ndarray:
    """Distance (m) from each trace to the nearest *pixel* of a strictly longer trace (edge-to-edge)."""
    L = tr.length_m if length is None else length
    n = tr.n
    rr, cc = np.nonzero(tr.labels)
    lab = tr.labels[rr, cc] - 1
    pts = np.column_stack([cc, rr]).astype(float) * tr.pixel_m
    order = np.lexsort((np.arange(n), L))
    rank = np.empty(n, int)
    rank[order] = np.arange(n)
    pix_rank = rank[lab]
    out = np.full(n, np.nan)
    by_label = np.argsort(lab, kind="stable")
    bounds = np.searchsorted(lab[by_label], np.arange(n + 1))
    # one global tree; ask for growing k until a pixel of a larger trace is found
    tree = cKDTree(pts)
    for i in range(n):
        if rank[i] == n - 1:
            continue
        mine = by_label[bounds[i]:bounds[i + 1]]
        q = pts[mine]
        k = 16
        while True:
            kk = min(k, len(pts))
            dist, ind = tree.query(q, k=kk)
            dist = np.atleast_2d(dist.reshape(len(q), -1))
            ind = np.atleast_2d(ind.reshape(len(q), -1))
            ok = pix_rank[ind] > rank[i]
            if ok.any():
                dm = np.where(ok, dist, np.inf).min()
                # an unseen candidate could only be closer if every neighbour inside dm was already seen;
                # the k-th neighbour distance bounds that.
                if dm <= dist[:, -1].min() or kk >= len(pts):
                    out[i] = dm
                    break
            if kk >= len(pts):
                break
            k *= 4
    return out


def fit_nearest_larger(length: np.ndarray, dist: np.ndarray, n_bins: int = 10, min_per_bin: int = 12,
                       n_boot: int = 300, seed: int = 0, l_min: Optional[float] = None) -> Dict:
    """Fit  <d>(l) = A * l**x  using log-binned means (Bour & Davy's 'average distance') and, as a check,
    a robust fit of the geometric mean.  Reports x with a bootstrap interval over traces."""
    L = np.asarray(length, float)
    d = np.asarray(dist, float)
    ok = np.isfinite(d) & (d > 0) & (L > 0)
    if l_min is not None:
        ok &= L >= l_min
    L, d = L[ok], d[ok]
    if L.size < 4 * min_per_bin:
        return dict(x=float("nan"), n=int(L.size), note="too few traces")

    def one(Lb, db):
        q = np.unique(np.quantile(np.log(Lb), np.linspace(0, 1, n_bins + 1)))
        rows = []
        for lo, hi in zip(q[:-1], q[1:]):
            m = (np.log(Lb) >= lo) & (np.log(Lb) <= hi if hi == q[-1] else np.log(Lb) < hi)
            if m.sum() < min_per_bin:
                continue
            rows.append((np.log(Lb[m]).mean(), np.log(db[m].mean()), np.log(db[m]).mean(), int(m.sum())))
        if len(rows) < 4:
            return None
        r = np.array(rows)
        sx_mean = np.polyfit(r[:, 0], r[:, 1], 1)
        sx_geo = np.polyfit(r[:, 0], r[:, 2], 1)
        return sx_mean, sx_geo, r

    base = one(L, d)
    if base is None:
        return dict(x=float("nan"), n=int(L.size), note="too few populated bins")
    sx_mean, sx_geo, r = base
    rng = np.random.default_rng(seed)
    xs, xg = [], []
    for _ in range(n_boot):
        ii = rng.integers(0, L.size, L.size)
        o = one(L[ii], d[ii])
        if o is not None:
            xs.append(o[0][0]); xg.append(o[1][0])
    from scipy.stats import spearmanr
    rho, p = spearmanr(L, d)
    pred = np.polyval(sx_mean, r[:, 0])
    r2 = 1.0 - ((r[:, 1] - pred) ** 2).sum() / max(((r[:, 1] - r[:, 1].mean()) ** 2).sum(), 1e-12)
    return dict(x=float(sx_mean[0]), A_m=float(np.exp(sx_mean[1])), x_ci95=[float(v) for v in np.percentile(xs, [2.5, 97.5])],
                x_geometric_mean=float(sx_geo[0]), x_geo_ci95=[float(v) for v in np.percentile(xg, [2.5, 97.5])],
                r2_binned=float(r2), spearman_rho=float(rho), spearman_p=float(p), n=int(L.size),
                bins=[dict(l_geomean_m=float(np.exp(a)), d_mean_m=float(np.exp(b)), d_geomean_m=float(np.exp(c)), n=int(k))
                      for a, b, c, k in r])


# ------------------------------------------------------------------------------------------------
# (3) correlation integral / dimension and the normalised correlation count
# ------------------------------------------------------------------------------------------------
def sample_in_mask(mask: np.ndarray, n: int, rng: np.random.Generator, pixel_m: float = PIXEL_M) -> np.ndarray:
    """n points uniform inside a boolean footprint (sub-pixel jitter), as (x, y) in metres."""
    rr, cc = np.nonzero(mask)
    pick = rng.integers(0, rr.size, n)
    return np.column_stack([(cc[pick] + rng.random(n)) * pixel_m, (rr[pick] + rng.random(n)) * pixel_m])


def pair_counts(points: np.ndarray, r_edges_m: np.ndarray, max_points: int = 40000,
                rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Cumulative ordered-pair counts N(<= r) for each r in ``r_edges_m`` (self-pairs excluded).
    If the set is larger than ``max_points`` it is thinned uniformly and the counts are rescaled."""
    P = np.asarray(points, float)
    scale = 1.0
    if len(P) > max_points:
        rng = rng or np.random.default_rng(0)
        P = P[rng.choice(len(P), max_points, replace=False)]
        scale = (len(points) / max_points) ** 2
    tree = cKDTree(P)
    c = tree.count_neighbors(tree, r_edges_m, cumulative=True).astype(float) - len(P)
    return c * scale


def csr_null_counts(footprint: np.ndarray, m: int, r_edges_m: np.ndarray, n_null: int = 40, seed: int = 0,
                    pixel_m: float = PIXEL_M) -> np.ndarray:
    """Cumulative pair counts for ``n_null`` replicates of ``m`` points uniform in the footprint
    (shape (n_null, len(r_edges)))."""
    rng = np.random.default_rng(seed)
    return np.array([pair_counts(sample_in_mask(footprint, m, rng, pixel_m), r_edges_m, max_points=m + 1)
                     for _ in range(n_null)])


def ncc_against_null(points: np.ndarray, r_edges_m: np.ndarray, null: np.ndarray, m: int,
                     seed: int = 0) -> Dict:
    """Normalised correlation sum / count of ``points`` against a precomputed CSR null of size ``m``.

    The observed set is thinned uniformly to ``m`` points when larger (independent thinning leaves the
    pair-correlation function unchanged, so the ratio to CSR of the same size is unbiased) and is compared
    with the null replicates of exactly that size."""
    rng = np.random.default_rng(seed)
    P = np.asarray(points, float)
    if len(P) > m:
        P = P[rng.choice(len(P), m, replace=False)]
    elif len(P) < m:
        raise ValueError("fewer points than the null size; build a null with m <= len(points)")
    obs = pair_counts(P, r_edges_m, max_points=m + 1)
    exp = null.mean(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        s_obs = np.where(exp > 0, obs / exp, np.nan)
        s_null = null / exp
    d_obs = np.diff(np.concatenate([[0.0], obs]))
    d_null = np.diff(np.concatenate([np.zeros((null.shape[0], 1)), null], axis=1), axis=1)
    d_exp = d_null.mean(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        c_obs = np.where(d_exp > 0, d_obs / d_exp, np.nan)
        c_null = d_null / d_exp
    lo_s, hi_s = np.nanpercentile(s_null, [2.5, 97.5], axis=0)
    lo_c, hi_c = np.nanpercentile(c_null, [2.5, 97.5], axis=0)
    return dict(r_edges_m=[float(v) for v in r_edges_m], n_points=int(len(points)), n_used=int(m),
                sum_ratio=[float(v) for v in s_obs], sum_lo=[float(v) for v in lo_s], sum_hi=[float(v) for v in hi_s],
                count_ratio=[float(v) for v in c_obs], count_lo=[float(v) for v in lo_c], count_hi=[float(v) for v in hi_c])


def ncc_2d(points: np.ndarray, footprint: np.ndarray, r_edges_m: np.ndarray, n_null: int = 100,
           seed: int = 0, pixel_m: float = PIXEL_M, max_points: int = 40000) -> Dict:
    """Normalised correlation *sum* and *count* in 2-D against complete spatial randomness restricted to
    the footprint (so edge effects and the irregular outline are in the null by construction).

        sum(r)   = N_obs(<= r) / E[N_null(<= r)]            (Ripley-K ratio; Marrett's 'correlation sum')
        count(r) = dN_obs(r1, r2] / E[dN_null(r1, r2]]       (Marrett's 'correlation count', annuli)

    The null draws the same number of points uniformly inside ``footprint``; a 95 % envelope comes from
    the replicates.  This is the 2-D adaptation of a method published for 1-D scanlines and is labelled as
    such everywhere it is reported.  ``log-log slope of sum(r) + 2`` estimates the correlation dimension.
    """
    m = min(len(points), max_points)
    null = csr_null_counts(footprint, m, r_edges_m, n_null=n_null, seed=seed + 1, pixel_m=pixel_m)
    out = ncc_against_null(points, r_edges_m, null, m, seed=seed)
    out["pairs_expected"] = [float(v) for v in null.mean(0)]
    return out


def correlation_dimension(points: np.ndarray, r_m: np.ndarray, max_points: int = 40000) -> Dict:
    """Grassberger-Procaccia slope: C(r) = N(<=r)/N^2 ~ r^D over the supplied radii."""
    c = pair_counts(points, np.asarray(r_m, float), max_points=max_points)
    n = len(points)
    cr = c / max(n * (n - 1), 1)
    ok = cr > 0
    if ok.sum() < 4:
        return dict(D=float("nan"), n=int(n))
    x = np.log(np.asarray(r_m)[ok])
    y = np.log(cr[ok])
    coef = np.polyfit(x, y, 1)
    pred = np.polyval(coef, x)
    r2 = 1.0 - ((y - pred) ** 2).sum() / max(((y - y.mean()) ** 2).sum(), 1e-12)
    return dict(D=float(coef[0]), r2=float(r2), n=int(n), r_m=[float(v) for v in np.asarray(r_m)[ok]],
                log_c=[float(v) for v in y])


def ncc_scanline(mask: np.ndarray, axis: int, lag_edges_px: np.ndarray, min_points: int = 5,
                 footprint: Optional[np.ndarray] = None) -> Dict:
    """Marrett et al. (2018) normalised correlation count on 1-D scanlines through a raster.

    ``axis=1`` scans each row (east-west lines), ``axis=0`` each column.  Counts are pooled over scanlines
    (observed and expected summed before the ratio).  For n points placed uniformly at random on a line of
    length L the expected number of unordered pairs with separation in [r1, r2) is
    C(n, 2) [(1 - r1/L)^2 - (1 - r2/L)^2]  (exact), so no Monte Carlo is needed.

    ``footprint`` matters: a scan line crosses an irregular footprint over only part of the raster width, and
    the random arrangement must be placed on that stretch.  When given, each line uses L = the span from its first
    to its last footprint pixel and positions are measured from the first; without it the full raster length is
    used, which over-states the available length (and so the clustering) for lines that cross little footprint."""
    m = np.asarray(mask).astype(bool)
    fp = None if footprint is None else np.asarray(footprint).astype(bool)
    if axis == 0:
        m = m.T
        fp = None if fp is None else fp.T
    H, W = m.shape
    obs = np.zeros(len(lag_edges_px) - 1)
    exp = np.zeros(len(lag_edges_px) - 1)
    used = 0
    for r in range(H):
        pos = np.flatnonzero(m[r]).astype(float)
        L = float(W)
        if fp is not None:
            valid = np.flatnonzero(fp[r])
            if valid.size < 2:
                continue
            L = float(valid[-1] - valid[0] + 1)
            pos = pos - valid[0]
        n = pos.size
        if n < min_points:
            continue
        used += 1
        d = pos[None, :] - pos[:, None]
        d = d[np.triu_indices(n, 1)]
        h, _ = np.histogram(d, bins=lag_edges_px)
        obs += h
        q = np.clip(1.0 - np.asarray(lag_edges_px) / L, 0.0, None) ** 2
        exp += n * (n - 1) / 2.0 * (q[:-1] - q[1:])
    with np.errstate(divide="ignore", invalid="ignore"):
        ncc = np.where(exp > 0, obs / exp, np.nan)
    return dict(lag_edges_px=[float(v) for v in lag_edges_px], ncc=[float(v) for v in ncc],
                observed=[float(v) for v in obs], expected=[float(v) for v in exp], n_scanlines=int(used),
                line_length="footprint span per line" if fp is not None else "full raster length")


# ------------------------------------------------------------------------------------------------
# synthetic populations with known (a, D): the check that the implementation and the reading of
# x = (a - 1)/D are right
# ------------------------------------------------------------------------------------------------
def levy_dust(n: int, D: float, seed: int = 0, step_min: float = 1.0) -> np.ndarray:
    """Rayleigh-Levy dust: isotropic steps with Pareto(D) lengths give a point set of fractal dimension D
    (Mandelbrot) for 1 < D < 2 in the plane."""
    rng = np.random.default_rng(seed)
    step = step_min * (1.0 - rng.random(n)) ** (-1.0 / D)
    ang = rng.random(n) * 2 * np.pi
    xy = np.cumsum(np.column_stack([step * np.cos(ang), step * np.sin(ang)]), axis=0)
    return xy


def synthetic_population(n: int, a_density: float, D: float, seed: int = 0, l_min: float = 1.0):
    """Positions: Levy dust of dimension D.  Lengths: Pareto with density exponent ``a_density``,
    independent of position.  Returns (cx, cy, length)."""
    xy = levy_dust(n, D, seed)
    rng = np.random.default_rng(seed + 1)
    length = l_min * (1.0 - rng.random(n)) ** (-1.0 / (a_density - 1.0))
    return xy[:, 0], xy[:, 1], length


def bour_davy_check(n: int = 6000, a_density: float = 2.6, D: float = 1.5, seed: int = 0) -> Dict:
    """Measure x on a simulated population (positions: Levy dust of dimension D; lengths: Pareto with
    density exponent ``a_density``; independent) and compare with (a - 1)/D.  The check is that the measured
    x tracks (a_density - 1)/D and NOT (a_density - 2)/D, i.e. that a *cumulative* exponent must not be
    inserted for ``a``.  The arithmetic-mean and geometric-mean estimators bracket the prediction."""
    cx, cy, L = synthetic_population(n, a_density, D, seed)
    d = nearest_larger_centroid(L, cx, cy)
    fit = fit_nearest_larger(L, d, n_bins=10, min_per_bin=15)
    return dict(x_measured=fit.get("x"), x_geometric_mean=fit.get("x_geometric_mean"),
                x_predicted_density_reading=(a_density - 1.0) / D,
                x_if_cumulative_exponent_were_used_as_a=(a_density - 2.0) / D)
