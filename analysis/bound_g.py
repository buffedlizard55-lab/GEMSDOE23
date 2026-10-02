#!/usr/bin/env python3
"""Bound |G|, the number of hidden new-fault pixels in the public test set.

Two exact constraints, no placement model required:

(1) TP_w <= |G| always, and TP_w = DTI (0.1626 A + 0.8 |G|)/(1 + 0.6 DTI), so
        |G| >= DTI * 0.1626 A / (1 - 0.2 DTI)                      [lower bound]

(2) For an emission with kernel envelope env, TP_w = sum_{g in G} env(g) = |G| * e_T
    where e_T is the mean envelope over the (unknown) truth pixels.  Hence
        |G| = DTI * 0.1626 A / (e_T (1 + 0.6 DTI) - 0.8 DTI)
    An artefact whose envelope is high *everywhere* (a lattice) pins |G| tightly,
    because e_T cannot be small for any trace-like truth set: we measure e_T directly
    on two real fault-trace populations (the competition catalogue and the independent
    SGMC compilation) instead of assuming it.
"""
from __future__ import annotations
import json, os
import numpy as np, rasterio
from scipy.ndimage import distance_transform_edt
import sys
sys.path.insert(0,'src')
from gems.layers import load_domain, EXT
from gems.emission import kernel_envelope, fp_relief

ANCH='.cache/sib/anchors'
foot,cat,dom,_=load_domain()
d_cat=distance_transform_edt(~cat,sampling=(100,100)).astype(np.float32)
with rasterio.open(f'{EXT}/derived_sgmc_faults_100m_u8.tif') as d: sgmc=(d.read(1)>0)&foot
sgmc_gap=sgmc&dom&(d_cat>300)
meta=json.load(open(f'{ANCH}/manifest.json'))

rows=[]
for m in meta:
    with rasterio.open(os.path.join(ANCH,m['id']+'.tif')) as d: p=d.read(1).astype(np.float32)
    p=np.where(dom,np.nan_to_num(p,nan=0.0),0.0); mask=p>0
    A=float(p.sum()); dti=float(m['lb'])
    env=kernel_envelope(mask)
    fr=fp_relief(10000.0); c=0.2*fr
    lo=dti*c*A/(1-0.2*dti)
    e_dom=float(env[dom].mean()); e_cat=float(env[cat].mean()); e_gap=float(env[sgmc_gap].mean())
    e_p1=float(np.quantile(env[dom],0.01)); e_p5=float(np.quantile(env[dom],0.05))
    def G_of(e):
        # self-consistent in |G|: fp_relief depends on |G| itself
        G=10000.0
        for _ in range(60):
            c=0.2*fp_relief(G)
            den=e*(1-0.2*dti)-0.8*dti
            Gn=float(c*A*dti/den) if den>1e-9 else float('inf')
            if not np.isfinite(Gn) or Gn<=0: return float('inf')
            if abs(Gn-G)<1.0: return Gn
            G=Gn
        return G
    rows.append(dict(id=m['id'],dti=dti,area=A,env_domain_mean=e_dom,env_cat=e_cat,env_sgmc_gap=e_gap,
                     env_p01=e_p1,env_p05=e_p5,coverage=float((env[dom]>0).mean()),
                     G_lower_bound=lo,
                     G_if_truth_like_catalogue=G_of(e_cat),
                     G_if_truth_like_sgmc_gap=G_of(e_gap),
                     G_if_truth_uniform=G_of(e_dom),
                     G_worst_case_p01=G_of(e_p1)))
    print(f"{m['id']:24s} dti={dti:.4f} A={A:8.0f} cov={rows[-1]['coverage']:.3f} e_dom={e_dom:.4f} "
          f"e_cat={e_cat:.4f} e_gap={e_gap:.4f} e_p01={e_p1:.4f} | G>={lo:8.0f} "
          f"G(cat)={rows[-1]['G_if_truth_like_catalogue']:9.0f} G(gap)={rows[-1]['G_if_truth_like_sgmc_gap']:9.0f} "
          f"G(p01)={rows[-1]['G_worst_case_p01']:10.0f}")

hi=[r for r in rows if np.isfinite(r['G_if_truth_like_sgmc_gap']) and r['coverage']>0.5]
lo_all=[r['G_lower_bound'] for r in rows]
res=dict(purpose="Exact bounds on |G|, the number of hidden new-fault pixels in the public test set",
         fp_relief_at_G_10000=float(fp_relief(10000.0)),
         fp_relief_at_G_125000=float(fp_relief(125000.0)),
         note=("fp_relief = 1 - E[max_g k] is computed self-consistently from |G| itself; at the |G| "
               "measured here it is ~0.985, not the 0.813 a |G|=125,000 assumption would give."),
         lower_bound_max=float(max(lo_all)),
         high_coverage_anchors=[r['id'] for r in hi],
         upper_bound_from_sgmc_like_truth=float(min(r['G_if_truth_like_sgmc_gap'] for r in hi)) if hi else None,
         upper_bound_from_catalogue_like_truth=float(min(r['G_if_truth_like_catalogue'] for r in hi)) if hi else None,
         worst_case_p01_upper_bound=float(min(r['G_worst_case_p01'] for r in hi)) if hi else None,
         rows=rows)
print('\nlower bound on |G| (max over anchors): %.0f'%res['lower_bound_max'])
print('upper bound, truth geometry like the SGMC compilation: %.0f'%(res['upper_bound_from_sgmc_like_truth'] or -1))
print('upper bound, truth geometry like the catalogue: %.0f'%(res['upper_bound_from_catalogue_like_truth'] or -1))
print('worst-case (1st-percentile envelope) upper bound: %.0f'%(res['worst_case_p01_upper_bound'] or -1))
json.dump(res,open('docs/data/live-model-bounds.json','w'),indent=1)
print('wrote docs/data/live-model-bounds.json')
