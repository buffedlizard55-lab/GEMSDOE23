# GEMSDOE23 — DOE GEMS Prize (DrivenData #306): find the faults the catalogue has not captured

## ⬇ Downloadable Submission GeoTIFF (`.tif`) — First-Screen Quick Access

* **Live GitHub Pages site (top-of-page `.tif` download + executive summary + live leaderboard):**
  [**https://buffedlizard55-lab.github.io/GEMSDOE23/**](https://buffedlizard55-lab.github.io/GEMSDOE23/) · [**Executive Summary / How to Submit**](https://buffedlizard55-lab.github.io/GEMSDOE23/executive-summary.html)
* **⬇ Primary submission `.tif` (NaN outside footprint · 10/10 template checks PASS):**
  [**`gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-nan.tif`**](docs/downloads/gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-nan.tif)
  (`1,692,444` bytes · SHA-256 `38539dc647d5ede0d8fa90123810d18130ee15e524097f55e83b6b8a57976ea9` · `EPSG:32611` · `3292 × 3730` single-band `float32` · 100 m pixels · `5,167,373` finite pixels in `[0.0, 1.0]` · `7,111,787` `NaN` outside footprint · `91,533` emitted dots)
* **⬇ Compatibility all-finite `.tif` (`0.0` outside footprint · prevents `[0, 1]` NaN-validator rejection):**
  [**`gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-allfinite.tif`**](docs/downloads/gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-allfinite.tif)
  (`922,168` bytes · SHA-256 `d07cbb6f69076e76f1a8a4806ddc5639421bc9a59b10d80a09b9fb423bb99427` · `12,279,160` finite pixels in `[0.0, 1.0]` · `0` NaN/Inf · `nodata=0.0`)
* **⬇ Reference live-scored `.tif` (`h19-5`, live public DTI `0.1922`):**
  [**`gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif`**](docs/downloads/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif)
  (`1,712,322` bytes · SHA-256 `ec1f9b56b83ce33cad781ceb9f104b18fb4f2ff785263a4e89616af4aabdee8d`)
* **Unique filename:** `gemsdoe23-h30-arrangement-matched-habitat-20261002-0d4e02e8-nan.tif`
* **Short submission note (`<250` chars):** `GEMSDOE23 H30 | QA-only, unscored; no score forecast; release blocked pending independent uncatalogued-fault holdout | 91,533 dots | sha256 38539dc6`
* **Release gate status (`docs/data/current-holdout-best.json`):** **`BLOCKED` (QA candidate only)** — both H30 GeoTIFF variants pass 10/10 strict template checks against `data/sample_submission.tif` (`docs/data/current-template-validation.json`) and the stdlib LZW/value audit (`docs/data/current-tiff-audit.json`), but per the standing constraint (*never spend a submission slot on an idea that has not beaten the current holdout best*), do not spend a weekly live submission slot until an independent uncatalogued-fault spatial holdout is unblocked.

---

**Read this file first, every session.** It carries the standing brief, the current state of the
evidence, and the two rules that decide what may be uploaded.

---

## 0. The standing brief (transcribed from the project owner's request; treat as permanent)

> Build a project that places at the top of the DrivenData competition 306 (DOE GEMS Prize)
> leaderboard, beating the current best. Specifically:
>
> 1. Review the repository. There must be an **easy one-click downloadable submission `.tif`**,
>    obvious on the first screen, exactly as the competition prompt describes.
> 2. **Decompose predictive uncertainty into epistemic and aleatoric** using a *true deep ensemble*
>    — independently initialised, independently trained networks, not test-time dropout
>    (Lakshminarayanan, Pritzel & Blundell, NeurIPS 2017). Treat epistemic uncertainty concentrated
>    in **historically under-surveyed terrain as a finding** that *raises* a candidate's priority,
>    while high epistemic uncertainty in **well-surveyed** terrain is treated with **suspicion**.
>    Report the split for **every** candidate handed to Phase 2 reviewers.
> 3. Study **why the H19 submissions scored highest** (`h19-4` 0.1894, `h19-5` 0.1922) and whether a
>    higher-scoring submission can be generated. Answer with PhD-level judgement.
> 4. Generate **3–5 new geological hypotheses** naming the specific layers, the physical
>    signature/transform, why it would catch faults missing from the USGS/INGENIOUS catalogue, and
>    how it differs from existing work in this repository. **Rank** them by defensible expected score
>    benefit and implementation cost; quantify ΔDTI only when the evidence supports it, otherwise use
>    an explicitly ordinal/conditional estimate. Validate the top candidate on a **spatially blocked
>    holdout** before spending a weekly submission slot. If new external data is needed, name the specific free
>    official source and confirm it is obtainable.
> 5. Do **deep autonomous research** into geothermal-vent and fault discovery from **free, official,
>    verified** sources; store the knowledge in-repo as a reusable starting point; be **contrarian but
>    scientifically grounded**.
> 6. Build a **clean GitHub Pages site** (organised, user-friendly) holding all of it with official
>    verified links, an **executive-summary subpage** explaining exactly how to submit, a **unique
>    filename** and a **short submission note**, and a **current leaderboard feed** so nothing has to
>    be checked manually.
> 7. Put this prompt into the repository README and read it every session as a starting point.
> 8. Fix the submission rejection **`"Predicted values must be in range [0, 1]"`**.
> 9. Unblock data placement: `bash scripts/download_competition_data.sh` then
>    `python scripts/prepare_data.py` must run **autonomously, with no manual input**.
> 10. Do **three passes** — implement, then adversarial review, then re-check every requirement —
>     then open a **pull request and merge it onto `main`**, and list remaining work and limitations.
> 11. **Treat faults as a spatial statistic, not independent pixels** *(added 2026-10-02)*. Bour & Davy
>     (*Geophysical Research Letters*, 1999) establish a direct mathematical link between a fault
>     network's clustering dimension and the exponent of its length-frequency distribution, measured
>     through the distance from each fault to its nearest larger neighbour; later structural-geology
>     studies apply a normalised correlation count to test, at a given length scale, whether the faults
>     in a population are clustered, randomly spaced or regularly spaced. **Fit this statistic on the
>     known INGENIOUS/USGS traces inside the footprint before touching the model**, then use it two ways:
>     (a) as a **geometric prior** that favours a candidate pixel lying along the extrapolated clustering
>     pattern of a known larger fault over an equally scored but spatially isolated one, and (b) as a
>     **post-hoc audit** — compute the same statistic on our own predicted raster and flag sharp divergence
>     from the measured regional statistics as a likely artefact (survey-line aliasing, acquisition-block
>     edges). Work from the latest continuation status and release-gate record first; older H24/H25/H26
>     next-step lists are historical and must not override current evidence or the no-slot holdout rule.
>
> **Standing constraints.** No hallucinations; verify line by line; work autonomously; **flag
> irregularities for review**; provide links to official verified trusted sources for manual review;
> store all gathered knowledge in the repo for reuse; **never spend a submission slot on an idea that
> has not beaten the current holdout best**; the submission must be a single-band GeoTIFF matching the
> official CRS, shape and geotransform with values in `[0, 1]` and null/NaN outside the footprint, with
> a unique name and a short note; keep the download obvious on the first screen; keep the Arena core
> values **“Maximize P(Win)”** and **“Own the Outcome”** as the focal point; do not stop after the
> first review pass; do not bypass access controls or use credentials for login-gated competition data.

---

## 1. At a glance (latest recorded analysis, 2026-10-02 continuation session; all inputs restored and hash-verified in this checkout)

| | |
|---|---|
| **QA candidate file** | `docs/downloads/gemsdoe23-h30-arrangement-matched-habitat-*.tif` (**H30**, primary) — one click from the first-page download. H29 is the de-aliased lattice control; H24 is superseded. Stdlib TIFF audit confirms one float32 band, EPSG:32611, 3292×3730, 100 m pixels and finite predictions in `[0,1]`; the sample template is restored in this session's checkout, so strict template comparison can be re-run any time. The geological release gate is **BLOCKED**; **do not upload or spend a slot.** |
| **Data state** | **Restored and verified this session** through the public git data bridge (SHA-256 match on all three official rasters, all 12 external layers, all 24 live-scored anchor artefacts identity-verified; `docs/data/restore-receipt.json`). `data/` is populated via `~/.cache/gems-data` symlinks. |
| **Grid** | 3292 × 3730, single band float32, EPSG:32611, 100 m, transform `(100, 0, 243350 / 0, −100, 4508550)`, NaN outside the footprint, values in `[0, 1]` |
| **Scored domain** | 5,106,385 px = 5,167,373 footprint − 60,988 known-fault pixels (staff ruling, [forum 11516](https://community.drivendata.org/t/11516), re-read 2026-10-02) |
| **Hidden public-test truth \|G\|** | **5,564 – 14,944 px**, exact bounds from 24 live scores (unchanged; the previously assumed 125,000 stays refuted). New this session: the leaders' 0.3049–0.3195 is **algebraically unreachable** at h19-5's budget unless \|G\| ≳ 12,000, and needs \|G\| ≳ 8,000 even at H30's more efficient geometry — the leaders are finding a large fraction of a large truth set (`docs/data/h19-placement-analysis.json`). |
| **H30 emission** | 91,533 dots at ≥ 400 m separation inside the top 30 % of the habitat score, row-phase equalised, tie-broken NMS; η = 0.931, 300 m coverage 37.9%, K̄ = 0.157 |
| **Official public board** | Latest verified headless-render capture at `2026-10-02T19:22:06+00:00`: DARD 0.3195, nchuzhoy 0.3128, alexoktaba 0.3042. User-reported 0.3049 is absent. The 0.1922 and 0.1894 rows are rank 28 and 30 in this capture; scores alone do not identify H19 files/accounts (flag I-28). |
| **Why h19-5 leads the group** | Measured this session (`docs/data/h19-placement-analysis.json`): highest placement skill of all 24 artefacts at every admissible \|G\| (7.2 at \|G\|=10k vs ens12's 5.9), achieved with broad coverage (recall 0.64 at \|G\|=10k). The +0.0028 h19-5−h19-4 delta prefers **specific scarp morphology** (`lid_downface_max`/`lid_step_max`/`lid_relief` up, generic slope-variability and `sgmc_gap_density9` down). All four top artefacts share one signature: enriched **near** catalogue and SGMC structure, on steep rough scarp ground, with **zero** pixels on the masked catalogue itself. |
| **Score expectation** | **No score is predicted.** DTI figures in the historical budget/scenario records are conditional metric-algebra sensitivities, not observed or validated performance. H30 has no live score; the current spatial-holdout registry is BLOCKED. |
| **Validated offline?** | **No.** No offline proxy ranks the 24 live artefacts better than chance, and no blocked holdout can test hidden-fault placement. The new-hypothesis validation (H-38/H-39) uses the blocked SGMC-proxy protocol with that limitation stated in the record itself. |
| **Fault statistics (fitted before the model)** | catalogue = 3,199 traces; length exponent a = **3.15** [2.99, 3.34] above 3.0 km; nearest-larger-neighbour x = **1.54** [1.33, 1.75] vs Bour & Davy prediction [1.20, 1.55]; D = 1.51–1.66; normalised correlation sum 4.2× at 1 km → 2.3× at 5 km → 1.15× at 30 km (95 % CSR envelope 0.8–1.2 at 1 km, ±0.01 at 30 km) |
| **Audit findings** | H24 carried a spectral line at exactly the **400 m GeoDAWN Area 2 flight-line spacing** (strength 243 vs control p95 10, rank p = 0.016), **931 dots closer than its stated 400 m**, and a lattice-like arrangement (signed divergence −0.58). H29/H30 remove the first two (strength 2.4/2.3, 0 violations); only H30 moves the arrangement into the bin that holds the best live scores (−0.21) |
| **Deep ensemble** | **Retrained this session on the restored rasters, fresh seeds, identical config** (5 blocked folds × 3 independently initialised members out-of-fold + 5 full-domain members; 2,223 s). Admission gate **failed a second time, 0/5 folds beat a seed-matched random emission** (mean DTI 0.0450 vs random 0.1023; prior run 0.0440 vs 0.1012) → a twice-reproduced negative result: detector weight stays 0. The epistemic/aleatoric split (share 0.145) is regenerated from the fresh members and remains a reviewer-ranking aid only. |
| **New hypotheses (this session)** | **H-38** cross-family azimuth coherence and **H-39** shallow-residual potential-field edges: implemented (`src/gems/orientation.py`, unit-tested — the tests caught a real kernel bug) and **validated then honestly rejected as standalone emissions** (0/5 blocked folds beat a random emission; record: `docs/data/new-hypothesis-validation.json`). In addition, the single permitted follow-up on H-39 — **15-fold leave-one-family-out habitat nested-CV evaluation** — was executed and completed: H-39 ranks 37–50/96 by univariate \|Spearman\| (below the top-8 cutoff 0.5548 and top-14 cutoff 0.5070), is selected in **0/15 folds** in unforced nested CV (leaving nested-CV Spearman unchanged at 0.437391), and degrades CV when the raw layer is force-appended (0.383478, Δ = −0.053913 at \|G\|=6,000). Both H-38 and H-39 are therefore closed. **H-40** fine-scale seismicity (USGS ComCat FDSN; obtainability verified 2026-10-02: 15,802 events M≥2.5 in the AOI box; acquisition automated in `.github/workflows/seismicity.yml`), **H-41** direction-resolved tip/step-over lobes (Faulds & Hinz verified for the INGENIOUS area), **H-42** playa/basin-margin association: proposed with sources verified. No slot may be spent until a candidate beats the registered current best on a valid holdout. |

The findings are on the [clustering-audit page](https://buffedlizard55-lab.github.io/GEMSDOE23/clustering.html),
the [evidence page](https://buffedlizard55-lab.github.io/GEMSDOE23/evidence.html) and in [`docs/data/`](docs/data)
(`fault-statistics.json`, `prediction-audit.json`, `candidates.json`, `h29-build.json`, `h30-build.json`).

---

## 2. The two rules that decide what may be uploaded

1. **Never upload or spend a weekly slot until a candidate beats the registered current best on a valid spatial holdout.** `docs/data/current-holdout-best.json` is `BLOCKED`: this checkout has no verified independent uncatalogued-fault truth plus exact current-best OOF artifact. The legacy known-catalogue OOF report and live-board correlations cannot stand in for that target. The H30/H29/H24 files are QA-only regardless of scenario calculations or format checks; do not accept a score projection as approval.
2. **Every component must pass its own gate before it may influence a release candidate.** The retrained 5-member convolutional deep ensemble failed its seed-matched-random admission gate across all 5 blocked folds (mean OOF DTI 0.0450 vs random 0.1023, 0/5 folds), so its raster weight in H30 is **0**, while its epistemic/aleatoric variance split (`epistemic_share_of_total = 0.145`) is retained strictly for Phase 2 reviewer candidate ranking (`docs/data/phase2-candidates.json`). `scripts/build_audited_emission.py` creates format-checked QA files (`release_approved=false`, `ok_to_upload=false`); the generic `scripts/build_submission.py` additionally requires a non-withdrawn independent holdout comparison against the exact registered current-best OOF hashes. The bounded `scripts/record_score.py` is only relevant after a future approved upload; no upload occurred here.

---

## 3. Reproduce everything

```bash
python3 scripts/restore_workspace.py --all  # official rasters + hash-pinned external layers + the 23 live-scored artefacts (identity-verified by exact pixel count and mass)
bash scripts/download_competition_data.sh   # acquire + hash-verify the official rasters (no manual input)
python scripts/prepare_data.py              # grid/validity audit -> data/manifest.json
python scripts/fit_habitat_model.py         # 24 live scores -> habitat weights, nested-CV rho (reproduces the committed record exactly)
python scripts/run_ensemble.py              # deep ensemble + epistemic/aleatoric split (retrained 2026-10-02)
python scripts/evaluate_oof.py              # admission gate vs a random-emission control
python scripts/build_submission_live.py     # budget, dispersion, TIFF, template validation (H24)
python scripts/rebuild_h24_check.py         # rebuild H24 from public inputs; verified bit-for-bit identical to the shipped file
python scripts/fit_fault_statistics.py      # fault-population statistics on labels.tif (before any model) -> docs/data/fault-statistics.json
python scripts/audit_predictions.py --extra <rasters>   # audit + calibration against the 23 live scores -> docs/data/prediction-audit.json
python scripts/build_audited_emission.py --variant h30 --set-primary   # H29 / H30: de-aliased, arrangement-audited emissions
python scripts/make_cluster_figures.py      # SVG figures for docs/clustering.html (needs matplotlib)
python scripts/phase2_candidates.py         # reviewer candidates with the variance split (fresh ensemble output)
python scripts/analyze_h19_placement.py     # why h19-5 leads: |G|-scenario skills, h19-5 vs h19-4 delta attribution, leader-target algebra
python scripts/validate_new_hypotheses.py   # H-38/H-39 on the blocked SGMC-proxy holdout + live-score consistency
python scripts/fetch_seismicity.py          # H-40 input: USGS ComCat AOI catalogue (needs egress; automated in CI)
python scripts/build_site.py                # regenerate the whole site from docs/data/*.json
python -m unittest discover -s tests        # dependency-free checks
```

Dependencies: `numpy`, `scipy`, `rasterio`, `pyshp` (GeoDAWN outlines), `torch` (CPU is enough), `scikit-learn`, `pandas`; `matplotlib` only for the figures.
Compute actually used: **2 CPU cores, 3 GB RAM, no GPU.** In a size-limited workspace set `GEMS_PREPARED_DIR=~/.cache/gems-data/processed`
before `download_competition_data.sh` (the prepared float32 array is ~0.9 GB), and keep the venv under a name such as `.venv`.

---

## 4. Data: where it comes from and how it is verified

The competition originals sit behind a login-gated data tab. This repository never authenticates to
anything. Instead [`scripts/fetch_data_bridge.py`](scripts/fetch_data_bridge.py) reassembles them from
the group's public **git data bridge** (the official rasters split into <100 MB parts and committed to
a sibling repository with a manifest that pins every SHA-256), falls back to the Dropbox mirrors named
in that manifest, verifies every part and the whole file, and **fails closed**.

**Restored and SHA-256 verified (`docs/data/restore-receipt.json`):** `data/`, `outputs/` and `.cache/` are git-ignored by repository policy so 420 MB+ rasters are not committed to Git. Running `python3 scripts/restore_workspace.py --all` (or `bash scripts/download_competition_data.sh`) autonomously restores and hash-verifies all three official rasters, all 15 external USGS/DOE layers and metadata files, and all 24 live-scored anchor artefacts into `data/` and `.cache/`. Both H30 submission variants were re-validated directly against the restored `data/sample_submission.tif` (`docs/data/current-template-validation.json`, 10/10 checks pass).

| file | bytes | verified SHA-256 |
|---|---|---|
| `data/training_features.tif` (official 19-band stack) | 418,912,844 | `4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5` |
| `data/labels.tif` (rasterised known faults) | 425,830 | `7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093` |
| `data/sample_submission.tif` (official template) | 1,599,597 | `2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc` |

The restore receipt (`docs/data/restore-receipt.json`) also pins and verifies all external layers in `data/external/` (GeoDAWN radiometrics/extensions, 1 m 3DEP geomorphometry, USGS SGMC faults, GDR/INGENIOUS spring/well records, vents, temperature probes and survey outlines). Official sources include [GeoDAWN DOI 10.5066/P93LGLVQ](https://doi.org/10.5066/P93LGLVQ), [USGS 3DEP](https://www.usgs.gov/3d-elevation-program), [USGS SGMC DOI 10.3133/ds1052](https://doi.org/10.3133/ds1052), and the [Geothermal Data Repository](https://gdr.openei.org/).

`data/`, `outputs/` and `.cache/` are git-ignored: the rasters are private competition data and the
derived arrays are reproducible.

---

## 5. Repository map

| path | what it is |
|---|---|
| `docs/index.html` … `docs/verification.html` and root `index.html` … `verification.html` | the generated static site (published at both `/` and `/docs/` so legacy root-branch and workflow GitHub Pages builds resolve identically; flag I-33) |
| `docs/data/*.json` | every number the site prints; each is produced by a script in `scripts/` |
| `docs/downloads/` | the submission rasters, their manifests and their stdlib audits |
| `docs/research/knowledge_base.md` | the reusable, sourced knowledge base (start here on a new project) |
| `docs/research/review-log-2026-10-02.md` | three review passes, checks, blockers, and remaining work |
| `docs/data/current-holdout-best.json` | authoritative current-best gate registry; BLOCKED until independent target validation exists |
| `docs/PROJECT_BRIEF.md` | the project brief and the research shortlist |
| `src/gems/layers.py` | the streaming evidence-layer bank (95 layers, 3 GB RAM safe) |
| `src/gems/orientation.py` | H-38/H-39 transforms: structure-tensor azimuths, cross-family agreement, upward continuation and shallow-residual edges (unit-tested) |
| `src/gems/emission.py` | dispersion, the budget marginal rule, expected-DTI algebra |
| `src/gems/ensemble.py` | the deep ensemble and the epistemic/aleatoric decomposition |
| `src/gems/metric.py` | the official DTI, unit-tested against the organiser's worked example |
| `src/gems/faultstats.py` | fault-population statistics: length exponent, Bour & Davy nearest-larger-neighbour scaling, correlation dimension, normalised correlation count; includes a synthetic check of the relation |
| `src/gems/clusterprior.py` | empirical enrichment of faults around long faults with spatial-block bootstrap, blocked out-of-fold AUC, tie-break bonus |
| `src/gems/audit.py` | post-hoc audit: survey-line spectral detector (verified GeoDAWN geometry), boundary jumps, arrangement descriptors, row-phase equaliser |
| `src/gems/submission.py` | float32/[0,1]/NaN-outside writer and strict template preflight |
| `scripts/restore_workspace.py` | stdlib-only rebuild of every git-ignored input with verification (pinned hashes; exact pixel-count identity for artefacts) |
| `analysis/` | one-off investigations, kept for auditability |
| `tests/` | dependency-free unit tests plus geospatial tests that skip when numpy/scipy are absent |

---

## 6. Limitations, and what access would change them

See [`docs/verification.html`](https://buffedlizard55-lab.github.io/GEMSDOE23/verification.html) for the
full list and [`docs/data/irregularities.json`](docs/data/irregularities.json) for the flag register.
The short version:

* **No valid hidden-target holdout** — the single largest limitation. The `current-holdout-best.json` registry is `BLOCKED`; public scores and known-catalogue folds are not independent uncatalogued-fault evidence. A weekly upload is not a substitute for a controlled validation and no slot was used.
* **The arrangement audit is correlational.** Signed divergence from the catalogue orders the 23 live
  emissions (ρ = −0.66, p = 0.001), but the bins were defined after looking at them, the emissions fall in
  families, and the only controlled pair (pindrop ridge vs nodes, same score, same pixel count) scored
  alike at +0.20 and −0.62. H30's arrangement target (−0.21) is a rule applied *after* the audit table was seen.
* **NCC is a 2-D adaptation.** Marrett et al. (2018) published the normalised correlation count for 1-D
  scanlines; the 2-D pair-count form used here (and the scanline form, reported alongside) are labelled as such.
* **The clustering prior is weak for the faults that matter.** Catalogue short traces are enriched ×2.3 within
  1 km of long faults (blocked AUC 0.67) but faults *missing* from the catalogue (SGMC-only proxy) only ×1.8/×1.4 in
  the first 600 m and ≈ 1 beyond (AUC 0.55); live scores do not reward concentration near known faults. In a dispersed
  lattice it can only be a tie-break (~1 % of dots move).
* **\|G\| is bounded, not measured.** The upper bound assumes no artefact is actively anti-correlated
  with the hidden truth.
* **The deep ensemble is undertrained** (2 cores, no GPU) and its admission gate failure is now
  **twice-reproduced** (independent retrain with fresh seeds: mean OOF DTI 0.0450 vs random 0.1023, 0/5 folds) —
  treat the exclusion as systematic, not a bad seed.
* **Lidar coverage report: 75.4 %**, with a north-east gap (flag I-26): the lidar product (`lidar_scarp_features_u8.tif`) is restored and hash-verified in this checkout (I-31/I-32 resolved), and band 12 (`valid`) covers 75.4 % of the footprint, but the 716-tile list behind the 24.6 % gap comes from an OCR-recovered inventory rather than an official National Map tile query. Enumerate the footprint's 1 m tiles from the public National Map API from a machine with egress before assuming the north-east gap has no 1 m lidar coverage.
* **Public ≠ private.** All 24 live scores are public-test scores; the split is unpublished and the
  Final Round re-scores against expanded labels.
* **Sandbox egress** allows only `github.com`, `api.github.com`, `codeload.github.com`, `pypi.org` and
  `files.pythonhosted.org`. DrivenData, Dropbox, USGS, ScienceBase, the National Map and
  `download.pytorch.org` all fail the TLS handshake here; GitHub Actions has full egress and repeats the
  leaderboard fetch and USGS ComCat seismicity fetch there.
* **The official leaderboard is client-rendered** (flag I-13). A plain HTTP GET of the leaderboard URL
  returns 200 and ~30 KB of page shell with `tables: 0, rows: 0, user_links: 0` and a `Loading...`
  placeholder — the board is built by JavaScript. There is no anonymous JSON endpoint:
  `/api/competitions/306/leaderboard/` answers 404 with "make sure that you are signed in and signed up
  for that competition", and this repository uses no credentials and bypasses no access control. So
  `.github/workflows/pages.yml` installs Playwright/Chromium and refreshes with
  `scripts/update_leaderboard.py --render`, which executes the page's own public JavaScript anonymously
  and hands the rendered HTML to the same validating parser. If rendering ever fails, the last verified
  rows are retained and `docs/data/leaderboard-status.json` records why — the site badge says so instead
  of silently showing an old board.
* **GitHub Pages legacy root deployment race resolved (flag I-33).** Repo Pages settings use `build_type: "legacy", source: {"branch": "main", "path": "/"}`, causing `pages-build-deployment` to deploy `/` after `.github/workflows/pages.yml`. `scripts/build_site.py` now writes all 9 static HTML pages at both `/` and `docs/` (with `.nojekyll` at both levels) and places the downloadable `.tif` card at the very top of `<main>` and `<header>`, so both `https://buffedlizard55-lab.github.io/GEMSDOE23/` and `https://buffedlizard55-lab.github.io/GEMSDOE23/docs/` always serve the complete static site with the downloadable `.tif` at the very top.

---

## 7. Disclosure

Generative AI was used to produce code, analysis and prose in this repository, as the competition rules
require participants to disclose. Every quantitative claim is traceable to a script in `scripts/` and a
record in `docs/data/`; anything that is inference rather than measurement is labelled as such where it
appears.
