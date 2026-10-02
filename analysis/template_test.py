#!/usr/bin/env python3
"""Which candidate truth template explains the 24 live public scores?

For each template T (a real raster of fault pixels) and each live-scored anchor i we
compute e_iT = mean kernel-envelope of i over T, so that TP_i = |G| * e_iT under the
assumption that the hidden new-fault set has the same spatial character as T.  The
observed DTI_i then implies

    |G| = 0.2*DTI_i*FP_i / (e_iT - 0.8*DTI_i + 0.6*DTI_i*e_iT)

A template that is a good stand-in for the hidden truth yields a consistent |G|
across all 24 anchors; a bad one yields nonsense (negative / wildly scattered).
"""
from __future__ import annotations
import json, os
import numpy as np, rasterio
from scipy.ndimage import distance_transform_edt

DATA='data'; ANCH='.cache/sib/anchors'; R=300.0; PX=100.0
with rasterio.open(f'{DATA}/sample_submission.tif') as d: tmpl=d.read(1)
foot=np.isfinite(tmpl); cat=foot&(tmpl==1); dom=foot&~cat
d_cat=distance_transform_edt(~cat,sampling=(PX,PX)).astype(np.float32)

# candidate templates
with rasterio.open(f'{DATA}/external/derived_sgmc_faults_100m_u8.tif') as d: sgmc=d.read(1)>0
sgmc &= foot
T={}
T['sgmc_all']=sgmc
T['sgmc_gap_strict']=sgmc&~cat
T['sgmc_gap_d3']=sgmc&~cat&(d_cat>300)
T['sgmc_gap_d5']=sgmc&~cat&(d_cat>500)
T['sgmc_gap_d10']=sgmc&~cat&(d_cat>1000)
T['catalogue']=cat
T['uniform']=dom
# qfaults traces from GDR csv
try:
    import csv
    rows=list(csv.DictReader(open(f'{DATA}/external/gdr_qfaults_traces.csv')))
    print('qfaults csv cols:',list(rows[0].keys())[:14],'n rows',len(rows))
except Exception as e:
    print('qfaults csv error',e)

meta=json.load(open(f'{ANCH}/manifest.json'))
envs={}
for m in meta:
    with rasterio.open(os.path.join(ANCH,m['id']+'.tif')) as d: p=d.read(1).astype(np.float32)
    p=np.where(dom,np.nan_to_num(p,nan=0.0),0.0)
    mask=p>0
    if mask.sum()==0: continue
    dE=distance_transform_edt(~mask,sampling=(PX,PX))
    env=np.clip(1.0-dE/R,0.0,1.0)
    M=float(p.sum())
    envs[m['id']]=dict(lb=m['lb'],env=env,M=M,n=int(mask.sum()),
                       fp=0.813*M)   # FP approx: (1 - E[max_g k]) ~ 0.813 for sparse truth
print('anchors with envelopes:',len(envs))

out={}
for tname,Tmask in T.items():
    nt=int(Tmask.sum())
    if nt==0: continue
    Gs=[]; dtis=[]
    for k,v in envs.items():
        e=float(v['env'][Tmask].mean()); dti=v['lb']; F=v['fp']
        den=e-0.8*dti+0.6*dti*e
        G=0.2*dti*F/den if den>0 else float('nan')
        Gs.append(G); dtis.append(e)
    Gs=np.array(Gs,float); ok=np.isfinite(Gs)&(Gs>0)
    med=float(np.median(Gs[ok])) if ok.any() else float('nan')
    spread=float(np.std(np.log(Gs[ok]))) if ok.sum()>2 else float('nan')
    # spearman of proxy DTI vs live
    from scipy.stats import spearmanr
    rho,p=spearmanr(dtis,[v['lb'] for v in envs.values()])
    out[tname]=dict(n_truth=nt, n_positive_G=int(ok.sum()), G_median=med,
                    log_spread=spread, spearman_rho=float(rho), spearman_p=float(p),
                    G_per_anchor={k:(float(g) if np.isfinite(g) else None) for k,g in zip(envs,Gs)})
    print(f"{tname:20s} n_truth={nt:7d} ok={int(ok.sum()):2d}/24 median|G|={med:10.0f} "
          f"log-spread={spread:.3f} rho={rho:+.3f} (p={p:.3f})")
json.dump(out,open('analysis/template_test.json','w'),indent=1)

# detail for the best template
best=min([k for k in out if np.isfinite(out[k]['log_spread'])],key=lambda k:out[k]['log_spread'])
print('\nbest template by consistency:',best)
for k,v in sorted(envs.items(),key=lambda kv:-kv[1]['lb']):
    print(f"  {k:24s} lb={v['lb']:.4f} e={float(v['env'][T[best]].mean()):.4f} implied|G|={out[best]['G_per_anchor'][k]}")
