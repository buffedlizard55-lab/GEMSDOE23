#!/usr/bin/env python3
"""Why the H19 emissions lead the group's live scores, and what beating them takes.

Produces docs/data/h19-placement-analysis.json from the restored anchors and the
95-layer evidence bank.  Everything is measured; nothing is assumed about the
hidden truth beyond the published |G| bounds (5,564-14,944 px,
docs/data/live-model-bounds.json).

Sections
--------
1. anchor table   - geometry (area, Kbar, coverage) and, for every |G| scenario in
                    the published bounds, the exactly inverted TP, recall and skill.
2. h19-5 vs h19-4 - the two emissions differ only in line weights and budget; the
                    set algebra plus a layer-enrichment attribution of the two
                    difference sets measures *what the +0.0028 DTI delta rewards*.
3. top-family     - shared and divergent layer enrichment of the four best live
                    artefacts (h19-5, h19-4, h16-1, h28-dotted-ridge).
4. targets        - the exact skill a submission needs (at h19-5's and H30's
                    geometry) to reach 0.1922 / 0.3049 / 0.3195 for each |G|, and
                    the best skill ever measured at that |G|.
5. budget         - h19-5's marginal-rule optimum budget vs its actual 2.45 %.

Run:  python scripts/analyze_h19_placement.py [--anchor-dir .cache/sib/anchors]
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

from gems.emission import CONE_WEIGHT, ALPHA, BETA, DOMAIN_PX, fp_relief, geometry, kernel_envelope  # noqa: E402
from gems.habitat import EPS, FAMILIES, G_TRIALS, anchor_geometry, implied_tp  # noqa: E402
from gems.layers import PIXEL_M, RADIUS_M, iter_layers, load_domain  # noqa: E402

TOP_IDS = ["h19-5", "h19-4", "h16-1", "h28-dotted-ridge"]
TARGET_DTIS = {"h19-5_live": 0.1922, "user_reported_top": 0.3049, "leader_dard_20261002": 0.3195}


def _load_raster(path: Path, domain: np.ndarray) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as src:
        p = src.read(1).astype(np.float32)
    return np.where(domain, np.nan_to_num(p, nan=0.0), 0.0)


def skill_needed(target_dti: float, area: float, kbar: float, g: float) -> float:
    """Invert expected_dti for the skill at fixed geometry: solve
    DTI = tp/(0.2 tp + 0.2 relief A + 0.8 (G - tp)) with tp = min(skill*G*kbar, G)."""
    c = ALPHA * fp_relief(g, DOMAIN_PX)
    # DTI = tp (1 - 0.2) / (0.2 tp ... ) ->  tp = DTI (c A + 0.8 G) / (1 - 0.2 DTI)  (same algebra as implied_tp)
    tp = implied_tp(target_dti, area, g)
    if tp > g:            # unreachable even at perfect recall
        return float("inf")
    return tp / (g * kbar)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anchor-dir", default=str(ROOT / ".cache" / "sib" / "anchors"))
    ap.add_argument("--h30", default=str(ROOT / "docs" / "downloads" /
                                         "gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-nan.tif"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "data" / "h19-placement-analysis.json"))
    args = ap.parse_args()

    t0 = time.time()

    def log(*a):
        print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)

    footprint, catalogue, domain, _ = load_domain()
    log("domain", int(domain.sum()), "px")

    anchors = anchor_geometry(args.anchor_dir)
    log("anchors", len(anchors))

    # ---- 1. anchor table with |G|-scenario inversions ------------------------------------
    rows = []
    by_id = {a["id"]: a for a in anchors}
    for a in sorted(anchors, key=lambda x: -x["lb"]):
        scen = {}
        for g in G_TRIALS:
            tp = implied_tp(a["lb"], a["area"], g)
            ok = tp <= g + 1e-9
            scen[str(int(g))] = {
                "implied_tp": float(tp),
                "recall_of_G": float(min(tp / g, 1.0)),
                "skill": float(tp / (g * a["kbar"])) if ok else None,
                "reachable": bool(ok),
            }
        rows.append(dict(id=a["id"], family=a["family"], live_dti=a["lb"],
                         area_px=a["area"], emitted_px=a["n"], kbar=a["kbar"],
                         scenarios=scen))
    # H30 as the unscored in-house comparison
    h30_path = Path(args.h30)
    h30_row = None
    if h30_path.exists():
        p = _load_raster(h30_path, domain)
        m = p > 0
        geo = geometry(m, domain)
        h30_row = dict(id="h30-inhouse-QA", family="gemsdoe23", live_dti=None,
                       area_px=geo["area"], emitted_px=geo["area"], kbar=geo["kbar"],
                       scenarios={})
        del p, m
        log("h30 geometry", geo)

    # ---- 2. h19-5 vs h19-4 set algebra + difference attribution ---------------------------
    anch = Path(args.anchor_dir)
    p5 = _load_raster(anch / "h19-5.tif", domain) > 0
    p4 = _load_raster(anch / "h19-4.tif", domain) > 0
    both = p5 & p4
    only5 = p5 & ~p4
    only4 = p4 & ~p5
    jac = float(both.sum() / float((p5 | p4).sum()))
    log("h19-5 only", int(only5.sum()), "h19-4 only", int(only4.sum()), "jaccard", round(jac, 4))

    # distance-to-catalogue profile of each difference set
    from scipy.ndimage import distance_transform_edt

    d_cat = distance_transform_edt(~catalogue, sampling=(PIXEL_M, PIXEL_M))
    prof = {}
    for nm, m in (("h19-5_full", p5), ("h19-4_full", p4), ("h19-5_only", only5), ("h19-4_only", only4)):
        d = d_cat[m]
        prof[nm] = dict(mean_m=float(d.mean()), median_m=float(np.median(d)),
                        frac_gt_500m=float((d > 500).mean()), frac_gt_1500m=float((d > 1500).mean()))
    del d_cat

    # layer enrichment of the two difference sets: what does the +0.0028 prefer?
    dsets = {"h19_5_only": only5, "h19_4_only": only4}
    dflat = domain.ravel()
    diff_rows = []
    for name, layer in iter_layers():
        flat = layer.ravel()
        base = float(flat[dflat].mean())
        if base <= 1e-6:
            continue
        vals = {}
        for k, m in dsets.items():
            vals[k] = float(flat[m.ravel()].mean())
        diff_rows.append(dict(layer=name, domain_base=base, **vals,
                              delta=vals["h19_5_only"] - vals["h19_4_only"]))
        del flat
    diff_rows.sort(key=lambda r: -abs(r["delta"]))
    log("layers attributed:", len(diff_rows))

    # ---- 3. shared / divergent enrichment of the four best live artefacts -----------------
    top_idx = {k: by_id[k]["idx"] for k in TOP_IDS if k in by_id}
    top_rows = []
    for name, layer in iter_layers():
        flat = layer.ravel()
        base = float(flat[dflat].mean())
        if base <= 1e-6:
            continue
        enr = {k: float(np.log((flat[v].mean() + EPS) / (base + EPS))) for k, v in top_idx.items()}
        spread = max(enr.values()) - min(enr.values())
        top_rows.append(dict(layer=name, domain_base=base, enrichment=enr, spread=float(spread)))
        del flat
    shared = sorted([r for r in top_rows if r["spread"] < 0.6], key=lambda r: -np.mean(list(r["enrichment"].values())))
    divergent = sorted(top_rows, key=lambda r: -r["spread"])

    # ---- 4. what beating the leaders takes -----------------------------------------------
    targets = {}
    for geo_name, a in (("h19-5_geometry", by_id["h19-5"]),):
        tgt = {}
        for label, dti in TARGET_DTIS.items():
            per_g = {}
            for g in G_TRIALS:
                need = skill_needed(dti, a["area"], a["kbar"], g)
                best_measured = max(
                    (r["scenarios"][str(int(g))]["skill"] or 0.0) for r in rows
                ) if any(r["scenarios"][str(int(g))]["skill"] for r in rows) else 0.0
                per_g[str(int(g))] = dict(skill_required=float(need),
                                          best_measured_skill_among_24=float(best_measured),
                                          ratio_to_best=float(need / best_measured) if (need < float("inf") and best_measured > 0) else None)
            tgt[label] = per_g
        targets[geo_name] = tgt
    if h30_row is not None:
        tgt = {}
        a30 = dict(area=h30_row["area_px"], kbar=h30_row["kbar"])
        for label, dti in TARGET_DTIS.items():
            per_g = {}
            for g in G_TRIALS:
                need = skill_needed(dti, a30["area"], a30["kbar"], g)
                per_g[str(int(g))] = dict(skill_required=float(need))
            tgt[label] = per_g
        targets["h30_geometry"] = tgt

    # ---- 5. budget check for h19-5 ---------------------------------------------------------
    budget = {}
    for g in G_TRIALS:
        tp = implied_tp(0.1922, by_id["h19-5"]["area"], g)
        c = ALPHA * fp_relief(g, DOMAIN_PX)
        thr = c * tp / (c * by_id["h19-5"]["area"] + BETA * g)
        budget[str(int(g))] = dict(
            implied_tp=float(tp),
            marginal_tp_threshold_per_extra_px=float(thr),
            mean_tp_per_emitted_px=float(tp / by_id["h19-5"]["area"]),
        )

    out = dict(
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        purpose=("Measured attribution of the group's two best live scores and the algebra of "
                 "what beating them (and the leaders) requires. All skill/TP values are exact "
                 "inversions of the official metric under the stated |G| hypothesis; |G| itself "
                 "is bounded, not known (docs/data/live-model-bounds.json)."),
        g_bounds_px=[5564, 14944],
        g_scenarios=[int(g) for g in G_TRIALS],
        anchors=rows,
        h30_reference=h30_row,
        h19_delta=dict(
            jaccard=jac,
            both_px=int(both.sum()), h19_5_only_px=int(only5.sum()), h19_4_only_px=int(only4.sum()),
            live_dti_delta=0.1922 - 0.1894,
            distance_to_catalogue_profile_m=prof,
            layer_attribution_top20_by_abs_delta=diff_rows[:20],
        ),
        top_family=dict(
            ids=TOP_IDS,
            shared_enrichment_top15=shared[:15],
            most_divergent_layers=divergent[:15],
        ),
        targets=targets,
        h19_5_budget_check=budget,
        caveats=[
            "Attribution from 24 live scores is observational: the difference sets measure what "
            "the +0.0028 delta is consistent with, not a controlled experiment.",
            "skill depends on the unknown |G|; only the published bound interval is used.",
            "Score-to-artefact attribution for 0.1922/0.1894 remains a numerical match only (flag I-28).",
        ],
    )
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    log("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
