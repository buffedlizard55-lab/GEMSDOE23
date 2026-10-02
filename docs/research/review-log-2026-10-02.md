# Implementation and review log — 2026-10-02

This log records three deliberate passes over the request. It is not evidence that a model passed the spatial holdout or that an upload is approved.

## Pass 1 — evidence intake and current-state audit

- Read `README.md`, `docs/PROJECT_BRIEF.md`, the prior knowledge base, submission/holdout manifests, format-validation report, leaderboard snapshot/status, and irregularity register before changing the site.
- Confirmed the core competition rasters and prepared arrays are present locally; `data/external/` is absent. The recorded input hashes match the public bridge manifest, not an independent organizer-host signature.
- Re-hashed H24 NaN, H24 all-finite, H19-5 NaN and official template files. H24 hashes: `e29e8f04e048a4aa210edbc1128dc39703e9271a11c02a5a391c7753339b0125` (NaN) and `aac907db6aadc3d07a4eeb2531a0be200ee0143599ab304921e4f4f742fbc02a` (all-finite); official template hash `2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc`.
- Read the official DrivenData leaderboard page through the Arena page reader. Persisted a 50-row manual snapshot dated 2026-10-02; the capture tool did not expose an exact retrieval time. The top displayed rows were DARD 0.3195, alexoktaba 0.3042, and Batik Shirt Brothers 0.2998. The reported 0.3049 was absent. Rows at 0.1922 and 0.1894 remain score matches only; one older passage calls 0.1894 the highest while listing 0.1922 elsewhere, even though 0.1922 is numerically larger.
- Read the public H19 hub. It describes four strategy families (fault-length/power-law, thermal/geochemical, 3DEP topography, geopotential lineaments) and claims 4/4-fold gains while also saying H19-4/H19-5 are “not live-scored yet.” The local checkout lacks the fold predictions/config/truth needed to reproduce those claims.

## Pass 2 — adversarial scientific, UX, and release-gate review

- Kept `docs/data/current-holdout-best.json` at `BLOCKED`; the historic catalogue-quadrant validation report remains `WITHDRAWN`. No independent uncatalogued-fault truth/current-best OOF map is available, so no holdout claim or submission-slot decision can be made.
- Found the old generated manifest marked H24 variants `ok_to_upload=true` despite the blocked holdout. Replaced it with explicit `release_decision.status=BLOCKED`, false approval flags, hard-format checks, and no numerical score projection.
- Removed unsupported score forecasts and superseded claims from the homepage, submission guide, evidence and leaderboard pages. Made the first-page TIFF buttons explicitly QA-only; made upload instructions conditional on a future spatial-holdout approval; documented that live uploader acceptance remains untested.
- Corrected the 0.3049 vs 0.3195/0.3042 mismatch and the internal “0.1894 highest” vs 0.1922 wording conflict. Added attribution, public/private/final-round, external-data-availability, and historical-model caveats.
- Re-ranked four distinct hypotheses (H-29–H-32) by ordinal potential/cost. H-29 remains unimplemented and the top-candidate holdout is explicitly blocked; no submission slot was used.
- Reworked the uncertainty page to preserve the independently trained deep-ensemble decomposition/policy while labeling old JSON values as historical and not reproduced. High epistemic disagreement may raise review priority only in independently verified under-surveyed terrain; it warrants suspicion in well-surveyed terrain.
- Corrected the CI push filter to include the fixed Arena session branch `arena/01a0fd30-gemsdoe23` so branch pushes can run the project checks.

## Pass 3 — implementation and final verification

- Regenerated the static pages with `python scripts/build_site.py` after the changes above.
- Initial verification run: `python -m py_compile ...` and `git diff --check` passed. The first `unittest` run exposed four failures and one error: the new manual-snapshot state needed to use the documented JSON schema, the manifest needed its full hard-check detail for the existing artifact test, and the new review-log link had to exist. These were implementation issues, not holdout results; corrections were applied.
- Final verification rerun: `.venv/bin/python -m unittest discover -s tests -v` — **65 tests passed**. `python scripts/check_site.py` — **8 HTML pages, all local links/fragments resolve**. `python scripts/build_site.py` — **8 pages regenerated**. `py_compile` for the touched Python scripts and `git diff --check` — **passed**.
- Re-ran `scripts/validate_submission.py` against `data/sample_submission.tif` for H24 NaN, H24 all-finite and H19-5 NaN TIFFs. Each report passed all hard requirements for single band, float32, EPSG:32611, dimensions/affine, finite in-footprint `[0,1]`, and outside-footprint nodata; the all-finite H24 nodata=0 difference is advisory. Independent SHA-256 checks matched the manifest values.
- Checked leaderboard ordering/schema (50 sequential ranks, scores in descending order); the file is explicitly a dated manual capture. The automated live refresher and GitHub Actions workflow were not exercised.
- One Rasterio `PendingDeprecationWarning` appears in a synthetic unit test; the test passes. Model training, fresh ensemble inference, a valid independent spatial holdout, online uploader testing, PR creation, and merge have not been run in this pass.

## Remaining work and limitations

1. Obtain an independent uncatalogued-fault truth and exact registered current-best OOF predictions, then run the frozen spatial holdout before any release or slot.
2. Implement H-29 with pre-registered transforms/folds and synthetic tests; assess H-30 through H-32 only after checking data coverage, metadata, CRS, licensing and scale.
3. Retrain independently initialized ensemble members with retained configs/checkpoints; regenerate per-candidate aleatoric/epistemic values and a sourced survey-coverage mask.
4. Refresh the public leaderboard again from an official capture, recording its date, available time precision, and method; explicitly say when an exact retrieval time is unavailable. The current committed snapshot is dated, not continuous.
5. Test the actual competition uploader only after release approval; the all-finite range-error fallback is template-preflighted but has not been live-upload tested.
