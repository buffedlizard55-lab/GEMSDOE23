# Persistent project brief — read before every project session

**Last evidence check:** 2026-10-02 (UTC). This file is the standing brief for GEMSDOE23. It is intentionally maintained in-repository so future sessions start from the same goal, evidence, limitations, and decision rules rather than repeating research from memory.

## Mission and success criteria

Build a reproducible, auditable research and submission system for the [DOE GEMS Prize / DrivenData competition 306](https://www.drivendata.org/competitions/306/competition-doe-gems/). The task is to predict geological fault traces in the GeoDAWN region, not to claim geothermal vents have been discovered. A geologic fault may be evidence relevant to geothermal exploration, but a fault prediction is not itself a verified geothermal vent or resource.

Long-term objective: improve the chance of placing highly on both the public competition and the final expert-reviewed prize evaluation, while producing useful, defensible geological evidence. Do not promise a score or prize. Keep all sources, assumptions, data lineage, configurations, model seeds, spatial validation results, output hashes, and irregularities auditable.

### Scientific and operational requirements

1. Read the official competition description, data page, about page, rules, and reference solution before changing the modeling or submission contract.
2. Store knowledge from official, trusted sources with links and a statement of what each source does—and does not—establish. Re-check changing pages, especially the leaderboard and deadlines.
3. Keep an easily discoverable, one-click `.tif` download on the first screen of the site. Provide an executive-summary/upload-guide subpage with exact steps, a unique filename, and a short identifying note.
4. Prevent the submission rejection `Predicted values must be in range [0, 1]`. Use the official sample submission as the mask/grid template, ensure all prediction pixels in the official footprint are finite and in `[0, 1]`, and set outside-footprint pixels to the official null/NaN convention. Validate band count, dtype, CRS, dimensions, transform, nodata, and values after writing and re-reading the file.
5. Train an actual deep ensemble: separately initialized and separately trained model instances (not a single model with test-time dropout), following the deep-ensemble principle in Lakshminarayanan, Pritzel & Blundell (NeurIPS 2017). Calibrate predictions out of fold and keep inference deterministic.
6. Report uncertainty to human reviewers for every proposed candidate: ensemble mean, epistemic disagreement, conditional/aleatoric uncertainty, total uncertainty, survey-coverage provenance, and interpretation. The competition upload remains one-band; uncertainty maps/CSV are companion review products.
7. Test the premise that missing catalogue faults correlate with low historical survey coverage. The competition states that known-fault data are incomplete and may be inaccurate; it does **not**, by itself, prove that omissions are caused by sparse fieldwork in particular terrain. Never label an epistemic-uncertainty hotspot as a survey gap without an independent coverage proxy.
8. Generate three to five new geological hypotheses before implementation. Each must name exact layers, physical signature/transform, why it may reveal faults absent from the USGS/INGENIOUS catalogue, how it differs from previous attempts, expected DTI direction/rank, cost, source needs, and validation gate.
9. Use frozen spatially blocked holdout folds, with spatial buffers and equal-compute/equal-pixel-budget comparisons. A new method must beat the current holdout incumbent under a preregistered rule before it is considered for a weekly upload. Do not use public leaderboard scores as a substitute for local validation, and do not spend a submission slot on an unvalidated idea.
10. Keep a dated current leaderboard feed so people do not have to manually refresh and compare every project page. Clearly separate public score, holdout proxy score, private score, and Phase 2 score.
11. Run three review passes: (1) implement and test; (2) review bugs, assumptions, and edge cases; (3) re-check every requirement and rerun tests. Report any blocker rather than inventing a result.
12. The official rules require disclosure of generative-AI use in the submission narrative when applicable. Document the use accurately; the competitor remains responsible for truthfulness and authorship representations.

## Core values

### Maximize P(Win)

Use expected value, evidence quality, risk, and opportunity cost in every decision. A novel method is not automatically a good method. Measure, compare, conserve the limited feedback submissions, and prioritize a method that can generalize beyond the public leaderboard.

### Own the Outcome

Own the result end-to-end: data access, model, validation, geospatial format, interpretation, source audit, and live feed. Fix what can be fixed. Make blockers visible, learn from a weak result, and do not outsource accountability to a future session.

## Competition facts verified from official sources

| Fact | Verified statement | Source |
|---|---|---|
| Task | Predict faults/structures indicative of geothermal resources in the GeoDAWN region. | [Problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/) |
| Labels | Training labels include existing fault data; experts have identified additional faults absent from the public database for test/evaluation. Existing ground truth is incomplete and may be inaccurate. | [Problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/) |
| Metric | Distance-weighted Tversky index; `alpha=0.2`, `beta=0.8`; triangular support `R=300 m` on the competition page. | [Performance metric](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/#performance-metric) |
| Submission raster | One band, 32-bit float, UTM zone 11N / EPSG:32611, 100 m resolution, same bounds/grid as training, predictions in `[0,1]`, null or NaN outside bounds. | [Submission format](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/#submission-format) |
| Public/private and prize phases | Public leaderboard is not the private Phase 1 score; experts revise labels, and Phase 2 rescoring uses the updated labels. A competitor must select one final submission for both phases. | [Official DOE/NLR rules PDF, §§1.1, 3.4–3.6](https://docs.nlr.gov/docs/fy26osti/96647.pdf) |
| Feedback upload limit | Official rules say automated feedback submissions are allowed up to three per week, subject to the competition website. | [Official DOE/NLR rules PDF, §3.4](https://docs.nlr.gov/docs/fy26osti/96647.pdf) |
| AI disclosure | The official rules allow generative AI but require its use to be indicated in the narrative when applicable. | [Official DOE/NLR rules PDF, §3.2](https://docs.nlr.gov/docs/fy26osti/96647.pdf) |
| Provided features | The competition describes GeoDAWN/INGENIOUS-derived features and 1 m DEM links; the data tab is account-gated. | [Problem/data page](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/) · [data tab](https://www.drivendata.org/competitions/306/competition-doe-gems/data/) |
| Reference baseline | A public reference implementation is maintained by DrivenData. | [Reference repository](https://github.com/drivendataorg/gems-prize-reference-solution) |

## Current research shortlist — 2026-10-02

After comparing newly discovered USGS data leads with the supplied H19/H20 methods and this repository's code, the ranked unvalidated geological tests are: **(1)** GeoDAWN radiometric K/eU/eTh ratio/gradient features corroborated by independent structure (official USGS/DOE DOI `10.5066/P93LGLVQ`, CC0; public GeoTIFF archives listed, but not downloaded/aligned); **(2)** 3DEP drainage deflection and channel-profile breaks (public-domain source; the 1 m index query found only an intersecting dissolved polygon, not exact tile/full-footprint coverage); **(3)** depth-coherent upper-crustal MT conductance boundaries (USGS DOI `10.5066/P9TWT2LU`, five public GeoTIFFs listed; exact valid-pixel support/alignment/reuse terms not checked). Ranking, layer transforms, physical rationale, prior-art differences, cost, and stop conditions are in [`docs/hypotheses.html`](hypotheses.html) and the source register in [`docs/sources.html`](sources.html). No new geological feature has been implemented or validated. The previously coded edge-consensus path is an unscored diagnostic, not the top-ranked hypothesis or a real holdout incumbent. The radiometric test must beat a reproducible baseline on frozen, buffered spatial folds before a weekly slot is considered.

## Supplied submission-score history (user-provided; not all artifact/account links independently verified)

The entries below preserve the score list in the project request. A blank or dash means the request supplied no score; it is not zero. The project/research pages linked by the user are not official score provenance. Where possible, compare them with the official leaderboard and record the date and identity confidence.

| Project/site | Entry | Score supplied |
|---|---|---:|
| [GEMSDOE](https://buffedlizard55-lab.github.io/GEMSDOE/docs/index.html) | `gems-submission-20260925T001403Z-7f00890a` | 0.1563 |
| [6GEMSDOE](https://buffedlizard55-lab.github.io/6GEMSDOE/) | `gems6_hgb88-topk03_33cec71ff0` | 0.0286 |
| [GEMSDOE3](https://buffedlizard55-lab.github.io/GEMSDOE3/docs/index.html) | `pindrop-v4-nodes-20260925T152420Z-f347b70daa` | 0.1193 |
| [GEMSDOE3](https://buffedlizard55-lab.github.io/GEMSDOE3/docs/index.html) | `pindrop-v4-discovery-20260925T152423Z-37f9d5b855` | 0.0830 |
| [GEMSDOE3](https://buffedlizard55-lab.github.io/GEMSDOE3/docs/index.html) | `pindrop-v4-ridge-20260925T152422Z-4e03fc9705` | 0.1152 |
| [GEMSDOE2](https://buffedlizard55-lab.github.io/GEMSDOE2/docs/index.html) | `gemsdoe2-dual-family-union-20260925T160406Z-f68e590f` | 0.1560 |
| [GEMSDOE4](https://buffedlizard55-lab.github.io/GEMSDOE4/) | `gems-submission-20260926T163915Z-237f0063` | 0.0343 |
| [5GEMSDOE](https://buffedlizard55-lab.github.io/5GEMSDOE/docs/index.html) | `gems-submission-20260926T175114Z-7f00890a` | 0.1563 |
| [7GEMSDOE](https://buffedlizard55-lab.github.io/7GEMSDOE/) | `lidarscarp-ridge-top2pct-36c3a3f341c8` | 0.1461 |
| [8GEMSDOE](https://buffedlizard55-lab.github.io/8GEMSDOE/) | `Hedge-v2_submission` | 0.1563 |
| [GEMSDOE9](https://buffedlizard55-lab.github.io/GEMSDOE9/docs/index.html) | `2314b599` | 0.0107 |
| [11GEMSDOE](https://buffedlizard55-lab.github.io/11GEMSDOE/docs/index.html) | `gems-structural-area06-v1` | 0.0202 |
| [12GEMSDOE](https://buffedlizard55-lab.github.io/12GEMSDOE/docs/index.html) | `r7-nms3-dem10-scarp_0c9199f14e62` | 0.1294 |
| [12GEMSDOE](https://buffedlizard55-lab.github.io/12GEMSDOE/docs/index.html) | `r7-nms3-dem10-scarp_0c9199f14e62_allfinite` | 0.1294 |
| [15GEMSDOE](https://buffedlizard55-lab.github.io/15GEMSDOE/docs/index.html) | `gems-tso1-20260929T005627Z-conj_alteration_mag` | 0.0782 |
| [14GEMSDOE](https://buffedlizard55-lab.github.io/14GEMSDOE/docs/index.html) | `GEMS_r5-geom-horse-ensemble_20260929T154852Z_ccbe1de0_site_e96e942f` | 0.0020 |
| [17GEMSDOE](https://buffedlizard55-lab.github.io/17GEMSDOE/) | `17GEMSDOE_F-ensemble-2pct_20260930T050626Z` | 0.0187 |
| [18GEMSDOE](https://buffedlizard55-lab.github.io/18GEMSDOE/) | `H19-C_20260930T212401Z_c11e495e` | 0.0297 |
| [19GEMSDOE](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html) | `h19-4-multiline-corroborated-openness-thermal-pop-20260930-691e4dfa-nan` | 0.1894 |
| [19GEMSDOE](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html) | `h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan` | 0.1922 |
| [GEMSDOE10](https://buffedlizard55-lab.github.io/GEMSDOE10/) | `h16-continuation-20260927T065521077735Z-3431b83c7c` | 0.0461 |
| [GEMSDOE10](https://buffedlizard55-lab.github.io/GEMSDOE10/) | `h20-dem10-scarp-thin-20260927T155223039488Z-ffc91a1686` | 0.0921 |
| [GEMSDOE10](https://buffedlizard55-lab.github.io/GEMSDOE10/) | `H25-ctx-ridge-20260927T232947704150Z-6452ae1d00` | 0.1280 |
| [GEMSDOE10](https://buffedlizard55-lab.github.io/GEMSDOE10/) | `h28-dotted-ridge-20260928T020256236880Z-6452ae1d00` | 0.1839 |
| [13GEMSDOE](https://buffedlizard55-lab.github.io/13GEMSDOE/) | `20261001_r13-lattice-s5_v2_nan-outside` | 0.0904 |
| [16GEMSDOE](https://buffedlizard55-lab.github.io/16GEMSDOE/docs/index.html) | `h16-1-topo-geophys-baseline-ridges-20260930-df20f65e-nan` | 0.1855 |
| [16GEMSDOE](https://buffedlizard55-lab.github.io/16GEMSDOE/docs/index.html) | `h18-3a-topo-geophys-x-complexity-prior-20260930-c502dfab-nan` | 0.0976 |
| [16GEMSDOE](https://buffedlizard55-lab.github.io/16GEMSDOE/docs/index.html) | `h18-4-usgs-geologic-map-faults-gap-20260930-aef8f42c-nan` | not supplied |
| [20GEMSDOE](https://buffedlizard55-lab.github.io/20GEMSDOE/docs/index.html) | `h20-1-sarnnpu-powerlaw-pi0363-tilt-wingcrack-20260930-be0e8f6b-nan` | not supplied |
| [20GEMSDOE](https://buffedlizard55-lab.github.io/20GEMSDOE/docs/index.html) | `h20-5-continuous-pu-proxy-unverified-20260930-824ce73a-nan` | not supplied |
| [GEMSDOE21](https://buffedlizard55-lab.github.io/GEMSDOE21/) | `h19-4-reference-20260930-691e4dfa` | 0.1894 |
| 22–27GEMSDOE | no entry supplied | not supplied |

## Score interpretation and research question

The request calls `0.1894` the best local score, while also listing H19-5 at `0.1922`. The full listed local history's highest numeric value is therefore `0.1922`. The official public leaderboard page retrieved 2026-10-02 showed DARD at `0.3195` (rank 1) and alexoktaba at `0.3042` (rank 2); public rows at ranks 24 and 26 displayed `0.1922` and `0.1894`, respectively. Thus:

- **The prompt-reported former leader `.3049` is not the current leader.** Its historical provenance was not authenticated in this retrieval; the current visible rank 1 and rank 2 are `.3195` and `.3042`.
- **A local H19 result exists above `.1894` in the supplied values:** `.1922`, a `+0.0028` absolute difference. Its matching public score is a score-level match only; the page exposes no file digest, public submission ID, or verified account/team mapping.
- **The official public board is not the private Initial Prize Round (Phase 1) score or the expert-updated Final Prize Round (Phase 2) score.** It also cannot explain why a model scored as it did: it shows no ablations, hidden-label composition, or file-hash-to-account mapping.
- A complete dated 50-row capture, retrieval method, attribution caveat, and phase caveat are stored in `docs/data/leaderboard.json`; direct shell refresh failed TLS/SSL, but the official page was read through the web reader.
- **No reliable causal statement about H19 is warranted from scores alone.** The old H19 pages claim a power-law completeness budget, thermal/geochemical conduit inversion, high-resolution topographic openness/local relief, and geophysical lineaments, plus a sparse emission budget. The exact file's independently observed values are binary (`0`/`1`) inside its finite area; the page's score and mechanism claims are not official evaluation evidence.
- Under the official distance-weighted Tversky metric, false negatives carry the larger coefficient (`beta=0.8` versus `alpha=0.2`), with distance tolerance around ground-truth/predicted traces. A limited budget of thin, structurally plausible traces could trade precision for recall, but this is a rationale to test—not an explanation proven by the public result.

## Persistent discovery-uncertainty requirement

For ensemble members `m = 1,…,M`, each independent model returns a calibrated per-pixel Bernoulli probability `p_m`. Then

- mean prediction: `p̄ = mean_m(p_m)`;
- epistemic variance: `Var_m(p_m)` (disagreement between separately trained models);
- conditional/aleatoric variance: `mean_m[p_m(1-p_m)]`;
- total predictive Bernoulli variance: `p̄(1-p̄) = Var_m(p_m) + mean_m[p_m(1-p_m)]`.

This is the law of total variance for a uniform mixture of Bernoulli models. It does not prove that the second term is geological randomness: calibration, label uncertainty, and the incomplete-label observation process must be examined. The system must call it a conditional Bernoulli/aleatoric estimate and state those assumptions.

For discovery triage, let `c` be a validated mapped-survey-coverage score in `[0,1]` (`0` = less coverage; `1` = more coverage). An uncertainty-based ranking adjustment has signed direction `u_epi × (1 - 2c)`: it increases priority for high epistemic uncertainty at low coverage and decreases it for high epistemic uncertainty at high coverage. Its coefficient is selected only on blocked holdout data; no coverage data means no adjustment. This is a *review priority*, not a calibrated probability, and not a substitute for expert review.

## Three-pass protocol for each meaningful implementation

1. **Pass 1 — build:** implement the smallest reproducible version, link official sources, test mathematical/format invariants, log provenance.
2. **Pass 2 — adversarial review:** inspect missing-data paths, raster masks/nodata, value range, CRS/geotransform equality, spatial leakage, unknown survey coverage, calibration, duplicate artifacts, and stale leaderboard data; fix findings.
3. **Pass 3 — requirement audit:** compare the final tree and outputs to this brief, rerun tests and validators, record what ran and what could not run, and stop short of claiming success where inputs are absent.

## Prior review record — 2026-10-01 (local)

All three code-review passes for this implementation were completed; the following are code and synthetic checks only, not competition evidence.

- **Pass 1 — build/test:** Python compilation succeeded. `python -m unittest discover -s tests -v` in a temporary ignored `.venv` passed **29 tests**, including synthetic metric, geology feature, GeoTIFF format, leaderboard-fallback, and 64×64 OOF→gate→manifest integration tests.
- **Pass 2 — adversarial review:** added checks for label-nodata masking, polarity-invariant edge aggregation, per-candidate missing coverage, fold/config/inference hash alignment, prediction-file hash binding, strict output template validation, and failed leaderboard-refresh handling. Found and recorded the official/reference-notebook filename and depth-band naming discrepancy; H1 refuses to guess the conductive-depth mapping.
- **Pass 3 — requirement audit:** static HTML links/fragments passed (`7` pages); `node --check` passed for site JS; `bash -n` passed for the gated-data script; both GitHub Actions YAML files parsed; `git diff --check` passed before staging. The public leaderboard refresh attempt failed with TLS/SSL EOF; the last official snapshot is retained with a stale badge.
- **Scope limitation:** there is no authorized competition data, no PyTorch, no trained model, no genuine spatial holdout, no fitted calibration report, and no new submission raster. A synthetic pass only verifies interface contracts. Do not claim H1 is viable or spend a competition slot on it.

## Current review record — 2026-10-02 (local)

All three review passes for this documentation/CI/feed update are complete. They are code, source, and synthetic checks—not competition validation.

- **Pass 1 — build and test:** corrected the CI push branch from the mistyped `arena/01a0f9ce-gemsdoe23` to the active `arena/01a0f9ff-gemsdoe23`; captured all 50 rows from the official leaderboard through the Arena web reader; updated the dated score/source pages and ranked three genuinely distinct geological candidates after screening duplicate/previously attempted leads. The leaderboard updater now writes public/private Phase 1/Phase 2 and file-attribution caveats on successful refreshes too.
- **Pass 2 — adversarial review:** confirmed the data page still redirects to login; checked official USGS/ScienceBase listings, licenses where stated, geographic metadata, and the limits of the preliminary 3DEP query. Preserved unknowns for tile coverage, local downloads, actual feature tags, and external-raster alignment. A feed-schema test caught an unsupported refresh-status value during the update; the snapshot now uses the existing schema and its captured-page/failed-shell-refresh provenance is explicit. Prior H19 score matches remain un-attributed.
- **Pass 3 — requirement audit:** `python -m unittest discover -s tests -v` passed **29 tests** in a temporary `/tmp` environment with NumPy/SciPy/rasterio; Python compilation, 7-page local-link/fragment checks, JavaScript syntax, shell syntax, JSON parsing, YAML workflow parsing, active-branch assertion, and `git diff --check` passed. The independent reference-TIFF audit re-read all 12,279,160 pixels and reconfirmed one float32 band, EPSG:32611, 100 m, finite `[0,1]`, and NaN nodata; it still cannot check the absent official sample template.
- **Scope limitation:** no competition data or labels, model training, PyTorch ensemble, real spatial holdout, calibrated uncertainty report, external-raster download/alignment, or new submission was produced. The local public-board refresh still fails TLS/SSL; the dated public snapshot came from the official page via the web reader. Do not claim a new result or spend a weekly slot.

## Current blockers and next work

- **Competition data placement:** the official data page redirected to DrivenData login when rechecked on 2026-10-02. This sandbox has no authorized competition session. The model data, label raster, sample submission, and 1 m DEM link CSV are absent. Do not ask for or store a password/token in chat; do not circumvent the login.
- **External-data coverage:** the USGS GeoDAWN radiometric release is public and CC0, with GeoTIFF archives listed, but no file was downloaded and band units/masks/grid alignment remain unknown. The 3DEP index query produced one dissolved 1 m coverage feature only; exact tiles/full AOI coverage remain unknown. USGS MT conductance rasters are publicly listed and their broad geographic extent overlaps the region, but exact valid-pixel coverage, resolution, alignment, and reuse terms have not been checked.
- **Train/validation:** no training data means no model can be fitted and no spatially blocked holdout can be scored. A code path or synthetic unit test is not a real validation result.
- **Reference artifact:** the H19-5 GeoTIFF is hosted here for convenience and its SHA-256 is pinned. Its finite pixels are within `[0,1]`, but its exact equality to the official sample template has not been independently tested in this checkout.
- **Coverage proxy:** NGMDB makes map catalog coverage and map-scale information public, but mapped area is not direct evidence of field-survey effort. Extract and validate the relevant coverage product, then preregister sensitivity tests before using it to alter review priority.
- **Score attribution:** official leaderboard participants/scores are visible, but a public file hash or submission ID for the H19 artifact was not returned. Treat the matching score as a score-level match, not confirmed attribution.

Next data-enabled sequence: obtain the official files only through authorized access → run the geospatial contract/data-profile checks and inspect actual band metadata → assemble and QA the public GeoDAWN radiometric grids under CC0 → derive and freeze buffered spatial folds and a reproducible baseline → train independently initialized/optimized ensemble members → calibrate and evaluate epistemic, conditional/aleatoric, and total uncertainty → compare the top radiometric hypothesis against baseline at equal compute and emission budget (then evaluate ranks 2–3 only if warranted) → export reviewer uncertainty sidecars and a one-band GeoTIFF → re-read, hash, and validate against the exact sample template → only after the frozen spatial gate passes consider a weekly submission.
