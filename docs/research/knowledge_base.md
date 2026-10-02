# Knowledge base: DOE GEMS fault discovery

**Evidence snapshot:** 2026-10-02 UTC. This file separates verified facts, working geological hypotheses, and unknowns. Update only with a source URL, access date, relevant passage/result, and scope limitation. The complete user-provided score ledger remains in [`../PROJECT_BRIEF.md`](../PROJECT_BRIEF.md).

## Verified problem structure

1. GEMS asks for predictions of geological faults/structures indicative of geothermal resources in the GeoDAWN region. The official competition description says the known public fault set is incomplete and may contain inaccurate data; experts manually identified additional faults absent from the public USGS database for the initial test set. This does **not** establish that catalogue omissions are caused by low historical field effort in any particular terrain. Source: [DrivenData problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/), retrieved 2026-10-02.
2. Competition metric: distance-weighted Tversky index with `alpha=0.2`, `beta=0.8`, triangular support `R=300 m`, as stated on the problem page. Public score is not private Phase 1 or final Phase 2 performance.
3. Submission requirements: one band, float32, EPSG:32611, 100 m, same bounds as training, `[0,1]` on valid data and null/NaN outside. The exact official sample raster remains the operational source for shape, transform, and footprint checks.
4. Feature-file naming differs across official/organizer materials: the problem page names `training_features.tif`, while the [reference notebook](https://github.com/drivendataorg/gems-prize-reference-solution/blob/main/unet-mc-cv-reference-solution.ipynb) uses `data/numeric_features.tif`. The notebook's printed 19-band inventory names magnetic, gravity, strain, seismic, topographic, and subsurface fields; it does not list K/eU/eTh radioelement channels. That printed notebook output is a useful source-level prior-art check, not confirmation of the inaccessible competition TIFF's current tags.
5. Rules: [DOE/NLR official rules PDF](https://docs.nlr.gov/docs/fy26osti/96647.pdf), September 2026. Section 3.4 allows up to three feedback submissions per week subject to the website; sections 1.1 and 3.5 distinguish public/private and Phase 1/Phase 2 and require one final selection. Section 3.2 requires generative-AI use to be indicated in the narrative when applicable.
6. Official data-tab access was rechecked on 2026-10-02: unauthenticated access redirects to `/accounts/login/`. The model feature raster, labels, sample template, and `1m_DEM_links.csv` are not present in this checkout. Do not bypass access controls, ask for credentials, or claim a model/holdout/submission exists.

## Public leaderboard snapshot and attribution

The official public leaderboard page was retrieved through the Arena web reader on 2026-10-02. It showed DARD at **0.3195 (rank 1)** and alexoktaba at **0.3042 (rank 2)**. The supplied H19-5 value **0.1922** matched a displayed public row at rank 24 (smrtdoog5); H19-4 **0.1894** matched rank 26 (SDCF9). The `+0.0028` difference is a score-level comparison only. The board does not expose the evaluated TIFF digest or public submission identifier, so neither match verifies account/team/file attribution. The prompt-reported former leader **0.3049** is not the current leader and was not independently authenticated as a historical board result in this retrieval. Public rows do not establish either private Initial Prize Round or expert-updated Final Prize Round scores.

The 50-row dated capture, retrieval method, and attribution/phase caveats are persisted in [`../data/leaderboard.json`](../data/leaderboard.json). Direct shell `urllib` refresh failed with TLS/SSL EOF; the dated official page capture was still readable in the web tool. The automated workflow remains a fallback and should mark the feed stale if its next direct refresh fails.

## Official source notes and data-lead screening

### GeoDAWN airborne radiometry — ranked candidate 1

- Official USGS/DOE data release: [GeoDAWN](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and), DOI [`10.5066/P93LGLVQ`](https://doi.org/10.5066/P93LGLVQ). USGS marks it CC0 1.0. ScienceBase lists Area 1 and Area 2 GeoTIFF archives (~43.6 MB and ~230.5 MB) with metadata and a ReadMe; the page describes the competition study region as GeoDAWN.
- Glen & Earney's [USGS-authored technical manuscript](https://publications.mygeoenergynow.org/grc/1034804.pdf), retrieved 2026-10-02, describes K, equivalent U, and equivalent Th radiometric measurements. It notes near-surface sensitivity (roughly the upper half-meter), flight-height/cover/moisture caveats, and shows GeoDAWN potassium contrasts at mapped geological boundaries and within previously mapped units. This supports a testable mapping hypothesis, not fault ground truth.
- The candidate transform is native-resolution, quality-masked K/eTh and eU/eTh ratios (only after positive-value, unit, and band-name checks), multiscale gradients, and line persistence corroborated with competition magnetic/topographic evidence. Actual files were not downloaded; band names, units, valid masks, CRS, and exact pixel overlap remain unknown. A listed public archive is not proof of local usability.
- Prior-art scope: supplied H19 pages describe thermal/geochemical reasoning, openness/local relief, and geophysical lineaments. The organizer notebook's printed 19-band inventory does not list radioelement channels, but the actual authorized feature raster and all earlier project manifests still require inspection before claiming novelty.

### Elevation / lidar — ranked candidate 2

- [USGS 3DEP products](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services) are free and without use restrictions; USGS links public 1 m DEM availability/download services.
- A preliminary query of the official [3DEP elevation index](https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer?f=pjson), 1-meter layer, using the reference TIFF's broad EPSG:32611 envelope returned one intersecting feature labelled `dissolve`. It had no tile identifiers and did not establish complete AOI coverage. `1m_DEM_links.csv` remains inaccessible/missing; exact tiles, acquisition dates, and quality are unknown.
- Candidate: multi-channel drainage deflection and channel-profile/knickpoint persistence, with controls for lithology, catchment size, base level, roads, and landslides. This differs from the supplied H19 openness/local-relief/scarp/ridge methods but has high processing cost.

### Multi-depth MT conductance — ranked candidate 3

- [USGS ScienceBase release](https://www.sciencebase.gov/catalog/item/62979746d34ec53d276c113b), DOI [`10.5066/P9TWT2LU`](https://doi.org/10.5066/P9TWT2LU), lists five GeoTIFF conductance products: 2–12, 12–20, 20–50, 50–90, and 90–200 km. The record says these are derived from a regional 3-D MT inversion of publicly available transfer functions and are intended to inform subsurface fluids/pathways. Its geographic bounding box overlaps the broad Great Basin/GeoDAWN region.
- Exact valid-pixel overlap, coordinate transform, pixel resolution, and reuse terms have not been checked on downloaded rasters. Conductance is non-unique (for example, fluids, conductive basin fill, graphite, or alteration) and is a coarse regional context, not a fault trace. Test only depth-persistent broad boundaries at native support; do not interpret an upsampled grid as 100 m information.

### Screened-out public layers

- [Regional geophysical maps](https://www.sciencebase.gov/catalog/item/628d4fabd34ef70cdba3c4a4), DOI `10.5066/P9Z6SA1Z`, list a 6.5 MB gravity/magnetic/depth-to-basement grid package. Those source classes overlap the competition features; no new independent measurement or scale advantage was established, so the package is not ranked.
- [USGS slip/dilation-tendency release](https://www.sciencebase.gov/catalog/item/6296974dd34ec53d276bb33d), DOI `10.5066/P9YL58W6`, lists public shapefile/KMZ products for slip/dilation tendency calculated on existing Quaternary-fault segments. It is not a direct unknown-fault raster and using known fault geometries as an answer key risks circularity. The supplied H20-1 history also names a wing-crack/mechanical method; therefore this is not advanced as a distinct new test.
- [DOE/NREL GDR 1391](https://gdr.openei.org/submissions/1391), DOI `10.15121/1881483`, lists a CC BY 4.0 INGENIOUS compilation including geodetic, thermal, fault, earthquake-density, well, and spring data. The public listing does not show predictive benefit, and several layers overlap prior H19 thermal/geochemical reasoning; it is not used as a novelty claim.

## Uncertainty and review policy

Reference: Lakshminarayanan, Pritzel & Blundell (2017), [NeurIPS paper](https://proceedings.neurips.cc/paper_files/paper/2017/file/9ef2ed4b7fd2c810847ffa5fa85bce38-Paper.pdf). Use separately initialized and independently optimized members; do not approximate this with test-time dropout.

For member probabilities `p_m`, a uniformly mixed Bernoulli ensemble has:

- `p_mean = E_m[p_m]`;
- `U_epistemic = Var_m[p_m]`;
- `U_aleatoric = E_m[p_m (1 - p_m)]`;
- `U_predictive = p_mean (1 - p_mean) = U_epistemic + U_aleatoric`.

This is a mathematical variance identity. Calling the conditional Bernoulli term irreducible geological/annotation ambiguity additionally requires calibration and an appropriate model of the incomplete-label observation process. High epistemic disagreement in independently supported low-map-coverage terrain may elevate reviewer priority; the same disagreement in well-mapped terrain requires scrutiny. NGMDB coverage is a map/publication proxy, not direct field-effort truth. Review priority must remain separate from the one-band prediction raster. Every human-review candidate must receive all variance terms and calibration/coverage caveats.

## Current hypothesis register and gate

The current ranked shortlist is documented in [`../hypotheses.html`](../hypotheses.html): (1) official GeoDAWN K/eU/eTh ratio/gradient anomalies corroborated by independent structure; (2) cross-channel 3DEP drainage deflection/profile breaks; (3) depth-coherent upper-crustal MT conductance boundaries. A fourth, separate reviewer-priority analysis combines independently trained-ensemble epistemic variance with independently sourced NGMDB map-coverage metadata; it is not a direct DTI feature.

The previously coded edge-consensus feature (`src/gems/geology.py`) is not a new shortlist candidate or a validated incumbent; it remains an unscored diagnostic/ablation. No new geologic feature code was added in this review. The top radiometric candidate must be compared with a reproducible baseline on frozen, buffered spatial folds, equal compute/candidate budget, and the official DTI support before any weekly upload is considered. No real fold score, trained model, calibrated ensemble, or new TIFF exists here.

## Open unknowns

- Actual training raster band tags/order/nodata, label encoding, valid footprint, official sample grid, and the permitted competition-account data inventory.
- Exact GeoDAWN radiometric bands/units/masks and overlap with the contest template; exact 3DEP tile IDs/coverage/quality; exact MT conductance raster support and terms.
- Geographic distribution and label uncertainty of private newly identified faults.
- Whether omitted faults concentrate in historically under-surveyed locations; official competition materials establish incompleteness, not this cause.
- Which previous H19 artifact received which leaderboard score; no hash-to-submission mapping is public in the retrieved leaderboard.
- Whether local spatial holdout wins predict hidden test, public/private, or expert-updated Phase 2 performance.
- Actual uncertainty calibration and survey-coverage quality; no model or data are present to measure these.
