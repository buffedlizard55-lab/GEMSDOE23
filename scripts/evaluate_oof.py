#!/usr/bin/env python3
"""Score the deep ensemble's out-of-fold map against a random-emission control.

The gate that decides whether the detector is allowed to influence the submission:

    the ensemble is admitted only if its out-of-fold DTI at the operating budget beats a
    seed-matched random emission of the same size on the same folds.

Everything is computed with the official metric (src/gems/metric.py) on the official grid,
with the known-fault catalogue masked out of the scored domain per the staff ruling
(https://community.drivendata.org/t/11516/2).
"""
from __future__ import annotations
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from gems.layers import load_domain
from gems.featurecube import load_target
from gems.ensemble import blocked_folds
from gems.metric import distance_weighted_tversky

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oof", default="outputs/oof_mean.npy")
    ap.add_argument("--cov", default="outputs/oof_covered.npy")
    ap.add_argument("--epi", default="outputs/oof_epistemic.npy")
    ap.add_argument("--ale", default="outputs/oof_aleatoric.npy")
    ap.add_argument("--out", default="docs/data/oof-evaluation.json")
    ap.add_argument("--budget-frac", type=float, default=0.0122)
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()
    t0=time.time()
    footprint, catalogue, domain, _ = load_domain()
    target, tinfo = load_target()
    p = np.load(args.oof); cov = np.load(args.cov).astype(bool)
    epi = np.load(args.epi) if os.path.exists(args.epi) else np.zeros_like(p)
    ale = np.load(args.ale) if os.path.exists(args.ale) else np.zeros_like(p)
    folds = blocked_folds(target.shape, 5, 15)
    rows=[]
    for fi,fold in enumerate(folds):
        hold = fold & domain & cov
        truth = target & hold
        if truth.sum() < 100: continue
        k = int(round(args.budget_frac * hold.sum()))
        thr = float(np.quantile(p[hold], 1 - k / max(1, int(hold.sum()))))
        emis = (p >= thr) & hold
        r = distance_weighted_tversky(emis.astype(np.float32), truth, mask=hold)
        rng = np.random.default_rng(1000 + fi)
        ctrls=[]
        for s in range(args.seeds):
            rnd = rng.random(hold.shape)
            t2 = float(np.quantile(rnd[hold], 1 - k / max(1, int(hold.sum()))))
            rc = distance_weighted_tversky(((rnd >= t2) & hold).astype(np.float32), truth, mask=hold)
            ctrls.append(rc["dti"])
        rows.append(dict(fold=fi, holdout_px=int(hold.sum()), truth_px=int(truth.sum()), budget=k,
                         emitted_px=int(emis.sum()), dti=float(r["dti"]),
                         recall=float(r["tp_weighted"]/max(1,int(truth.sum()))),
                         tp=float(r["tp_weighted"]), fp=float(r["fp_weighted"]), fn=float(r["fn_weighted"]),
                         random_control_dti=[float(c) for c in ctrls],
                         random_control_mean=float(np.mean(ctrls)),
                         beats_random=bool(r["dti"] > np.mean(ctrls)),
                         mean_epistemic=float(epi[hold].mean()), mean_aleatoric=float(ale[hold].mean()),
                         epistemic_share=float(epi[hold].sum()/max(1e-12,float((epi[hold]+ale[hold]).sum())))))
        print(f"fold {fi}: truth {rows[-1]['truth_px']:6d} budget {k:6d} DTI={rows[-1]['dti']:.4f} "
              f"random={rows[-1]['random_control_mean']:.4f} beats_random={rows[-1]['beats_random']} "
              f"epi_share={rows[-1]['epistemic_share']:.3f}", flush=True)
    n_beat = sum(r["beats_random"] for r in rows)
    out = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               target=tinfo, budget_frac=args.budget_frac, folds=rows,
               folds_beating_random=int(n_beat), n_folds=len(rows),
               gate="detector admitted to the emission only if folds_beating_random >= ceil(n_folds/2)+1",
               gate_passed=bool(n_beat >= (len(rows)//2 + 1)),
               mean_dti=float(np.mean([r["dti"] for r in rows])) if rows else None,
               mean_random=float(np.mean([r["random_control_mean"] for r in rows])) if rows else None,
               mean_epistemic_share=float(np.mean([r["epistemic_share"] for r in rows])) if rows else None,
               runtime_s=round(time.time()-t0,1))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(out, open(args.out,"w"), indent=1)
    print("gate_passed:", out["gate_passed"], "mean DTI", out["mean_dti"], "mean random", out["mean_random"])
    print("wrote", args.out)

if __name__ == "__main__":
    main()
