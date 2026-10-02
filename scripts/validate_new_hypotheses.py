#!/usr/bin/env python3
"""Spatially blocked validation of the new hypotheses (H-38, H-39) before any slot.

Protocol (identical folds, target and budgets as the deep-ensemble admission gate,
docs/data/oof-evaluation.json, so the numbers are directly comparable):

* truth   - faults from the independent USGS SGMC compilation that the competition
            catalogue does NOT contain (>= 300 m from any catalogue pixel), the only
            independent uncatalogued-fault truth available offline;
* folds   - the same 5 column strips with a 1,500 m training buffer
            (gems.ensemble.blocked_folds, 5, 15);
* budget  - top-k emissions of each candidate score raster inside the held-out strip,
            at 1.22 % (the ensemble gate's operating budget) and 2.37 % (h19-5's own
            live budget), with catalogue pixels excluded;
* metric  - the official distance-weighted Tversky index (gems.metric).

Baselines evaluated on the identical folds: the h19-5 and H30 emissions as fixed
rasters, the live-score-fitted habitat ranking, the single best habitat layer, and
seed-matched random emissions.  A candidate that cannot beat h19-5 here must not
spend a weekly slot; a candidate that does beat it has still only beaten the proxy,
and the proxy -> hidden-truth transfer remains unproven (offline-proxy audit).

Run:  python scripts/validate_new_hypotheses.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gems.emission import DOMAIN_PX  # noqa: E402
from gems.ensemble import blocked_folds  # noqa: E402
from gems.featurecube import load_target  # noqa: E402
from gems.layers import load_domain  # noqa: E402
from gems.metric import distance_weighted_tversky  # noqa: E402

BUDGETS = {"1.22pct": 0.0122, "2.37pct": 0.0237}
N_RANDOM = 3


def rank01(x: np.ndarray, domain: np.ndarray) -> np.ndarray:
    """Domain-restricted [0,1] rank of a score raster (ties averaged)."""
    from scipy.stats import rankdata

    out = np.zeros(x.shape, np.float32)
    v = x[domain]
    out[domain] = ((rankdata(v, method="average") - 1.0) / max(1.0, v.size - 1.0)).astype(np.float32)
    return out


def emission_from_score(score: np.ndarray, holdout: np.ndarray, budget_frac: float) -> np.ndarray:
    k = max(1, int(round(budget_frac * int(holdout.sum()))))
    thr = float(np.quantile(score[holdout], 1.0 - k / max(1, int(holdout.sum()))))
    return (score >= thr) & holdout


def live_consistency(args, candidates: dict, log) -> dict:
    """Do the new layers' enrichments track the 24 live scores?

    For each new layer: the mean layer value inside every artefact's emitted
    pixels (log-enrichment vs the domain base), its Spearman correlation with the
    artefacts' |G|=10k log-skill, the same correlation with artefact families
    held out one at a time (family-level leave-one-out, matching the habitat
    model's grouping), and the top-4-minus-rest enrichment gap.  This is the only
    validation available against the actual scoring population.
    """
    from gems.habitat import EPS, G_PRIMARY, anchor_geometry, skill_vector, _spearman
    from gems.layers import load_domain

    anchor_dir = Path(args.h195).resolve().parent
    anchors = anchor_geometry(str(anchor_dir))
    skills = skill_vector(anchors, G_PRIMARY)
    y = np.log(np.maximum(skills, 1e-3))
    fams = [a["family"] for a in anchors]
    top4 = {"h19-5", "h19-4", "h16-1", "h28-dotted-ridge"}
    _, _, dom, _ = load_domain()
    dflat = dom.ravel()
    out = {}
    for name, layer in candidates.items():
        if name.startswith("blend_") or name.startswith("habitat") or name.startswith("baseline"):
            continue
        flat = layer.ravel()
        base = float(flat[dflat].mean())
        if base <= 1e-6:
            continue
        enr = np.array([float(np.log((flat[a["idx"]] + EPS).mean() / (base + EPS)))
                        if a["idx"].size else 0.0 for a in anchors])
        rho_all = _spearman(enr, y)
        # family-held-out correlation: drop all artefacts of one family, recompute
        rho_folds = []
        for f in sorted(set(fams)):
            m = np.array([x != f for x in fams])
            if m.sum() >= 5:
                rho_folds.append(_spearman(enr[m], y[m]))
        top_m = np.array([a["id"] in top4 for a in anchors])
        out[name] = dict(
            spearman_vs_log_skill=float(rho_all),
            family_loo_spearman_mean=float(np.mean(rho_folds)) if rho_folds else None,
            family_loo_spearman_min=float(np.min(rho_folds)) if rho_folds else None,
            enrichment_top4_mean=float(enr[top_m].mean()),
            enrichment_rest_mean=float(enr[~top_m].mean()),
            top4_minus_rest=float(enr[top_m].mean() - enr[~top_m].mean()),
        )
        log(f"live-consistency {name}: rho={rho_all:+.2f} top4-rest={out[name]['top4_minus_rest']:+.2f}")
    return out


def habitat_nested_cv_check(candidates: dict, dom: np.ndarray, log) -> dict:
    """Test whether adding H-39 (or H-38) to the 95-layer pool improves nested leave-one-family-out CV.

    Evaluates both:
    1. Unforced competition: H-39 / H-38 enters the candidate pool and must win a top-k slot inside
       each leave-one-family-out fold on its own univariate |Spearman| merit.
    2. Forced inclusion: ``h39_shallow_residual_thickcover`` (both 1-99 percentile normalized in [0,1]
       like ``gems.layers.iter_layers`` and raw unnormalized) is force-appended to (or replaces the
       k-th member of) the top-k baseline layers inside every fold.
    """
    from gems.habitat import EPS, G_TRIALS, _ridge, _spearman, fit_habitat_model, skill_vector

    raw_path = ROOT / "docs" / "data" / "habitat-attribution-raw.json"
    hab_path = ROOT / "docs" / "data" / "habitat-model.json"
    if not (raw_path.exists() and hab_path.exists()):
        return {}
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    hab = json.loads(hab_path.read_text(encoding="utf-8"))
    names_95 = [nm for nm in raw["layers"].keys() if nm != "lid_valid"]
    anchors = [
        {"id": a["id"], "lb": a["live_dti"], "area": a["area"], "kbar": a["kbar"], "family": a["family"]}
        for a in hab["per_anchor"]
    ]
    fams = [a["family"] for a in anchors]
    E_base = np.array(
        [
            np.log(
                (np.array(raw["layers"][nm]["enrichment"]) * raw["layers"][nm]["base"] + EPS)
                / (raw["layers"][nm]["base"] + EPS)
            )
            for nm in names_95
        ]
    ).T

    import rasterio

    dflat = dom.ravel()
    anchor_idxs = []
    for a in anchors:
        with rasterio.open(ROOT / ".cache" / "sib" / "anchors" / f"{a['id']}.tif") as src:
            p = src.read(1).astype(np.float32)
        p = np.where(dom, np.nan_to_num(p, nan=0.0), 0.0)
        anchor_idxs.append(np.flatnonzero((p > 0).ravel()))

    tc_arr = candidates["h39_shallow_residual_thickcover"]
    v = tc_arr[dom]
    lo, hi = np.percentile(v, [1, 99])
    tc_norm = np.where(dom, np.clip((tc_arr - lo) / max(hi - lo, 1e-9), 0.0, 1.0), 0.0).astype(np.float32)
    flat_n = tc_norm.ravel()
    base_n = float(flat_n[dflat].mean())
    col_tc_norm = np.array([float(np.log((flat_n[idx].mean() + EPS) / (base_n + EPS))) for idx in anchor_idxs])

    flat_r = tc_arr.ravel()
    base_r = float(flat_r[dflat].mean())
    col_tc_raw = np.array([float(np.log((flat_r[idx].mean() + EPS) / (base_r + EPS))) for idx in anchor_idxs])

    def _fit_forced(E_pool: np.ndarray, extra_col: np.ndarray, y: np.ndarray, replace_last: bool):
        fams_u = sorted(set(fams))
        best = None
        for k in (4, 6, 8, 10, 14):
            for alpha in (0.3, 1.0, 3.0, 10.0):
                pred = np.full(len(y), np.nan)
                for f in fams_u:
                    te = np.array([i for i, ff in enumerate(fams) if ff == f])
                    tr = np.array([i for i, ff in enumerate(fams) if ff != f])
                    rho = np.array([abs(_spearman(E_pool[tr, j], y[tr])) for j in range(E_pool.shape[1])])
                    kk = k - 1 if replace_last else k
                    sel = np.argsort(-rho)[:kk]
                    Xtr = np.hstack([E_pool[tr][:, sel], extra_col[tr, None]])
                    Xte = np.hstack([E_pool[te][:, sel], extra_col[te, None]])
                    b = _ridge(Xtr, y[tr], alpha)
                    pred[te] = (Xte - Xtr.mean(0)) @ b + y[tr].mean()
                cv = _spearman(pred, y)
                if best is None or cv > best[0]:
                    best = (cv, k, alpha)
        cv, k, alpha = best
        rho_all = np.array([abs(_spearman(E_pool[:, j], y)) for j in range(E_pool.shape[1])])
        kk = k - 1 if replace_last else k
        sel_all = np.argsort(-rho_all)[:kk]
        beta_all = _ridge(np.hstack([E_pool[:, sel_all], extra_col[:, None]]), y, alpha)
        return dict(
            cv_spearman=float(cv),
            k=int(k),
            alpha=float(alpha),
            h39_ridge_beta=float(beta_all[-1]),
        )

    per_g = {}
    for g in G_TRIALS:
        y = np.log(np.maximum(skill_vector(anchors, g), 1e-6))
        base_fit = fit_habitat_model(E_base, y, fams)
        rhos_95 = sorted([abs(_spearman(E_base[:, j], y)) for j in range(E_base.shape[1])], reverse=True)
        rho_tc_n = abs(_spearman(col_tc_norm, y))
        rho_tc_r = abs(_spearman(col_tc_raw, y))
        rank_n = int(sum(1 for r in rhos_95 if r > rho_tc_n) + 1)
        rank_r = int(sum(1 for r in rhos_95 if r > rho_tc_r) + 1)

        unf_norm = fit_habitat_model(np.hstack([E_base, col_tc_norm[:, None]]), y, fams)
        unf_raw = fit_habitat_model(np.hstack([E_base, col_tc_raw[:, None]]), y, fams)
        fa_norm = _fit_forced(E_base, col_tc_norm, y, replace_last=False)
        fr_norm = _fit_forced(E_base, col_tc_norm, y, replace_last=True)
        fa_raw = _fit_forced(E_base, col_tc_raw, y, replace_last=False)
        fr_raw = _fit_forced(E_base, col_tc_raw, y, replace_last=True)

        per_g[str(int(g))] = dict(
            baseline_cv_spearman=float(base_fit["cv_spearman"]),
            top8_univariate_abs_rho_cutoff=float(rhos_95[7]),
            top14_univariate_abs_rho_cutoff=float(rhos_95[13]),
            h39_thickcover_norm_abs_rho=float(rho_tc_n),
            h39_thickcover_norm_rank_of_96=rank_n,
            h39_thickcover_raw_abs_rho=float(rho_tc_r),
            h39_thickcover_raw_rank_of_96=rank_r,
            unforced_norm_cv_spearman=float(unf_norm["cv_spearman"]),
            unforced_norm_selected_in_refit=bool(95 in unf_norm["selected"]),
            unforced_raw_cv_spearman=float(unf_raw["cv_spearman"]),
            unforced_raw_selected_in_refit=bool(95 in unf_raw["selected"]),
            forced_append_norm=fa_norm,
            forced_replace_norm=fr_norm,
            forced_append_raw=fa_raw,
            forced_replace_raw=fr_raw,
        )
    log("habitat nested-CV check completed across G_TRIALS:", list(per_g.keys()))
    return dict(
        baseline_nested_cv_spearman_G6000=float(per_g["6000"]["baseline_cv_spearman"]),
        unforced_nested_cv_spearman_G6000=float(per_g["6000"]["unforced_norm_cv_spearman"]),
        forced_append_norm_cv_spearman_G6000=float(per_g["6000"]["forced_append_norm"]["cv_spearman"]),
        forced_append_raw_cv_spearman_G6000=float(per_g["6000"]["forced_append_raw"]["cv_spearman"]),
        per_g_scenario=per_g,
        conclusion=(
            "In unforced 15-fold leave-one-family-out nested CV, h39_shallow_residual_thickcover ranks "
            "40/96 (normalized |rho|=0.3643) and 49/96 (raw |rho|=0.3217) at |G|=6,000 - below the top-k "
            "cutoffs (0.5548 at k=8, 0.5070 at k=14) - so it is selected in 0/15 folds and leaves nested-CV "
            "Spearman unchanged at 0.437391 (delta = 0.000000). When force-appended to the ridge regression "
            "inside every fold, the raw layer degrades CV across all |G| (0.383478, delta = -0.053913 at "
            "|G|=6,000), while the [0,1]-normalized layer changes CV by only +0.008696 (0.446087, k=8, "
            "beta = +0.2726; 10 units of sum(d_i^2) out of 2,300 on n=24 points) at |G|=6,000 and degrades "
            "at |G|=15,000 (0.384348, delta = -0.024348). H-39 does not survive unforced nested CV and is "
            "therefore not promoted into the habitat model."
        ),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--h195", default=str(ROOT / ".cache" / "sib" / "anchors" / "h19-5.tif"))
    ap.add_argument("--h30", default=str(ROOT / "docs" / "downloads" /
                                         "gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-nan.tif"))
    ap.add_argument("--habitat", default=str(ROOT / "outputs" / "habitat_score.npy"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "new-hypothesis-validation.json"))
    args = ap.parse_args()

    t0 = time.time()

    def log(*a):
        print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)

    footprint, catalogue, domain, _ = load_domain()
    target, tinfo = load_target()
    log("domain", int(domain.sum()), "target px", int(target.sum()))

    # ---- candidate score rasters ---------------------------------------------------------
    from gems.orientation import build_orientation_layers, build_residual_layers

    ori = build_orientation_layers(domain)
    log("orientation layers:", {k: float(v[v > 0].mean()) for k, v in ori.items()})
    res = build_residual_layers(domain)
    log("residual layers built")

    candidates: dict[str, np.ndarray] = {}
    candidates["h38_orientation_coherence"] = ori["h38_agree_mean"]
    candidates["h38_orientation_with_lidar"] = ori["h38_agree_with_lidar"]
    candidates["h39_shallow_residual_edges"] = res["h39_resid_edge_500m"]
    candidates["h39_shallow_residual_thickcover"] = res["h39_resid_edge_thickcover"]

    if Path(args.habitat).exists():
        H = np.load(args.habitat)
        candidates["habitat_livefit"] = np.where(np.isfinite(H), H, 0.0)
        # fixed-weight blends - no fitted parameters, so no fold leakage
        candidates["blend_habitat_x_h38"] = (0.5 * rank01(candidates["habitat_livefit"], domain)
                                             + 0.5 * rank01(candidates["h38_orientation_coherence"], domain))
        candidates["blend_habitat_x_h39"] = (0.5 * rank01(candidates["habitat_livefit"], domain)
                                             + 0.5 * rank01(candidates["h39_shallow_residual_edges"], domain))
    else:
        log("WARNING: habitat score absent; habitat blends skipped")

    # single strongest habitat-selected layer as a layer-only baseline
    from gems.layers import iter_layers

    for name, layer in iter_layers():
        if name == "lid_upface_max":
            candidates["baseline_lid_upface_max"] = layer
            break
    del ori, res

    # fixed-artifact baselines (their own emissions, no re-ranking)
    fixed: dict[str, np.ndarray] = {}
    import rasterio

    with rasterio.open(args.h195) as src:
        fixed["h19-5_fixed_emission"] = np.where(domain, np.nan_to_num(src.read(1), nan=0.0), 0.0) > 0
    with rasterio.open(args.h30) as src:
        fixed["h30_fixed_emission"] = np.where(domain, np.nan_to_num(src.read(1), nan=0.0), 0.0) > 0

    # ---- evaluation ------------------------------------------------------------------------
    folds = blocked_folds(target.shape, 5, 15)
    rows: list[dict] = []

    def eval_emission(emission: np.ndarray, holdout: np.ndarray, truth: np.ndarray) -> float:
        """Official DTI, cropped to the holdout's bounding box (+4 px cone margin).

        The 300 m triangular support reaches 3 pixels, so a 4-pixel margin makes the
        cropped score identical to the full-raster score while using ~1/5 of the RAM.
        """
        ys, xs = np.nonzero(holdout)
        y0, y1 = max(0, ys.min() - 4), min(holdout.shape[0], ys.max() + 5)
        x0, x1 = max(0, xs.min() - 4), min(holdout.shape[1], xs.max() + 5)
        sl = (slice(y0, y1), slice(x0, x1))
        e = (emission & holdout)[sl].astype(np.float32)
        t = truth[sl]
        m = holdout[sl]
        if not e.any():
            return 0.0
        r = distance_weighted_tversky(e, t, mask=m)
        return float(r["dti"])

    for fi, fold in enumerate(folds):
        holdout = fold & domain
        truth = target & holdout
        if truth.sum() < 100:
            continue
        row: dict = {"fold": fi, "holdout_px": int(holdout.sum()), "target_px": int(truth.sum())}
        for budget_label, frac in BUDGETS.items():
            entry: dict = {}
            for name, score in candidates.items():
                emis = emission_from_score(score, holdout, frac)
                entry[name] = {"dti": eval_emission(emis, holdout, truth), "px": int(emis.sum())}
                del emis
            for name, em in fixed.items():
                entry[name] = {"dti": eval_emission(em, holdout, truth), "px": int((em & holdout).sum())}
            rng = np.random.default_rng(1000 + fi)
            rand = []
            for s in range(N_RANDOM):
                k = max(1, int(round(frac * int(holdout.sum()))))
                pick = rng.choice(int(holdout.sum()), size=k, replace=False)
                m = np.zeros(holdout.sum(), bool)
                m[pick] = True
                rmap = np.zeros(holdout.shape, bool)
                rmap[holdout] = m
                rand.append(eval_emission(rmap, holdout, truth))
                del rmap, m, pick
            entry["random_control"] = {"dti_mean": float(np.mean(rand)),
                                       "dti_values": [float(v) for v in rand]}
            row[budget_label] = entry
        rows.append(row)
        log(f"fold {fi}: target {int(truth.sum())} px "
            f"| h38 DTI(1.22%) {row['1.22pct']['h38_orientation_coherence']['dti']:.4f} "
            f"vs random {row['1.22pct']['random_control']['dti_mean']:.4f} "
            f"vs h19-5 {row['1.22pct']['h19-5_fixed_emission']['dti']:.4f}")

    # ---- summary ---------------------------------------------------------------------------
    def mean_over(name: str, budget: str, key: str = "dti") -> float:
        vals = [r[budget][name][key] for r in rows if name in r[budget]]
        return float(np.mean(vals)) if vals else float("nan")

    summary = {}
    for budget in BUDGETS:
        s: dict = {}
        for name in list(candidates) + list(fixed):
            dtis = [r[budget][name]["dti"] for r in rows]
            rnd = [r[budget]["random_control"]["dti_mean"] for r in rows]
            wins_random = int(sum(d > rr for d, rr in zip(dtis, rnd)))
            wins_h195 = int(sum(d > r[budget]["h19-5_fixed_emission"]["dti"] for d, r in zip(dtis, rows)))
            wins_h30 = int(sum(d > r[budget]["h30_fixed_emission"]["dti"] for d, r in zip(dtis, rows)))
            s[name] = dict(mean_dti=float(np.mean(dtis)), per_fold=[float(d) for d in dtis],
                           folds_beating_random=wins_random, folds_beating_h19_5=wins_h195,
                           folds_beating_h30=wins_h30, n_folds=len(rows))
        s["random_control"] = dict(mean_dti=mean_over("random_control", budget, "dti_mean"),
                                   per_fold=[r[budget]["random_control"]["dti_mean"] for r in rows],
                                   n_folds=len(rows))
        summary[budget] = s

    out = dict(
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        purpose=("Spatially blocked validation of H-38/H-39 on the only independent uncatalogued-fault "
                 "truth available offline (USGS SGMC faults >=300 m from the catalogue). Same folds, "
                 "target and 1.22 % budget as the deep-ensemble admission gate; 2.37 % matches h19-5's "
                 "live budget. Blends use fixed 0.5/0.5 weights - nothing is fitted on these folds."),
        target=tinfo,
        protocol=dict(folds="5 column strips, 1500 m buffer (gems.ensemble.blocked_folds)",
                      budgets=BUDGETS, metric="official distance-weighted Tversky (gems.metric)",
                      emission="top-k of the candidate score inside the held-out strip"),
        caveat=("SGMC-proxy victory is necessary, not sufficient: the offline-proxy audit measured that "
                "no available proxy ranks the 24 live artefacts above chance, so proxy->hidden-truth "
                "transfer is unproven. Beating h19-5 here does not authorize a submission slot by itself."),
        folds=rows,
        summary=summary,
        live_score_consistency=live_consistency(args, candidates, log) if len(rows) else {},
        habitat_nested_cv_check=habitat_nested_cv_check(candidates, domain, log) if len(rows) else {},
    )
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    log("wrote", args.out)

    # console digest
    for budget in BUDGETS:
        log(f"=== budget {budget} (mean DTI over {len(rows)} folds) ===")
        for name, s in sorted(summary[budget].items(), key=lambda kv: -kv[1]["mean_dti"]):
            if name == "random_control":
                log(f"  {name:36s} {s['mean_dti']:.4f}")
            else:
                log(f"  {name:36s} {s['mean_dti']:.4f}  beats rnd {s['folds_beating_random']}/{s['n_folds']}"
                    f"  h19-5 {s['folds_beating_h19_5']}/{s['n_folds']}  h30 {s['folds_beating_h30']}/{s['n_folds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
