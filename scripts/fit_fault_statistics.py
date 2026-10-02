#!/usr/bin/env python3
"""Fit the fault-population spatial statistics on the known INGENIOUS / USGS traces - BEFORE any model.

    python scripts/fit_fault_statistics.py            # -> docs/data/fault-statistics.json

Inputs are only the official label raster and public external layers (all hash-verified by
scripts/restore_workspace.py).  Nothing here uses a feature band, a model or a leaderboard score.

Measured (definitions and sources in src/gems/faultstats.py):
  1. length distribution of the 8-connected traces: power-law exponent a (density), its cumulative form
     a - 1, the lower cut-off chosen by KS distance, a bootstrap interval and a lognormal comparison;
  2. nearest-larger-neighbour scaling <d>(l) = A l^x, by centroid distance and by edge distance, over all
     lengths and over the power-law tail only;
  3. correlation dimension D of trace centroids and of all fault pixels;
  4. normalised correlation sum and count (Marrett et al. 2018) - 2-D pair counts against complete spatial
     randomness inside the footprint, plus the published 1-D scanline form along E-W and N-S lines;
  5. the Bour & Davy (1999) consistency check x = (a - 1)/D with the density exponent, next to the value
     obtained with the cumulative exponent so that the difference is visible;
  6. a synthetic check of the relation on simulated populations;
  7. enrichment of other faults at distance r from the known long faults - for the catalogue's own short
     traces and for SGMC faults the catalogue does not capture - with blocked out-of-fold AUCs, and in angular
     wedges around the tips (continuation beyond the tip vs flanks: the 'extrapolated pattern' of the brief);
  8. lidar scarp-metric profile around the catalogue (the H-25 relocation test).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import rasterio                                     # noqa: E402
from scipy import ndimage as ndi                     # noqa: E402

from gems import faultstats as fs, clusterprior as cp   # noqa: E402

R_CENTROID = np.array([500, 750, 1000, 1500, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000], float)
LONG_M = 3000.0


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "data", "fault-statistics.json"))
    ap.add_argument("--n-null", type=int, default=100)
    args = ap.parse_args()
    t0 = time.time()

    def log(*a):
        print(f"[{time.time()-t0:6.0f}s]", *a, flush=True)

    labels_path = os.path.join(ROOT, "data", "labels.tif")
    with rasterio.open(labels_path) as s:
        lab = s.read(1)
    foot = lab >= 0
    cat = lab == 1
    tr = fs.extract_traces(cat)
    L = tr.length_m
    out = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               inputs=dict(labels_sha256=sha256(labels_path), footprint_px=int(foot.sum()), catalogue_px=int(cat.sum())),
               definitions=dict(
                   fault="one 8-connected component of the label raster (touching traces merge: a lower bound on the number "
                         "of faults, an upper bound on fault length)",
                   length="maximum Feret diameter + 1 pixel (extent); cumulative path length = pixels x 100 m is the check",
                   a="DENSITY exponent n(l) ~ l^-a; the cumulative exponent is a - 1",
                   ncc="2-D pair-count adaptation of the 1-D scanline method of Marrett et al. (2018); null = CSR inside the footprint"))
    out["population"] = dict(n_traces=int(tr.n), n_pixels=int(cat.sum()),
                             length_m_quantiles={str(q): float(np.percentile(L, q)) for q in (0, 10, 25, 50, 75, 90, 99, 100)},
                             n_ge_3km=int((L >= LONG_M).sum()), px_in_ge_3km=int(tr.n_px[L >= LONG_M].sum()))
    log("traces", tr.n)

    # ---- 1. length distribution ----------------------------------------------------------------
    ld = {"extent": fs.fit_length_distribution(L, n_boot=300), "path": fs.fit_length_distribution(tr.path_m, n_boot=300)}
    out["length_distribution"] = ld
    grid = np.logspace(np.log10(L.min()), np.log10(L.max()), 60)
    out["length_ccdf"] = dict(l_m=[float(g) for g in grid], n_ge=[int((L >= g).sum()) for g in grid])
    log("length fit: a_density=%.3f [%.2f, %.2f] xmin=%.0f m n_tail=%d (%s)" % (
        ld["extent"]["a_density"], *ld["extent"]["a_ci95"], ld["extent"]["xmin_m"], ld["extent"]["n_tail"], ld["extent"]["preferred"]))

    # ---- 2. nearest larger neighbour -------------------------------------------------------------
    d_cen = fs.nearest_larger_centroid(L, tr.cx, tr.cy)
    d_edge = fs.nearest_larger_edge(tr)
    xmin = ld["extent"]["xmin_m"]
    nln = {}
    for name, d in (("centroid", d_cen), ("edge", d_edge)):
        nln[name] = dict(all_lengths=fs.fit_nearest_larger(L, d), tail_ge_xmin=fs.fit_nearest_larger(L, d, l_min=xmin, n_bins=8),
                         median_m=float(np.nanmedian(d)))
    out["nearest_larger"] = nln
    rng = np.random.default_rng(0)
    pick = rng.choice(tr.n, size=min(900, tr.n), replace=False)
    out["nearest_larger_binned"] = dict(sample_l_m=[float(L[i]) for i in pick],
                                        sample_d_centroid_m=[None if not np.isfinite(d_cen[i]) else float(d_cen[i]) for i in pick])
    log("NLN x (tail, centroid) = %.2f %s ; (all) = %.2f" % (nln["centroid"]["tail_ge_xmin"]["x"], nln["centroid"]["tail_ge_xmin"]["x_ci95"],
                                                          nln["centroid"]["all_lengths"]["x"]))

    # ---- 3. correlation dimension ---------------------------------------------------------------
    pts = np.column_stack([tr.cx, tr.cy])
    rr, cc = np.nonzero(cat)
    pix = np.column_stack([cc, rr]).astype(float) * 100.0
    cd = dict(centroids_0p5_10km=fs.correlation_dimension(pts, R_CENTROID[[0, 1, 2, 3, 4, 5, 6, 7, 8]]),
              centroids_1p5_30km=fs.correlation_dimension(pts, R_CENTROID[3:]),
              pixels_0p3_10km=fs.correlation_dimension(pix, np.array([300, 500, 750, 1000, 1500, 2000, 3000, 5000, 7500, 10000.]), max_points=30000))
    for v in cd.values():
        v.pop("log_c", None)
    out["correlation_dimension"] = cd
    log("D: centroids 0.5-10 km %.2f, 1.5-30 km %.2f, pixels %.2f" % (cd["centroids_0p5_10km"]["D"], cd["centroids_1p5_30km"]["D"], cd["pixels_0p3_10km"]["D"]))

    # ---- 4. normalised correlation sum / count ---------------------------------------------------
    ncc_c = fs.ncc_2d(pts, foot, R_CENTROID, n_null=args.n_null, seed=1)
    pix_r = np.array([500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000], float)
    ncc_p = fs.ncc_2d(pix, foot, pix_r, n_null=40, seed=2, max_points=20000)
    s_ratio = np.array(ncc_c["sum_ratio"])
    sel = (R_CENTROID >= 1500)
    slope = np.polyfit(np.log(R_CENTROID[sel]), np.log(s_ratio[sel]), 1)[0]
    ncc_c["loglog_slope_1p5_30km"] = float(slope)
    ncc_c["implied_correlation_dimension_2_plus_slope"] = float(2.0 + slope)
    lags = np.array([0.5, 1.5, 2.5, 3.5, 5.5, 8.5, 13.5, 20.5, 30.5, 45.5, 70.5, 110.5, 170.5, 260.5, 400.5])
    scan = dict(east_west=fs.ncc_scanline(cat, 1, lags, footprint=foot), north_south=fs.ncc_scanline(cat, 0, lags, footprint=foot))
    out["ncc"] = dict(centroids_2d=ncc_c, pixels_2d=ncc_p, scanline_1d_published_form=scan)
    log("NCC sum (centroids):", np.round(ncc_c["sum_ratio"], 2), "slope->D=%.2f" % (2 + slope))

    # ---- 5. Bour & Davy consistency --------------------------------------------------------------
    a_dens, a_ci = ld["extent"]["a_density"], ld["extent"]["a_ci95"]
    D_lo = min(cd["centroids_0p5_10km"]["D"], cd["centroids_1p5_30km"]["D"])
    D_hi = max(cd["centroids_0p5_10km"]["D"], cd["centroids_1p5_30km"]["D"])
    xp_lo, xp_hi = (a_ci[0] - 1.0) / D_hi, (a_ci[1] - 1.0) / D_lo
    xt = nln["centroid"]["tail_ge_xmin"]
    xe = nln["edge"]["tail_ge_xmin"]
    a_cum = a_dens - 1.0
    out["bour_davy_consistency"] = dict(
        relation="x = (a - 1) / D, a = density exponent (Bour & Davy 1999, GRL 26(13) 2001-2004)",
        a_density=a_dens, a_density_ci95=a_ci, D_range=[D_lo, D_hi],
        x_predicted=(a_dens - 1.0) / ((D_lo + D_hi) / 2), x_predicted_range=[xp_lo, xp_hi],
        x_measured_tail_centroid=xt["x"], x_measured_tail_centroid_ci95=xt["x_ci95"], x_measured_tail_geomean=xt["x_geometric_mean"],
        x_measured_tail_edge=xe["x"], x_measured_tail_edge_ci95=xe["x_ci95"],
        x_measured_all_lengths_centroid=nln["centroid"]["all_lengths"]["x"],
        consistent_centroid=bool(xt["x_ci95"][0] <= xp_hi and xt["x_ci95"][1] >= xp_lo),
        consistent_edge=bool(xe["x_ci95"][0] <= xp_hi and xe["x_ci95"][1] >= xp_lo),
        if_cumulative_exponent_were_inserted_for_a=dict(x_predicted=(a_cum - 1.0) / ((D_lo + D_hi) / 2),
                                                        note="what a cumulative-exponent reading of the formula would predict; simulations "
                                                             "show this is not the relation (see synthetic_validation)"),
        interpretation=("the catalogue is self-similar above the power-law cut-off (nearest-larger-neighbour exponent consistent with "
                        "(a-1)/D for the centroid definition); over ALL lengths the exponent is flatter (about 0.9), i.e. short "
                        "traces sit farther from their nearest larger neighbour than the long-fault scaling predicts. That "
                        "deficit is what catalogue incompleteness, trace merging or a physical break in scaling would each produce; "
                        "the data alone cannot separate them."))
    log("Bour-Davy: x_pred range [%.2f, %.2f], measured tail (centroid) %.2f %s, edge %.2f %s" % (xp_lo, xp_hi, xt["x"], xt["x_ci95"], xe["x"], xe["x_ci95"]))

    # ---- 6. synthetic validation -----------------------------------------------------------------
    rows = []
    for a, D in ((2.6, 1.5), (2.6, 1.2), (2.2, 1.5), (3.0, 1.8), (2.6, 1.8)):
        r = [fs.bour_davy_check(n=6000, a_density=a, D=D, seed=s) for s in range(3)]
        rows.append(dict(a_density=a, D=D, x_mean_estimator=float(np.mean([q["x_measured"] for q in r])),
                         x_geomean_estimator=float(np.mean([q["x_geometric_mean"] for q in r])),
                         x_predicted=(a - 1.0) / D, x_if_cumulative_were_a=(a - 2.0) / D))
    out["synthetic_validation"] = dict(
        n_points=6000, seeds=3, rows=rows,
        verdict="measured x is bracketed by the geometric-mean and arithmetic-mean estimators around (a_density - 1)/D in every case and is far "
                "from (a_density - 2)/D: the density exponent is the right reading of the published relation")
    log("synthetic validation done")

    # ---- 7. enrichment around long faults + blocked AUC -------------------------------------------
    long_ids = tr.ids[L >= LONG_M]
    big = np.isin(tr.labels, long_ids)
    d_long = ndi.distance_transform_edt(~big) * 100.0
    d_cat = ndi.distance_transform_edt(~cat) * 100.0
    short = (tr.labels > 0) & ~big
    with rasterio.open(os.path.join(ROOT, "data", "external", "derived_sgmc_faults_100m_u8.tif")) as s:
        sg = (s.read(1) > 0) & foot
    gap = sg & ~cat & (d_cat > 300)
    el_short = foot & ~big
    el_gap = foot & ~big & (d_cat > 300)
    prof_short = cp.enrichment_profile(short, d_long, el_short, seed=1)
    prof_gap = cp.enrichment_profile(gap, d_long, el_gap, seed=2)
    cons = dict(prof_gap)
    cons["enrichment"] = [float(min(a, b)) if np.isfinite(a) and np.isfinite(b) else float("nan")
                          for a, b in zip(prof_short["enrichment"], prof_gap["enrichment"])]
    out["enrichment"] = dict(
        long_fault_threshold_m=LONG_M, n_long_traces=int(len(long_ids)),
        catalogue_short_traces=prof_short, sgmc_not_in_catalogue=prof_gap, conservative_min_of_both=cons,
        note="first band (0-200 m) is structural: distinct 8-connected traces cannot be closer than 200 m; SGMC-gap pixels are by "
             "construction > 300 m from the catalogue, so its 200-400 m band only holds 300-400 m")
    out["blocked_auc"] = dict(
        folds="2 x 2 geographic blocks; profile fitted on three blocks, scored on the fourth",
        catalogue_short_traces=cp.blocked_auc(short, d_long, el_short),
        sgmc_not_in_catalogue=cp.blocked_auc(gap, d_long, el_gap))
    log("enrichment (cat-short):", np.round(prof_short["enrichment"], 2))
    log("enrichment (SGMC gap) :", np.round(prof_gap["enrichment"], 2))
    log("blocked AUC cat-short %.3f | SGMC-gap %.3f" % (out["blocked_auc"]["catalogue_short_traces"]["auc_mean"],
                                                     out["blocked_auc"]["sgmc_not_in_catalogue"]["auc_mean"]))

    # ---- 7b. along-strike geometry: continuation beyond tips vs flanks ------------------------------
    tip_gap = cp.tip_wedge_profile(tr.labels, long_ids, gap, el_gap, seed=3)
    tip_short = cp.tip_wedge_profile(tr.labels, long_ids, short, el_short, seed=4)
    zone = cp.wedge_union_mask(tr.labels, long_ids, (0.0, 25.0), (300.0, 1000.0))
    zone_el = zone & el_gap
    zone_el_s = zone & el_short
    out["tip_wedges"] = dict(
        definition="enrichment of the target in angular wedges around the tips (endpoints) of the long traces; E is relative to the "
                   "all-wedge, all-band tip neighbourhood; bootstrap over endpoints",
        sgmc_not_in_catalogue=tip_gap, catalogue_short_traces=tip_short,
        continuation_zone_300_1000m=dict(
            area_share_of_eligible=float(zone_el.sum() / max(el_gap.sum(), 1)),
            share_of_missing_fault_pixels_inside=float((gap & zone_el).sum() / max(gap[el_gap].sum(), 1)),
            area_share_of_eligible_catalogue_short=float(zone_el_s.sum() / max(el_short.sum(), 1)),
            share_of_catalogue_short_pixels_inside=float((short & zone_el_s).sum() / max(short[el_short].sum(), 1)),
            n_pixels=int(zone.sum())),
        reading="the continuation wedge is the richest part of the tip neighbourhood, but it covers about 1 % of the scored domain; its absolute "
                "capture of missing-fault pixels is a few percent at most, so it can re-rank near-ties but cannot carry a budget")
    log("tip wedges: continuation/lateral SGMC-gap %.2f %s | catalogue-short %.2f; continuation zone covers %.2f%% of eligible px and holds %.2f%% of SGMC-gap px" % (
        tip_gap["continuation_over_lateral"], np.round(tip_gap["continuation_over_lateral_ci95"], 2), tip_short["continuation_over_lateral"],
        100 * out["tip_wedges"]["continuation_zone_300_1000m"]["area_share_of_eligible"],
        100 * out["tip_wedges"]["continuation_zone_300_1000m"]["share_of_missing_fault_pixels_inside"]))

    # ---- 7c. independent replication on the vector USGS Quaternary traces (surveyed lengths, no rasterisation) --------
    rows_v = list(csv.DictReader(open(os.path.join(ROOT, "data", "external", "gdr_qfaults_traces.csv"))))

    def fnum(x):
        try:
            return float(x)
        except Exception:
            return float("nan")
    clip = np.array([fnum(r["clipped_length_m"]) for r in rows_v])
    vx = np.array([fnum(r["centroid_utm_x"]) for r in rows_v])
    vy = np.array([fnum(r["centroid_utm_y"]) for r in rows_v])
    vin = np.array([r["centroid_in_footprint"] in ("1", "True", "true") for r in rows_v])
    vm = vin & np.isfinite(clip) & (clip > 0) & np.isfinite(vx)
    vfit = fs.fit_length_distribution(clip[vm], n_boot=300)
    vd = fs.nearest_larger_centroid(clip[vm], vx[vm], vy[vm])
    v_all = fs.fit_nearest_larger(clip[vm], vd, n_bins=8, min_per_bin=10)
    v_tail = fs.fit_nearest_larger(clip[vm], vd, l_min=vfit["xmin_m"], n_bins=6, min_per_bin=8)
    v_D = fs.correlation_dimension(np.column_stack([vx[vm], vy[vm]]), np.array([1500, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000.0]))
    v_scale = np.array([fnum(r["map_scale"]) for r in rows_v])
    out["vector_replication"] = dict(
        source="data/external/gdr_qfaults_traces.csv (GDR 1391 USGS Quaternary fault traces; lengths, map scale and centroids only, no geometry)",
        n_rows=len(rows_v), n_centroid_in_footprint=int(vin.sum()), n_used=int(vm.sum()),
        median_length_m=float(np.median(clip[vm])),
        length_fit=dict(a_density=vfit["a_density"], a_ci95=vfit["a_ci95"], xmin_m=vfit["xmin_m"], n_tail=vfit["n_tail"], preferred=vfit["preferred"]),
        nln_all_lengths=dict(x=v_all["x"], x_ci95=v_all["x_ci95"]), nln_tail=dict(x=v_tail["x"], x_ci95=v_tail.get("x_ci95"), n=v_tail["n"]),
        correlation_dimension_1p5_30km=dict(D=v_D["D"], r2=v_D["r2"], n=v_D["n"]),
        bour_davy_predicted_x=float((vfit["a_density"] - 1.0) / v_D["D"]),
        map_scale_attribute_counts={str(int(k)): int(v) for k, v in zip(*np.unique(v_scale[np.isfinite(v_scale)], return_counts=True))},
        note="a different object definition from the raster components (whole surveyed traces, median ~10 km versus 1.2 km), so agreement of a, D and the tail x "
             "is a replication, not a duplicate. map_scale takes the values 100 and 250 (read as 1:100,000 and 1:250,000; the file does not state the unit).")
    log("vector replication: a=%.2f %s, D=%.2f, tail x=%.2f %s (predicted %.2f), n=%d" % (
        vfit["a_density"], np.round(vfit["a_ci95"], 2), v_D["D"], v_tail["x"], np.round(v_tail.get("x_ci95", [np.nan, np.nan]), 2),
        out["vector_replication"]["bour_davy_predicted_x"], vm.sum()))

    # ---- 8. H-25 relocation: scarp metrics vs distance from catalogue ---------------------------------
    with rasterio.open(os.path.join(ROOT, "data", "external", "lidar_scarp_features_u8.tif")) as s:
        names = ["ex_max", "ex_mean", "step_max", "lapneg_max", "lappos_max", "downface_max", "upface_max", "cross_max", "relief",
                 "coh100", "strike", "valid"]
        lid = {nm: s.read(b).astype(np.float32) for b, nm in zip(range(1, 13), names) if nm in ("upface_max", "downface_max", "step_max", "lapneg_max", "valid")}
    valid = (lid["valid"] > 0) & foot
    edges = [0, 50, 150, 250, 350, 450, 550, 700, 900, 1200, 1600, 2200, 3000]
    prof = {}
    for nm in ("upface_max", "downface_max", "step_max", "lapneg_max"):
        far = lid[nm][valid & (d_cat > 4000)].mean()
        row = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = valid & ((d_cat >= lo) & (d_cat < hi) if lo == 0 else (d_cat > lo) & (d_cat <= hi))
            row.append(float(lid[nm][m].mean() / far) if m.any() else None)
        prof[nm] = row
    out["h25_offset_profile"] = dict(
        edges_m=edges, ratio_to_far_field_gt_4km=prof, lidar_valid_share_of_catalogue=float((valid & cat).sum() / cat.sum()),
        peak_at_zero_offset=all(prof[k][0] == max(v for v in prof[k] if v is not None) for k in prof),
        reading="monotone decay from the catalogue pixels with the maximum at distance 0 and no off-centre ring: no average displacement between "
                "catalogued traces and lidar scarps is visible at 100 m resolution; a displaced subset cannot be excluded")

    out["runtime_s"] = round(time.time() - t0, 1)
    json.dump(out, open(args.out, "w"), indent=1)
    log("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
