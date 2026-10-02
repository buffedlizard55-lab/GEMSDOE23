#!/usr/bin/env python3
"""Audit predicted rasters with the regional fault-population statistics, then calibrate the audit.

    python scripts/audit_predictions.py                       # anchors + H24 + features -> docs/data/prediction-audit.json
    python scripts/audit_predictions.py --extra path1.tif ... # also audit other rasters (no live score)

What is computed for every raster (see src/gems/audit.py for the definitions):
  * arrangement: normalised correlation sum of the emitted pixels at 0.5-30 km against complete spatial
    randomness inside the footprint, and its log-divergence from the known catalogue measured the same way;
  * enrichment of the emission near long known faults (>= 3 km) by distance band;
  * dot / line structure and the share of isolated dots;
  * survey-line detector at the verified GeoDAWN geometry (400 m traverse lines along y, 4 km tie lines
    along x) and boundary-jump indices at the footprint edge, the 1 m lidar-validity edge and the
    Area 1 / Area 2 edge;
and then, across the live-scored artefacts, the Spearman correlation of each audit descriptor with the live
public DTI and with the placement skill.  The calibration is the point: a flag is only worth acting on if
the descriptor it is built on has been shown to move with the score.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import rasterio                                  # noqa: E402
from scipy import ndimage as ndi                  # noqa: E402
from scipy.stats import spearmanr                 # noqa: E402

from gems import audit, faultstats as fs          # noqa: E402

DATA = os.path.join(ROOT, "data")
ANCH = os.path.join(ROOT, ".cache", "sib", "anchors")
M_POINTS = 20_000
R_M = audit.NCC_R_M
LONG_M = 3000.0


def read_pred(path, domain):
    with rasterio.open(path) as src:
        p = src.read(1).astype(np.float32)
    return (np.nan_to_num(p, nan=0.0) > 0) & domain


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--h24", default=os.path.join(ROOT, "docs", "downloads",
                                                   "gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "data", "prediction-audit.json"))
    ap.add_argument("--skip-features", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    def log(*a):
        print(f"[{time.time()-t0:6.0f}s]", *a, flush=True)

    with rasterio.open(os.path.join(DATA, "sample_submission.tif")) as s:
        tmpl = s.read(1)
        T = s.transform
    footprint = np.isfinite(tmpl)
    with rasterio.open(os.path.join(DATA, "labels.tif")) as s:
        lab = s.read(1)
    cat = lab == 1
    domain = footprint & ~cat
    area1 = audit.rasterize_polygon_zip(os.path.join(DATA, "external", "GeoDAWN_area1_outline.zip"), T, footprint.shape) & footprint
    with rasterio.open(os.path.join(DATA, "external", "lidar_scarp_features_u8.tif")) as s:
        lid_valid = (s.read(12) > 0) & footprint
    tr = fs.extract_traces(cat)
    dist_long = ndi.distance_transform_edt(~np.isin(tr.labels, tr.ids[tr.length_m >= LONG_M])) * 100.0
    log(f"domain {int(domain.sum()):,} px; lidar-valid share {lid_valid.sum()/footprint.sum():.3f}; area1 share {area1.sum()/footprint.sum():.3f}")

    # ---- common CSR null (computed once) ---------------------------------------------------------
    null = fs.csr_null_counts(footprint, M_POINTS, R_M, n_null=40, seed=11)
    log("CSR null built")

    def pts_of(mask):
        rr, cc = np.nonzero(mask)
        return np.column_stack([cc, rr]).astype(float) * 100.0

    def describe(mask, name, live=None, skill=None):
        d = dict(id=name, live_dti=live, skill=skill)
        d["structure"] = audit.structure_summary(mask)
        n = fs.ncc_against_null(pts_of(mask), R_M, null, M_POINTS, seed=3) if mask.sum() >= M_POINTS else None
        if n is not None:
            d["ncc_sum_ratio"] = n["sum_ratio"]
            d["ncc_sum_lo"] = n["sum_lo"]; d["ncc_sum_hi"] = n["sum_hi"]
        d["near_long"] = audit.near_long_enrichment(mask, domain, dist_long)
        d["survey_lines"] = audit.survey_line_test(mask.astype(np.float32), footprint, area1)
        d["edge_lidar"] = audit.edge_jump(mask, domain, lid_valid, cat, footprint, 3.0)
        d["edge_area1"] = audit.edge_jump(mask, domain, area1, cat, footprint, 3.0)
        return d

    # ---- reference: the known catalogue, measured identically -----------------------------------
    ref = describe(cat, "known-catalogue")
    ref_ncc = np.array(ref["ncc_sum_ratio"])
    log("catalogue NCC(sum):", np.round(ref_ncc, 2))

    # catalogue-like samples: independent thinning of whole traces preserves the large-scale point process
    # (dropping whole tiles would empty half the footprint and inflate clustering, so it is NOT used)
    rng = np.random.default_rng(5)
    self_div = []
    for k in range(12):
        keep_ids = tr.ids[rng.random(tr.n) < 0.5]
        sub = np.isin(tr.labels, keep_ids)
        if sub.sum() < M_POINTS:
            continue
        n = fs.ncc_against_null(pts_of(sub), R_M, null, M_POINTS, seed=100 + k)
        self_div.append((audit.log_divergence(n["sum_ratio"], ref_ncc, idx=range(2, 10)),
                         audit.log_divergence(n["sum_ratio"], ref_ncc, idx=range(0, 2))))
    sd = np.array(self_div)
    log("catalogue-like (trace-thinned) divergence large/small scale: mean", np.round(sd.mean(0), 3), "max", np.round(sd.max(0), 3))

    # ---- artefacts --------------------------------------------------------------------------------
    hm = json.load(open(os.path.join(ROOT, "docs", "data", "habitat-model.json")))
    skill = {a["id"]: a["skill"] for a in hm["per_anchor"]}
    man = json.load(open(os.path.join(ANCH, "manifest.json")))
    rows = []
    for m in man:
        if m.get("alias_of"):
            continue                      # byte-identical emission to another anchor: counting it twice would double-weight it
        mask = read_pred(os.path.join(ANCH, m["file"]), domain)
        d = describe(mask, m["id"], m["lb"], skill.get(m["id"]))
        if "ncc_sum_ratio" in d:
            d["delta_large"] = audit.log_divergence(d["ncc_sum_ratio"], ref_ncc, idx=range(2, 10))
            d["delta_small"] = audit.log_divergence(d["ncc_sum_ratio"], ref_ncc, idx=range(0, 2))
            d["signed_large"] = audit.signed_log_divergence(d["ncc_sum_ratio"], ref_ncc)
            d["arrangement_bin"] = audit.arrangement_bin(d["signed_large"])
        rows.append(d)
        log(f"{m['id']:26s} lb={m['lb']:.4f} dLarge={d.get('delta_large', float('nan')):.2f} "
            f"nearLong={d['near_long']['200-1000m']:.2f} isolated={d['structure']['share_isolated_dots']:.2f} "
            f"y400 p={d['survey_lines'].get('traverse_400m_along_y', {}).get('p_rank', float('nan')):.3f}")

    extras = []
    paths = [("h24-dispersed-habitat (unscored)", args.h24)] + [(os.path.basename(p), p) for p in args.extra]
    for name, path in paths:
        if not os.path.exists(path):
            continue
        mask = read_pred(path, domain)
        d = describe(mask, name)
        d["delta_large"] = audit.log_divergence(d["ncc_sum_ratio"], ref_ncc, idx=range(2, 10))
        d["delta_small"] = audit.log_divergence(d["ncc_sum_ratio"], ref_ncc, idx=range(0, 2))
        d["signed_large"] = audit.signed_log_divergence(d["ncc_sum_ratio"], ref_ncc)
        d["arrangement_bin"] = audit.arrangement_bin(d["signed_large"])
        d["sha256_note"] = os.path.basename(path)
        extras.append(d)
        log(f"{name}: dLarge={d['delta_large']:.2f} dSmall={d['delta_small']:.2f} nearLong={d['near_long']['200-1000m']:.2f} "
            f"isolated={d['structure']['share_isolated_dots']:.2f}")

    # ---- calibration against the live scores ------------------------------------------------------
    def col(fn):
        return np.array([fn(r) for r in rows], float)

    desc = {
        "delta_large (log NCC divergence 2-30 km)": col(lambda r: r.get("delta_large", np.nan)),
        "delta_small (0.5-1 km)": col(lambda r: r.get("delta_small", np.nan)),
        "signed divergence 2-30 km (neg = less clustered than catalogue)": col(lambda r: r.get("signed_large", np.nan)),
        "NCC-sum at 5 km": col(lambda r: r["ncc_sum_ratio"][4] if "ncc_sum_ratio" in r else np.nan),
        "NCC-sum at 10 km": col(lambda r: r["ncc_sum_ratio"][6] if "ncc_sum_ratio" in r else np.nan),
        "enrichment 0.2-1 km of long faults": col(lambda r: r["near_long"]["200-1000m"]),
        "enrichment >7 km from long faults": col(lambda r: r["near_long"]["7000-99999m"]),
        "share isolated dots": col(lambda r: r["structure"]["share_isolated_dots"]),
        "share in components >=5 px": col(lambda r: r["structure"]["share_in_components_ge5"]),
        "survey-line strength 400 m (y)": col(lambda r: r["survey_lines"].get("traverse_400m_along_y", {}).get("strength", np.nan)),
        "survey-line strength 4 km (x)": col(lambda r: r["survey_lines"].get("tie_4km_along_x", {}).get("strength", np.nan)),
        "lidar-edge jump index": col(lambda r: (r["edge_lidar"] or {}).get("jump_index", np.nan)),
        "area1-edge jump index": col(lambda r: (r["edge_area1"] or {}).get("jump_index", np.nan)),
        "n emitted pixels": col(lambda r: r["structure"]["n_pixels"]),
    }
    lb = col(lambda r: r["live_dti"])
    sk = col(lambda r: r["skill"] if r["skill"] is not None else np.nan)
    cal = {}
    for k, v in desc.items():
        ok = np.isfinite(v) & np.isfinite(lb)
        if ok.sum() < 8:
            continue
        a = spearmanr(v[ok], lb[ok])
        b = spearmanr(v[ok], sk[ok])
        cal[k] = dict(n=int(ok.sum()), rho_live_dti=float(a.statistic), p_live_dti=float(a.pvalue),
                      rho_skill=float(b.statistic), p_skill=float(b.pvalue))
    log("calibration (Spearman vs live DTI):")
    for k, v in cal.items():
        log(f"  {k:44s} rho={v['rho_live_dti']:+.2f} (p={v['p_live_dti']:.3f})  vs skill rho={v['rho_skill']:+.2f} (p={v['p_skill']:.3f})")

    bins = []
    for lo, hi, name in audit.ARRANGEMENT_BINS:
        sel = [r for r in rows if "signed_large" in r and lo <= r["signed_large"] < hi]
        bins.append(dict(lo=lo, hi=hi, name=name, n=len(sel), members=[r["id"] for r in sel],
                         mean_live_dti=float(np.mean([r["live_dti"] for r in sel])) if sel else None,
                         min_live_dti=float(min(r["live_dti"] for r in sel)) if sel else None,
                         max_live_dti=float(max(r["live_dti"] for r in sel)) if sel else None))
    top = sorted([r for r in rows if "signed_large" in r], key=lambda r: -r["live_dti"])
    top7 = top[:7]
    target = dict(rule="median signed divergence of the 7 live-scored emissions with the highest public DTI (all >= 0.146)",
                  members=[r["id"] for r in top7], dti_floor=float(top7[-1]["live_dti"]),
                  value=float(np.median([r["signed_large"] for r in top7])),
                  status="post-hoc: fixed after the audit table was seen; descriptive of 23 emissions; not validated")
    log("arrangement bins:", [(b["name"][:22], b["n"], None if b["mean_live_dti"] is None else round(b["mean_live_dti"], 3)) for b in bins])
    log("arrangement target (median of top-7):", round(target["value"], 3))
    out = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               arrangement_bins=bins, arrangement_target=target,
               method=dict(null=f"{M_POINTS} CSR points inside the footprint x 40 replicates, reused for every raster",
                           r_m=[float(r) for r in R_M], long_fault_threshold_m=LONG_M,
                           note="NCC here is the 2-D pair-count adaptation of the 1-D scanline method of Marrett et al. (2018)"),
               geometry=dict(footprint_km2=float(footprint.sum() / 100.0), area1_km2=float(area1.sum() / 100.0),
                             lidar_valid_share=float(lid_valid.sum() / footprint.sum()),
                             official_data_extent_km2=51695.2, official_area1_km2=2411.7),
               reference=ref, catalogue_subset_divergence=dict(
                   large_scale_mean=float(sd[:, 0].mean()), large_scale_max=float(sd[:, 0].max()),
                   small_scale_mean=float(sd[:, 1].mean()), small_scale_max=float(sd[:, 1].max()), n=int(len(sd))),
               artefacts=rows, unscored=extras, calibration=cal)

    if not args.skip_features:
        log("survey-line detector on the 19 official feature bands ...")
        feats = {}
        with rasterio.open(os.path.join(DATA, "training_features.tif")) as src:
            names = [str(d).split(" - ")[0] for d in src.descriptions]
            for b in range(1, src.count + 1):
                raw = src.read(b).astype(np.float64)
                good = footprint & np.isfinite(raw) & (np.abs(raw) < 1e30)
                z = np.where(good, (raw - raw[good].mean()) / (raw[good].std() + 1e-12), 0.0)
                feats[names[b - 1]] = audit.survey_line_test(z, good, area1)
        out["feature_band_lines"] = feats
    json.dump(out, open(args.out, "w"), indent=1)
    log("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
