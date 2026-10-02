"""Turn a ranked score into a submission: dispersion, budget and the metric algebra.

Three facts drive this module, all measured in ``docs/data/habitat-model.json``.

1.  **The metric is a covering problem.**  TP_w = sum over hidden truth pixels of
    max_x p(x) k(d(x,g)) with k a 300 m cone.  Stacking emitted pixels inside one
    another's cone buys nothing and still costs FP_w, so the value of an emission is
    governed by its *dispersion efficiency*

        eta = (Kbar / A) / (9.42 / D),   Kbar = mean over the scored domain of the
                                         emission's kernel envelope,
                                         A = emitted probability mass,
                                         D = scored-domain pixels,

    i.e. the fraction of the theoretically available cone weight the emission actually
    spreads over the domain.  Across the 24 live-scored artefacts eta correlates with
    TP per emitted pixel at Spearman rho = +0.61 (p = 0.0015) and with placement skill
    at rho = +0.13 (p = 0.54): dispersion pays and does not measurably cost alignment.
    The group's best artefacts sit at eta = 0.39-0.41; the "dotted ridge" artefact at
    eta = 0.85 has the highest TP per pixel of any of them.

2.  **|G| is small.**  The exact inversion TP_i = DTI_i (0.1626 A_i + 0.8 |G|)/(1+0.6 DTI_i)
    plus the geometric fact that TP_i <= |G| bounds the public-test truth at a few times
    10^4 pixels, not the 1.25e5 assumed by earlier group work (see
    docs/data/live-model-bounds.json).  Small |G| means the 0.8|G| false-negative floor
    dominates the denominator, so recall per emitted pixel - not emitted area - is the
    lever.

3.  **The budget follows from the marginal rule.**  Adding a pixel is worth it while its
    expected TP contribution exceeds 0.1626 * TP / (0.1626 A + 0.8 |G|).
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, Sequence, Tuple

import numpy as np

from .layers import PIXEL_M, RADIUS_M

def _discrete_cone_weight() -> float:
    """Sum of k(d) over every 100 m pixel offset inside the 300 m cone: 9.3803.

    The continuous integral of the cone is 9.4248 pixel-units; the metric is evaluated on
    the discrete grid, so the discrete sum is the right normaliser for dispersion.
    """
    total = 0.0
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            k = max(1.0 - (math.hypot(dy, dx) * PIXEL_M) / RADIUS_M, 0.0)
            total += k
    return total


CONE_WEIGHT = _discrete_cone_weight()
ALPHA, BETA = 0.2, 0.8
DOMAIN_PX = 5_106_385       # scored domain: 5,167,373 footprint - 60,988 masked catalogue pixels
CONE_AREA_PX = math.pi * (RADIUS_M / PIXEL_M) ** 2      # 28.274 pixels within 300 m


def fp_relief(g_size: float, domain_px: float = DOMAIN_PX) -> float:
    """1 - E[max_g k(d(x,g))]: the share of an emitted pixel's mass that is pure false positive.

    For a truth set of |G| pixels spread over the scored domain, the expected kernel weight
    a predicted pixel receives from the truth is  E[max_g k] = int_0^1 (1 - exp(-c u^2)) du
    with c = 28.274 |G| / D (Poisson approximation over the 300 m cone).  At the |G| this
    repository measures (4.6e3-1.2e4) that is ~0.015, so FP_relief is ~0.985 - NOT the 0.813
    that a |G| = 125,000 assumption would give.  Using the larger relief understates the cost
    of area by ~20% and was the single largest algebraic error in the inherited analysis.
    """
    c = CONE_AREA_PX * float(g_size) / float(domain_px)
    u = np.linspace(0.0, 1.0, 2001)
    m = float(np.trapezoid(1.0 - np.exp(-c * u * u), u))
    return 1.0 - m


def fp_coefficient(g_size: float, domain_px: float = DOMAIN_PX) -> float:
    """alpha * fp_relief: the denominator's cost per emitted pixel."""
    return ALPHA * fp_relief(g_size, domain_px)


def kernel_envelope(mask: np.ndarray) -> np.ndarray:
    """max_x p(x) k(d(x, .)) for a binary emission - one Euclidean distance transform."""
    from scipy.ndimage import distance_transform_edt

    d = distance_transform_edt(~mask, sampling=(PIXEL_M, PIXEL_M))
    return np.clip(1.0 - d / RADIUS_M, 0.0, 1.0).astype(np.float32)


def geometry(mask: np.ndarray, domain: np.ndarray) -> Dict[str, float]:
    A = float(mask.sum())
    if A <= 0:
        return dict(area=0.0, kbar=0.0, eta=0.0, coverage=0.0)
    env = kernel_envelope(mask)
    kbar = float(env[domain].mean())
    D = float(domain.sum())
    return dict(area=A, kbar=kbar, eta=(kbar / A) / (CONE_WEIGHT / D),
                coverage=float((env[domain] > 0).mean()))


def expected_dti(area: float, kbar: float, g_size: float, skill: float,
                 domain_px: float = DOMAIN_PX) -> float:
    """DTI implied by an emission's geometry, an assumed |G| and an assumed skill.

    skill = TP_w / (|G| * Kbar): 1.0 means the emission does exactly as well as a
    uniform-random placement with the same geometry, >1 means its pixels are on ground
    where the hidden faults actually are.
    """
    tp = skill * g_size * kbar
    tp = min(tp, g_size)
    fp = fp_relief(g_size, domain_px) * area
    fn = max(g_size - tp, 0.0)
    return tp / (tp + ALPHA * fp + BETA * fn + 1e-12)


def marginal_tp_threshold(area: float, tp: float, g_size: float,
                          domain_px: float = DOMAIN_PX) -> float:
    """Expected TP a further emitted pixel must add to be worth its FP cost."""
    c = fp_coefficient(g_size, domain_px)
    return c * tp / (c * area + BETA * g_size)


def optimal_dti_and_area(q: float, g_size: float, domain_px: float = DOMAIN_PX) -> dict:
    """Closed form: with TP per emitted pixel q, DTI(A) peaks at A* = |G|/q."""
    c = fp_coefficient(g_size, domain_px)
    a_star = g_size / q if q > 0 else float("inf")
    return dict(q=q, a_star=a_star, dti_max=1.0 / (ALPHA + c / q) if q > 0 else 0.0,
                fp_coefficient=c)


def disperse_select(score: np.ndarray, domain: np.ndarray, budget: int,
                    r_min_px: float = 4, forbid: np.ndarray | None = None,
                    break_ties: bool = False, tie_seed: int = 0) -> np.ndarray:
    """Greedy highest-score-first selection with a minimum separation.

    Equivalent to non-maximum suppression on the score field: in each round only local
    maxima of the not-yet-blocked score are accepted, then their r_min_px discs are
    blocked.  With a distinct-valued score and a budget below the round-1 capacity this
    terminates in one or two rounds and yields eta close to 1.
    """
    from scipy.ndimage import grey_dilation, maximum_filter

    s = np.where(domain, score, -np.inf).astype(np.float64)
    if forbid is not None:
        s[forbid] = -np.inf
    if break_ties:
        # The peak test below is ``cand >= local max``, so every pixel of an equal-score plateau is accepted in
        # the same round and the minimum separation is silently violated (931 of the 100,000 dots of the
        # shipped H24 have a neighbour < 4 px away, 898 of them adjacent).  A deterministic 1e-9 jitter makes
        # the local maxima unique.  Off by default so that the shipped H24 file stays reproducible bit-for-bit.
        fin = np.isfinite(s)
        s[fin] += np.random.default_rng(tie_seed).random(int(fin.sum())) * 1e-9
    accepted = np.zeros(domain.shape, bool)
    blocked = np.zeros(domain.shape, bool)
    rc = int(math.ceil(r_min_px))               # integer radii behave exactly as before; fractional radii
    size = 2 * rc + 1                           # (e.g. 4.4 px) let the spacing be incommensurate with the
    foot = np.zeros((size, size), bool)         # 400 m flight-line spacing (see src/gems/audit.py)
    yy, xx = np.ogrid[-rc:rc + 1, -rc:rc + 1]
    foot[(yy * yy + xx * xx) <= r_min_px * r_min_px] = True
    rounds = 0
    while accepted.sum() < budget and rounds < 60:
        rounds += 1
        cand = s.copy()
        cand[blocked] = -np.inf
        loc = maximum_filter(cand, size=size, mode="constant", cval=-np.inf)
        peaks = (cand >= loc) & np.isfinite(cand) & ~accepted
        n_peak = int(peaks.sum())
        if n_peak == 0:
            break
        need = budget - int(accepted.sum())
        if n_peak > need:
            idx = np.flatnonzero(peaks.ravel())
            vals = cand.ravel()[idx]
            keep = idx[np.argsort(-vals)[:need]]
            sel = np.zeros(cand.size, bool); sel[keep] = True
            peaks = sel.reshape(cand.shape)
        accepted |= peaks
        blocked |= grey_dilation(peaks, footprint=foot)
    return accepted


def choose_budget(score: np.ndarray, domain: np.ndarray, budgets: Sequence[int],
                  g_sizes: Sequence[float], skills: Sequence[float], skill_weights: Sequence[float],
                  r_min_px: int = 4, forbid: np.ndarray | None = None) -> Tuple[int, list]:
    """Pick the budget that maximises the skill-weighted expected DTI, worst case over |G|."""
    table = []
    for b in budgets:
        mask = disperse_select(score, domain, b, r_min_px, forbid)
        g = geometry(mask, domain)
        row = dict(budget=b, **g)
        per_g = {}
        for G in g_sizes:
            vals = [expected_dti(g["area"], g["kbar"], G, s) for s in skills]
            per_g[str(int(G))] = dict(dti=[float(v) for v in vals],
                                      weighted=float(np.dot(vals, skill_weights) / np.sum(skill_weights)),
                                      worst=float(min(vals)))
        row["by_G"] = per_g
        row["min_over_G_of_weighted"] = float(min(v["weighted"] for v in per_g.values()))
        row["mean_over_G_of_weighted"] = float(np.mean([v["weighted"] for v in per_g.values()]))
        table.append(row)
    best = max(table, key=lambda r: r["min_over_G_of_weighted"])
    return int(best["budget"]), table
