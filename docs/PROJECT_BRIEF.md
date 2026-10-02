# GEMS DOE project brief

**Read `README.md` first at the start of each session.** This file is the working brief and evidence log; the README is the durable aim and release policy.

## Objective

Discover geothermal-relevant geological faults/structures not captured in the USGS/INGENIOUS known-fault catalogue. The competition's stated target is a manually mapped set of faults absent from the existing public USGS fault database, and the competition warns that known labels may be incomplete or inaccurate ([official task description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/)). Optimize for scientifically credible discoveries and the actual distance-weighted Tversky metric, not for reproducing catalogue pixels.

## Current state (2026-10-02 UTC)

### Data and environment

- Official `training_features.tif`, `labels.tif` and `sample_submission.tif` are present locally and match the SHA-256 hashes recorded in the public bridge manifest. This authenticates agreement with that mirror only; it is not an independent signature from the login-gated competition server.
- `scripts/prepare_data.py` completed. Prepared grid: EPSG:32611, 100 m, 3292×3730, 19 bands; 5,167,373 footprint pixels and 60,988 positive catalogue pixels. Background label pixels are unlabelled, not verified fault-free.
- `data/external/` is not present. Do not claim the USGS SGMC, 1 m lidar, radiometric extension, GDR spring/well or 2 m temperature layers are locally available in this checkout merely because older code or reports refer to them.
- `.venv` currently has NumPy/SciPy/Rasterio, but no Torch, scikit-learn or pandas. No deep model training or new ensemble inference was performed in this continuation. Existing ensemble/Phase 2 JSON files are historical records without current checkpoint/input reproduction in this checkout.

### Submission artifact and gate

- H24 and H19-5 TIFFs were formally checked with `scripts/validate_submission.py` against the official template. Their hard format checks pass: one float32 band; EPSG:32611; dimensions and affine transform match; finite in-footprint values lie in `[0,1]`; no infinities; outside cells satisfy the template null convention. Details, hashes and all advisory outcomes are in [`data/current-template-validation.json`](data/current-template-validation.json).
- The first-page H24 download remains useful as a **QA candidate**. It is not a model recommendation and is not cleared for a competition slot. The all-finite variant's `nodata=0.0` difference is advisory and is documented.
- The submission generator has been split conceptually: `build_submission_live.py` can create/preflight research candidates but always records `release_approved=false`; `build_submission.py` is the release path and requires both a passing four-fold OOF comparison and a verified current-best registry record.
- [`data/current-holdout-best.json`](data/current-holdout-best.json) is intentionally `BLOCKED`. The only old detailed comparison [`data/validation-report.json`](data/validation-report.json) is `WITHDRAWN` (I-05): it evaluated known catalogue labels, which are masked from competition scoring, and its validation design was not fit to release a new-fault submission. The known-label runner now labels its output `PROXY_ONLY` and cannot approve release.

### Leaderboard / H19 claims

- The official public leaderboard page was fetched through the Arena page reader on **2026-10-02** and persisted as a dated 50-row manual snapshot (not an automated/live API feed). It records DARD 0.3195, alexoktaba 0.3042 and Batik Shirt Brothers 0.2998 at ranks 1–3. The user-reported 0.3049 is absent; no primary archived capture confirming it as an earlier official leader was found.
- Scores matching the reported H19 values appear on the public board at 0.1922 (smrtdoog5, rank 26) and 0.1894 (SDCF9, rank 28). DrivenData's page exposes no prediction-file hashes or public submission IDs; score equality is not attribution. Prior prose calling 0.1894 the “highest” conflicts with 0.1922 elsewhere; numerically 0.1922 is higher, but neither is verified as an H19 artifact.
- The self-published [19GEMSDOE hub](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html) describes power-law fault population scaling, thermal/geochemical conduit inversion, 1 m/10 m topographic openness/local relief, and geophysical lineaments. It reports four-quadrant holdout results, but those numbers and the evaluation data are absent here and have not been independently reproduced. The same page calls H19-4/H19-5 “not live-scored yet”, lists a group best of 0.1855, and displays a 0.3168 leader. Those statements conflict with score matches on the current official board and its 0.3195 leader. Treat H19 holdout and score attribution as unresolved, not as established fact.
- There is no sound causal explanation for a reported H19 score from one scalar public result. Controlled ablation on a frozen, spatially blocked holdout is required to isolate feature contributions.

### New hypotheses

The current shortlist is maintained on [`hypotheses.html`](hypotheses.html) and in [`research/knowledge_base.md`](research/knowledge_base.md). It contains four not-yet-implemented ideas ranked by ordinal DTI potential and cost. No numeric uplift is claimed because a valid current-best holdout does not exist. The highest-ranked hypothesis is a proposed potential-field source-depth/edge-stability analysis using existing magnetic and gravity bands; it has not passed a spatial holdout and is not approved for a slot.

### Uncertainty

The Phase 2 interface and decomposition logic are in `src/gems/uncertainty.py`; the reported ensemble method is documented in `docs/data/ensemble-report.json` and its review candidates in `docs/data/phase2-candidates.json`. These records describe independently initialized members, but this continuation did not reproduce their weights/checkpoints or retrain the ensemble. Do not report those uncertainty values as freshly generated. Before reuse, retrain/save independent model artifacts, verify training provenance, and re-export candidate-level epistemic and aleatoric components plus survey coverage.

## Release checklist (all required)

1. Freeze the candidate configuration and code/spec hash.
2. Register the current-best OOF candidate, exact OOF prediction SHA-256, holdout/truth semantics, truth SHA-256, spatial fold definition, and prior validation-report hash in `data/current-holdout-best.json` only after independent review.
3. Produce four spatially blocked out-of-fold predictions for the candidate and current best on the same independent uncatalogued-fault target and frozen folds. Do not use random pixel splits or tune the candidate on its holdout.
4. Recompute the gate from fold metrics; candidate must beat the registered current best under the documented minimum mean delta and fold-win criteria. Preserve all predictions/reports/hashes.
5. Build the final probability raster with `scripts/build_submission.py`; verify the final output against `sample_submission.tif` using the strict validator.
6. Confirm `[0,1]`, single-band float32, template CRS/shape/geotransform and footprint null encoding. Save the unique file, short note, and SHA-256.
7. Only then consider a weekly submission slot. Record the returned public score and keep it distinct from private-round or final-round results.

The checklist is currently blocked at steps 2–4. No submission slot should be used.

## Research sources

- [DrivenData task and data](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/): target definition, supplied bands, public/private/Final Prize Round distinction and metric.
- [Official public leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/): dated snapshot in `data/leaderboard.json`, caveats in its metadata.
- [USGS GeoDAWN](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and), [ScienceBase item](https://www.sciencebase.gov/catalog/item/657e1d85d34e23d3533209f7), DOI [10.5066/P93LGLVQ](https://doi.org/10.5066/P93LGLVQ): official airborne magnetic/radiometric products; Area 1 and Area 2 acquisition geometries differ.
- [USGS 3DEP products and services](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services): free elevation products and coverage tools; exact 1 m tile coverage must be checked for the competition footprint.
- [USGS Great Basin conductance data release](https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b), DOI [10.5066/P9TWT2LU](https://doi.org/10.5066/P9TWT2LU): five public GeoTIFF depth-integrated conductance grids; regional and very deep, so local fault-scale utility is uncertain.
- H19 self-report (not official and not independently reproduced): [19GEMSDOE hub](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html).

## Review / limitations

Three implementation/review passes are recorded in [`research/review-log-2026-10-02.md`](research/review-log-2026-10-02.md). The final pass includes the test suite, static-site checks and formal TIFF template preflight; these do not constitute competition validation.

Remaining limitations: no valid current holdout-best baseline; no external layers or saved model checkpoints in this checkout; no fresh deep-ensemble uncertainty output; no independent reproducible H19 evaluation; no new geological candidate has passed the required spatially blocked test. Preserve these blockers in future updates—do not replace them with an upload recommendation based only on a score projection.
