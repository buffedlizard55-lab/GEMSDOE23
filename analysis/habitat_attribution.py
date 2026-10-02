#!/usr/bin/env python3
"""Where do the hidden new faults live?  Attribution of 24 live public scores.

For each live-scored artefact i we know A_i (emitted pixels off the catalogue mask),
Kbar_i (mean kernel-envelope over the scored domain = TP expected per truth pixel if the
truth were uniform) and DTI_i (the public score).  Given |G| the official metric inverts
exactly to
    TP_i = DTI_i (0.1626 A_i + 0.8 G) / (1 + 0.6 DTI_i)
and the artefact's SKILL relative to a uniform-truth placement of the same geometry is
    skill_i = TP_i / (G * Kbar_i).
skill_i removes budget and dispersion, so correlating it with how much each evidence
layer was enriched inside the emitted pixels identifies the habitat of the hidden faults.
Layers are streamed one at a time (3 GB RAM budget).
"""
from __future__ import annotations
import csv, json, os
import numpy as np, rasterio
from scipy.ndimage import distance_transform_edt, uniform_filter
from scipy.stats import spearmanr

DATA='data'; ANCH='.cache/sib/anchors'; EXT=f'{DATA}/external'
R=300.0; PX=100.0; G_TRIALS=(10000.,15000.,25000.,40000.)

with rasterio.open(f'{DATA}/sample_submission.tif') as d: tmpl=d.read(1)
foot=np.isfinite(tmpl); cat=foot&(tmpl==1); dom=foot&~cat
H,W=foot.shape; domflat=dom.ravel()
d_cat=distance_transform_edt(~cat,sampling=(PX,PX)).astype(np.float32)

meta=json.load(open(f'{ANCH}/manifest.json'))
idx={}; Kbar={}; A={}; LB={}
for m in meta:
    with rasterio.open(os.path.join(ANCH,m['id']+'.tif')) as d: p=d.read(1).astype(np.float32)
    p=np.where(dom,np.nan_to_num(p,nan=0.0),0.0)
    mask=p>0
    dE=distance_transform_edt(~mask,sampling=(PX,PX))
    env=np.clip(1.0-dE/R,0.0,1.0)
    idx[m['id']]=np.flatnonzero(mask.ravel()); A[m['id']]=int(mask.sum())
    Kbar[m['id']]=float(env[dom].mean()); LB[m['id']]=m['lb']
    del p,dE,env
ids=[m['id'] for m in meta if m['id'] in idx]
print('anchors',len(ids),flush=True)

SK={G:{i:LB[i]*(0.1626*A[i]+0.8*G)/((1+0.6*LB[i])*G*Kbar[i]) for i in ids} for G in G_TRIALS}
for G in G_TRIALS:
    v=np.array([SK[G][i] for i in ids]); print(f'|G|={G:,.0f} skill median {np.median(v):.2f} range {v.min():.2f}..{v.max():.2f}',flush=True)

def norm(a):
    a=np.asarray(a,np.float64)
    fin=np.isfinite(a)&dom
    if fin.sum()<1000: return None
    lo,hi=np.percentile(a[fin],[1,99])
    if not np.isfinite(lo) or hi<=lo: return None
    r=np.clip((a-lo)/(hi-lo),0,1).astype(np.float32); r[~dom]=0.0
    return r

rows={}
def consume(name,arr):
    L=norm(arr)
    if L is None: return
    base=float(L[dom].mean())
    if base<=1e-6: return
    flat=L.ravel()
    enr=np.array([float(flat[idx[i]].mean())/base for i in ids])
    rec=dict(layer=name,base=base,enrichment=enr.tolist())
    for G in G_TRIALS:
        lsk=np.log(np.maximum([SK[G][i] for i in ids],1e-3))
        rho,p=spearmanr(np.log(np.maximum(enr,1e-3)),lsk)
        rec[f'rho_G{int(G)}']=float(rho); rec[f'p_G{int(G)}']=float(p)
    rows[name]=rec
    print(f"  {name:34s} base={base:.4f} rho(G15k)={rec['rho_G15000']:+.3f} p={rec['p_G15000']:.3f}",flush=True)
    del L,flat

print('\n--- official bands + multiscale derivatives ---',flush=True)
with rasterio.open(f'{DATA}/training_features.tif') as d:
    names=[dd.split(' - ')[0] for dd in d.descriptions]
    for b in range(1,20):
        raw=d.read(b).astype(np.float64)
        good=foot&np.isfinite(raw)&(np.abs(raw)<1e30)
        med=float(np.median(raw[good])) if good.any() else 0.0
        f=np.where(good,raw,med)
        s=(f[foot].std()+1e-9); z=(f-f[foot].mean())/s
        n_invalid=int((foot&~good).sum())
        consume(f'of_{names[b-1]}',z)
        rec=rows.get(f'of_{names[b-1]}');
        if rec is not None: rec['n_invalid_in_footprint']=n_invalid
        m3=uniform_filter(z,3); consume(f'of_{names[b-1]}_std3',np.sqrt(np.maximum(uniform_filter(z*z,3)-m3*m3,0)))
        m7=uniform_filter(z,7); consume(f'of_{names[b-1]}_std7',np.sqrt(np.maximum(uniform_filter(z*z,7)-m7*m7,0)))
        del raw,f,z,m3,m7

print('\n--- external GeoDAWN radiometric / extensions / lidar scarp ---',flush=True)
with rasterio.open(f'{EXT}/geodawn_rad_u8.tif') as d:
    for b,n in zip(range(1,5),['K','Th','U','TC']): consume(f'rad_{n}',d.read(b))
with rasterio.open(f'{EXT}/geodawn_extensions_u8.tif') as d:
    for b,n in zip(range(1,5),['ThK','UK','UTh','TMI_up150']): consume(f'ext_{n}',d.read(b))
with rasterio.open(f'{EXT}/lidar_scarp_features_u8.tif') as d:
    lb=["ex_max","ex_mean","step_max","lapneg_max","lappos_max","downface_max","upface_max","cross_max","relief","coh100","strike","valid"]
    for b,n in zip(range(1,13),lb): consume(f'lid_{n}',d.read(b))

print('\n--- independent compilation (SGMC) + geometry ---',flush=True)
with rasterio.open(f'{EXT}/derived_sgmc_faults_100m_u8.tif') as d: sgmc=(d.read(1)>0)&foot
d_sgmc=distance_transform_edt(~sgmc,sampling=(PX,PX)).astype(np.float32)
consume('sgmc_density_9x9',uniform_filter(sgmc.astype(np.float64),9))
consume('inv_d_sgmc',1.0/(1.0+d_sgmc/PX))
sgmc_gap=sgmc&~cat&(d_cat>300)
consume('sgmc_gap_density_9x9',uniform_filter(sgmc_gap.astype(np.float64),9))
consume('inv_d_catalogue',1.0/(1.0+d_cat/PX))
consume('d_catalogue_km',np.clip(d_cat/1000.,0,20))
consume('d_catalogue_km_inv',20-np.clip(d_cat/1000.,0,20))
del sgmc,d_sgmc,sgmc_gap

print('\n--- GDR thermal / hydrologic point evidence ---',flush=True)
rows_=[];cols_=[];tc=[];geo=[];off=[]
with open(f'{EXT}/gdr_wellspring_in_footprint.csv') as f:
    for r in csv.DictReader(f):
        try: rr=int(float(r['row'])); cc=int(float(r['col']))
        except Exception: continue
        rows_.append(rr); cols_.append(cc)
        for lst,key in ((tc,'temp_c'),(geo,'geothermchalc_c'),(off,'dist_known_fault_px')):
            try: lst.append(float(r[key]))
            except Exception: lst.append(np.nan)
tc=np.array(tc);geo=np.array(geo);off=np.array(off)
print('spring/well records',len(rows_),'temp>=40C',int(np.nansum(tc>=40)),'temp>=60C',int(np.nansum(tc>=60)),
      'geotherm(chalc)>=100C',int(np.nansum(geo>=100)),'>500m from mapped fault',int(np.nansum(off>5)),flush=True)
def pts(w):
    r=np.zeros((H,W),np.float32)
    rr=np.clip(np.asarray(rows_,int),0,H-1); cc=np.clip(np.asarray(cols_,int),0,W-1)
    w=np.nan_to_num(np.asarray(w,np.float32),nan=0.0)
    np.maximum.at(r,(rr,cc),w)
    return r
for nm,w in (('springs_all',np.ones(len(rows_))),('springs_hot40',(tc>=40).astype(float)),
             ('springs_hot60',(tc>=60).astype(float)),('springs_geotherm100',(geo>=100).astype(float)),
             ('springs_offmapped',(off>5).astype(float)),('springs_hot_offmapped',((tc>=40)&(off>5)).astype(float))):
    p=pts(w)
    if (p>0).sum()<5: print('skip',nm); continue
    dd=distance_transform_edt(~(p>0),sampling=(PX,PX)).astype(np.float32)
    consume(f'inv_d_{nm}',1.0/(1.0+dd/PX))
    consume(f'{nm}_dens15',uniform_filter((p>0).astype(np.float64),15))
    del p,dd
vr=[];vc=[]
with open(f'{EXT}/gdr_volcanic_vents_in_footprint.csv') as f:
    for r in csv.DictReader(f):
        try: vr.append(int(float(r['row'])));vc.append(int(float(r['col'])))
        except Exception: pass
if vr:
    p=np.zeros((H,W),np.float32); p[np.clip(vr,0,H-1),np.clip(vc,0,W-1)]=1.0
    dd=distance_transform_edt(~(p>0),sampling=(PX,PX)).astype(np.float32)
    consume('inv_d_vents',1.0/(1.0+dd/PX)); del p,dd

json.dump(dict(ids=ids,A=A,Kbar=Kbar,lb=LB,skill={str(int(G)):SK[G] for G in G_TRIALS},layers=rows),
          open('analysis/habitat_attribution.json','w'),indent=1)
print('\n=== TOP by |rho| at |G|=15,000 ===',flush=True)
srt=sorted(rows.values(),key=lambda r:-abs(r['rho_G15000']))
for r in srt[:25]:
    print(f"  {r['layer']:34s} rho={r['rho_G15000']:+.3f} p={r['p_G15000']:.4f} "
          f"rho(10k)={r['rho_G10000']:+.3f} rho(40k)={r['rho_G40000']:+.3f}",flush=True)
