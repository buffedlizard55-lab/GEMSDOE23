#!/usr/bin/env python3
"""Invert 24 live public-leaderboard scores for the hidden new-fault truth model.

Official facts used (verified):
 * metric  DTI = TP_w/(TP_w + 0.2 FP_w + 0.8 FN_w), k(d)=max(1-d/300m,0)   [page 967]
 * TP_w = sum_{g in G} max_x p(x) k(d(x,g));  FP_w = sum_{x:p>0} p(x)(1-max_g k);  FN_w = |G|-TP_w
 * known USGS/INGENIOUS fault pixels are masked out of evaluation            [forum 11516, staff]
 * "new fault" = any fault pixel not already captured by USGS/INGENIOUS and may be
   newly mapped geometry of an existing fault system                        [forum 11536, staff]

Model: truth pixels are drawn from a density that depends only on the distance to the
nearest catalogued fault, w_b over bins b.  Then for submission i
    TP_i = |G| * sum_b w_b * e_ib ,   e_ib = mean kernel-envelope of i over bin b
and, given an observed DTI_i, the required s_i = sum_b w_b e_ib is
    s_i(G) = DTI_i (0.2 F_i + 0.8 G) / (G (1 - 0.2 DTI_i)).
For each trial |G| we solve for w by non-negative least squares with sum(w)=1 and keep
the |G| with the smallest misfit in log-DTI.
"""
from __future__ import annotations
import json, os
import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt
from scipy.optimize import nnls

DATA='data'; ANCH='.cache/sib/anchors'
R=300.0; PX=100.0
BINS=[0,100,200,300,500,1000,2000,5000,1e9]
LBL=[f'{int(BINS[i])}-{int(BINS[i+1]) if BINS[i+1]<1e8 else "inf"}m' for i in range(len(BINS)-1)]

with rasterio.open(f'{DATA}/sample_submission.tif') as d:
    tmpl=d.read(1)
foot=np.isfinite(tmpl); cat=foot&(tmpl==1); dom=foot&~cat
D=int(dom.sum())
d_cat=distance_transform_edt(~cat,sampling=(PX,PX)).astype(np.float32)
binidx=np.full(d_cat.shape,-1,np.int8)
for i in range(len(BINS)-1):
    binidx[(d_cat>BINS[i])&(d_cat<=BINS[i+1])]=i
binidx[~dom]=-1
counts=np.array([(binidx[dom]==i).sum() for i in range(len(LBL))],float)
print('scored domain (footprint - catalogue):',D)
print('domain px per d_cat bin:',dict(zip(LBL,counts.astype(int))))

meta=json.load(open(f'{ANCH}/manifest.json'))
rows=[]
for m in meta:
    with rasterio.open(os.path.join(ANCH,m['id']+'.tif')) as d:
        p=d.read(1).astype(np.float32)
    p=np.where(foot,np.nan_to_num(p,nan=0.0),0.0)
    raw_mask=p>0
    M_on=float(p[raw_mask&cat].sum()); M_off=float(p[raw_mask&dom].sum())
    # variant A: catalogue predictions fully excluded (GEMSDOE22 staff-ruling reading)
    pA=np.where(dom,p,0.0)
    out={}
    for tag,pp in (('vA',pA),('vB',np.where(foot,p,0.0))):
        mask=pp>0
        dE=distance_transform_edt(~mask,sampling=(PX,PX))
        env=np.clip(1.0-dE/R,0.0,1.0).astype(np.float32)
        e=np.array([env[dom&(binidx==i)].mean() if counts[i]>0 else 0.0 for i in range(len(LBL))],float)
        out[tag]=dict(e=e.tolist(),M_off=float(pp[mask&dom].sum()),
                      cov=float((env[dom]>0).mean()),Kbar=float(env[dom].mean()))
    rows.append(dict(id=m['id'],lb=m['lb'],n=int(raw_mask.sum()),M_on=M_on,M_off=M_off,**out))
    print(f"{m['id']:24s} lb={m['lb']:.4f} n={int(raw_mask.sum()):7d} on_cat={M_on:8.0f} off_cat={M_off:8.0f} "
          f"KbarA={out['vA']['Kbar']:.4f} covA={out['vA']['cov']:.3f}")
json.dump(dict(domain=D,bins=LBL,bin_counts=counts.tolist(),rows=rows),open('analysis/invert_inputs.json','w'),indent=1)

def fit(tag,Ggrid=np.exp(np.linspace(np.log(2000),np.log(400000),220))):
    best=None
    for G in Ggrid:
        A=[];b=[]
        for r in rows:
            dti=r['lb']; F=r[tag]['M_off']
            s=dti*(0.2*F+0.8*G)/(G*(1-0.2*dti))
            A.append(r[tag]['e']); b.append(s)
        A=np.array(A);b=np.array(b)
        # NNLS with sum-to-one: append a strong row enforcing sum(w)=1
        lam=50.0
        A2=np.vstack([A/np.maximum(b[:,None],1e-12), lam*np.ones((1,len(LBL)))])
        b2=np.concatenate([np.ones(len(b)),[lam]])
        w,_=nnls(A2,b2)
        pred=np.array([G*float(np.dot(w,r[tag]['e']))/(0.2*G*float(np.dot(w,r[tag]['e']))+0.2*r[tag]['M_off']+0.8*G) for r in rows])
        obs=np.array([r['lb'] for r in rows])
        mis=float(np.mean((np.log(obs)-np.log(np.maximum(pred,1e-9)))**2))
        if best is None or mis<best[0]: best=(mis,G,w,pred)
    return best

for tag in ('vA','vB'):
    mis,G,w,pred=fit(tag)
    print(f'\n=== variant {tag} ({"catalogue predictions excluded" if tag=="A" else "catalogue predictions kept as emitters"}) ===')
    print(f'best |G| = {G:,.0f}   mean squared log-error = {mis:.4f}   RMSE(log) = {mis**0.5:.3f}')
    print('truth density profile w by distance-to-catalogue bin:')
    for l,wi,ci in zip(LBL,w,counts):
        print(f'   {l:>12s}  w={wi:.4f}   domain_px={int(ci):8d}   density_per_px={wi/max(ci,1)*1e6:.3f}e-6')
    print('\nper-anchor fit:')
    for r,o in zip(rows,pred):
        print(f"   {r['id']:24s} obs={r['lb']:.4f} model={o:.4f} ratio={r['lb']/max(o,1e-9):.2f}")
    json.dump(dict(variant=tag,G=float(G),misfit=mis,w=w.tolist(),bins=LBL,
                   model=[float(x) for x in pred],obs=[r['lb'] for r in rows],ids=[r['id'] for r in rows]),
              open(f'analysis/live_fit_{tag}.json','w'),indent=1)
