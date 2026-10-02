# analysis/ — one-off investigations, kept for auditability

These scripts produced the numbers in `docs/data/`. They are not part of the pipeline that
`scripts/` runs, and two of them are **superseded**: they were written before the false-positive
relief term was made self-consistent in `|G|` (see `src/gems/emission.py::fp_relief`), so their
absolute numbers are ~20 % off and must not be cited.

| script | status | what it produced |
|---|---|---|
| `anchor_geometry.py` | superseded by `analysis/bound_g.py` | first pass at per-artefact geometry (used the `|G| = 125,000` relief of 0.813) |
| `invert_live.py` | **superseded** | distance-to-catalogue-only truth model; same stale relief term |
| `template_test.py` | **superseded** | per-template implied `|G|`; same stale relief term. Its conclusion (no template explains the live ordering) was re-derived correctly in `proxy_harness.py` |
| `habitat_attribution.py` | superseded by `scripts/fit_habitat_model.py` | the exploratory per-layer Spearman screen; stale relief term, and no nested cross-validation |
| `proxy_harness.py` | **current** | `docs/data/offline-proxy-audit.json` — the negative result on offline proxies |
| `bound_g.py` | **current** | `docs/data/live-model-bounds.json` — exact bounds on `|G|` |

Inputs the current scripts need and where they come from:

* `.cache/sib/anchors/*.tif` + `manifest.json` — the 24 live-scored public artefacts, mirrored from
  the sibling repositories in the same GitHub organisation with their live scores transcribed from
  the public leaderboard and the group's own submission register. Not committed (git-ignored).
* `data/training_features.tif`, `data/labels.tif`, `data/sample_submission.tif`, `data/external/*` —
  acquired and hash-verified by `scripts/fetch_data_bridge.py`.

Re-run order: `bound_g.py` → `proxy_harness.py` → `scripts/fit_habitat_model.py` →
`scripts/evaluate_oof.py` → `scripts/build_submission_live.py`.
