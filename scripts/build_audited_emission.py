#!/usr/bin/env python3
"""Build audited emissions from the H24 score S: H29 (lattice regime) and H30 (arrangement-matched).

    python scripts/build_audited_emission.py --variant h29
    python scripts/build_audited_emission.py --variant h30 --set-primary

Both use the SAME ranking as H24 (S = 0.625 rank(habitat) + 0.375 rank(votes), the 100,000-pixel budget, the 400 m
separation rule, off-catalogue).  Nothing here adds placement skill.  What changes is what the audit
(scripts/audit_predictions.py, src/gems/audit.py) found wrong with the *arrangement* of H24:

 1. a spectral line at exactly the 400 m GeoDAWN Area 2 traverse spacing (strength 243 against a control 95th
    percentile of 10, rank p = 0.016)             -> row-phase equalisation (about 5 % of dots move 100-200 m);
 2. 931 dots (6,651 pairs) closer than the stated 400 m, from equal-score plateaus accepted together in one NMS
    round                                         -> deterministic tie-breaking;
 3. an arrangement that is statistically a lattice (signed NCC divergence from the catalogue -0.59: Poisson-like at
    >= 1 km, where the catalogue sits at 1.1-4x).  The four live-scored artefacts in that bin scored 0.078-0.119; the seven
    that are mildly LESS clustered than the catalogue (-0.55 to -0.15) average 0.170 and contain the top three.
                                                  -> H30 only: the NMS candidate set is limited to the top ``keep_top`` of S, a
       concentration that was fixed by a rule (target = median signed divergence of the seven best-scoring live emissions,
       -0.21 -> keep_top 0.30) and that costs ~10 % of kernel coverage.  Post-hoc and unvalidated: the arrangement bins
       come from 23 emissions, the one controlled pair (pindrop ridge vs nodes) shows equal DTI at +0.20 and -0.62, and no
       offline holdout can test it.
 4. a clustering tie-break (rank bonus <= 0.003 from the conservative lift profile) is also applied; it moves ~1 % of dots.
"""
from __future__ import annotations

import argparse, hashlib, json, os, subprocess, sys, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import rasterio                                       # noqa: E402
from scipy import ndimage as ndi                       # noqa: E402
from scipy.spatial import cKDTree                      # noqa: E402

from gems import audit, clusterprior as cp, faultstats as fs        # noqa: E402
from gems.emission import disperse_select, expected_dti, geometry, fp_relief    # noqa: E402
from gems.habitat import implied_tp                    # noqa: E402
from gems.layers import load_domain                    # noqa: E402
from gems.submission import validate_submission, write_submission_raster    # noqa: E402

PRESETS = {
    "h29": dict(keep_top=1.0, tag="h29-dealiased-habitat", band="fault_probability_h29_dealiased_dispersed_habitat",
                label="H29 · de-aliased lattice-regime emission (H24 ranking)"),
    "h30": dict(keep_top=0.30, tag="h30-arrangement-matched-habitat", band="fault_probability_h30_arrangement_matched_habitat",
                label="H30 · arrangement-matched habitat emission (H24 ranking, audit-constrained)"),
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def separation_violations(mask, r=4.0):
    rr, cc = np.nonzero(mask)
    P = np.column_stack([rr, cc]).astype(float)
    pairs = cKDTree(P).query_pairs(r - 1e-9)
    bad = {i for p in pairs for i in p}
    return int(len(pairs)), int(len(bad))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=sorted(PRESETS), required=True)
    ap.add_argument("--prior-weight", type=float, default=0.003)
    ap.add_argument("--budget", type=int, default=100_000)
    ap.add_argument("--r-min", type=float, default=4.0)
    ap.add_argument("--keep-top", type=float, default=None, help="override the preset concentration (fraction of the domain kept as candidates)")
    ap.add_argument("--set-primary", action="store_true", help="make this variant the file the site and manifest point to")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "docs", "downloads"))
    ap.add_argument("--manifest", default=os.path.join(ROOT, "docs", "data", "submission-manifest.json"))
    ap.add_argument("--candidates", default=os.path.join(ROOT, "docs", "data", "candidates.json"))
    ap.add_argument("--h24", default=os.path.join(ROOT, "docs", "downloads", "gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif"))
    ap.add_argument("--template", default=os.path.join(ROOT, "data", "sample_submission.tif"))
    args = ap.parse_args()
    pre = dict(PRESETS[args.variant])
    if args.keep_top is not None:
        pre["keep_top"] = args.keep_top
    t0 = time.time()
    os.chdir(ROOT)

    def log(*a):
        print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

    if not os.path.exists("outputs/h24_S.npy"):
        log("outputs/h24_S.npy missing -> running scripts/rebuild_h24_check.py first")
        subprocess.check_call([sys.executable, "scripts/rebuild_h24_check.py"])
    S = np.load("outputs/h24_S.npy")
    footprint, catalogue, domain, _ = load_domain()
    with rasterio.open(args.template) as s:
        T = s.transform
    area1 = audit.rasterize_polygon_zip("data/external/GeoDAWN_area1_outline.zip", T, footprint.shape) & footprint
    with rasterio.open("data/labels.tif") as s:
        cat = s.read(1) == 1
    tr = fs.extract_traces(cat)
    big = np.isin(tr.labels, tr.ids[tr.length_m >= 3000.0])
    d_long = ndi.distance_transform_edt(~big) * 100.0
    stats = json.load(open("docs/data/fault-statistics.json"))
    lift = cp.lift_map(d_long, stats["enrichment"]["conservative_min_of_both"])
    bonus = cp.tiebreak_bonus(lift, args.prior_weight)
    for need in ("docs/data/fault-statistics.json", "docs/data/prediction-audit.json"):
        if not os.path.exists(need):
            raise SystemExit(f"{need} is missing: run scripts/fit_fault_statistics.py and scripts/audit_predictions.py first")
    pa = json.load(open("docs/data/prediction-audit.json"))
    ref_ncc = np.array(pa["reference"]["ncc_sum_ratio"])
    target = pa.get("arrangement_target", {}).get("value")
    null = fs.csr_null_counts(footprint, 20000, audit.NCC_R_M, n_null=40, seed=11)

    with rasterio.open(args.h24) as s:
        h24 = np.nan_to_num(s.read(1), nan=0.0) > 0

    Sx = np.where(np.isfinite(S), S + bonus, -np.inf)
    keep = float(pre["keep_top"])
    if keep < 1.0:
        thr = np.quantile(Sx[domain], 1.0 - keep)
        cand = domain & (Sx >= thr)
    else:
        cand = domain
    mask = disperse_select(np.where(cand, Sx, -np.inf), cand, args.budget, args.r_min, break_ties=True)
    log(f"tie-broken NMS on the top {keep:.0%} of the score: {int(mask.sum()):,} dots")
    eq = audit.equalize_row_phase(mask, domain, period=4, block=300, min_sep_px=args.r_min, max_shift=2, seed=0, forbid=cat)
    mask2 = eq["mask"]
    log(f"row-phase equalisation moved {eq['n_moved']} dots ({eq['share_moved']:.2%}), mean |shift| {eq['mean_abs_shift_px']:.2f} px")

    def snapshot(m):
        lines = audit.survey_line_test(m.astype(np.float32), footprint, area1)
        g = geometry(m, domain)
        pairs, bad = separation_violations(m, args.r_min)
        rr, cc = np.nonzero(m)
        pts = np.column_stack([cc, rr]).astype(float) * 100.0
        if len(pts) >= 20000:                # the CSR null was built for exactly 20,000 points
            ncc = fs.ncc_against_null(pts, audit.NCC_R_M, null, 20000, seed=3)
            sg = audit.signed_log_divergence(ncc["sum_ratio"], ref_ncc)
        else:
            ncc, sg = dict(sum_ratio=[float("nan")] * len(audit.NCC_R_M)), float("nan")
        return dict(n=int(m.sum()), survey_lines=lines, flags=audit.survey_flags(lines),
                    row_phase_hist=[float(v) for v in audit.row_phase_hist(m)], kbar=g["kbar"], eta=g["eta"], coverage=g["coverage"],
                    separation_violating_pairs=pairs, dots_with_violation=bad,
                    ncc_sum_ratio=ncc["sum_ratio"], signed_divergence=sg, arrangement_bin=audit.arrangement_bin(sg),
                    near_long_enrichment=audit.near_long_enrichment(m, domain, d_long),
                    mean_score_rank=float(np.nanmean(np.where(np.isfinite(S), S, np.nan)[m])))
    before, after = snapshot(h24), snapshot(mask2)
    d_h24 = ndi.distance_transform_edt(~h24)
    after["share_within_200m_of_h24_dot"] = float((d_h24[mask2] <= 2.01).mean())
    after["share_identical_to_h24"] = float((mask2 & h24).sum() / mask2.sum())
    y0, y1 = before["survey_lines"]["traverse_400m_along_y"], after["survey_lines"]["traverse_400m_along_y"]
    log(f"H24  y400 {y0['strength']:.1f} p={y0['p_rank']:.3f} | violating pairs {before['separation_violating_pairs']} | signed {before['signed_divergence']:+.2f} ({before['arrangement_bin'][:20]})")
    log(f"{args.variant.upper()}  y400 {y1['strength']:.1f} p={y1['p_rank']:.3f} | violating pairs {after['separation_violating_pairs']} | signed {after['signed_divergence']:+.2f} ({after['arrangement_bin'][:20]})")

    values = np.zeros(domain.shape, np.float32)
    values[mask2] = 1.0
    values[~footprint] = 0.0
    sha = hashlib.sha256(values.tobytes()).hexdigest()[:8]
    stem = f"gemsdoe23-{pre['tag']}-{time.strftime('%Y%m%d', time.gmtime())}-{sha}"
    os.makedirs(args.out_dir, exist_ok=True)
    nan_path, allf_path = os.path.join(args.out_dir, stem + "-nan.tif"), os.path.join(args.out_dir, stem + "-allfinite.tif")
    write_submission_raster(values, args.template, nan_path, description=pre["band"])
    write_submission_raster(np.where(footprint, values, 0.0).astype(np.float32), args.template, allf_path, outside="zero", description=pre["band"])
    v1, v2 = validate_submission(nan_path, args.template), validate_submission(allf_path, args.template)
    log("validation nan:", v1["passed"], " allfinite:", v2["passed"])
    assert v1["passed"] and v2["passed"]

    g = geometry(mask2, domain)
    scen = {}
    for label, skill in (("lattice-type skill 2.0 (nodes/discovery/r13 measured 1.9-2.7)", 2.0), ("pindrop-nodes skill 2.7", 2.7),
                         ("dotted-ridge skill 5.5 (best dotted, measured)", 5.5)):
        scen[label] = {str(int(G)): float(expected_dti(g["area"], g["kbar"], G, skill)) for G in (6000.0, 10000.0, 15000.0)}
    # minimum-regret check: if the score carried NO information (skill 1) the cost of limiting the candidates is the coverage it gives up
    null_chk = {str(int(G)): dict(h24=float(expected_dti(before["n"], before["kbar"], G, 1.0)), this=float(expected_dti(g["area"], g["kbar"], G, 1.0)))
                for G in (6000.0, 10000.0, 15000.0)}
    for v in null_chk.values():
        v["relative_change"] = float(v["this"] / v["h24"] - 1.0)
    hm = json.load(open("docs/data/habitat-model.json"))
    a195 = {x["id"]: x for x in hm["per_anchor"]}["h19-5"]
    q_eq = {}
    for G in (6000.0, 10000.0, 15000.0):
        q = implied_tp(a195["live_dti"], a195["area"], G) / a195["n"]
        tp = min(q * g["area"], G)
        fp = fp_relief(G) * g["area"]
        q_eq[str(int(G))] = float(tp / (tp + 0.2 * fp + 0.8 * max(G - tp, 0.0)))
    q_lo, q_hi = min(q_eq.values()), max(q_eq.values())
    sc_list = list(scen.values())
    lat = [v for d in sc_list[:2] for v in d.values()]
    rid = [v for v in sc_list[2].values()]
    sc_lo, sc_hi = min(lat + rid), max(lat + rid)
    summary = dict(central=[q_lo, q_hi], lattice_type_skill=[min(lat), max(lat)], ridge_level_skill=[min(rid), max(rid)], scenario_range=[sc_lo, sc_hi])
    note = (f"GEMSDOE23 {args.variant.upper()} | lidar scarps + detrended slope + low U habitat, off-catalogue | {int(g['area']):,} dots, "
            f"tie-broken 400 m NMS on the top {keep:.0%} of the score, row-phase equalised (no 400 m flight-line comb) | unscored; "
            f"central expectation ~ h19-5: DTI {q_lo:.2f}-{q_hi:.2f} if TP per emitted pixel matches | sha256 {sha256_file(nan_path)[:8]}")
    files = dict(nan=dict(name=os.path.basename(nan_path), href="downloads/" + os.path.basename(nan_path), bytes=os.path.getsize(nan_path),
                          sha256=sha256_file(nan_path), variant="nan-outside-footprint", ok_to_upload=v1["passed"]),
                 allfinite=dict(name=os.path.basename(allf_path), href="downloads/" + os.path.basename(allf_path), bytes=os.path.getsize(allf_path),
                                sha256=sha256_file(allf_path), variant="zeros-outside-footprint", ok_to_upload=v2["passed"]))
    ev = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), variant=args.variant, label=pre["label"], keep_top=keep,
              prior_weight=args.prior_weight, budget=args.budget, r_min_px=args.r_min,
              equalisation=dict(n_moved=eq["n_moved"], share_moved=eq["share_moved"], mean_abs_shift_px=eq["mean_abs_shift_px"],
                                period_px=4, block_px=300, max_shift_px=2),
              arrangement_target=dict(value=target, achieved=after["signed_divergence"],
                                      within_0p08=(None if target is None or keep >= 1.0 else bool(abs(after["signed_divergence"] - target) <= 0.08)),
                                      status="post-hoc target; see docs/data/prediction-audit.json arrangement_target"),
              audit_before_h24=before, audit_after=after, geometry=g, files=files, expected_dti_scenarios=scen, expected_dti_if_q_equals_h19_5=q_eq,
              expectation_summary=summary, uninformative_score_check=null_chk, note=note,
              what_is_not_claimed="No placement skill is added or validated. Blocked-holdout gate: NOT PASSED (no valid holdout exists, I-05); the file is provided "
                                  "for the owner's slot decision, not recommended on score grounds.")
    json.dump(ev, open(os.path.join(ROOT, "docs", "data", f"{args.variant}-build.json"), "w"), indent=1)

    cands = json.load(open(args.candidates)) if os.path.exists(args.candidates) else dict(candidates=[])
    entry = dict(id=args.variant, label=pre["label"], nan=files["nan"], allfinite=files["allfinite"], note=note,
                 keep_top=keep, signed_divergence=after["signed_divergence"], arrangement_bin=after["arrangement_bin"],
                 y400_strength=y1["strength"], y400_p=y1["p_rank"], kbar=g["kbar"], eta=g["eta"], coverage=g["coverage"], n_dots=int(g["area"]),
                 separation_violating_pairs=after["separation_violating_pairs"], evidence=f"data/{args.variant}-build.json")
    cands["candidates"] = [c for c in cands.get("candidates", []) if c["id"] != args.variant] + [entry]
    cands["generated_utc"] = ev["generated_utc"]
    cands["h24_reference"] = dict(id="h24", name=os.path.basename(args.h24), y400_strength=y0["strength"], y400_p=y0["p_rank"],
                                  signed_divergence=before["signed_divergence"], arrangement_bin=before["arrangement_bin"],
                                  separation_violating_pairs=before["separation_violating_pairs"], kbar=before["kbar"], eta=before["eta"], coverage=before["coverage"])
    json.dump(cands, open(args.candidates, "w"), indent=1)

    if args.set_primary:
        man = json.load(open(args.manifest))
        man.update(generated_utc=ev["generated_utc"], note=note, geometry=g, r_min_px=args.r_min, candidate_label=pre["label"],
                   primary=files["nan"], compatibility=files["allfinite"], validation=dict(nan=v1, allfinite=v2), expected_dti=scen,
                   claims=dict(score_predicted=False, statement=(
                       "No score is predicted. Central expectation: this emission performs like h19-5 (live 0.1922) if its TP per emitted pixel q matches "
                       f"that artefact, i.e. DTI {q_lo:.2f}-{q_hi:.2f} at this budget (|G| 6k-15k). Scenario range {sc_lo:.2f}-{sc_hi:.2f} depends on whether placement skill survives the "
                       f"arrangement: lattice-type skill (1.9-2.7, measured on the group's dispersed artefacts) gives {min(lat):.2f}-{max(lat):.2f}, ridge-level skill (5.5+) "
                       f"gives {min(rid):.2f}-{max(rid):.2f}. The one controlled pair (pindrop ridge vs nodes) shows dispersal alone did not raise TP. The earlier "
                       "'0.12-0.34 projected' headline is superseded.")),
                   supersedes=dict(name="gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif",
                                   reason="audit: 400 m comb (strength 243, rank p 0.016), 931 dots violating the stated 400 m separation, lattice-like arrangement"))
        json.dump(man, open(args.manifest, "w"), indent=1)
        json.dump(man, open(os.path.join(args.out_dir, "latest.json"), "w"), indent=1)
        log("manifest + latest.json now point to", files["nan"]["name"])
    log("wrote", nan_path, allf_path)
    print("\nSUBMISSION NOTE:\n" + note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
