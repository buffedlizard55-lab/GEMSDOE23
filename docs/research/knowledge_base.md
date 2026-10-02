# Knowledge base: DOE GEMS fault discovery

**Evidence snapshot:** 2026-10-01 UTC. This file separates verified facts, working geologic hypotheses, and unknowns. Update only with a source URL, access date, relevant passage/result, and scope limitation.

## Verified problem structure

1. GEMS asks for predictions of geological faults/structures indicative of geothermal resources in the GeoDAWN region. The official competition description says the known public fault set is incomplete and may contain inaccurate data. It says experts manually identified additional faults absent from the current public USGS database for the initial test set. Source: [DrivenData problem description](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/).
2. Competition metric: distance-weighted Tversky index with `alpha=0.2`, `beta=0.8`, triangular kernel support `R=300 m`, as stated on the problem page. Higher beta penalizes missed ground-truth faults more than the corresponding alpha false-positive term. Public score is not private Phase 1 or final Phase 2 performance.
3. Submission requirements: one band, float32, EPSG:32611, 100 m, same bounds as training, `[0,1]` on valid data and null/NaN outside. The official problem page says a sample submission is provided; that exact raster is the operational source for shape, transform, and footprint checks.
4. Feature-file naming has a documented source discrepancy: the official problem page names `training_features.tif`, while the organizer's [reference notebook](https://github.com/drivendataorg/gems-prize-reference-solution/blob/main/unet-mc-cv-reference-solution.ipynb) sets `FEATURE_DATA_PATH = data/numeric_features.tif`. Local preparation accepts exactly one of those names and rejects both-present ambiguity; the authenticated data inventory is still needed to verify which file was downloaded.
5. Rules document: [DOE/NLR official rules PDF](https://docs.nlr.gov/docs/fy26osti/96647.pdf), September 2026. Section 3.4 allows up to three feedback submissions per week subject to the website; sections 1.1 and 3.5 describe public/private and Phase 1/Phase 2 distinction and require one final selection. Section 3.2 requires generative-AI use to be indicated in the narrative when applicable.
6. Official data-tab access: retrieved page redirected unauthenticated visitor to the DrivenData login route on 2026-10-01. The data cannot be reconstructed here by guessing or bypassing access controls.

## Official source notes

### GeoDAWN airborne geophysics

- USGS/DOE data release: [GeoDAWN airborne magnetic and radiometric surveys](https://www.usgs.gov/data/geodawn-airborne-magnetic-and-radiometric-surveys-northwestern-great-basin-nevada-and), DOI `10.5066/P93LGLVQ`.
- The release describes airborne surveys in northern/western Nevada and eastern California intended to support geologic/geophysical mapping and geothermal/critical-mineral studies.
- The official problem page lists TMI, reduced-to-pole magnetics, isostatic gravity, surface conductivity, and depth to conductive base surface among the features. The organizer reference notebook prints a 19-band description list including raw TMI, raw isostatic gravity, reduced-to-pole, `Conductivity surface`, plus separate slope/gradient bands; it sets the feature path to `numeric_features.tif`. Those notebook outputs are useful as an organizer-published inventory, but this checkout has not opened the authorized raster.
- The notebook's printed `Depth to basement surface` tag is not safely interchangeable with the official page's `depth to conductive base surface`. The H1 resolver therefore does not guess that mapping. H1 remains blocked until the downloaded raster metadata confirms the exact channel; the resolver also excludes TMI/gravity derivative bands when selecting raw scalar fields.
- A magnetic/gravity/conductivity edge is evidence of a physical contrast, not proof of a fault. Lithologic contacts, acquisition/processing effects, and raster seams are alternative explanations.

### Elevation / lidar

- [USGS 3DEP product page](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services) states 3DEP elevation products are free of charge and without use restrictions; it links 1 m DEM availability and download tools.
- [USGS 1 m DEM availability record](https://catalog.data.gov/dataset/1-meter-digital-elevation-models-dems-usgs-national-map-3dep-downloadable-data-collection) is a public catalogue entry.
- The existence of a public collection does not verify exact tile coverage, acquisition dates, or quality over the competition grid. The absent `1m_DEM_links.csv` is the study-area inventory to check.
- Topographic openness/local relief/scarp extraction have been described by the linked H19 page; the proposed H3 target in this project is drainage-network deflection and along-channel profile breaks, a different geomorphic operator. Both require lithology/erosion controls.

### Mapping coverage / fieldwork proxy

- [USGS NGMDB FAQ](https://www.usgs.gov/faqs/what-national-geologic-map-database) and [NGMDB MapView](https://ngmdb.usgs.gov/mapview/index.html) provide public map catalogue/viewing access; USGS describes its map archive and notes detailed mapping is not complete everywhere.
- Map records, footprints, scale, year, and publication density can serve as a *candidate mapping-coverage proxy*. They do not directly measure fieldwork hours, survey completeness, or the effort that produced a fault catalogue. Digitization and publication patterns can bias the proxy.
- Do not treat missing map metadata as confirmed low survey coverage. A coverage correction remains disabled until an independently checked spatial coverage product is assembled and its limitations are documented.

## Uncertainty method notes

Reference: Lakshminarayanan, Pritzel & Blundell (2017), [NeurIPS paper PDF](https://proceedings.neurips.cc/paper_files/paper/2017/file/9ef2ed4b7fd2c810847ffa5fa85bce38-Paper.pdf). Use separately initialized and independently optimized members; do not approximate this with test-time dropout.

For member probabilities `p_m`, a uniformly mixed Bernoulli ensemble has

`p_mean = E_m[p_m]`,
`U_epistemic = Var_m[p_m]`,
`U_aleatoric = E_m[p_m (1 - p_m)]`,
`U_predictive = p_mean (1 - p_mean) = U_epistemic + U_aleatoric`.

The variance identity is mathematical. Interpreting conditional Bernoulli variance as irreducible geological/annotation ambiguity additionally requires calibration and an appropriate model of how labels are observed. The ensemble's epistemic variance can indicate model disagreement but is not a direct measurement of survey effort.

## Working geological hypotheses (unvalidated)

1. Multi-sensor edge-normal consensus across TMI, reduced-to-pole magnetics, isostatic gravity, surface conductivity, and conductive-base depth.
2. NGMDB mapped-coverage proxy × independently estimated ensemble epistemic variance for review priority; source is public, exact spatial coverage not assembled.
3. 3DEP-derived drainage-network deflection / channel knickpoints; exact GeoDAWN tile availability not verified.
4. Conductive-base / magnetic-source-depth discontinuities as potential basement fault indicators.
5. Strain-tensor gradients and seismicity-density transitions as exploratory deformation boundaries.

See [`../hypotheses.html`](../hypotheses.html) for the full named layers, physical signatures, prior ranking, source checks, and holdout protocol.

## Open unknowns

- Exact training raster band order/descriptions, label encoding, nodata/sentinel patterns, official footprint, and official raster transform.
- Geographic distribution and label uncertainty of the private new-fault dataset.
- Whether omitted faults concentrate in historically under-surveyed locations; competition rules establish incompleteness, not this cause.
- Which previous H19 artifact received which public score; no hash-to-submission mapping is public in the retrieved leaderboard.
- Whether local spatial holdout wins predict hidden test/public/private/Phase 2 performance.
- Actual uncertainty calibration and survey coverage quality; no model/data are present to measure these.
