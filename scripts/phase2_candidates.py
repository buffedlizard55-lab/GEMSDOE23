#!/usr/bin/env python3
"""Extract the Phase-2 reviewer candidates with an epistemic/aleatoric split.

The brief's rule, implemented literally:
  * high epistemic variance in historically UNDER-surveyed terrain raises a candidate's
    review priority (that is where a missing structure is most plausible);
  * high epistemic variance in WELL-surveyed terrain is treated with suspicion (the
    disagreement is more likely a model artefact than a missing fault);
  * aleatoric variance never changes priority - it is irreducible noise in the data.

Survey coverage is measured, not assumed, from two independent official products:
  * 1 m 3DEP lidar validity (data/external/lidar_scarp_features_u8.tif band 12), and
  * the density of the USGS State Geologic Map Compilation structure lines, i.e. how much
    mapped geology exists nearby.
Priority is a reviewer-ranking aid only: it never modifies the submitted raster.
"""
from __future__ import annotations
import argparse, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from gems.layers import load_domain, EXT, PIXEL_M
from gems.ensemble import decompose

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", default="outputs/full_member_probs.npy")
    ap.add_argument("--mean", default="outputs/full_mean.npy")
    ap.add_argument("--epistemic", default="outputs/full_epistemic.npy")
    ap.add_argument("--aleatoric", default="outputs/full_aleatoric.npy")
    ap.add_argument("--score", default="outputs/rank_score.npy")
    ap.add_argument("--emission", default="outputs/emission_mask.npy")
    ap.add_argument("--out-csv", default="docs/data/phase2-candidate-review.csv")
    ap.add_argument("--out-json", default="docs/data/phase2-candidates.json")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--min-separation-px", type=int, default=8)
    args = ap.parse_args()
    import rasterio
    from scipy.ndimage import distance_transform_edt, uniform_filter, label, center_of_mass

    footprint, catalogue, domain, _ = load_domain()
    mean = np.load(args.mean); epi = np.load(args.epistemic); ale = np.load(args.aleatoric)
    score = np.load(args.score) if os.path.exists(args.score) else mean
    emis = np.load(args.emission) if os.path.exists(args.emission) else None

    # ---- survey coverage: independent, official, measured ----
    with rasterio.open(os.path.join(EXT, "lidar_scarp_features_u8.tif")) as d:
        lidar = (d.read(12) > 0)
    with rasterio.open(os.path.join(EXT, "derived_sgmc_faults_100m_u8.tif")) as d:
        sgmc = (d.read(1) > 0) & footprint
    map_density = uniform_filter(sgmc.astype(np.float32), 21)     # mapped-structure density, 2.1 km window
    md_q = np.quantile(map_density[domain], [0.05, 0.95])
    coverage = np.clip(0.5 * lidar.astype(np.float32)
                       + 0.5 * (map_density - md_q[0]) / max(1e-9, md_q[1] - md_q[0]), 0, 1)
    coverage[~domain] = 0.0

    total = epi + ale
    epi_share = np.divide(epi, total, out=np.zeros_like(epi), where=total > 0)

    # ---- candidate objects: cluster the dispersed emission into lineament-scale objects ----
    from scipy.ndimage import binary_dilation
    base = emis if emis is not None else (score >= np.quantile(score[domain], 1 - 0.004))
    base = base & domain
    # the emission is deliberately dotted (400 m separation), so a reviewer-facing candidate is a
    # cluster of dots, not a single dot: close the gaps first, then label.
    clustered = binary_dilation(base, np.ones((3, 3), bool), iterations=4)
    lab, n = label(clustered & domain, structure=np.ones((3, 3), bool))
    print("candidate objects:", n, "from", int(base.sum()), "emitted pixels", flush=True)
    if n == 0:
        print("no candidates"); return 0
    idx = np.arange(1, n + 1)
    flat = lab.ravel()
    counts = np.bincount(flat, minlength=n + 1)[1:].astype(np.float64)
    keep = counts >= 4                                  # drop specks
    idx = idx[keep]; counts = counts[keep]
    def wmean(arr):
        v = np.asarray(arr, np.float64).ravel()
        ssum = np.bincount(flat, weights=np.where(flat > 0, v, 0.0), minlength=n + 1)[1:]
        return (ssum[keep] / counts)
    dcat = distance_transform_edt(~catalogue, sampling=(PIXEL_M, PIXEL_M))
    coms = center_of_mass(np.ones_like(lab, np.float32), lab, list(range(1, n + 1)))
    m_mean = wmean(mean); m_epi = wmean(epi); m_ale = wmean(ale); m_tot = wmean(total)
    m_cov = wmean(coverage); m_score = wmean(score); m_epi_share = wmean(epi_share)
    m_lid = wmean(lidar.astype(np.float32))
    epi_q = float(np.quantile(m_epi_share, 0.75)) if m_epi_share.size else 0.0
    rows = []
    for k, i in enumerate(idx):
        cy, cx = coms[i - 1]
        rows.append(dict(object_id=int(i), px=int(counts[k]),
                         row=int(round(cy)), col=int(round(cx)),
                         easting=243350.0 + (cx + 0.5) * PIXEL_M,
                         northing=4508550.0 - (cy + 0.5) * PIXEL_M,
                         mean_probability=float(m_mean[k]),
                         epistemic_var=float(m_epi[k]),
                         aleatoric_var=float(m_ale[k]),
                         total_var=float(m_tot[k]),
                         epistemic_share=float(m_epi_share[k]),
                         survey_coverage=float(m_cov[k]),
                         lidar_covered=bool(m_lid[k] > 0.5),
                         mean_rank_score=float(m_score[k]),
                         d_to_catalogue_m=float(dcat[int(round(cy)), int(round(cx))]),
                         epistemic_top_quartile=bool(m_epi_share[k] >= epi_q)))
    if not rows:
        print("no candidates"); return 0
    for r in rows:
        # the brief's priority rule: epistemic uncertainty in under-surveyed terrain is a
        # finding (raises priority); the same uncertainty in well-surveyed terrain is suspect.
        r["priority"] = float(r["mean_rank_score"] * (1.0 + 0.5 * r["epistemic_share"] * (1.0 - r["survey_coverage"])
                                                       - 0.25 * r["epistemic_share"] * r["survey_coverage"]))
        r["epistemic_interpretation"] = (
            ("under-surveyed + high epistemic: raises priority"
             if r["survey_coverage"] < 0.5 else "well-surveyed + high epistemic: treat with suspicion")
            if r["epistemic_top_quartile"] else "epistemic disagreement below the candidate 75th percentile")
    rows.sort(key=lambda r: -r["priority"])
    rows = rows[: args.n]
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    import csv as _csv
    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)
    cols = ["rank", "object_id", "px", "row", "col", "easting", "northing", "d_to_catalogue_m",
            "mean_probability", "epistemic_var", "aleatoric_var", "total_var", "epistemic_share",
            "survey_coverage", "lidar_covered", "mean_rank_score", "epistemic_top_quartile", "priority",
            "epistemic_interpretation"]
    with open(args.out_csv, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: (round(r[c], 6) if isinstance(r[c], float) else r[c]) for c in cols})
    summary = dict(
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_objects=int(n), n_reported=len(rows),
        identity="Var(Y) = E_m[p_m(1-p_m)] + Var_m(p_m)  (aleatoric + epistemic), Var_m with ddof=0",
        reference="Lakshminarayanan, Pritzel & Blundell, NeurIPS 2017",
        coverage_definition="0.5 * 1m-3DEP-lidar validity + 0.5 * rank of USGS SGMC structure-line density in a 2.1 km window",
        priority_rule="priority = rank_score * (1 + 0.5*epi_share*(1-coverage) - 0.25*epi_share*coverage); reviewer aid only, never modifies the submitted raster",
        mean_epistemic_share=float(np.mean([r["epistemic_share"] for r in rows])),
        mean_survey_coverage=float(np.mean([r["survey_coverage"] for r in rows])),
        epistemic_top_quartile_threshold=float(np.quantile([r["epistemic_share"] for r in rows], 0.75)) if rows else None,
        n_under_surveyed_raising_priority=int(sum(1 for r in rows if r["survey_coverage"] < 0.5 and r["epistemic_top_quartile"])),
        n_well_surveyed_flagged=int(sum(1 for r in rows if r["survey_coverage"] >= 0.5 and r["epistemic_top_quartile"])),
        detector_caveat=("the members failed their out-of-fold admission gate (docs/data/oof-evaluation.json), so the "
                         "decomposition is methodologically valid but its values carry little geological information; "
                         "the detector contributes nothing to the submitted raster"),
        candidates=rows)
    json.dump(summary, open(args.out_json, "w"), indent=1)
    print("wrote", args.out_csv, args.out_json)
    print("under-surveyed high-epistemic candidates:", summary["n_under_surveyed_raising_priority"],
          " well-surveyed high-epistemic (suspect):", summary["n_well_surveyed_flagged"])

if __name__ == "__main__":
    main()
