# Implementation and review log — 2026-10-02

This log records deliberate implementation/review passes. It is not evidence that a model passed the spatial holdout or that an upload is approved. The first review below is retained as a historical pre-integration record; the continuation review immediately following it supersedes its filesystem, leaderboard-test, and PR-status details.

## Continuation review — 2026-10-02 (post-main integration, three passes)

### Pass 1 — reconcile evidence and release state

- Re-read the README starting brief, persistent project brief, knowledge base, current holdout registry, submission manifests, current leaderboard capture, and irregularity register before editing.
- Confirmed `data/training_features.tif`, `data/labels.tif`, `data/sample_submission.tif`, and `data/external/` are absent in the current checkout; historical restore receipts are not evidence of current availability. The prior local-file statement is now explicitly historical.
- Re-read the official 50-row rendered leaderboard snapshot at `2026-10-02T16:54:29+00:00`: DARD 0.3195, nchuzhoy 0.3128, alexoktaba 0.3042; user-reported 0.3049 is absent. 0.1922 is displayed at rank 27 and 0.1894 at rank 29. Neither row identifies an H19 TIFF/account.
- Queried PR #9 on GitHub: OPEN, base `main`, head `arena/01a0fd30-gemsdoe23` at `24c91f86031afca70c858380e83de53193a2c34b`, `mergeable=CONFLICTING`; its then-current check run was successful. A local origin/main merge was in progress with no unresolved conflict paths; local state was not treated as a GitHub merge.

### Historical Pass 2 — adversarial review before main integration

- Set every existing H29/H30 primary/compatibility record in `submission-manifest.json`, `candidates.json`, and build records to `ok_to_upload=false` and `release_approved=false`; added an explicit BLOCKED release decision bound to the current holdout-registry hash. Preserved prior format-validation reports as historical evidence, not approval.
- Removed current score-forecast language. Kept conditional metric algebra only as explicitly unvalidated sensitivity. Added a score reconciliation callout and corrected the leaderboard test: `smrtdoog5` is rank 27 in this capture, not the stale rank 26 assertion.
- Added H-34–H-37 as four distinct, unimplemented hypotheses with exact layer-bank keys, physical signatures, catalogue-missing-fault rationale, code differences, ordinal potential/cost, official/free source links, and stop rules. Added explicit source-availability and coverage caveats.
- Reworked site and project copy to mark H30/H29 QA-only, the holdout BLOCKED, current source rasters absent, and ensemble/coverage values historical. Added a direct current TIFF audit record; it does not compare against the absent template.

### Pass 3 — rebuild and verification

- Rebuilt the static site: **9 HTML pages**. `scripts/check_site.py`: all local links, asset paths and fragments resolve.
- Fresh standalone `scripts/audit_reference_tif.py` on H30 primary and all-finite TIFFs: both classic single-band IEEE float32, 3292×3730, EPSG:32611, 100 m, finite values `[0,1]`, no infinities; primary has 7,111,787 NaNs outside. Both outputs match their manifest SHA-256/byte counts. **Exact official-template comparison was not checked** because `data/sample_submission.tif` is absent; `docs/data/current-tiff-audit.json` records this distinction.
- `/tmp/gemsdoe-test-venv/bin/python -m unittest discover -s tests -v`: **90 tests passed, 1 skipped** (the external GeoDAWN outline fixture is not present). An initial run found one stale assertion for the 0.1922 leaderboard row at rank 26; corrected to rank 27 per the captured board, then the full suite passed.
- `python3 -m py_compile` on edited scripts, `compileall` for `scripts/`, `src/`, `tests/`, all 31 repository data JSON files plus `downloads/latest.json`, `node --check`, `bash -n` for shell scripts, and `git diff --check`: all passed.
- The scientific release gate remains **BLOCKED**; no spatially blocked independent uncatalogued-fault holdout, model retraining, external-layer coverage audit, or online uploader test was possible. No competition slot was used. PR #9 status must be rechecked after pushing this integration; a GitHub merge does not approve a scientific release.


## Historical Pass 1 — evidence intake and pre-integration state

- Read `README.md`, `docs/PROJECT_BRIEF.md`, the prior knowledge base, submission/holdout manifests, format-validation report, leaderboard snapshot/status, and irregularity register before changing the site.
- At first intake, the core rasters/prepared arrays were present and their hashes matched the public bridge manifest, not an independent organizer-host signature. After integrating the newer main-branch clustering work, rechecked the current filesystem: `data/training_features.tif`, `data/labels.tif`, `data/sample_submission.tif`, and `data/external/` are absent. The earlier local-file statement is historical and must not be used as a current availability claim.
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

## Historical Pass 3 — implementation and verification before current edits

- Regenerated the static pages with `python scripts/build_site.py` after the changes above.
- Initial verification run: `python -m py_compile ...` and `git diff --check` passed. The first `unittest` run exposed four failures and one error: the new manual-snapshot state needed to use the documented JSON schema, the manifest needed its full hard-check detail for the existing artifact test, and the new review-log link had to exist. These were implementation issues, not holdout results; corrections were applied.
- Final verification rerun: `.venv/bin/python -m unittest discover -s tests -v` — **65 tests passed**. `python scripts/check_site.py` — **8 HTML pages, all local links/fragments resolve**. `python scripts/build_site.py` — **8 pages regenerated**. `py_compile` for the touched Python scripts and `git diff --check` — **passed**.
- Re-ran `scripts/validate_submission.py` against `data/sample_submission.tif` for H24 NaN, H24 all-finite and H19-5 NaN TIFFs. Each report passed all hard requirements for single band, float32, EPSG:32611, dimensions/affine, finite in-footprint `[0,1]`, and outside-footprint nodata; the all-finite H24 nodata=0 difference is advisory. Independent SHA-256 checks matched the manifest values.
- Checked leaderboard ordering/schema (50 sequential ranks, scores in descending order); the file is explicitly a dated manual capture. The automated live refresher and GitHub Actions workflow were not exercised.
- One Rasterio `PendingDeprecationWarning` appears in a synthetic unit test; the test passes. Model training, fresh ensemble inference, a valid independent spatial holdout, online uploader testing, PR creation, and merge have not been run in this pass.

## Remaining work and limitations

1. Recheck PR #9, required checks, and Pages deployment on GitHub after the integrated branch is pushed. Merge completion is separate from scientific release approval.
2. Restore the official rasters and exact sample template through documented, access-control-compliant sources; verify hashes, terms, CRS/grid, coverage and metadata.
3. Rerun strict exact-template format validation for H30 variants after restoration; no online uploader test exists.
4. Acquire independent uncatalogued-fault truth, freeze buffered spatial folds and equal-budget baselines, and register exact current-best OOF hashes. Until then, the release gate stays BLOCKED and no slot is used.
5. Implement H-34 first after restoring/validating its input bands; evaluate H-35–H-37 as separate pre-registered tests. Numeric score benefit is not forecastable without valid holdout evidence.
6. Retrain/calibrate independent ensemble members and regenerate Phase 2 uncertainty/coverage outputs before reuse; saved reports are historical.
