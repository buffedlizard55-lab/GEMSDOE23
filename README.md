# GEMSDOE23 — DOE GEMS Prize (DrivenData #306)

**Start every work session by reading this file.** This is the durable brief, the current evidence state, the submission safety rule, and the pointers to the auditable records. The project objective is to identify geologic faults/structures that may indicate geothermal resources and may be missing from the public USGS/INGENIOUS catalogue. The organizer explicitly warns that known-fault labels may be incomplete or inaccurate; the hidden Initial Prize Round faults were manually identified by experts ([official problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/)).

## Project aim and standing requirements

Build a competitive, scientifically defensible, auditable project for the DOE GEMS Prize—not merely a file that passes format checks. Work toward the public and final prize rounds while preserving the competition’s discovery goal.

1. Keep a valid, single-band downloadable GeoTIFF obvious on the first page of the GitHub Pages site. State clearly whether it is only a QA candidate or approved for an upload.
2. For Phase 2 reviewer candidates, report aleatoric and epistemic uncertainty from independently initialized and independently trained deep-ensemble members—not dropout at inference. High epistemic uncertainty in genuinely under-surveyed terrain may elevate a candidate for review; the same uncertainty in well-surveyed terrain warrants suspicion. Report the decomposition per candidate and its survey-coverage evidence.
3. Analyze reported high-scoring approaches and the live official leaderboard; distinguish observed scores from author claims and from artifact attribution. Explain what can and cannot be inferred.
4. Propose 3–5 genuinely distinct geological hypotheses. For each, specify layers, physical signature/transform, why it might find uncatalogued faults, differences from code and prior attempts here, qualitative expected DTI potential and implementation cost. Do not invent a numeric score uplift. Test the highest-ranked idea on a spatially blocked holdout before any submission slot is considered.
5. Research from free, official/trusted public sources; link sources and preserve reusable findings in `docs/research/knowledge_base.md`. Be contrarian where evidence warrants it, but label hypotheses and uncertainties.
6. Keep GitHub Pages clean and auditable: a first-page download, an executive-summary submission guide, a unique filename and short note for any release candidate, and a dated leaderboard feed with retrieval status.
7. Keep the full project aim in this README and use it as the starting point for future work.
8. Prevent the reported `Predicted values must be in range [0, 1]` rejection: validate values, band count, data type, CRS, dimensions, transform, footprint, and outside-footprint null convention against the official template.
9. Make competition-raster acquisition and preparation autonomous and fail-closed; do not bypass the login-gated data tab or request/store credentials.
10. Use at least three implementation/review passes: build, adversarial review, final requirement audit. Verify final changes, record irregularities and limitations, and create a PR/merge only on the session branch when feasible.

**Non-negotiable decision rule:** never use a weekly submission slot for a candidate that has not beaten the *registered current holdout best* on a reproducible, spatially blocked validation. A format-valid TIFF is not model validation. If there is no verified current-best record or no valid holdout, do not upload. “Maximize P(Win)” means maximize evidence before risk; “Own the Outcome” means state blockers and provenance honestly.

## Current status — checked 2026-10-02 (UTC)

### Safe download / upload status

- First-page download: [`docs/downloads/gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif`](docs/downloads/gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif). It is a **research candidate for QA only, not cleared for a competition slot**.
- Current formal template preflight is recorded in [`docs/data/current-template-validation.json`](docs/data/current-template-validation.json). The H24 NaN-outside, H24 all-finite fallback, and H19-5 NaN-outside TIFFs all pass the hard format requirements against `data/sample_submission.tif`: one float32 band, EPSG:32611, 3292×3730, matching affine transform, in-footprint finite `[0,1]`, no infinities, and outside-footprint null/NaN or template-tagged null value. The all-finite fallback has one advisory-only difference: its nodata tag is `0.0` rather than NaN.
- This preflight prevents a structural cause of the `[0,1]` error; it **does not prove the competition uploader will accept the file, validate geological placement, or predict a score**. The short note in the manifest is for candidate traceability and is explicitly marked not for upload.
- `docs/data/current-holdout-best.json` is `BLOCKED`: no reproducible, non-withdrawn current-best holdout is registered. The old `docs/data/validation-report.json` is marked `WITHDRAWN` (irregularity I-05); the public H19 site’s holdout table cannot be reproduced from the files in this checkout. The release builder now fails closed until a verified current-best OOF record exists and a candidate beats it.

### Data and compute actually available in this checkout

- The official bridge-archived feature raster, labels, and sample template were hash-checked against the public bridge manifest. This confirms the acquired bytes match that bridge; the bridge is a mirror, not an independent signature from the login-gated competition server.
- `scripts/prepare_data.py` completed successfully. The prepared grid is EPSG:32611, 100 m, 3292×3730, 19 bands, 5,167,373 footprint pixels, 60,988 known-positive label pixels, and no missing labels inside the footprint. Background pixels must not be interpreted as verified fault-free terrain.
- `data/external/` is **absent** in this checkout. Some historical code/docs describe lidar, radiometric, SGMC, spring/well and other external rasters; those descriptions do not establish that those layers are currently present or reproducible here.
- The active `.venv` imports NumPy 2.4.6, SciPy 1.17.1 and Rasterio 1.4.4. Torch, scikit-learn and pandas are not installed. No model training or new deep-ensemble run was performed in this continuation. Historical uncertainty/OOF JSON records are retained, but their checkpoints and some input layers are not present here; treat them as recorded results, not a newly reproduced run.

### Leaderboard and H19 evidence: attribution is unresolved

- The official public leaderboard page was read through the Arena page fetch on **2026-10-02** and saved as a dated 50-row manual snapshot (not a claim of a continuously live feed). It showed **DARD, 0.3195** at rank 1, **alexoktaba, 0.3042** at rank 2, and **Batik Shirt Brothers, 0.2998** at rank 3. The user-reported 0.3049 is absent from this current capture; no primary archived capture confirming it as a past leader was found.
- The public rows at **0.1922** (rank 26, `smrtdoog5`) and **0.1894** (rank 28, `SDCF9`) are numeric score matches to the locally reported H19-5/H19-4 values. The official board exposes neither prediction hashes nor public submission identifiers, so the matches do **not** attribute those files or results to those participants. One project passage calls 0.1894 the highest while another lists 0.1922; numerically 0.1922 is higher, but neither is verified as an H19 artifact. That wording conflict is recorded as unresolved.
- The [19GEMSDOE submission hub](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html) reports four physical reasoning lines and dense/sparse four-quadrant holdout claims, but its own page calls H19-4/H19-5 **“not live-scored yet”**, lists its group best as 0.1855, and displays an older leaderboard leader of 0.3168. Those are author-reported claims, not independently reproduced here. The available H19-5 TIFF was template-validated in this checkout; its score attribution and holdout evidence are not verified. H19-4 TIFF/OOF artifacts are not present here.
- Consequently, the evidence does **not** support a causal answer to “why did H19 score highest?” The current official leader is higher, H19 score-to-file attribution is unresolved, and scalar leaderboard scores cannot isolate feature contributions. A causal claim would require reproducible, controlled ablations on the same frozen spatial holdout.

### Current candidate hypotheses and gate

The current ranked hypotheses, expected-DTI *ordinal* potential, cost, sources and novelty relative to this code are on [`docs/hypotheses.html`](docs/hypotheses.html), with the evidence register in [`docs/research/knowledge_base.md`](docs/research/knowledge_base.md). Numerical ΔDTI estimates are intentionally withheld until a valid comparator and holdout exist. The top candidate is not holdout-approved. **No weekly slot is authorized.**

## Reproduce the available checks

```bash
# Acquires/hash-verifies competition rasters through the public bridge without login credentials.
bash scripts/download_competition_data.sh
.venv/bin/python scripts/prepare_data.py

# Re-check a candidate GeoTIFF against the official sample template.
.venv/bin/python scripts/validate_submission.py \
  --template data/sample_submission.tif \
  --prediction docs/downloads/gemsdoe23-h24-dispersed-habitat-20261002-ada8df14-nan.tif

# Run the repository suite and rebuild the static site.
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_site.py
.venv/bin/python scripts/build_site.py
```

`python -m pytest` is not configured in the active `.venv`; the project’s suite is `unittest`. `scripts/build_submission_live.py` only makes a preflight candidate and marks it **not approved**. The stricter `scripts/build_submission.py` is the release path: it requires an eligible four-fold OOF report bound to the hash-verified `docs/data/current-holdout-best.json` record. Do not change that registry to `VERIFIED` without auditable independent truth, frozen fold design, candidate/incumbent prediction hashes, and a passing comparison.

## Important files

| Path | Purpose / caution |
|---|---|
| `data/training_features.tif`, `data/labels.tif`, `data/sample_submission.tif` | Official competition rasters acquired through a public bridge; SHA-256 values are in `data/processed/manifest.json`. |
| `data/processed/` | Prepared arrays and grid manifest; only the 19 official feature bands are represented. |
| `docs/data/leaderboard.json`, `docs/data/leaderboard-status.json` | Dated public leaderboard snapshot and refresh state. The official page is client-rendered; a hand-captured snapshot is clearly marked. |
| `docs/data/current-holdout-best.json` | Release registry; currently BLOCKED. |
| `docs/data/current-template-validation.json` | Formal TIFF-to-template preflight for the available artifacts. |
| `docs/data/irregularities.json` | Audit flags, including stale claims and unresolved attribution. |
| `docs/data/ensemble-report.json`, `docs/data/phase2-candidates.json` | Historical ensemble/uncertainty records; missing checkpoints/external inputs mean the current checkout has not reproduced them. |
| `docs/data/validation-report.json` | Retained for audit, status WITHDRAWN; not a release gate. |
| `docs/downloads/` | Small, uniquely named candidate GeoTIFFs. Download is for QA; no artifact is presently upload-approved. |
| `scripts/build_site.py` | Generates the Pages site from evidence records. |
| `scripts/validate_submission.py`, `src/gems/submission.py` | Formal single-band GeoTIFF template preflight and writer. |
| `scripts/build_submission_live.py` | Candidate generation and format checks only; cannot approve an upload. |
| `scripts/build_submission.py` | Strict release builder, bound to a verified current-best registry record. |
| `scripts/run_spatial_validation.py` | Known-catalogue spatial diagnostic only; the known labels are not hidden uncatalogued-fault truth and its output is never release approval. |

## Official and trusted sources

- Competition task, data, target, metric and phases: [DrivenData problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/).
- Current public scores: [official leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/). The page shows public scores, not hidden/private results or prediction hashes.
- Known-fault masking / evaluation discussion: [staff ruling, forum 11516](https://community.drivendata.org/t/11516); interpretation of “new fault”: [forum 11536](https://community.drivendata.org/t/11536).
- Public airborne magnetic and radiometric survey: [USGS GeoDAWN data release](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and), [ScienceBase item](https://www.sciencebase.gov/catalog/item/657e1d85d34e23d3533209f7), DOI [10.5066/P93LGLVQ](https://doi.org/10.5066/P93LGLVQ).
- Free, unrestricted USGS DEM products and coverage tools: [3DEP products/services](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services); this does not establish complete 1 m coverage at every competition pixel.
- Independent Great Basin conductance products (possible future layer; not downloaded): [USGS ScienceBase item](https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b), DOI [10.5066/P9TWT2LU](https://doi.org/10.5066/P9TWT2LU). The item lists five downloadable GeoTIFFs, but their depth ranges are 2–200 km; exact usefulness/resolution for near-surface fault mapping remains to be assessed.
- Self-reported H19 approach page, not an official source: [19GEMSDOE hub](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html).

## Review passes and remaining limitations

The current work is recorded in [`docs/research/review-log-2026-10-02.md`](docs/research/review-log-2026-10-02.md). Review passes distinguish: (1) repository/data/artifact intake, (2) adversarial source and release-gate review, and (3) final tests/site/format audit. Passing unit tests and template checks are software/format evidence, not competition validation.

Remaining high-priority work: obtain and hash the specific external layers needed for a genuinely new hypothesis; reproduce training/ensemble runs with saved code, seeds, checkpoints and uncertainty maps; implement the top hypothesis and compare it to a registered current-best OOF baseline on spatial blocks with independent uncatalogued-fault truth; validate the output GeoTIFF against the official template; only then consider a slot. Preserve public/private score distinction and update the official-board snapshot with its date, the time precision actually supplied by the source (or an explicit note that the exact time is unavailable), and the capture method.
