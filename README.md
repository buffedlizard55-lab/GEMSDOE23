# GEMSDOE23 — GEMS fault-discovery research and submission system

> **Session-start rule:** Before changing this project, read this README from top to bottom and read [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md). That is the persistent project brief: the scientific goal, the supplied score history, the required uncertainty treatment, the submission constraints, and the standing verification rules. Update it when verified evidence changes.

## At a glance

- **Competition:** DOE Geologic Enhanced Mapping System (GEMS) Prize, DrivenData competition 306.
- **Task:** map likely geological-fault traces in the GeoDAWN region; the submission is a single-band, 32-bit-float GeoTIFF on the competition grid, with confidence values in `[0, 1]` and null/NaN outside the data bounds.
- **Current state:** this checkout started as an 11-byte README-only repository. No competition data, training code, model, holdout reports, or previous submission artifacts were present.
- **Hard blocker:** the official DrivenData data URL redirects unauthenticated visitors to its login page. We do not have competition-account access in this environment and will not bypass authentication or invent data. Therefore **no new model has been trained, no spatial holdout has run, and no new competitive prediction has been generated here**.
- **Useful existing artifact:** the landing page exposes a downloadable copy of the previously published H19-5 GeoTIFF as a *reference artifact only*. Its binary raster metadata and finite value range were independently checked in this checkout. It was not produced by this checkout; exact equality to the official sample grid and attribution of a public leaderboard score to this file remain unverified.

## First-click download

The site landing page makes the existing reference file obvious. The file is [`gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif`](docs/downloads/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif). It is a copy of the artifact linked from the [19GEMSDOE submission page](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html), SHA-256 `ec1f9b56b83ce33cad781ceb9f104b18fb4f2ff785263a4e89616af4aabdee8d`.

**Do not mistake this for a new, holdout-qualified submission from GEMSDOE23.** The pixel values pass the `[0, 1]` check where finite, but the exact official template/footprint comparison cannot be completed without the authenticated sample-submission raster. Do not spend a submission slot on this copied artifact unless you have independently checked your submission history and the official template.

Suggested identifying note (not a performance claim):

```text
GEMSDOE23 reference copy: H19-5, artifact e27054cf; not a new model; score-to-file association unverified
```

The [Executive Summary & Upload Guide](docs/executive-summary.html) has the exact upload steps and the pre-upload caveats. The supported submission output remains **one band**; ensemble variance and reviewer notes belong in separate sidecars, not extra submission bands.

## What we learned from the requested score review

The official public leaderboard was retrieved on **2026-10-02** and persisted as a 50-row dated snapshot. It showed DARD at **0.3195** (rank 1) and alexoktaba at **0.3042** (rank 2). The prompt-reported former leader `0.3049` is not current and was not independently authenticated as a historical board result in this retrieval. The supplied H19-5 `0.1922` and H19-4 `0.1894` values match public rows at ranks 24 and 26, respectively, but the board does not expose a file hash, public submission ID, or team/account proof tying either score to a particular TIFF. Treat these only as score-level matches. Public scores are not private Phase 1 or expert-updated Phase 2 results.

The H19 site describes a multi-line candidate combining power-law fault-length completeness, thermal/geochemical conduit evidence, 1 m/10 m DEM openness and local relief, and geophysical lineaments. Those are plausible *hypotheses*, not a causal explanation of the public score. Its own spatial-proxy results cannot establish performance on the hidden labels. The competition's public test score is not the private Phase 1 score or the Phase 2 expert-reviewed score. See [`docs/results.html`](docs/results.html) and [`docs/verification.html`](docs/verification.html) for the dated snapshot and irregularities.

## Scientific direction and uncertainty policy

We will test, not assume, the claim that catalogue omissions are concentrated in historically under-surveyed terrain. For every candidate sent to a human review package, the intended report includes:

- the ensemble-mean model confidence (a calibrated probability only if supported by an out-of-fold calibration report);
- **epistemic variance** across independently initialized and independently trained networks;
- **aleatoric / within-member Bernoulli variance**;
- the total predictive variance and a calibration/status note;
- the mapped-survey-coverage proxy and its source; and
- a separate discovery-priority score.

For a uniform ensemble of Bernoulli predictions `p_m`, the decomposition is

`Var(Y) = Var_m(p_m) + E_m[p_m(1 - p_m)]`.

The first term is epistemic disagreement; the second is conditional Bernoulli (aleatoric) uncertainty. The latter is only interpretable as intrinsic geological/annotation ambiguity if the probabilities are calibrated and the label process is appropriate. We will say when that condition is not established. The ensemble members are separate models, each initialized and trained independently; test-time dropout is not used. **No out-of-fold calibrator has been fitted in this checkout.** Unless a verifiable calibration report is supplied, inference marks outputs uncalibrated model-confidence scores; do not present the aleatoric component as validated geological ambiguity.

A separate, preregistered survey-gap term raises the review priority of epistemically uncertain candidates in mapped-low-coverage areas and lowers it in mapped-high-coverage areas. **It never silently changes the submission probability raster.** The survey-coverage proxy is not fieldwork truth: map coverage/scale and actual field effort are different. If a defensible coverage layer is unavailable, the adjustment is omitted and reported as unknown.

The source-screened shortlist of three distinct geological tests is in [`docs/hypotheses.html`](docs/hypotheses.html): (1) public GeoDAWN K/eU/eTh radiometric-ratio/edge evidence corroborated by independent structure, (2) 3DEP drainage deflection and channel-profile breaks, and (3) depth-coherent USGS MT conductance boundaries. The first uses a public USGS/DOE CC0 release, but its raster bands, masks, exact alignment, and local download have not been checked. The already-coded edge-consensus function is an unscored diagnostic, not the new top candidate or a validated incumbent. No new geological feature was implemented, no competition holdout exists, and no weekly slot should be spent until the top candidate beats a reproducible baseline on frozen, spatially blocked folds.

## Core values

### Maximize P(Win)

Choose work by expected competition value, evidence quality, and risk—not novelty for its own sake. Use controlled comparisons and conserve submission opportunities. A small, reproducible holdout gain is a prerequisite, not a guarantee of leaderboard improvement.

### Own the Outcome

Own the full path from source provenance to a valid GeoTIFF, reviewer interpretation, current leaderboard feed, and honest reporting. When evidence is missing, expose the blocker, build the next useful tool, and never turn an assumption into a result.

## Standing project brief — non-negotiable requirements

1. **Research before modeling.** Read the official competition problem, data page, rules, current leaderboard, scientific literature, and organizer reference solution. Keep dated links, evidence scope, and uncertainty about third-party claims in the source register.
2. **Be autonomous but respect access controls.** Automate public, free, correctly licensed inputs where possible. The competition data tab is login-gated in this environment; do not request, store, or bypass credentials. Report exact blockers instead of fabricating access or evidence.
3. **Make outputs usable.** Keep the first screen's single-band GeoTIFF download obvious, with an executive summary, exact upload steps, a unique filename, and a short note. Validate against the official sample template after writing and rereading; finite in-footprint values must be in `[0,1]`, and outside pixels must be null/NaN.
4. **Rank new geology tests before implementation.** Record three to five falsifiable hypotheses, exact layers/signatures, why they could find uncatalogued faults, differences from prior methods, likely value/cost, and data dependencies. Public external data must have verified provenance/license and AOI accessibility.
5. **Require local evidence before consuming a slot.** Compare equal-budget candidates to a reproducible incumbent on frozen spatially blocked folds with buffers. A candidate must pass the predeclared local gate; a public leaderboard score is not a substitute. The current known-catalogue proxy does not reveal hidden-fault performance.
6. **Keep ensemble uncertainty substantive.** Use independently initialized and fully trained members, not dropout-at-inference. Report mean, epistemic variance, conditional/aleatoric variance, total variance, calibration status, and survey-coverage source separately. Do not call epistemic disagreement “noise.”
7. **Use coverage as evidence, not truth.** Raise review priority for epistemic uncertainty in independently supported low-coverage terrain; scrutinize similarly high disagreement in well-mapped terrain. Map coverage is only a proxy for field effort; if unavailable, omit the adjustment and label it unknown. Never silently alter the submission raster with a triage score.
8. **Separate phases and own disclosure.** Distinguish public, private Phase 1, and expert-updated Phase 2 scores. The official rules require applicable generative-AI use to be disclosed in the narrative; the competitor remains responsible for accuracy.
9. **Review in three passes.** Build and test; adversarially review assumptions, edge cases, and provenance; then re-check every requirement and rerun tests. Record the review and what was not runnable.
10. **Own the outcome.** Preserve data/code/config/seed/output hashes, expose limitations, use Arena values **Maximize P(Win)** and **Own the Outcome**, and create/merge a pull request when repository access permits.

The detailed source-checked charter and complete user-supplied score history are preserved in [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md). This README is the mandatory starting point; the linked ledger supplies the full historic row-by-row score list and current evidence notes.

## Verified sources to review

| Source | What it establishes | Link |
|---|---|---|
| Competition problem and submission format | Fault-mapping task, distance-weighted Tversky score, CRS/resolution/float32/range/null-outside requirements | [DrivenData problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/) |
| Current public leaderboard | Public participants' current public scores (a moving snapshot) | [DrivenData leaderboard](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/) |
| Official prize rules (September 2026) | Data access requires registering; weekly feedback submissions; one final selection; Phase 1/Phase 2 evaluation; AI disclosure requirement | [NLR/DOE PDF](https://docs.nlr.gov/docs/fy26osti/96647.pdf) |
| Competition data tab | Official data page; unauthenticated access redirects to login | [DrivenData data page](https://www.drivendata.org/competitions/306/competition-doe-gems/data/) |
| GeoDAWN data release | Public USGS/DOE magnetic and radiometric grids; DOI `10.5066/P93LGLVQ`; USGS marks the release CC0 1.0 | [USGS GeoDAWN](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and) |
| 3DEP products | Free official lidar/DEM products; a preliminary 1 m index query found only a dissolved intersecting polygon, not tile-level/full-footprint proof | [USGS 3DEP products](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services) · [1 m index](https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer?f=pjson) |
| Great Basin MT conductance | USGS catalog lists five public depth-band GeoTIFFs; exact AOI pixel coverage/resolution/alignment/reuse terms not checked | [ScienceBase DOI `10.5066/P9TWT2LU`](https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b) |
| Official public leaderboard | Dated 50-row capture as of 2026-10-02; rank/score matches do not establish H19 file attribution | [Public board](https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/) · [`docs/data/leaderboard.json`](docs/data/leaderboard.json) |
| Geologic-map coverage | NGMDB map catalog and map-coverage limitations | [USGS NGMDB FAQ](https://www.usgs.gov/faqs/what-national-geologic-map-database) · [NGMDB MapView](https://ngmdb.usgs.gov/mapview/index.html) |
| Deep ensembles | Independently trained ensembles as a scalable uncertainty estimator | [Lakshminarayanan, Pritzel & Blundell (NeurIPS 2017)](https://proceedings.neurips.cc/paper_files/paper/2017/file/9ef2ed4b7fd2c810847ffa5fa85bce38-Paper.pdf) |
| Official baseline / input inventory | Organizer reference notebook; it uses `data/numeric_features.tif` while the official problem page calls the feature file `training_features.tif`. Local prep accepts either name and fails if both are present. | [DrivenData reference notebook](https://github.com/drivendataorg/gems-prize-reference-solution/blob/main/unet-mc-cv-reference-solution.ipynb) |

See [`docs/sources.html`](docs/sources.html) for claim-by-claim scope and source caveats.

## Reproducible workflow

The code is designed to fail closed when inputs are absent or misaligned. It will not download private competition files or ask for credentials. The four-fold workflow is spatial, excludes a training buffer around each validation quadrant, and reports a **known-catalogue proxy**, not the hidden-fault contest score. The commands below exercise only the existing baseline/edge-consensus pipeline; that edge feature is unscored and is not the newly ranked radiometric candidate. The public GeoDAWN radiometric test has not been implemented, and the example does not authorize a submission.

```bash
set -euo pipefail

# Optional: confirm the data-placement blocker / detect files already in data/
bash scripts/download_competition_data.sh || true

# After files are legitimately available in data/:
python -m pip install -r requirements.txt
python scripts/prepare_data.py
python -m pip install -r requirements-model.txt

# Optional legacy edge-consensus diagnostic, using actual band descriptions.
# It is not the new radiometric shortlist leader and has no holdout score.
# The script fails closed if names are missing/ambiguous; it does not guess indexes.
python scripts/build_edge_consensus.py

# Train and infer 4 spatial folds for the baseline and legacy edge-consensus diagnostic (5 separate networks per fold).
for config in configs/default.json configs/h1-edge-consensus.json; do
  out=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["output_dir"])' "$config")
  for fold in 0 1 2 3; do
    python scripts/train_ensemble.py --config "$config" --holdout-fold "$fold"
    python scripts/predict_ensemble.py --config "$config" \
      --model-dir "$out/fold-$fold" --out-dir "$out/fold-$fold/predictions"
  done
done

# Assemble out-of-fold rasters, then compare the candidate against the same-fold baseline.
python scripts/build_oof_map.py --candidate-id baseline-unet \
  --fold-runs outputs/baseline/fold-0 outputs/baseline/fold-1 outputs/baseline/fold-2 outputs/baseline/fold-3 \
  --output outputs/baseline-oof.npy --metadata outputs/baseline-oof.json
python scripts/build_oof_map.py --candidate-id H1-edge-consensus \
  --fold-runs outputs/h1-edge-consensus/fold-0 outputs/h1-edge-consensus/fold-1 outputs/h1-edge-consensus/fold-2 outputs/h1-edge-consensus/fold-3 \
  --output outputs/h1-oof.npy --metadata outputs/h1-oof.json
python scripts/run_spatial_validation.py --candidate outputs/h1-oof.npy \
  --incumbent outputs/baseline-oof.npy --metadata outputs/h1-oof.json \
  --incumbent-metadata outputs/baseline-oof.json \
  --output outputs/h1-validation-report.json

# Generic output-pipeline example only. Do not use the legacy H1 unless it
# actually passes the frozen spatial holdout gate; it is not validated now.
python scripts/train_ensemble.py --config configs/h1-edge-consensus.json
python scripts/predict_ensemble.py --config configs/h1-edge-consensus.json \
  --model-dir outputs/h1-edge-consensus/full-ensemble --out-dir outputs/h1-final
python scripts/build_submission.py --strategy H1-edge-consensus \
  --probabilities outputs/h1-final/mean_probability.npy \
  --template data/sample_submission.tif --config configs/h1-edge-consensus.json \
  --inference-report outputs/h1-final/uncertainty-report.json \
  --gate-report outputs/h1-validation-report.json

# Unit and synthetic end-to-end tests (does not access private data or train a model)
python -m unittest discover -s tests -v
```

The complete constraint list, historical score table, open hypotheses, and session protocol are in [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md). Current public scores are refreshed by the GitHub Pages workflow when available; the static page retains its dated snapshot if DrivenData is unreachable.
