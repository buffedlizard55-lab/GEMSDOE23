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

---

## Continuation session #3 (2026-10-02, branch `arena/01a0fdcb-gemsdoe23`) — three passes

### Pass 1 — implementation

- Restored every input through the documented public git data bridge (3 core rasters, 12 external layers,
  24 live-scored anchor artefacts; SHA-256 re-verified) and refit the habitat model on them:
  reproducible on key fields (24 anchors, 95 layers, g=6000, k=8, α=0.3, nested-CV ρ=0.437).
- Implemented H-38 (cross-family azimuth coherence) and H-39 (shallow-residual potential-field edges) in
  `src/gems/orientation.py` with a 7-test physics-derived suite (analytic exp(−2πh/λ) attenuation targets).
- Built `scripts/analyze_h19_placement.py` → `docs/data/h19-placement-analysis.json`: per-artefact placement
  skill across admissible |G|, the h19-5 − h19-4 delta attribution, and exact leader-target algebra.
- Built `scripts/validate_new_hypotheses.py` (blocked SGMC-proxy protocol, same folds/target/budgets as the
  deep-ensemble admission gate; fixed-weight blends only, nothing fitted on the folds).
- Verified H-40 obtainability against the live USGS FDSN service (15,802 events M≥2.5 in the exact AOI box,
  1960→2026-10-01) and automated acquisition in `.github/workflows/seismicity.yml` (weekly, fail-closed).
- Wrote `docs/data/new-hypotheses.json`: the H-38…H-42 register with sources, transforms, stop rules.

### Pass 2 — adversarial review (what it caught)

- A cos²(2Δθ) azimuth kernel that scored *perpendicular* lines as agreeing — caught by the unit tests,
  corrected to cos²(Δθ); the erroneous form is recorded and must not be reintroduced.
- A hallucinated Coolbaugh DOI (10.1016/j.geothermics.2005.09.010) caught by web verification before it was
  published; replaced with the verifiable Coolbaugh 2002 GRC GIS study and 2005 NBMG Map 151. Coolbaugh 2002
  also measured earthquakes as the *lowest-weighted* evidence layer — recorded as a caution on H-40.
- First validation run OOM-killed (exit 137) when launched concurrently with ensemble training: rewritten to
  incremental pair/lidar means and bbox-cropped holdout scoring (identical score, ~1/5 RAM); heavy jobs then
  run strictly sequentially.
- `live_consistency` used a whole-raster mean (including zeros) as the enrichment base — fixed to the
  domain-only mean; and a str-vs-Path bug in the same function crashed the first completed run before the
  JSON was written — fixed and re-run to completion.
- Beat-leader feasibility claim on the results page initially overreached ("unreachable at |G| ≤ 10,000 for
  any emission of h19-5's or H30's size"); corrected to the exact algebra: h19-5's budget needs |G| ≳ 12,000,
  H30's smaller budget ≳ 8,000.
- Stale "rasters absent" copy across nine site locations (written for the pre-restore checkout) — all fixed,
  and the strict template validation was actually re-run against the restored official sample rather than
  re-worded: both H30 variants pass every hard requirement.

### Pass 3 — results and verification

- **Ensemble retrain (fresh seeds, identical config): admission gate failed a second time** — 0/5 folds beat
  a seed-matched random emission (mean DTI 0.0450 vs 0.1012; prior run 0.0440). Twice-reproduced negative
  result; detector weight stays 0 (flag I-08 updated). Phase 2 candidate decomposition regenerated from the
  fresh members (223 objects, 120 reported, epistemic share 0.145 of total variance).
- **H-38 rejected**: blocked-proxy mean DTI 0.0075 (1.22 % budget) vs random 0.0995, 0/5 folds; live-score
  consistency ρ = −0.06 (lidar-gated variant −0.33). Stop rule fired.
- **H-39 rejected as a standalone emission** (0.0151 vs random 0.0995, 0/5) **but it shows the strongest
  live-score consistency measured for any layer family**: ρ = +0.39, family-LOO-stable (min +0.23), top-4
  artefact enrichment +0.09 vs rest. Exactly one follow-up permitted: an h39 feature in the habitat
  regression under nested CV (compare against 0.437), never an emission.
- **Placement analysis (why h19-5 leads, what the leaders need)**: h19-5 has the highest placement skill of
  all 24 artefacts at every admissible |G| (7.2 at |G|=10k) with broad coverage (recall 0.64); the +0.0028
  delta over h19-4 rewards oriented scarp morphology over generic roughness and SGMC-gap ground; all four top
  artefacts emit zero pixels on the masked catalogue (median distance 0.86–1.49 km). Beating DARD's 0.3195
  needs skill ≈ 4.3–5.7 at H30's geometry with |G| = 10–15k — reachable only if |G| is near its upper bound
  and recall ≳ 0.5; unreachable at h19-5's budget below |G| ≈ 12k.
- Verification: `python -m unittest discover -s tests` — **97 tests OK** (90 prior + 7 orientation);
  `scripts/build_site.py` regenerated all 9 pages; `scripts/check_site.py` — PASS; strict submission-template
  validation re-run for both H30 variants against the restored official sample — all hard requirements pass
  (`docs/data/current-template-validation.json`); habitat refit reproducibility check — True.

### Stop-rule discipline this session

No submission slot was spent; no upload was made; the release gate stays BLOCKED. Both new mechanisms were
allowed to fail their pre-registered gates, and the failures are published on the site with the numbers.

---

## Continuation session #4 (2026-10-02, branch `arena/01a0fe19-gemsdoe23`) — three passes

### Pass 1 — implementation

- **Audited the live GitHub Pages deployment (`https://buffedlizard55-lab.github.io/GEMSDOE23/`) and found root-cause irregularity `I-33`.** Querying `gh api repos/buffedlizard55-lab/GEMSDOE23/pages` showed the repository uses `"build_type": "legacy"` with `"source": {"branch": "main", "path": "/"}`. Because the integration token cannot `PUT` `/pages` (`HTTP 403`), every push to `main` triggers GitHub's built-in `pages-build-deployment` after `.github/workflows/pages.yml`, serving the repository root `/` via Jekyll (`README.md`) and overwriting the custom `_site` deployment. As a result, `https://buffedlizard55-lab.github.io/GEMSDOE23/` previously had no `.tif` download link and root subpages (`/clustering.html`, etc.) returned 404.
- **Placed the downloadable `.tif` at the very top of the live site across both `/` and `/docs/` and in `README.md`.**
  - Updated `scripts/build_site.py` and `docs/assets/site.css` to add a persistent top-of-header `.header-download-bar` on all pages and moved `<section class="section section-top-download" id="download">` to be the **very first element inside `<main>`** (above `<section class="hero">`) on both `index.html` and `executive-summary.html`.
  - Updated `scripts/build_site.py` to generate all 9 static HTML pages at **both** `docs/<page>.html` and repository root `<page>.html` (with automatic relative-path adjustment to `docs/assets/`, `docs/downloads/`, and `docs/data/`), plus `.nojekyll` and `docs/.nojekyll`.
  - Updated `docs/assets/site.js` to fetch `data/leaderboard.json` with a fallback to `docs/data/leaderboard.json` so live client-side leaderboard hydration works identically at both `/` and `/docs/`.
  - Updated `.github/workflows/pages.yml` to run `python scripts/check_site.py`, commit back root `*.html` and `.nojekyll` alongside `docs/*.html`, and stage `_site` with both `docs/.` at `/` and `docs` at `/docs/`.
  - Added a prominent top-of-file downloadable `.tif` section at the very top of `README.md` (above `## 0. The standing brief`, preserving `## 0` verbatim).
- **Restored and verified all competition rasters, external layers, and live-scored anchors.**
  - Ran `python3 scripts/restore_workspace.py --all` (`docs/data/restore-receipt.json`: 3 official rasters, 15 external layers, 24 live-scored anchors, all SHA-256 verified) and verified `bash scripts/download_competition_data.sh` + `scripts/prepare_data.py` run autonomously in 14s with zero manual input.
  - Re-ran `scripts/validate_submission.py` against `data/sample_submission.tif` for both H30 GeoTIFF variants (`10/10` checks pass).
- **Executed the one permitted H-39 follow-up: 15-fold leave-one-family-out habitat nested-CV evaluation (`docs/data/new-hypothesis-validation.json`, `scripts/validate_new_hypotheses.py`).**
  - Baseline 95-layer habitat model reproduced to 16 decimal places (`nested_cv_spearman = 0.437391` at `|G|=6,000` and `8,000`, `0.436522` at `10,000`, `0.395652` at `12,000`, `0.408696` at `15,000`).
  - Univariate $|\rho|$ of `h39_shallow_residual_edges` (`0.3791` normalized / `0.3843` raw at `|G|=6,000`, rank 38/37 of 96) and `h39_shallow_residual_thickcover` (`0.3643` normalized / `0.3217` raw, rank 40/49 of 96) sit well below the top-$k$ selection cutoffs (`0.5548` at $k=8$, `0.5070` at $k=14$).
  - In unforced competition (`95 + H-39`), `0/15` leave-one-family-out folds select any `h39_*` layer across all 5 `|G|` trials, leaving nested-CV Spearman identical to baseline (`0.437391`, $\Delta\rho = 0.000000$).
  - When forced into every fold, raw `h39_*` layers degrade nested-CV Spearman (`0.383478`, $\Delta\rho = -0.053913$ for `thickcover`; `0.403478`, $\Delta\rho = -0.033913$ for `500m`), while `[0, 1]`-normalized forced inclusion moves nested-CV by at most `+0.008696` to `+0.011304` at `|G|=6,000` (10 units of $\sum d_i^2$ out of 2,300 on $n=24$) and degrades at `|G|=15,000` (`-0.024348`).
  - Verdict: H-39 does not survive unforced nested leave-one-family-out CV (`0/15` folds) and is formally retired without spending a weekly submission slot.

### Pass 2 — adversarial review (what it caught)

- **Caught contradictory checkout/template strings left over from PR #9 across JSON manifests, HTML pages, `README.md`, `docs/PROJECT_BRIEF.md`, and `docs/research/knowledge_base.md`.**
  - `docs/data/current-tiff-audit.json` still said `"exact sample-template comparison unavailable in this checkout"` while `docs/data/current-template-validation.json` recorded a 10/10 pass against `data/sample_submission.tif`. Reconciled `docs/data/current-tiff-audit.json`, `docs/data/submission-build.json`, `docs/data/submission-manifest.json`, `docs/data/candidates.json`, and `docs/data/irregularities.json` (`I-31` resolved, `I-33` added).
  - Caught duplicate consecutive template-validation sentences in `dl_block` on `index.html` and `executive-summary.html` and tightened the paragraph.
  - Caught stale H-36/H-37 wording on `hypotheses.html` claiming `"External rasters are not locally present"` right below the H-24–H-28 callout stating all 15 external bridge layers were restored; clarified that the 15 external bridge layers in `data/external/` (including the 100 m lidar-scarp product) are restored and verified, whereas raw 1 m/10 m 3DEP DEM tiles (H-36) and USGS MT conductance grids (H-37) are outside the bridge.
  - Caught a hardcoded `"rows 27 and 29"` string on `results.html` that drifted when `.github/workflows/pages.yml` refreshed `docs/data/leaderboard.json` at `2026-10-02T19:22:06+00:00` (where `0.1922` and `0.1894` are at ranks 28 and 30); replaced with dynamic rank lookup from `leaderboard.json`.
- **Caught test-suite hygiene issues under system Python and `-W default`.**
  - Fixed `ModuleNotFoundError: No module named 'numpy'` when running `python3 -m unittest discover -s tests` in system Python (without `.venv`) by adding `from __future__ import annotations`, `try/except ImportError` guards, and `@unittest.skipUnless(...)` in `tests/test_orientation.py`, `tests/test_spatial_pipeline_integration.py`, and `tests/test_submission_raster.py`.
  - Fixed a `SyntaxWarning` (`\d` in docstring of `src/gems/ensemble.py`), unclosed file `ResourceWarning`s in `scripts/record_score.py`, `scripts/update_leaderboard.py`, `tests/test_leaderboard.py`, and `tests/test_site.py`, and `/tmp/gems-leaderboard-rendered.html` temporary-file pollution in `tests/test_leaderboard.py`.
  - Added automated assertions in `scripts/check_site.py` and `tests/test_site.py` checking all 18 HTML pages (`docs/` + root), verifying `.header-download-bar` and `#download` placement before `<section class="hero">`, and forbidding contradictory checkout/template strings.

### Pass 3 — full verification against every requirement in the standing brief

- Regenerated all 18 static HTML pages (`docs/*.html` + root `/*.html`) and `docs/downloads/latest.json` via `.venv/bin/python scripts/build_site.py`.
- Ran `.venv/bin/python scripts/check_site.py`: `PASS: 18 HTML pages (docs/ + root); all local href/src targets, fragments, and top-of-page .tif download placement verified.`
- Ran `.venv/bin/python -W default -m unittest discover -s tests -v`: **102 tests ran in 23s — OK (0 skipped, 0 project warnings)**.
- Ran system `python3 -m unittest discover -s tests -v`: **102 tests ran — OK (numpy/rasterio-dependent tests cleanly skipped when run outside `.venv`)**.
- Ran `python3 -m compileall -q src scripts tests`, validated all JSON files in `docs/data/` and `docs/downloads/latest.json`, ran `node --check docs/assets/site.js`, `bash -n scripts/download_competition_data.sh`, and `git diff --check`: all passed.
