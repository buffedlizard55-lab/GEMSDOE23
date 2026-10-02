# Competition data placement (not committed)

Required filenames in this folder after legitimate access through the official DrivenData data tab:

- `training_features.tif` — multiband GeoTIFF named on the [official problem page](https://www.drivendata.org/competitions/306/competition-doe-gems/page/967/); the organizer's [reference notebook](https://github.com/drivendataorg/gems-prize-reference-solution/blob/main/unet-mc-cv-reference-solution.ipynb) uses `numeric_features.tif` for the feature raster instead. The preparer accepts either name and fails if both are present;
- `labels.tif` — known-fault raster (the unlabeled background is not proven fault-free);
- `sample_submission.tif` — sample referenced by the official problem page; use its profile and mask as the authoritative submission template;
- `1m_DEM_links.csv` — optional high-resolution elevation download index, if provided by the competition.

The data tab currently redirects unauthenticated visitors to DrivenData's login page. This repository does not store credentials and will not try to bypass that gate. Put files here only after downloading them through an authorized account. Do not commit the source files or derived rasters; `.gitignore` excludes this folder except for this note.

Once the files are present, run:

```bash
python -m pip install -r requirements.txt
python scripts/prepare_data.py --data-dir data --out-dir data/processed
```

`prepare_data.py` checks CRS, grid dimensions, affine transform, valid footprint, input nodata/sentinel handling, band count, and basic label contents before preparing normalized features. The output directory is also ignored by Git.
