#!/usr/bin/env python3
"""Train the deep ensemble, decompose its uncertainty and write the evidence records.

    python scripts/run_ensemble.py --out docs/data/ensemble-report.json

Honest out-of-fold design: 5 column-strip folds with a 1,500 m buffer removed from
training; 3 independently initialised and independently trained members per fold give an
out-of-fold ensemble prediction and therefore an out-of-fold epistemic/aleatoric split.
5 further members trained on every fold produce the full-domain map that is submitted.
"""
from __future__ import annotations
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from gems.ensemble import (EnsembleConfig, blocked_folds, decompose, predict_members, train_member, _buffered)
from gems.layers import load_domain
from gems.metric import distance_weighted_tversky

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cube", default="outputs/feature_cube.npy")
    ap.add_argument("--out", default="docs/data/ensemble-report.json")
    ap.add_argument("--members-dir", default="outputs/ensemble")
    ap.add_argument("--quick", action="store_true", help="fewer patches/epochs (smoke test)")
    args = ap.parse_args()
    cfg = EnsembleConfig()
    if args.quick:
        cfg.patches_per_epoch = 128; cfg.epochs = 2; cfg.n_members_oof = 2; cfg.n_members_full = 2
    t0 = time.time()
    def log(*a): print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)

    footprint, catalogue, domain, _ = load_domain()
    cube = np.load(args.cube, mmap_mode="r")
    from gems.featurecube import load_target
    target, tinfo = load_target()
    log("cube", cube.shape, "target px", int(target.sum()), tinfo["target_frac_of_domain"])

    folds = blocked_folds(target.shape, cfg.n_folds, cfg.spatial_buffer_px)
    os.makedirs(args.members_dir, exist_ok=True)
    oof_mean = np.zeros(target.shape, np.float32)
    oof_epi = np.zeros(target.shape, np.float32)
    oof_ale = np.zeros(target.shape, np.float32)
    oof_cov = np.zeros(target.shape, np.int8)
    fold_reports = []
    for fi, fold in enumerate(folds):
        holdout = fold & domain
        train = domain & ~_buffered(fold, cfg.spatial_buffer_px)
        rng = np.random.default_rng(cfg.seed_base + fi)
        members = []
        for m in range(cfg.n_members_oof):
            seed = int(rng.integers(0, 2**31 - 1))
            log(f"fold {fi} member {m} seed {seed} (train px {int(train.sum()):,})")
            members.append(train_member(cube, target, train, seed, cfg, log=log))
        probs = predict_members(members, np.asarray(cube), holdout, cfg)
        dec = decompose(probs)
        oof_mean[holdout] = dec["mean"][holdout]; oof_epi[holdout] = dec["epistemic"][holdout]
        oof_ale[holdout] = dec["aleatoric"][holdout]; oof_cov[holdout] = 1
        # honest out-of-fold DTI on this fold's target pixels
        truth = (target & holdout)
        pred = np.clip(dec["mean"], 0, 1)
        res = distance_weighted_tversky(pred, truth, mask=holdout) if truth.any() else dict(dti=float("nan"))
        # and the DTI of the binary top-k emission at the fold's operating budget
        k = int(round(0.0122 * holdout.sum()))
        thr = float(np.quantile(pred[holdout], 1 - k / max(1, int(holdout.sum()))))
        emis = (pred >= thr) & holdout
        res_topk = distance_weighted_tversky(emis.astype(np.float32), truth, mask=holdout) if truth.any() else {}
        fold_reports.append(dict(fold=fi, train_px=int(train.sum()), holdout_px=int(holdout.sum()),
                                 target_px=int(truth.sum()), members=cfg.n_members_oof,
                                 dti_prob=float(res.get("dti", float("nan"))),
                                 dti_topk=float(res_topk.get("dti", float("nan"))),
                                 topk_px=int(emis.sum()),
                                 mean_epistemic=float(dec["epistemic"][holdout].mean()),
                                 mean_aleatoric=float(dec["aleatoric"][holdout].mean()),
                                 mean_prob=float(dec["mean"][holdout].mean())))
        log(f"fold {fi} OOF DTI(prob)={fold_reports[-1]['dti_prob']:.4f} DTI(top-{k})={fold_reports[-1]['dti_topk']:.4f}")
        del members, probs

    log("training the full-domain ensemble")
    full_members = []
    rng = np.random.default_rng(cfg.seed_base + 999)
    for m in range(cfg.n_members_full):
        seed = int(rng.integers(0, 2**31 - 1))
        log(f"full member {m} seed {seed}")
        full_members.append(train_member(cube, target, domain, seed, cfg, log=log))
    fprobs = predict_members(full_members, np.asarray(cube), domain, cfg)
    fdec = decompose(fprobs)
    np.save("outputs/oof_mean.npy", oof_mean); np.save("outputs/oof_epistemic.npy", oof_epi)
    np.save("outputs/oof_aleatoric.npy", oof_ale); np.save("outputs/oof_covered.npy", oof_cov)
    np.save("outputs/full_mean.npy", fdec["mean"]); np.save("outputs/full_epistemic.npy", fdec["epistemic"])
    np.save("outputs/full_aleatoric.npy", fdec["aleatoric"]); np.save("outputs/full_member_probs.npy", fprobs)
    rep = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               config=cfg.__dict__, target=tinfo, folds=fold_reports,
               full_domain=dict(mean_prob=float(fdec["mean"][domain].mean()),
                                mean_epistemic=float(fdec["epistemic"][domain].mean()),
                                mean_aleatoric=float(fdec["aleatoric"][domain].mean()),
                                epistemic_share_of_total=float(fdec["epistemic"][domain].sum() /
                                                               max(1e-12, float((fdec["epistemic"] + fdec["aleatoric"])[domain].sum()))),
                                member_seeds=[m.seed for m in full_members]),
               runtime_s=round(time.time() - t0, 1),
               identity="Var(Y)=E_m[p_m(1-p_m)] + Var_m(p_m); epistemic uses ddof=0 across members",
               reference="Lakshminarayanan, Pritzel & Blundell, NeurIPS 2017 (deep ensembles)")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(rep, open(args.out, "w"), indent=1)
    log("wrote", args.out)

if __name__ == "__main__":
    main()
