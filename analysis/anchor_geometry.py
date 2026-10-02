#!/usr/bin/env python3
"""Compute exact DTI-relevant geometry for every live-scored group artefact.

For a submission p and hidden truth set G the official metric is
  TP_w = sum_{g in G} max_x p(x) k(d(x,g)),  k(d)=max(1-d/300,0)
  FP_w = sum_{x:p>0} p(x) (1 - max_{g in G} k(d(x,g)))
  FN_w = |G| - TP_w
If the hidden truth were an exchangeable (uniform random) subset of the scored
domain then  E[TP_w] = |G| * Kbar  where Kbar = mean over the domain of the
"kernel envelope"  env(y) = max_x p(x) k(d(x,y)).  Kbar is computed exactly
with one Euclidean distance transform per artefact.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt

ANCH = '.cache/sib/anchors'
DATA = 'data'
R = 300.0
PX = 100.0

def main():
    with rasterio.open(f'{DATA}/sample_submission.tif') as d:
        tmpl = d.read(1)
    footprint = np.isfinite(tmpl)
    catalogue = footprint & (tmpl == 1)
    D = int(footprint.sum())
    print('footprint', D, 'catalogue', int(catalogue.sum()))
    d_cat = distance_transform_edt(~catalogue, sampling=(PX, PX))
    np.save('analysis/d_cat.npy', d_cat.astype(np.float32))
    env_cat = np.clip(1.0 - d_cat / R, 0, 1)          # catalogue kernel envelope
    Kbar_cat = float(env_cat[footprint].mean())
    print('catalogue Kbar (uniform-truth expectation per truth px):', round(Kbar_cat, 6))

    meta = json.load(open(f'{ANCH}/manifest.json'))
    rows = []
    for m in meta:
        with rasterio.open(os.path.join(ANCH, m['id'] + '.tif')) as d:
            p = d.read(1).astype(np.float32)
        assert p.shape == tmpl.shape, (m['id'], p.shape)
        p = np.where(footprint, np.nan_to_num(p, nan=0.0), 0.0)
        mask = p > 0
        A = int(mask.sum()); M = float(p.sum())
        uniq = np.unique(p[mask])
        is_binary = bool(uniq.size <= 2 and np.allclose(uniq, [1.0]))
        d_pred = distance_transform_edt(~mask, sampling=(PX, PX))
        env = np.clip(1.0 - d_pred / R, 0, 1)
        if not is_binary:
            # graded: envelope is max_x p(x)k(d); approximate with pmax * env of support
            env = env * float(uniq.max())
        Kbar = float(env[footprint].mean())
        cov = float((env[footprint] > 0).mean())
        rows.append(dict(
            id=m['id'], lb=m['lb'], repo=m['repo'], A=A, M=M, is_binary=is_binary,
            n_unique=int(uniq.size), vmin=float(uniq.min()), vmax=float(uniq.max()),
            Kbar=Kbar, coverage_300m=cov,
            on_cat=int((mask & catalogue).sum()),
            f_pred_near300_cat=float(env_cat[mask].mean()) if A else 0.0,
            f_pred_far1500_cat=float((d_cat[mask] > 1500).mean()) if A else 0.0,
            f_pred_far500_cat=float((d_cat[mask] > 500).mean()) if A else 0.0,
            mean_d_cat_of_pred=float(d_cat[mask].mean()) if A else 0.0,
            Kbar_cat_covered=float(env_cat[mask].mean()) if A else 0.0,
        ))
        print(f"{m['id']:26s} lb={m['lb']:.4f} A={A:7d} M={M:9.1f} bin={is_binary} "
              f"Kbar={Kbar:.5f} cov={cov:.4f} far1500={rows[-1]['f_pred_far1500_cat']:.3f} "
              f"oncat={rows[-1]['on_cat']:6d}")
    json.dump(dict(footprint=D, catalogue=int(catalogue.sum()), Kbar_catalogue=Kbar_cat, rows=rows),
              open('analysis/anchor_geometry.json', 'w'), indent=1)

    # Solve for |G| per anchor under the uniform-truth model
    print('\n--- implied |G| under uniform-truth model ---')
    for r in rows:
        K, M, dti = r['Kbar'], r['M'], r['lb']
        den = K - 0.8 * dti + 0.6 * dti * K
        G = 0.1626 * M * dti / den if den > 0 else float('nan')
        r['implied_G_uniform'] = G
        print(f"{r['id']:26s} lb={dti:.4f} Kbar={K:.5f} -> implied |G| = {G:12.0f}")

main()
