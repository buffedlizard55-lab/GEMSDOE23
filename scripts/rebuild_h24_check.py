#!/usr/bin/env python3
"""Reproduce the shipped H24 emission from public inputs and report any difference.

    python scripts/rebuild_h24_check.py [--model docs/data/habitat-model.json] [--shipped <nan.tif>]

Steps (exactly those of scripts/build_submission_live.py with the deep-ensemble term excluded, because the
ensemble failed its admission gate):  habitat score from the committed layer list and weights ->
votes from the nine family-representative artefacts -> S = 0.625 rank(H) + 0.375 rank(V) -> greedy
non-maximum suppression at 400 m for the committed budget.  Also writes the three component maps
(outputs/h24_H.npy, h24_V.npy, h24_S.npy) so the audit can localise any artefact to a component.
"""
import argparse, importlib.util, json, os, sys, time
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import rasterio
from gems.layers import iter_layers, load_domain
from gems.habitat import habitat_score
from gems.emission import disperse_select


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_live", os.path.join(ROOT, "scripts", "build_submission_live.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(ROOT, "docs/data/habitat-model.json"))
    ap.add_argument("--shipped", default=os.path.join(ROOT, "docs/downloads/gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif"))
    ap.add_argument("--budget", type=int, default=100_000)
    ap.add_argument("--out", default=os.path.join(ROOT, "outputs"))
    args = ap.parse_args()
    t0 = time.time()
    os.chdir(ROOT)
    hm = json.load(open(args.model))
    names, beta = hm["selected_layers"], hm["beta"]
    bases = [hm["layer_bases"][n] for n in names]
    _, _, domain, _ = load_domain()
    want, picked = set(names), {}
    for nm, layer in iter_layers():
        if nm in want:
            picked[nm] = layer
            if len(picked) == len(want):
                break
    print(f"[{time.time()-t0:5.0f}s] layers rebuilt: {sorted(picked)}")
    H = habitat_score(picked, names, beta, bases, domain)
    bl = load_build_module()
    V, vdetail = bl.votes_map(domain)
    w = dict(habitat=0.5 / 0.8, votes=0.3 / 0.8)
    S = w["habitat"] * bl.rank01(np.where(np.isfinite(H), H, 0.0), domain) + w["votes"] * bl.rank01(V, domain)
    S[~domain] = -np.inf
    mask = disperse_select(S, domain, args.budget, bl.R_MIN_PX)
    os.makedirs(args.out, exist_ok=True)
    np.save(os.path.join(args.out, "h24_H.npy"), H.astype(np.float32))
    np.save(os.path.join(args.out, "h24_V.npy"), V.astype(np.float32))
    np.save(os.path.join(args.out, "h24_S.npy"), S.astype(np.float32))
    np.save(os.path.join(args.out, "h24_mask_rebuilt.npy"), mask)
    with rasterio.open(args.shipped) as s:
        ship = np.nan_to_num(s.read(1), nan=0.0) > 0
    inter = int((mask & ship).sum())
    rep = dict(n_rebuilt=int(mask.sum()), n_shipped=int(ship.sum()), identical=bool(np.array_equal(mask, ship)),
               overlap=inter, only_rebuilt=int((mask & ~ship).sum()), only_shipped=int((ship & ~mask).sum()),
               layers=names, family_skill={k: round(v["skill"], 3) for k, v in vdetail.items()})
    print(json.dumps(rep, indent=1))
    json.dump(rep, open(os.path.join(args.out, "h24_rebuild_report.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
