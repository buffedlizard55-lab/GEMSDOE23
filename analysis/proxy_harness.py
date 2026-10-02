#!/usr/bin/env python3
"""Which offline truth proxy ranks the 24 live-scored artefacts correctly?

For a template T (a real raster of fault pixels, catalogue pixels removed) the official
metric applied offline gives
    TP_i = |T| * mean_{g in T} env_i(g)
    FP_i = sum_{x:p_i>0, x not catalogued} (1 - env_T(x))
    DTI_proxy_i = TP / (TP + 0.2 FP + 0.8 (|T| - TP))
Spearman rho against the live public score tells us which proxy is safe to use for
model/budget selection.  A proxy that does not correlate must not be used to spend a slot.
"""
from __future__ import annotations
import json, os
import numpy as np, rasterio
from scipy.ndimage import distance_transform_edt
from scipy.stats import spearmanr

DATA='data'; ANCH='.cache/sib/anchors'; R=300.0; PX=100.0
with rasterio.open(f'{DATA}/sample_submission.tif') as d: tmpl=d.read(1)
foot=np.isfinite(tmpl); cat=foot&(tmpl==1); dom=foot&~cat
d_cat=distance_transform_edt(~cat,sampling=(PX,PX)).astype(np.float32)
with rasterio.open(f'{DATA}/external/derived_sgmc_faults_100m_u8.tif') as d: sgmc=(d.read(1)>0)&foot

T={}
T['sgmc_all']=sgmc&dom
T['sgmc_gap_strict']=sgmc&dom
T['sgmc_gap_d3']=sgmc&dom&(d_cat>300)
T['sgmc_gap_d5']=sgmc&dom&(d_cat>500)
T['sgmc_gap_d10']=sgmc&dom&(d_cat>1000)
T['sgmc_gap_d20']=sgmc&dom&(d_cat>2000)
T['catalogue']=cat
# thinned sgmc gap (1-px skeleton-ish: local maxima of distance along the trace is expensive; use every pixel)
meta=json.load(open(f'{ANCH}/manifest.json'))
preds={}
for m in meta:
    with rasterio.open(os.path.join(ANCH,m['id']+'.tif')) as d: p=d.read(1).astype(np.float32)
    p=np.where(dom,np.nan_to_num(p,nan=0.0),0.0)
    mask=p>0
    dE=distance_transform_edt(~mask,sampling=(PX,PX))
    preds[m['id']]=dict(lb=m['lb'],env=np.clip(1.0-dE/R,0,1).astype(np.float32),mask=mask,A=float(p.sum()))
    del p,dE
ids=list(preds)
out={}
for tn,Tm in T.items():
    nt=int(Tm.sum())
    if nt<500: continue
    dT=distance_transform_edt(~Tm,sampling=(PX,PX))
    envT=np.clip(1.0-dT/R,0,1).astype(np.float32)
    dt=[]
    for i in ids:
        v=preds[i]
        tp=nt*float(v['env'][Tm].mean())
        fp=float((1.0-envT[v['mask']]).sum())
        d=tp/(tp+0.2*fp+0.8*(nt-tp)+1e-12)
        dt.append(d)
    rho,p=spearmanr(dt,[preds[i]['lb'] for i in ids])
    out[tn]=dict(n_truth=nt,proxy_dti=dict(zip(ids,[float(x) for x in dt])),spearman_rho=float(rho),p=float(p))
    print(f"{tn:18s} |T|={nt:7d} rho={rho:+.3f} p={p:.4f}  (best proxy {max(dt):.3f})")
json.dump(out,open('analysis/proxy_harness.json','w'),indent=1)
best=max(out,key=lambda k:out[k]['spearman_rho'])
print('\nbest proxy:',best)
for i in sorted(ids,key=lambda i:-preds[i]['lb']):
    print(f"  {i:24s} live={preds[i]['lb']:.4f} proxy={out[best]['proxy_dti'][i]:.4f}")
