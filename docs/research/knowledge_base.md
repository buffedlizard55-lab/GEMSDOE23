# Knowledge base: DOE GEMS geothermal fault discovery

**Evidence snapshot:** 2026-10-02 UTC. Start from [`../../README.md`](../../README.md) before extending this file. Separate measured facts, external-source statements, self-reported claims, hypotheses, and unknowns. A source link is not proof that its data are locally present or aligned.

## 1. Official problem and evaluation context

- **Official target.** DrivenData asks for predictions of geologic faults/structures indicative of geothermal resources. Its page says the known public set may be incomplete/inaccurate and that experts manually mapped additional faults absent from the public USGS database for the Initial Prize Round. It does not reveal how those exact expert additions were sampled or prove that catalogue gaps track survey intensity. [Problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/), retrieved 2026-10-02.
- **Scoring/rounds.** The public leaderboard is not the hidden private Initial Prize Round score, and neither alone is the expanded expert-reviewed Final Prize Round score. The public page describes a 300 m distance-weighted Tversky metric. The local formula and tests are in [`src/gems/metric.py`](../../src/gems/metric.py) and [`tests/test_metric.py`](../../tests/test_metric.py); cite the exact official metric text when changing it.
- **Label semantics.** The known raster labels catalogue faults, not verified negative terrain. Staff ruling [forum 11516](https://community.drivendata.org/t/11516) says known USGS/INGENIOUS pixels are masked/excluded from evaluation. Staff ruling [forum 11536](https://community.drivendata.org/t/11536) says a “new fault” may be a new pixel/geometry on an existing fault system. This makes a known-label holdout a weak/invalid direct stand-in for the hidden “new geometry” target.
- **Submission format.** The official sample raster is the source of truth for grid, CRS, transform and footprint. Run [`scripts/validate_submission.py`](../../scripts/validate_submission.py); do not infer compliance from a generic TIFF reader. The in-footprint values must be finite and in `[0,1]`; outside cells must use the official null/NaN convention. A zero-outside fallback has `nodata=0` and is separately labelled.
- **AI and upload rules.** Consult the [official rules PDF](https://docs.nlr.gov/docs/fy26osti/96647.pdf) directly for upload frequency, AI disclosure, and final submission requirements; the board is subject to the website’s actual current rules.

## 2. Current checkout: verified facts

### Data and artifacts

- Official feature/label/template rasters are present and SHA-256 matched the public bridge manifest during this work. This establishes byte agreement with that bridge, **not** independent authenticity from the login-gated organizer download.
- `scripts/prepare_data.py` completed. Current grid: EPSG:32611; 100 m; 3292×3730; 19 bands; 5,167,373 footprint pixels; 60,988 positive known-label pixels. No missing label pixels inside the footprint. Background is unlabelled, not known absence.
- `data/external/` is absent in this checkout. External sources cited in old reports and code are not locally available unless re-acquired and re-hash-verified.
- Formal template preflight for H24 NaN-outside, H24 all-finite, and H19-5 NaN-outside is recorded in [`../data/current-template-validation.json`](../data/current-template-validation.json). All hard requirements pass. The all-finite variant differs from the sample’s NaN nodata tag; the validator records that as advisory, while confirming its outside cells equal the declared nodata value.
- Current official H24 TIFF: SHA-256 `e29e8f04e048a4aa210edbc1128dc39703e9271a11c02a5a391c7753339b0125`. Current H19-5 TIFF: `ec1f9b56b83ce33cad781ceb9f104b18fb4f2ff785263a4e89616af4aabdee8d`. These hashes identify local files only; they do not establish leaderboard attribution.
- The H24 first-page download is **QA-only, not upload-approved**. Format compliance is not spatial validation.

### Availability and historical outputs

- In the active `.venv`, NumPy/SciPy/Rasterio import; Torch, scikit-learn and pandas do not. No model training or new ensemble inference was run in this continuation.
- `docs/data/ensemble-report.json`, `docs/data/phase2-candidates.json`, `docs/data/oof-evaluation.json`, and prior model reports are historical records. Current model weights/checkpoints and several referenced external input layers are absent; do not report them as freshly reproduced.
- `docs/data/validation-report.json` is `WITHDRAWN` (irregularity I-05). It must not be used for a release gate, even though older nested fields still contain `eligible_for_submission: true`.
- [`../data/current-holdout-best.json`](../data/current-holdout-best.json) is intentionally `BLOCKED`. The strict release builder now requires a verified current-best record, exact OOF hashes and a candidate win on the same spatial folds. The known-catalogue diagnostic runner returns `PROXY_ONLY` and cannot authorize a slot.

## 3. Current public leaderboard and reported H19 methods

- The official rendered leaderboard page was read through the Arena page fetch on 2026-10-02 and saved as a manual, dated 50-row snapshot (not a continuously live API/automated feed). Top three: DARD 0.3195, alexoktaba 0.3042, Batik Shirt Brothers 0.2998. Current rows and capture provenance are in [`../data/leaderboard.json`](../data/leaderboard.json); status is in [`../data/leaderboard-status.json`](../data/leaderboard-status.json). The user-reported 0.3049 is absent; no primary official archived capture confirming it as a past leader was found.
- Current public rows at rank 26 (`smrtdoog5`) and rank 28 (`SDCF9`) display 0.1922 and 0.1894. The board does not expose an artifact digest or public submission ID. Score coincidences cannot identify the TIFF or entrant. One prior passage calls 0.1894 the highest while another lists 0.1922; numerically 0.1922 is higher, but the internal wording conflict and both artifact attributions remain unresolved.
- The nonofficial [19GEMSDOE hub](https://buffedlizard55-lab.github.io/19GEMSDOE/docs/index.html) describes: (i) fault-length/power-law tip and relay deficits; (ii) thermal/geochemical conduit inversion from springs, wells and temperature probes; (iii) 1 m/10 m 3DEP openness/local relief; (iv) geopotential lineaments and cross-line corroboration. It reports a four-quadrant holdout improvement over H16-1. These are **self-published claims**; fold maps, OOF predictions, model configs and raw validation data are not present here, so the results cannot be independently reproduced.
- The same H19 page calls H19-4/H19-5 “not live-scored yet,” lists its group best as 0.1855, and displays a 0.3168 leader. The current official page has score matches at 0.1894/0.1922 and a 0.3195 leader. Treat H19’s score attribution and its holdout/leaderboard statements as unresolved; do not call H19 the current leaderboard winner.
- A public score is one scalar over a hidden chunk. It cannot identify causal feature value, distinguish submission artifacts, show private score, or validate the final round. Causal attribution would require controlled ablations on a frozen, appropriately labelled spatial holdout.

## 4. Geological hypotheses to test (all presently unimplemented / not release-approved)

“Expected DTI potential” is **ordinal, not numerical**. No numeric ΔDTI is supportable before the hypothesis is tested against a registered current-best holdout. The ranking is a decision about scientific value and cost, not a claim of measured gain.

### H-29 — Potential-field Euler source-depth stability (rank 1)

- **Layers/data:** already-present `tmi`, `rtp`, `tmi_hg`, `tmi_vg`, `iso_grav_anom`, `iso_grav_anom_hg`, `iso_grav_anom_vg`; compare contact-like and dyke-like structural-index solutions at native grid support. Band 6 `tc` was found mislabeled in the input tag audit (I-02) and must not be assumed to be magnetic tilt.
- **Physical signature:** local Euler deconvolution estimates source edge/location/depth from potential-field values and derivatives. Retain only depth solutions stable to window/structural-index perturbations and supported by coherent, spatially connected gravity/magnetic contacts; treat isolated or implausible solutions as artifacts.
- **Why uncatalogued faults might be found:** buried basement offsets can juxtapose rocks with contrasting density/susceptibility yet leave little surface scarp. Depth-stable contacts could focus expert review in blind/covered terrain.
- **Difference from current code:** current `src/gems/geology.py` builds a consensus of geophysical gradients/edges plus external topographic/thermal terms; code search found no Euler source-location solve or structural-index stability filter. This is a new transform, not a new data source.
- **Expected DTI potential / cost:** **moderate-to-high upside**, **medium cost**. Potential-field contacts are not uniquely faults; intrusive bodies, lithologic contacts, cultural noise and the resampled 100 m grid can produce false depth solutions. No numeric uplift.
- **Method source:** open-access Scientific Reports study applies fixed-window joint Euler deconvolution to magnetic/gravity data, explaining source-depth interpretation; it is a mineral-exploration case study, not validation for geothermal fault discovery ([Hosseini et al. 2025](https://www.nature.com/articles/s41598-025-26220-9), CC BY-NC-ND 4.0).
- **Status:** data bands are available; method not implemented; spatial-holdout result **not available**. Release remains blocked.

### H-30 — Multi-height potential-field edge persistence (rank 2)

- **Layers/data:** `tmi`/`rtp` and `iso_grav_anom` with derivatives; apply Fourier upward continuation at a frozen set of heights, then measure ridge/edge persistence and cross-property coherence.
- **Physical signature:** shallow noise and acquisition-scale irregularities attenuate more quickly with continuation height; a large coherent source/contact should persist longer. Require edge position and orientation stability across heights rather than one gradient peak.
- **Why uncatalogued faults might be found:** regional/basement fault structures under basin fill may remain geophysically visible where surface maps/scarps are weak.
- **Difference from current code:** the historical feature bank mentions one fixed 150 m upward-continued TMI layer and a multiband edge consensus; this explicitly tests persistence over multiple heights and adds gravity-scale agreement. It is related prior art, not a wholly independent sensor family.
- **Expected DTI potential / cost:** **moderate**, **low-to-medium cost**; risk of smoothing away shallow geothermal structures and amplifying correlated-input evidence. No numeric uplift.
- **Method source:** the same open-access potential-field study describes upward continuation as a way to reduce shallow/high-frequency effects, but its outcomes are not transferable without testing ([Hosseini et al. 2025](https://www.nature.com/articles/s41598-025-26220-9)).
- **Status:** data bands are available; multi-height transform and holdout not run.

### H-31 — Fault-related channel deflection and knickpoint persistence (rank 3)

- **Layers/data:** derive drainage network, channel longitudinal profiles, local stream-power/gradient and reach azimuth from USGS 3DEP bare-earth DEMs at 1 m where available and 10 m as broader coverage; compare against competition magnetic/gravity contacts. Do not use a 100 m upsample as if it contained 1 m information.
- **Physical signature:** persistent channel deflection, offset, aligned knickpoints/terrace breaks, or a reach-scale orientation change across an independently inferred structural corridor; control catchment size, lithology, base level, roads, landslides and DEM seams.
- **Why uncatalogued faults might be found:** active/young faults can disrupt drainage and terrace continuity even where a mapped fault trace is absent; channel organization samples landscape response, not only local relief.
- **Difference from current code/H19:** current features emphasize openness, local relief and scarp shape; this targets network topology and longitudinal profile structure. H19’s broad claims about openness/LRM do not establish this method was tried.
- **Expected DTI potential / cost:** **moderate but coverage-dependent**, **high cost** (tile acquisition, hydrologic conditioning, channel extraction, seam/quality review). No numeric uplift.
- **Official source and obtainability:** USGS says 3DEP DEM/lidar products are free and without use restrictions, and provides a 1 m DEM availability viewer and GIS download services ([3DEP products/services](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services)). Public source is obtainable; **complete exact-AOI tile coverage, acquisition dates and quality have not been checked in this checkout**. Do not assume full coverage.

### H-32 — Deep conductance as a regional geothermal-permeability prior (rank 4)

- **Layers/data:** USGS Great Basin conductance GeoTIFFs for 2–12 km and 12–20 km depth; retain native resolution and mask outside valid data. Cross with existing magnetic/gravity contacts and candidate structures; never portray resampled coarse conductance as 100 m detail.
- **Physical signature:** a laterally coherent conductive body or depth-persistent conductivity contrast near a potential-field fault corridor may indicate fluid/alteration systems at depth; compare conductance across depth ranges to distinguish shallow basin fill from deeper conductive structure.
- **Why uncatalogued faults might be found:** regional subsurface fluid pathways may extend beyond mapped surface traces and could prioritize blind structural corridors.
- **Difference from current code/H19:** neither the official 19 bands nor the H19 page’s listed four lines establish that this regional multi-depth MT product was tested. It adds a separate electrical-conductivity observation, but the source is much deeper/coarser than fault-trace scale.
- **Expected DTI potential / cost:** **low-to-moderate**, **medium-to-high cost**; geologic nonuniqueness and deep support are major weaknesses. No numeric uplift.
- **Official source and obtainability:** USGS ScienceBase record lists five downloadable GeoTIFF grids for 2–200 km and describes their use for subsurface fluids/pathways ([ScienceBase item](https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b), DOI [10.5066/P9TWT2LU](https://doi.org/10.5066/P9TWT2LU)). The public file listing is confirmed; license metadata, grid resolution, exact AOI overlap and usefulness must be reviewed before competition use. Not locally downloaded.

### Holdout protocol for H-29 (not yet executed)

The first candidate to implement is H-29 because its input bands are already in the verified feature TIFF. Freeze structural indices, windows, allowed depth range, persistence score, metric budget and spatial folds before scoring. Compare candidate and the **registered current-best OOF prediction** on the same independent uncatalogued-fault truth, same four spatial blocks, same buffer and same scoring code. Report each fold, mean delta and win count, plus sensitivity to a second buffer/seed. The current-best registry is `../data/current-holdout-best.json` and currently `BLOCKED`; no valid comparison can be run until its required OOF prediction and independent target artifacts are available. The official known-catalogue labels may be used for a separate diagnostic only; they cannot approve a competition slot.

## 5. Deep-ensemble uncertainty and Phase 2

For independent member probabilities `p_m`, the Bernoulli-mixture decomposition is:

- `p_mean = E[p_m]`
- `U_epistemic = Var(p_m)`
- `U_aleatoric = E[p_m(1-p_m)]`
- `p_mean(1-p_mean) = U_epistemic + U_aleatoric`

The identity is exact for the mixture. Calling aleatoric uncertainty an irreducible property of geology requires calibration and a defensible observation/label-noise model, especially because background labels mean only “not in catalogue.” The paper motivating independent deep ensembles is [Lakshminarayanan, Pritzel & Blundell (2017), NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2017/file/9ef2ed4b7fd2c810847ffa5fa85bce38-Paper.pdf).

- Report member seeds/checkpoint hashes, per-candidate means and both variance terms, calibration status, and a sourced survey-coverage proxy.
- High epistemic uncertainty in terrain with low documented coverage may be a *review lead*, not automatic evidence of a fault. High epistemic uncertainty in well-surveyed terrain is a suspicion flag for model misspecification/artifact.
- Aleatoric uncertainty is reported, not used as a survey-gap reward.
- The previous JSON reports describe five independent members and Phase 2 splits but checkpoints/external inputs are absent from this checkout. Re-run and verify before public claims or model use.

## 6. Irregularities / scope controls

See [`../data/irregularities.json`](../data/irregularities.json) for the full ledger. Key active items:

- **I-01:** the supplied `sample_submission.tif` contains 60,988 ones matching the known-fault count, despite the competition page describing an all-absence example. Use it only as a grid/footprint template.
- **I-02:** band 6 `tc` tag is inconsistent with measured correlations and radiometric total count. Do not assume a tilt-angle interpretation.
- **I-05:** old catalogue-label “four-fold gate passed” is withdrawn; it is not a release gate.
- **I-14 (new):** H19 score matches, author claims and official board cannot currently be tied to specific TIFFs/submissions.
- **I-15 (new):** old builder/site treated file-format preflight as upload approval; release builder now fails closed on absent current-best/holdout evidence.
- **I-16 (new):** historical docs name external layers that are not present locally.

## 7. Next work

1. Acquire/verify official DEM coverage for the exact AOI if H-31 is pursued; obtain and review all licenses/metadata before use.
2. Implement H-29 without looking at validation labels; write deterministic tests on synthetic potential fields and preserve code/config hashes.
3. Find/rebuild the current-best independent spatial OOF map and truth data. Keep the registry `BLOCKED` until evidence meets schema.
4. Run frozen spatial holdout vs the current best; do not replace this with a public score projection, the official known-label catalogue, or unverified H19 claims.
5. Retrain independently seeded ensemble members in an environment with checkpoint retention; report uncertainty and survey coverage for every Phase 2 candidate.
6. Only if a candidate clears the gate, build a uniquely named single-band GeoTIFF, run the official-template preflight, update Pages, and consider a slot.
