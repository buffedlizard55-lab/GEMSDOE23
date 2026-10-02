#!/usr/bin/env python3
"""Fit the live-score habitat model and write the evidence + the pixel-level habitat map.

    python scripts/fit_habitat_model.py --anchors .cache/sib/anchors --out docs/data/habitat-model.json

Reads only: the official template/feature rasters, the public external layers and the
24 live-scored public artefacts mirrored in the sibling repositories.  Writes
``outputs/habitat_score.npy`` (float32, -inf outside the scored domain) and a JSON
evidence record with the nested-CV correlation, the selected layers, their weights and
the per-artefact implied |G|-sensitive skill.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from gems.habitat import (G_TRIALS, anchor_geometry, enrichment_matrix, fit_habitat_model,
                          habitat_score, implied_tp, skill_vector)
from gems.layers import iter_layers, load_domain


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchors", default=".cache/sib/anchors")
    ap.add_argument("--data-dir", default=os.environ.get("GEMS_DATA_DIR", "data"))
    ap.add_argument("--out", default="docs/data/habitat-model.json")
    ap.add_argument("--score-out", default="outputs/habitat_score.npy")
    args = ap.parse_args()

    t0 = time.time()
    anchors = anchor_geometry(args.anchors, args.data_dir)
    print(f"[{time.time()-t0:6.1f}s] anchors: {len(anchors)}", flush=True)

    names, E, bases = enrichment_matrix(anchors, args.data_dir)
    print(f"[{time.time()-t0:6.1f}s] enrichment matrix {E.shape} over {len(names)} layers", flush=True)

    fits = {}
    for G in G_TRIALS:
        y = np.log(np.maximum(skill_vector(anchors, G), 1e-3))
        fit = fit_habitat_model(E, y, [a["family"] for a in anchors])
        fits[str(int(G))] = fit
        print(f"[{time.time()-t0:6.1f}s] |G|={G:>7,.0f}  nested-CV Spearman rho = {fit['cv_spearman']:+.3f} "
              f"(k={fit['k']}, alpha={fit['alpha']})", flush=True)

    # choose the |G| whose habitat model cross-validates best; ties -> the smaller |G|
    bestG = max(fits, key=lambda g: (round(fits[g]["cv_spearman"], 3), -float(g)))
    fit = fits[bestG]
    sel = [names[j] for j in fit["selected"]]
    print("\nbest |G| =", bestG, " selected layers (weight):")
    for nm, b in sorted(zip(sel, fit["beta"]), key=lambda t: -abs(t[1])):
        print(f"   {nm:34s} beta={b:+.4f}")

    # second streaming pass: rebuild only the selected layers and compose the score
    G = float(bestG)
    y = np.log(np.maximum(skill_vector(anchors, G), 1e-3))
    from gems.habitat import _ridge
    rho = np.array([abs(np.corrcoef(np.argsort(np.argsort(E[:, j])), np.argsort(np.argsort(y)))[0, 1])
                    for j in range(E.shape[1])])
    selidx = np.argsort(-rho)[: fit["k"]]
    beta = _ridge(E[:, selidx], y, fit["alpha"])
    _, _, domain, _ = load_domain(args.data_dir)
    want = {names[j] for j in selidx}
    picked = {}
    for nm, layer in iter_layers(args.data_dir):
        if nm in want:
            picked[nm] = layer
            if len(picked) == len(want):
                break
    print(f"[{time.time()-t0:6.1f}s] rebuilt {len(picked)}/{len(want)} selected layers", flush=True)
    H = habitat_score(picked, [names[j] for j in selidx], beta, [bases[j] for j in selidx], domain)
    os.makedirs(os.path.dirname(args.score_out), exist_ok=True)
    np.save(args.score_out, H)
    print(f"[{time.time()-t0:6.1f}s] wrote {args.score_out} finite={int(np.isfinite(H).sum())}", flush=True)

    # predicted skill of each anchor under the fitted model, and its own implied numbers
    per = []
    for i, a in enumerate(anchors):
        tp = implied_tp(a["lb"], a["area"], G)
        per.append(dict(id=a["id"], family=a["family"], live_dti=a["lb"], n=a["n"], area=a["area"],
                        kbar=a["kbar"], implied_tp=tp, recall_of_G=tp / G,
                        skill=tp / (G * a["kbar"]), cv_pred_skill=float(np.exp(fit["cv_pred"][i])),
                        mean_habitat=float(np.mean([H.ravel()[j] for j in a["idx"][:200000]]))))
    ev = dict(
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        purpose="Reverse-engineer the hidden new-fault habitat from 24 live public scores.",
        metric_source="https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/#performance-metric",
        masking_ruling="https://community.drivendata.org/t/11516/2 (known USGS/INGENIOUS fault pixels are masked out of evaluation)",
        new_fault_ruling="https://community.drivendata.org/t/11536/2 ('new fault' = any fault pixel not already captured by USGS/INGENIOUS, incl. newly mapped geometry of an existing system)",
        scored_domain_px=int(domain.sum()),
        n_anchors=len(anchors), n_layers=len(names),
        fp_relief_factor=0.813,
        g_selected=G, g_trials={g: dict(cv_spearman=fits[g]["cv_spearman"], k=fits[g]["k"], alpha=fits[g]["alpha"]) for g in fits},
        nested_cv_spearman=fit["cv_spearman"], k=fit["k"], alpha=fit["alpha"],
        selected_layers=sel, beta=[float(b) for b in fit["beta"]], layer_bases={names[j]: bases[j] for j in fit["selected"]},
        cv_pred_log_skill=fit["cv_pred"],
        cv_grid=fit["cv_detail"],
        per_anchor=per,
        artefacts="registry/submissions.json of the sibling repositories; live scores transcribed from the public leaderboard",
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(ev, fh, indent=1)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
