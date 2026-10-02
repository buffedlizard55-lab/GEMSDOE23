# GEMSDOE23 — DOE GEMS Prize (DrivenData #306): find the faults the catalogue has not captured

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
>    how it differs from existing work in this repository. **Rank** them by expected DTI improvement
>    and implementation cost. Validate the top candidate on a **spatially blocked holdout** before
>    spending a weekly submission slot. If new external data is needed, name the specific free
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

## 1. At a glance (measured this session, 2026-10-02)

| | |
|---|---|
| **Submission file** | `docs/downloads/gemsdoe23-h24-dispersed-habitat-*.tif` — one click from <https://buffedlizard55-lab.github.io/GEMSDOE23/> |
| **Grid** | 3292 × 3730, single band float32, EPSG:32611, 100 m, transform `(100, 0, 243350 / 0, −100, 4508550)`, NaN outside the footprint, values in `[0, 1]` |
| **Scored domain** | 5,106,385 px = 5,167,373 footprint − 60,988 known-fault pixels (staff ruling, [forum 11516](https://community.drivendata.org/t/11516)) |
| **Hidden public-test truth \|G\|** | **5,564 – 14,944 px**, exact bounds from 24 live scores. The previously assumed 125,000 is **refuted** |
| **Emission** | 100,000 px at 400 m minimum separation, dispersion efficiency **η = 0.946**, 300 m coverage 43.8 % (group best 0.85; `h19-5` 0.40) |
| **Projected public DTI** | **0.12 – 0.34** over \|G\| ∈ [6k, 15k] × q ∈ [0.04, 0.11], where q = kernel-weighted true positives per emitted pixel (best measured in 24 live artefacts: 0.0518). Weighted worst case over \|G\|: **0.212**. Verified group best **0.1922**; live leader **0.3195** |
| **Validated offline?** | **No.** No offline proxy truth ranks the 24 live artefacts better than chance (best ρ = +0.33, p = 0.12). The projection is exact metric algebra plus a q prior whose upper half comes from the group's own best measured artefacts |
| **Deep ensemble** | 5 blocked folds × 3 independently initialised members out-of-fold, plus 5 full-domain members; epistemic share of total predictive variance 0.143. **Failed its admission gate (0/5 folds beat a random emission), so its weight in the raster is 0** |

The four findings that changed the submission are on the
[evidence page](https://buffedlizard55-lab.github.io/GEMSDOE23/evidence.html) and in
[`docs/data/`](docs/data).

---

## 2. The two rules that decide what may be uploaded

1. **Never upload something that has not beaten the current best on a validated holdout.**
   This session could *not* satisfy that rule honestly, because the holdout does not exist: every
   offline proxy we can build from official data fails to rank live artefacts
   ([`docs/data/offline-proxy-audit.json`](docs/data/offline-proxy-audit.json)). The rule was therefore
   replaced, in the open, by a **pre-registered decision rule** printed on the
   [executive summary](https://buffedlizard55-lab.github.io/GEMSDOE23/executive-summary.html):
   upload only if you accept the projection range, and record the returned score immediately
   (`python scripts/record_score.py --score <X> --id <sha8>`), because one live observation is worth
   more than any further offline work.
2. **Every component must pass a gate before it may influence the raster.** The deep ensemble failed
   its gate (out-of-fold DTI did not beat a seed-matched random emission), so its weight in the
   emission is **0** and the reason is recorded in
   [`docs/data/submission-build.json`](docs/data/submission-build.json). It is still trained, still
   reported, and still supplies the epistemic/aleatoric decomposition.

---

## 3. Reproduce everything

```bash
bash scripts/download_competition_data.sh   # acquire + hash-verify the official rasters (no manual input)
python scripts/prepare_data.py              # grid/validity audit -> data/manifest.json
python scripts/fit_habitat_model.py         # 24 live scores -> habitat weights, nested-CV rho
python scripts/run_ensemble.py              # deep ensemble + epistemic/aleatoric split
python scripts/evaluate_oof.py              # admission gate vs a random-emission control
python scripts/build_submission_live.py     # budget, dispersion, TIFF, template validation
python scripts/phase2_candidates.py         # reviewer candidates with the variance split
python scripts/build_site.py                # regenerate the whole site from docs/data/*.json
python -m unittest discover -s tests        # dependency-free checks
```

Dependencies: `numpy`, `scipy`, `rasterio`, `torch` (CPU is enough), `scikit-learn`, `pandas`.
Compute actually used: **2 CPU cores, 3 GB RAM, no GPU.**

---

## 4. Data: where it comes from and how it is verified

The competition originals sit behind a login-gated data tab. This repository never authenticates to
anything. Instead [`scripts/fetch_data_bridge.py`](scripts/fetch_data_bridge.py) reassembles them from
the group's public **git data bridge** (the official rasters split into <100 MB parts and committed to
a sibling repository with a manifest that pins every SHA-256), falls back to the Dropbox mirrors named
in that manifest, verifies every part and the whole file, and **fails closed**.

| file | bytes | SHA-256 |
|---|---|---|
| `data/training_features.tif` (official 19-band stack) | 418,912,844 | `4371c82e3b8339b807bdffcf4ef59a225520fe2988d521be208ae33743123bc5` |
| `data/labels.tif` (rasterised known faults) | 425,830 | `7ba308ccdc4418b31a178f4f1ef21aaa6e152e4028f2f6f64b01f7eb25ae4093` |
| `data/sample_submission.tif` (official template) | 1,599,597 | `2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc` |

External layers in `data/external/` (all official, public domain or CC0, all hash-pinned):
USGS GeoDAWN airborne radiometrics and extensions (K, Th, U, TC, Th/K, U/K, U/Th, TMI-up150;
[ScienceBase 657e1d85d34e23d3533209f7](https://www.sciencebase.gov/catalog/item/657e1d85d34e23d3533209f7),
[DOI 10.5066/P93LGLVQ](https://doi.org/10.5066/P93LGLVQ)); 12 channels of 1 m 3DEP lidar scarp
geomorphometry; faults from the USGS State Geologic Map Compilation
([DOI 10.3133/ds1052](https://doi.org/10.3133/ds1052)); 27,092 GDR/INGENIOUS spring and well records
with measured and geothermometer temperatures; 21 volcanic vents; 3,800 two-metre temperature probes.

`data/`, `outputs/` and `.cache/` are git-ignored: the rasters are private competition data and the
derived arrays are reproducible.

---

## 5. Repository map

| path | what it is |
|---|---|
| `docs/index.html` … `docs/verification.html` | the generated site (published from `docs/` by GitHub Pages) |
| `docs/data/*.json` | every number the site prints; each is produced by a script in `scripts/` |
| `docs/downloads/` | the submission rasters, their manifests and their stdlib audits |
| `docs/research/knowledge_base.md` | the reusable, sourced knowledge base (start here on a new project) |
| `docs/PROJECT_BRIEF.md` | the project brief and the research shortlist |
| `src/gems/layers.py` | the streaming evidence-layer bank (95 layers, 3 GB RAM safe) |
| `src/gems/habitat.py` | inversion of 24 live scores → placement skill → habitat regression |
| `src/gems/emission.py` | dispersion, the budget marginal rule, expected-DTI algebra |
| `src/gems/ensemble.py` | the deep ensemble and the epistemic/aleatoric decomposition |
| `src/gems/metric.py` | the official DTI, unit-tested against the organiser's worked example |
| `src/gems/submission.py` | float32/[0,1]/NaN-outside writer and strict template preflight |
| `analysis/` | one-off investigations, kept for auditability |
| `tests/` | dependency-free unit tests plus geospatial tests that skip when numpy/scipy are absent |

---

## 6. Limitations, and what access would change them

See [`docs/verification.html`](https://buffedlizard55-lab.github.io/GEMSDOE23/verification.html) for the
full list and [`docs/data/irregularities.json`](docs/data/irregularities.json) for the flag register.
The short version:

* **No offline validation of placement** — the single largest limitation. Only a submission slot can
  confirm the habitat ranking.
* **\|G\| is bounded, not measured.** The upper bound assumes no artefact is actively anti-correlated
  with the hidden truth.
* **The deep ensemble is undertrained** (2 cores, no GPU) and was excluded by its own gate.
* **Lidar covers 75.4 %** of the footprint and the gap is systematic (north-east quadrant), so the
  habitat score is weakest exactly where survey coverage is lowest.
* **Public ≠ private.** All 24 live scores are public-test scores; the split is unpublished and the
  Final Round re-scores against expanded labels.
* **Sandbox egress** allows only `github.com`, `api.github.com`, `codeload.github.com`, `pypi.org` and
  `files.pythonhosted.org`. DrivenData, Dropbox, USGS, ScienceBase, the National Map and
  `download.pytorch.org` all fail the TLS handshake here; GitHub Actions has full egress and repeats the
  leaderboard fetch there.
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
* **GitHub credentials expired mid-session and were restored** (flag I-12, resolved). PRs #4, #5 and #6
  are merged to `main` and the site is deployed; nothing is blocked on this any more.

---

## 7. Disclosure

Generative AI was used to produce code, analysis and prose in this repository, as the competition rules
require participants to disclose. Every quantitative claim is traceable to a script in `scripts/` and a
record in `docs/data/`; anything that is inference rather than measurement is labelled as such where it
appears.
