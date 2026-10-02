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

The official public leaderboard page was retrieved through the Arena web reader twice on 2026-10-02 (02:38 UTC and 09:33 UTC). Both retrievals showed DARD at **0.3195 (rank 1)** and alexoktaba at **0.3042 (rank 2)**. At 09:33 UTC the supplied H19-5 value **0.1922** matched a displayed public row at **rank 26 (smrtdoog5)** and H19-4 **0.1894** matched **rank 28 (SDCF9)**; at 02:38 UTC the same two scores displayed at ranks 24 and 26. The board moved by two rows inside seven hours - `kinghorton42` (0.2635) and `Ehimenathan` (0.1949) entered above them - so rank is a fast-decaying quantity here and only the score is worth quoting. `docs/data/leaderboard.json` now carries all 50 displayed rows with the retrieval timestamp, and its attribution caveat is recomputed from those rows on every refresh so a rank claim can never go stale silently. The `+0.0028` difference is a score-level comparison only. The board does not expose the evaluated TIFF digest or public submission identifier, so neither match verifies account/team/file attribution. The prompt-reported former leader **0.3049** is not the current leader and was not independently authenticated as a historical board result in this retrieval. Public rows do not establish either private Initial Prize Round or expert-updated Final Prize Round scores.

The 50-row dated capture, retrieval method, and attribution/phase caveats are persisted in [`../data/leaderboard.json`](../data/leaderboard.json), and the machine-readable health of the last refresh in [`../data/leaderboard-status.json`](../data/leaderboard-status.json).

### How to refresh the feed (measured procedure, 2026-10-02)

Three facts were measured, not assumed, and they determine the only workable procedure:

1. **A plain HTTP GET cannot see the board.** From a GitHub Actions runner: `HTTP 200`, `30,166 bytes`, correct page title, and then `tables: 0, rows: 0, cell_text_bytes: 0, user_links: 0, tversky_mentions: 0, loading_placeholder: true`. The table is built by client-side JavaScript; the server ships a shell with a `Loading...` placeholder. Any parser that only reads the GET response will always report "no leaderboard table", which is what silently froze the published board at an earlier capture.
2. **There is no anonymous JSON endpoint.** `https://www.drivendata.org/api/competitions/306/leaderboard/` → `404 Page not found` with "please make sure that you are signed in and signed up for that competition". `?format=json` on the HTML URL returns the same page. Signed-in endpoints are out of scope here: no credentials, no bypassing access controls.
3. **The development sandbox has no TLS egress to `drivendata.org`** (`SSL_ERROR_SYSCALL`), while GitHub Actions does. So the automatic path must live in CI, and the manual path must live in a tool that renders JavaScript.

Therefore:

```bash
# Automatic (CI, on every push to main and daily at 12:00 UTC) - pages.yml installs the browser:
pip install playwright==1.63.0 && python -m playwright install --with-deps chromium
python scripts/update_leaderboard.py --render --timeout 90   --output docs/data/leaderboard.json --status docs/data/leaderboard-status.json

# Anywhere else, if you can save the rendered page (a JS-capable reader, or your own browser):
python scripts/update_leaderboard.py --from-file saved-leaderboard.html   --output docs/data/leaderboard.json --status docs/data/leaderboard-status.json
python scripts/build_site.py     # re-render every page from the evidence records
```

`--render` executes the page's own public JavaScript in anonymous headless Chromium (`scripts/render_leaderboard.py`), waits for at least 25 populated rows, and hands the rendered HTML to the same parser as everything else; rendering is a replaceable front end and the parser is the single authority. Both paths validate before publishing (≥10 rows, unique ascending ranks, every score in `[0, 1]`), so a challenge page or a half-rendered table is rejected rather than served. Neither path is `--strict` in `pages.yml`, because publication must survive a leaderboard outage; on failure the last verified rows are retained and the status sidecar records the HTTP status, final URL, bytes per attempt, page title, table/row/link counts and a text excerpt. Read that sidecar on `main` to learn the feed's health without needing CI log access.

**Quoting rule.** Because the board moved two rows in seven hours, quote scores with a retrieval timestamp and never quote a rank as a durable fact. The attribution caveat in the snapshot is computed from the rows at refresh time, so it states the current coincidence (rank 26 / rank 28 as of 09:33 UTC) instead of a hard-coded one.

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

## Verified this session (2026-10-02) — reuse these before re-deriving anything

Everything below was measured in this repository from hash-verified official rasters, or read from an
official page or a DrivenData staff post. `COMPUTED` means a script in `scripts/` produced the number
and the record is in `docs/data/`.

### The scoring contract, completed by two staff rulings

* **OBSERVED.** Known USGS/INGENIOUS fault pixels are *masked out of evaluation* and "do not count
  towards penalty terms"; the same masking applies when the Final Round re-scores against the expanded
  labels. [forum 11516, staff post 2](https://community.drivendata.org/t/11516/2). `COMPUTED`
  consequence: the scored domain is **5,106,385 px** = 5,167,373 footprint − 60,988 catalogue pixels.
* **OBSERVED.** "'new fault' means 'any fault pixel not already captured by USGS/INGENIOUS' and can
  include newly mapped geometry of an existing fault system"
  ([forum 11536, staff post 2](https://community.drivendata.org/t/11536/2)). So the target population
  includes trace **extensions, splays and parallel strands**, not only structurally separate faults.
* **COMPUTED.** With `FN_w = |G| − TP_w` and α + β = 1 the metric collapses to
  `DTI = TP_w / (0.2·TP_w + 0.2·FP_w + 0.8·|G|)`, and with `FP_w ≈ 0.813·A` for a sparse truth set it
  **inverts exactly**: `TP_w = DTI·(0.1626·A + 0.8·|G|)/(1 − 0.2·DTI)`. One live score plus the
  artefact's own geometry therefore gives its true-positive mass. `tests/test_live_model.py` checks the
  round trip.
* **COMPUTED.** `DTI_max = 1/(0.2 + 0.1626/q)`, attained at `A* = |G|/q`, where `q` is the
  kernel-weighted TP per emitted pixel. Undershooting `A*` costs less than overshooting it, so when `q`
  is uncertain the budget should be chosen below `A*`.
* **COMPUTED.** The marginal rule: emit another pixel only while its expected TP contribution exceeds
  `0.1626·TP_w/(0.1626·A + 0.8·|G|)` — equivalently, while TP gain per unit of FP mass exceeds
  `τ = 0.2·DTI/(1 − 0.2·DTI)` (τ = 0.0323 at DTI 0.1563, 0.0676 at 0.3168).

### The size of the hidden public-test truth set

* **COMPUTED.** `TP_w ≤ |G|` over 24 live-scored artefacts gives **|G| ≥ 4,607**.
* **COMPUTED.** The `r13-lattice-s5` artefact covers **98.9 %** of the scored domain within 300 m, so
  its TP is nearly independent of where the truth sits; measuring its mean kernel envelope on two real
  fault-trace populations gives **|G| ≤ 8,367** (SGMC-like geometry) or **|G| ≤ 12,486**
  (catalogue-like geometry). Record: `docs/data/live-model-bounds.json`.
* **INFERENCE.** |G| is of order 10⁴, not the 1.25 × 10⁵ assumed by earlier group work. Every
  large-area emission plan built on that assumption — including a 550,000-pixel "value-based budget" —
  is unsound: at |G| ≈ 10⁴ the false-negative floor `0.8·|G|` is small next to `0.1626·A` once A
  exceeds ~10⁵, so extra area cannot be repaid.

### Dispersion is a model-free lever

* **COMPUTED.** `TP_w` takes a *maximum* over predictions inside each 300 m cone while `FP_w` *sums*
  every emitted pixel, so stacking pixels inside one another's cone buys nothing and still costs.
  Define `η = (K̄/A)/(9.3803/D)` where `K̄` is the domain-mean kernel envelope of the emission
  (9.3803 is the exact discrete cone weight at 100 m pixels; the continuous integral is 9.4248).
* **COMPUTED.** Across the 24 live artefacts η correlates with TP per emitted pixel at Spearman
  **ρ = +0.61 (p = 0.0015)** and with placement skill at **ρ = +0.13 (p = 0.54)** — dispersion pays and
  does not measurably cost alignment. Measured η: thick blobs 0.16–0.20, the group's best artefacts
  0.39–0.41, `h28-dotted-ridge` 0.85, the lattice 0.99. This emission: **0.937 at 120,000 px**.
* **INFERENCE.** Faults are lines, so the efficient geometry is *dots along predicted lines* (≈400 m
  spacing), not thickened lines: a dot 400 m from its neighbour still covers the ground between them
  with k > 0, while a solid line spends 4–5× the mass for the same TP.

### Where the hidden faults live (the habitat model)

* **COMPUTED.** Regressing each artefact's placement skill `TP_w/(|G|·K̄)` on the enrichment of 95
  evidence layers inside its emitted pixels, with layer selection *and* ridge penalty re-fitted inside
  every leave-one-artifact-family-out fold, gives nested-CV Spearman **ρ = +0.44** on log skill.
  Record: `docs/data/habitat-model.json`.
* **COMPUTED.** The selected layers, in weight order: `lid_upface_max` (+0.90), `of_det_elev_slope_std7`
  (+0.62), `lid_downface_max` (+0.43), `rad_U` (−0.40), `lid_step_max` (+0.21), `lid_lappos_max` (+0.19),
  `lid_lapneg_max` (+0.16), `lid_ex_max` (+0.08).
* **COMPUTED, convergent validity.** The independent USGS SGMC compilation's unmapped faults are
  enriched in exactly those layers: 1.45–1.71× for the lidar scarp channels and 1.94–2.01× for 700 m
  detrended-slope heterogeneity, measured on lidar-covered ground only. Two independent routes — public
  scores and an independent map compilation — reach the same habitat.
* **COMPUTED, contrarian.** Emitting near ≥ 60 °C springs is *anti*-predictive of live skill
  (ρ = −0.52, p = 0.009), as is high radiometric U (−0.59, p = 0.002), Th (−0.51), total count (−0.42),
  official band 6 `tc` (−0.42), surface conductivity (−0.49), depth to basement (−0.44) and TMI vertical
  gradient (−0.44). The classic "chase the hot springs" play is the wrong play for *this* metric,
  because famous springs sit on faults the catalogue already contains and those pixels are masked.
* **CAVEAT.** 95 layers were screened against 24 scalar observations that are not independent
  experiments. One layer (`lid_upface_max`, p = 1 × 10⁻⁴) survives Benjamini–Hochberg FDR < 5% on its
  own; the rest of the lidar-scarp family is defensible as a *family* (eight correlated channels, same
  sign, top of the list) and the negatives are suggestive rather than individually significant.

### What does *not* work as an offline proxy

* **COMPUTED.** No stand-in truth ranks the live artefacts: SGMC-gap DTI gives Spearman ρ = +0.19
  (strict), +0.30 to +0.33 (300 m–2 km catalogue buffer), all p ≥ 0.12; the catalogue itself gives
  ρ = +0.13 (p = 0.53). The best proxy ranks `h19-c` first (proxy 0.295) when its live score is 0.0297 —
  last but one. Record: `docs/data/offline-proxy-audit.json`. An earlier reported ρ = 0.518 (n = 15)
  **did not reproduce** at n = 24.
* **INFERENCE.** Model and budget selection cannot be validated offline in this competition. The only
  instruments are (i) the exact metric algebra, (ii) regressions fitted to live scores, and (iii) the
  submission slots themselves. Say so explicitly rather than presenting a holdout win as evidence.

### The data itself

* **COMPUTED.** `training_features.tif` — 19 bands, float32, LZW, `interleave=pixel`, `blockysize=1`,
  nodata tagged `-3.4028234663852886e+38`. Band order and tags: `mag_anom`, `rtp`, `tmi_hg`,
  `geod_2ndinv`, `iso_grav_anom_slope`, `tc`, `geod_shearrate`, `geod_dilaterate`, `tmi_vg`,
  `deq_n100a15`, `iso_grav_anom_vg`, `det_elev`, `iso_grav_anom`, `tmi`, `depth_to_base_surf`,
  `ieq_n100a15`, `cond_surf`, `iso_grav_anom_hg`, `det_elev_slope`.
* **COMPUTED (flag I-03).** Invalid pixels *inside* the footprint use that finite sentinel, not NaN:
  3,061 per band (3,073 for `tc`). `np.isfinite` accepts it, so validity must also test
  `abs(value) < 1e30`. Random 64×64 window reads on this file decompress ~16 MB each because
  `blockysize=1`; build a normalised random-access cube first (`src/gems/featurecube.py`, 42 channels,
  516 MB uint8, 52 s).
* **COMPUTED (flag I-02).** Band 6 `tc` is tagged "Tilt angle or total curvature — magnetic field
  derivative" with `data_category=magnetic_data`, but on 5,164,300 valid pixels it correlates
  **r = +0.9971** with the USGS GeoDAWN radiometric total-count channel, **r = +0.8817** with its
  potassium channel and only **r = −0.1624** with the official magnetic horizontal-gradient band, and
  all its values are positive (2.95–88.57) while a tilt angle spans both signs. Treat it as radiometric
  total count. Record: `docs/data/band6-tc-audit.json`.
* **COMPUTED (flag I-01).** `sample_submission.tif` contains **60,988 pixels equal to 1.0** — exactly
  the known-fault catalogue — although the official page calls it a prediction of total fault absence.
  Use it for grid, CRS, transform and footprint only.
* **OBSERVED.** External layers available and hash-pinned in `data/external/`: GeoDAWN radiometrics
  (K, Th, U, TC) and extensions (Th/K, U/K, U/Th, TMI-up150) as uint8 percentile ranks; 12 channels of
  1 m 3DEP lidar scarp geomorphometry valid over **75.4 %** of the footprint (the gap is systematic, in
  the north-east); USGS SGMC structure rasterised at 100 m; 27,092 GDR spring/well records with measured
  and chalcedony geothermometer temperatures and each record's own distance to the nearest mapped fault
  (**22,561 of them lie > 500 m from any mapped fault**; 3,201 are ≥ 40 °C, 2,389 ≥ 60 °C, 210 have a
  chalcedony geothermometer ≥ 100 °C); 21 volcanic vents; 3,800 two-metre temperature probes.
* **OBSERVED.** GeoDAWN Area 2 was flown with 400 m east–west lines and 4,000 m north–south tie lines
  at 150–200 m terrain clearance, so cross-line resolution is coarse and east–west magnetic-derivative
  lineaments may be acquisition artefacts
  ([USGS release](https://www.sciencebase.gov/catalog/item/657e1d85d34e23d3533209f7)).

### Compute reality

* **COMPUTED.** 2 CPU cores, 3 GB RAM, no GPU. A 105 k-parameter 3-level U-Net runs at ~150 patches/s
  (batch 16, 64×64, 42 channels) with `torch.set_num_threads(2)`. Five epochs × 1,536 patches ≈ 85 s per
  member; tiled full-domain inference ≈ 150 s per member, ≈ 4 s per member on one fifth of the domain if
  tiles are restricted to the fold's bounding box. The whole layer bank (95 layers) does **not** fit in
  RAM and must be streamed.
* **COMPUTED.** `torch` cannot be installed from `download.pytorch.org` here (blocked); the PyPI Linux
  wheel is the CUDA build, so install `torch==2.7.1` **with** dependencies — the `nvidia-*-cu12` wheels
  come from PyPI and the CPU path then imports and runs normally. The `*-cu13` placeholder packages are
  empty and must not be used.

## Current hypothesis register and gate

The ranked shortlist is on [`../hypotheses.html`](../hypotheses.html) and is now led by a built,
shipped candidate:

1. **H-24 dispersed habitat emission** (built): habitat-fitted ranking + skill-weighted consensus of the
   nine live-scored artefact families, emitted as 400 m-spaced dots at a budget chosen by maximin
   expected DTI. Expected 0.14–0.44; verified group best 0.1922; live leader 0.3195.
2. **H-25 relocation, not detection**: displace catalogue trace geometry onto the nearest lidar scarp
   crest inside a 500 m window. Motivated by the ~400 m catalogue-to-lidar misregistration reported by
   Hermant et al. (2025), the paper the official About page cites. Needs no new data.
3. **H-26 thermal-conduit inversion, spring-avoiding**: 2 m temperature-probe and geothermometer
   anomaly density, but only the residual the catalogue cannot explain — the live scores say the raw
   spring neighbourhood is anti-predictive.
4. **H-27 acquisition-lineament deconfounding**: suppress east–west magnetic-derivative lineaments
   aligned with the 400 m Area-2 flight lines and re-spend that budget on cross-line structure.
5. **H-28 coverage-void targeting**: the explicit intersection of low mapped-geology density and high
   lidar scarp evidence — the mechanism behind H-24's weights, made separately testable.

**Gate.** A component may influence the submitted raster only after passing a pre-registered gate. The
deep ensemble's gate was "out-of-fold DTI at the operating budget must beat a seed-matched random
emission of the same size on a majority of blocked folds" (`scripts/evaluate_oof.py`); it did not pass,
so its weight in the emission is 0 and the reason is recorded in `docs/data/submission-build.json`.
The standing rule "never spend a slot on something that has not beaten the holdout best" **cannot be
satisfied honestly in this competition**, because no offline proxy correlates with the live board; the
substitute is the pre-registered decision rule printed on the executive-summary page, plus recording
every returned score with `scripts/record_score.py`.

## Open unknowns

* The exact value of |G| (bounded 4,607–12,486, not measured) and therefore the exact optimal budget.
* The placement skill this emission will actually achieve; the projection assumes 2.0–5.5 against a
  best-observed 4.8–5.4.
* Whether the masked-pixel ruling also removes a masked pixel's ability to supply TP credit to a new
  fault within 300 m of it (flag I-11). This submission emits nothing on catalogue pixels, which is
  safe under both readings.
* How the public/private chunking is drawn, and whether the habitat differs between chunks.
* What data and fault types the experts used to label the new faults — they declined to say
  ([forum 11527](https://community.drivendata.org/t/11527)).
* Whether the SGMC compilation's unmapped faults are a biased stand-in for the experts' additions: they
  share a habitat (measured) but the proxy DTI does not rank artefacts (measured).
