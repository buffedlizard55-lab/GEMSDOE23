#!/usr/bin/env python3
"""Build a research-candidate raster and run format preflight; this is NOT a release command.

    python scripts/build_submission_live.py            # candidate build + format preflight
    python scripts/build_submission_live.py --dry-run  # geometry + budget table only

The output is deliberately marked not approved for a competition slot. Only
``scripts/build_submission.py`` can produce a release artifact, and only with a verified
current-best record plus a passing spatial holdout against that exact incumbent.

Rank score (pre-registered weights, not tuned on the 24 live scores):
    S = 0.50 rank(H)  habitat model fitted to the 24 live public scores
      + 0.30 rank(V)  skill-weighted consensus of the 9 live-scored artefact families
      + 0.20 rank(P)  deep-ensemble mean probability (independent detector)
Emission: highest S first with a 400 m minimum separation. Budget selection retains a legacy
exploratory scenario heuristic; its assumptions are not validated against a current-best spatial
holdout and must not be interpreted as a score forecast or release recommendation.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from gems.layers import load_domain
from gems.emission import disperse_select, geometry, fp_relief


def expected_dti_from_q(area: float, q: float, g_size: float) -> float:
    """DTI from emitted area, TP per emitted pixel q and |G| (TP is capped at |G|)."""
    tp = min(q * area, g_size)
    fp = fp_relief(g_size) * area
    return tp / (tp + 0.2 * fp + 0.8 * (g_size - tp) + 1e-12)
from gems.submission import validate_submission, write_submission_raster

ANCH = ".cache/sib/anchors"
# Legacy candidate-builder inputs. These score values are public-row matches, not verified
# artifact attribution; the official leaderboard does not expose file hashes/submission IDs.
FAMILY_REPS = {          # one reported score per emission family
    "h19-5": 0.1922, "h16-1": 0.1855, "ens12-adopted": 0.1563, "lidarscarp-top2pct": 0.1461,
    "r7-nms3-dem10-scarp": 0.1294, "pindrop-v4-ridge": 0.1152, "h25-ctx-ridge": 0.1280,
    "h20-dem10-scarp-thin": 0.0921, "h28-dotted-ridge": 0.1839,
}
G_GRID = (6_000.0, 10_000.0, 15_000.0)   # legacy scenario grid from historical, unverified |G| analysis
# Legacy scenario-only budget parameters retained to reproduce the archived candidate geometry.
# The q values/weights are not calibrated or validated on a current-best spatial holdout and must
# not be described as expected score, placement probability, or evidence of competitive benefit.
Q_GRID = (0.04, 0.06, 0.08, 0.11)
Q_W = (0.25, 0.30, 0.25, 0.20)
BUDGET_SELECTION_NOTE = (
    "Exploratory internal q/|G| scenario heuristic only; assumptions unvalidated; no numerical "
    "DTI projections are persisted or published, and this process cannot approve release."
)
BUDGETS = (20_000, 30_000, 45_000, 60_000, 80_000, 100_000, 120_000, 150_000, 180_000, 220_000)
R_MIN_PX = 4                            # 400 m minimum separation between emitted pixels
W = dict(habitat=0.50, votes=0.30, ensemble=0.20)


def rank01(x: np.ndarray, domain: np.ndarray) -> np.ndarray:
    """Rank-normalise to [0, 1] inside the scored domain; 0 outside (the caller masks)."""
    from scipy.stats import rankdata
    out = np.zeros(x.shape, np.float64)
    v = np.asarray(x, np.float64)[domain]
    v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
    out[domain] = (rankdata(v, method="average") - 1.0) / max(1.0, v.size - 1.0)
    return out


def votes_map(domain: np.ndarray, g_ref: float = 10_000.0):
    """Skill-weighted consensus of the live-scored artefact families."""
    import rasterio
    acc = np.zeros(domain.shape, np.float32)
    detail = {}
    for name, lb in FAMILY_REPS.items():
        path = os.path.join(ANCH, name + ".tif")
        if not os.path.exists(path):
            continue
        with rasterio.open(path) as src:
            p = src.read(1).astype(np.float32)
        p = np.where(domain, np.nan_to_num(p, nan=0.0), 0.0)
        m = p > 0
        A = float(p.sum())
        from gems.emission import kernel_envelope
        kbar = float(kernel_envelope(m)[domain].mean())
        from gems.habitat import implied_tp
        tp = implied_tp(lb, A, g_ref)
        skill = tp / (g_ref * kbar) if kbar > 0 else 0.0
        acc += np.float32(skill) * m
        detail[name] = dict(live_dti=lb, area=A, kbar=kbar, implied_tp=tp, skill=skill)
    return acc, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--habitat", default="outputs/habitat_score.npy")
    ap.add_argument("--ensemble", default="outputs/full_mean.npy")
    ap.add_argument("--out-dir", default="docs/downloads")
    ap.add_argument("--manifest", default="docs/data/submission-manifest.json")
    ap.add_argument("--evidence", default="docs/data/submission-build.json")
    ap.add_argument("--template", default="data/sample_submission.tif")
    ap.add_argument("--tag", default="h24-dispersed-habitat")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    def log(*a): print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)

    footprint, catalogue, domain, tmpl = load_domain()
    H = np.load(args.habitat)
    log("habitat score loaded", H.shape, "finite", int(np.isfinite(H).sum()))
    V, vdetail = votes_map(domain)
    log("consensus votes", {k: round(v["skill"], 2) for k, v in vdetail.items()})
    # ---- admission gate for the detector -------------------------------------------
    # The deep ensemble is allowed to influence the submission only if its out-of-fold DTI
    # on the independent-compilation target beats a seed-matched random emission of the
    # same size on a majority of folds (scripts/evaluate_oof.py).  This is the local form
    # of the standing rule "never spend a slot on something that has not beaten the
    # holdout best"; it is applied automatically so the decision cannot be forgotten.
    gate = dict(path="docs/data/oof-evaluation.json", found=False, passed=False, reason="not evaluated")
    if os.path.exists(gate["path"]):
        ev = json.load(open(gate["path"]))
        gate["found"] = True
        gate["passed"] = bool(ev.get("gate_passed"))
        gate["mean_dti"] = ev.get("mean_dti")
        gate["mean_random"] = ev.get("mean_random")
        gate["folds_beating_random"] = ev.get("folds_beating_random")
        gate["n_folds"] = ev.get("n_folds")
        gate["reason"] = ("out-of-fold DTI beat the random-emission control on a majority of folds"
                          if gate["passed"] else "out-of-fold DTI did not beat the random-emission control")
    else:
        gate["reason"] = "detector not evaluated (docs/data/oof-evaluation.json missing)"
    have_ens = os.path.exists(args.ensemble) and gate["passed"]
    P = np.load(args.ensemble) if have_ens else np.zeros(domain.shape, np.float32)
    if not os.path.exists(args.ensemble):
        gate["reason"] = "ensemble map not built yet"
    if not have_ens:
        log(f"detector EXCLUDED from the emission: {gate['reason']}")
    w = dict(W)
    if not have_ens:
        tot = w["habitat"] + w["votes"]
        w = {k: (v / tot if k != "ensemble" else 0.0) for k, v in w.items()}

    S = (w["habitat"] * rank01(np.where(np.isfinite(H), H, 0.0), domain)
         + w["votes"] * rank01(V, domain)
         + w["ensemble"] * rank01(P, domain))
    S[~domain] = -np.inf
    log("rank score combined; weights", w)

    geometry_table = []
    exploratory_objective = []
    for b in BUDGETS:
        mask = disperse_select(S, domain, b, R_MIN_PX)
        g = geometry(mask, domain)
        geometry_table.append(dict(budget_requested=b, **{k: float(v) for k, v in g.items()}))
        # Retain a legacy scenario objective only to reproduce the archived candidate budget.
        # It is not written to public records, is not validation, and cannot approve release.
        scenario_values = []
        for G in G_GRID:
            dtis = [expected_dti_from_q(g["area"], q, G) for q in Q_GRID]
            scenario_values.append(float(np.dot(dtis, Q_W) / sum(Q_W)))
        exploratory_objective.append(min(scenario_values))
        log(f"budget={b:8d} px area={g['area']:8.0f} eta={g['eta']:.3f} coverage={g['coverage']:.3f}")

    best_index = max(range(len(geometry_table)), key=lambda i: exploratory_objective[i])
    best = geometry_table[best_index]
    A = int(round(best["area"]))
    log(f"chosen candidate budget = {A:,} px; {BUDGET_SELECTION_NOTE}")
    mask = disperse_select(S, domain, A, R_MIN_PX)
    g = geometry(mask, domain)
    os.makedirs("outputs", exist_ok=True)
    np.save("outputs/rank_score.npy", np.where(domain, S, -np.inf).astype(np.float32))
    np.save("outputs/emission_mask.npy", mask)

    if args.dry_run:
        json.dump(dict(chosen=A, geometry=g, geometry_table=geometry_table,
                       budget_selection_note=BUDGET_SELECTION_NOTE,
                       release_decision="BLOCKED: no registered current-best spatial holdout"),
                  open("outputs/budget_table.json", "w"), indent=1)
        log("dry run: wrote outputs/budget_table.json (geometry only; no score projection)")
        return 0

    # graded hedge: the emitted core is 1.0; pixels immediately beside a core pixel whose
    # ensemble members disagree (high epistemic variance) get 0.5 - lateral position insurance
    prob = np.where(domain, np.clip(P, 0, 1), 0.0).astype(np.float32) if have_ens else np.zeros(domain.shape, np.float32)
    # the graded hedge needs a disagreement signal worth paying for; it is only emitted when
    # the detector passed the same admission gate as the ranking
    have_epi = os.path.exists("outputs/full_epistemic.npy") and gate["passed"]
    epi = np.load("outputs/full_epistemic.npy") if have_epi else np.zeros(domain.shape, np.float32)
    from scipy.ndimage import binary_dilation
    ring = binary_dilation(mask, np.ones((3, 3), bool)) & ~mask & domain & ~catalogue
    if have_epi and ring.any() and float(epi[ring].max()) > 0:
        epi_hi = ring & (epi >= np.quantile(epi[ring], 0.75))
    else:
        # no usable member disagreement: emit no halo rather than a hedge with no evidence
        epi_hi = np.zeros(domain.shape, bool)
        log("graded hedge skipped: no admitted disagreement signal (detector gate not passed)")
    values = np.zeros(domain.shape, np.float32)
    values[mask] = 1.0
    values[epi_hi] = 0.5
    values[~footprint] = 0.0
    mass = float(values[domain].sum())
    log(f"graded hedge: core {int(mask.sum()):,} px at 1.0, halo {int(epi_hi.sum()):,} px at 0.5, total mass {mass:,.0f}")

    sha = hashlib.sha256(values.tobytes()).hexdigest()[:8]
    date = time.strftime("%Y%m%d", time.gmtime())
    stem = f"gemsdoe23-{args.tag}-{date}-{sha}"
    os.makedirs(args.out_dir, exist_ok=True)
    nan_path = os.path.join(args.out_dir, stem + "-nan.tif")
    allf_path = os.path.join(args.out_dir, stem + "-allfinite.tif")
    write_submission_raster(values, args.template, nan_path)
    allf = np.where(footprint, values, 0.0).astype(np.float32)
    write_submission_raster(allf, args.template, allf_path, outside="zero")
    v1 = validate_submission(nan_path, args.template)
    v2 = validate_submission(allf_path, args.template)
    log("validation nan:", v1["passed"], " allfinite:", v2["passed"])

    def sha256(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 20), b""):
                h.update(c)
        return h.hexdigest()

    note = (f"GEMSDOE23 QA ONLY — not for upload | research candidate | {int(g['area']):,} px | "
            f"format preflight only; current-best spatial holdout BLOCKED | sha256 {sha256(nan_path)[:8]}")
    release_decision = dict(
        status="BLOCKED",
        eligible_for_submission=False,
        approved=False,
        reason="This builder checks candidate format only. No passing comparison against a verified registered current-best spatial OOF map exists.",
        current_best_registry="docs/data/current-holdout-best.json",
    )
    man = dict(schema_version=2,
               generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               template_sha256=sha256(args.template), weights=w, r_min_px=R_MIN_PX,
               artifact_role="research_candidate_preflight_only",
               budget_selection_note=BUDGET_SELECTION_NOTE,
               score_projection=dict(status="NOT_REPORTED", reason="No validated current-best spatial holdout; internal scenario parameters are not an empirical score model."),
               release_decision=release_decision,
               primary=dict(name=os.path.basename(nan_path), href="downloads/" + os.path.basename(nan_path),
                            bytes=os.path.getsize(nan_path), sha256=sha256(nan_path), variant="nan-outside-footprint",
                            format_preflight_passed=v1["passed"], release_approved=False, ok_to_upload=False),
               compatibility=dict(name=os.path.basename(allf_path), href="downloads/" + os.path.basename(allf_path),
                                  bytes=os.path.getsize(allf_path), sha256=sha256(allf_path),
                                  variant="zeros-outside-footprint-nodata-zero", format_preflight_passed=v2["passed"],
                                  release_approved=False, ok_to_upload=False,
                                  advisory="nodata=0 differs from the official NaN convention; no online uploader test"),
               note=note, geometry=g,
               detector_gate=dict(status="historical_not_reproduced", source="docs/data/oof-evaluation.json",
                                  candidate_influence_used=bool(have_ens), release_authority=False),
               validation=dict(nan=v1, allfinite=v2))
    json.dump(man, open(args.manifest, "w"), indent=2)
    json.dump(dict(schema_version=2, generated_utc=man["generated_utc"], status="QA_CANDIDATE_ONLY",
                   chosen_budget=A, geometry=g, geometry_candidates=geometry_table,
                   weights=w, budget_selection_note=BUDGET_SELECTION_NOTE,
                   detector_gate=man["detector_gate"], artifact_role=man["artifact_role"],
                   release_decision=release_decision, score_projection=man["score_projection"]),
              open(args.evidence, "w"), indent=2)
    log("wrote research candidate", nan_path, allf_path, args.manifest, args.evidence)
    print("\nCANDIDATE NOTE (NOT FOR AN UPLOAD):\n" + note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
