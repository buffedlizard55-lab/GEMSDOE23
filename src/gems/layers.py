"""Evidence-layer bank for the GeoDAWN footprint.

Every layer is a float32 array on the official 3730x3292 / EPSG:32611 / 100 m grid,
normalised to [0, 1] over the 1st-99th percentile of its finite in-footprint values
(higher = more evidence for that layer's physical signature).  Layers are *streamed*
one at a time: the full bank does not fit in the 3 GB sandbox budget.

Provenance of the inputs
-----------------------
* ``data/training_features.tif`` - the official 19-band competition feature stack
  (sha256 4371c82e..., reassembled and hash-verified from the git data bridge).
  Invalid pixels are the float32 sentinel -3.4028234663852886e+38, NOT NaN, so a
  layer is valid only where ``abs(value) < 1e30`` (flag F05 in the audit registry).
* ``data/external/geodawn_rad_u8.tif`` - K, Th, U, TC from the USGS GeoDAWN airborne
  radiometric survey (ScienceBase item 657e1d85d34e23d3533209f7, DOI 10.5066/P93LGLVQ,
  CC0), uint8 ranks over the 1st-99th percentile, 0 = nodata.
* ``data/external/geodawn_extensions_u8.tif`` - Th/K, U/K, U/Th ratios and 150 m
  upward-continued TMI from the same release.
* ``data/external/lidar_scarp_features_u8.tif`` - 12 scarp-geomorphometry channels
  aggregated from the 1 m 3DEP DEM (USGS 3DEP, public domain) over 706 of 716 tiles;
  valid over 75.4 % of the footprint, 0 = no lidar.
* ``data/external/derived_sgmc_faults_100m_u8.tif`` - faults rasterised from the USGS
  State Geologic Map Compilation (Horton, San Juan & Stoeser 2017, DS 1052,
  DOI 10.3133/ds1052), i.e. an independent, mostly pre-Quaternary bedrock structure
  compilation that is NOT the source of the competition labels.
* ``data/external/gdr_wellspring_in_footprint.csv`` - 27,092 spring/well records from
  the Geothermal Data Repository (INGENIOUS Great Basin compilation, GDR 1391), with
  measured temperature, chalcedony geothermometer temperature and the record's own
  distance to the nearest mapped fault.
"""
from __future__ import annotations

import csv
import os
from typing import Iterator, Tuple

import numpy as np

DATA_DIR = os.environ.get("GEMS_DATA_DIR", "data")
EXT = os.path.join(DATA_DIR, "external")
RADIUS_M = 300.0
PIXEL_M = 100.0
SENTINEL = 1e30


def load_domain(data_dir: str | None = None):
    """Official footprint, known-fault catalogue mask and scored domain."""
    import rasterio

    dd = data_dir or DATA_DIR
    with rasterio.open(os.path.join(dd, "sample_submission.tif")) as src:
        tmpl = src.read(1)
    footprint = np.isfinite(tmpl)
    catalogue = footprint & (tmpl == 1)
    domain = footprint & ~catalogue          # staff ruling, forum topic 11516
    return footprint, catalogue, domain, tmpl


def normalise(arr: np.ndarray, domain: np.ndarray) -> np.ndarray | None:
    a = np.asarray(arr, np.float64)
    fin = np.isfinite(a) & domain
    if int(fin.sum()) < 1000:
        return None
    lo, hi = np.percentile(a[fin], [1, 99])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None
    out = np.clip((a - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)
    out[~domain] = 0.0
    return out


def _points(shape, rows, cols, weights=None):
    h, w = shape
    r = np.zeros((h, w), np.float32)
    rr = np.clip(np.asarray(rows, int), 0, h - 1)
    cc = np.clip(np.asarray(cols, int), 0, w - 1)
    v = np.ones(len(rows), np.float32) if weights is None else np.nan_to_num(np.asarray(weights, np.float32), nan=0.0)
    np.maximum.at(r, (rr, cc), v)
    return r


def iter_layers(data_dir: str | None = None) -> Iterator[Tuple[str, np.ndarray]]:
    """Yield ``(name, normalised_layer)`` one at a time.

    Families
    --------
    ``of_*``   official competition bands and their 300 m / 700 m local variability
    ``rad_*``  GeoDAWN airborne radiometrics (K, Th, U, total count)
    ``ext_*``  GeoDAWN radiometric ratios and upward-continued TMI
    ``lid_*``  1 m 3DEP lidar scarp geomorphometry
    ``sgmc_*`` independent state-geologic-map fault compilation
    ``spring_*`` GDR thermal / hydrologic point evidence
    ``geom_*`` geometry and survey-coverage covariates
    """
    import rasterio
    from scipy.ndimage import distance_transform_edt, uniform_filter

    dd = data_dir or DATA_DIR
    footprint, catalogue, domain, _ = load_domain(dd)
    shape = footprint.shape
    d_cat = distance_transform_edt(~catalogue, sampling=(PIXEL_M, PIXEL_M)).astype(np.float32)

    with rasterio.open(os.path.join(dd, "training_features.tif")) as src:
        names = [str(d).split(" - ")[0] for d in src.descriptions]
        for b in range(1, src.count + 1):
            raw = src.read(b).astype(np.float64)
            good = footprint & np.isfinite(raw) & (np.abs(raw) < SENTINEL)
            med = float(np.median(raw[good])) if good.any() else 0.0
            f = np.where(good, raw, med)
            z = (f - float(f[footprint].mean())) / (float(f[footprint].std()) + 1e-9)
            n = normalise(z, domain)
            if n is not None:
                yield f"of_{names[b-1]}", n
            m3 = uniform_filter(z, 3)
            s3 = np.sqrt(np.maximum(uniform_filter(z * z, 3) - m3 * m3, 0.0))
            n = normalise(s3, domain)
            if n is not None:
                yield f"of_{names[b-1]}_std3", n
            m7 = uniform_filter(z, 7)
            s7 = np.sqrt(np.maximum(uniform_filter(z * z, 7) - m7 * m7, 0.0))
            n = normalise(s7, domain)
            if n is not None:
                yield f"of_{names[b-1]}_std7", n
            del raw, f, z, m3, s3, m7, s7

    path = os.path.join(EXT, "geodawn_rad_u8.tif")
    if os.path.exists(path):
        with rasterio.open(path) as src:
            for b, nm in zip(range(1, src.count + 1), ["K", "Th", "U", "TC"]):
                n = normalise(src.read(b), domain)
                if n is not None:
                    yield f"rad_{nm}", n
    path = os.path.join(EXT, "geodawn_extensions_u8.tif")
    if os.path.exists(path):
        with rasterio.open(path) as src:
            for b, nm in zip(range(1, src.count + 1), ["ThK", "UK", "UTh", "TMI_up150"]):
                n = normalise(src.read(b), domain)
                if n is not None:
                    yield f"ext_{nm}", n
    LID = ["ex_max", "ex_mean", "step_max", "lapneg_max", "lappos_max", "downface_max",
           "upface_max", "cross_max", "relief", "coh100", "strike", "valid"]
    path = os.path.join(EXT, "lidar_scarp_features_u8.tif")
    if os.path.exists(path):
        with rasterio.open(path) as src:
            for b, nm in zip(range(1, src.count + 1), LID):
                n = normalise(src.read(b), domain)
                if n is not None:
                    yield f"lid_{nm}", n

    path = os.path.join(EXT, "derived_sgmc_faults_100m_u8.tif")
    if os.path.exists(path):
        with rasterio.open(path) as src:
            sgmc = (src.read(1) > 0) & footprint
        d_sg = distance_transform_edt(~sgmc, sampling=(PIXEL_M, PIXEL_M)).astype(np.float32)
        for nm, arr in (("sgmc_density9", uniform_filter(sgmc.astype(np.float64), 9)),
                        ("sgmc_invdist", 1.0 / (1.0 + d_sg / PIXEL_M)),
                        ("sgmc_gap_density9", uniform_filter((sgmc & ~catalogue & (d_cat > 300)).astype(np.float64), 9))):
            n = normalise(arr, domain)
            if n is not None:
                yield nm, n
        del sgmc, d_sg

    n = normalise(1.0 / (1.0 + d_cat / PIXEL_M), domain)
    if n is not None:
        yield "geom_inv_d_catalogue", n
    n = normalise(np.clip(d_cat / 1000.0, 0, 20), domain)
    if n is not None:
        yield "geom_d_catalogue_km", n

    sw = os.path.join(EXT, "gdr_wellspring_in_footprint.csv")
    if os.path.exists(sw):
        rows, cols, tc, geo, off = [], [], [], [], []
        with open(sw) as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append(int(float(r["row"]))); cols.append(int(float(r["col"])))
                except Exception:
                    continue
                for lst, key in ((tc, "temp_c"), (geo, "geothermchalc_c"), (off, "dist_known_fault_px")):
                    try:
                        lst.append(float(r[key]))
                    except Exception:
                        lst.append(np.nan)
        tc = np.array(tc); geo = np.array(geo); off = np.array(off)
        sets = {
            "springs_all": np.ones(len(rows)),
            "springs_hot40": (tc >= 40).astype(float),
            "springs_hot60": (tc >= 60).astype(float),
            "springs_geotherm100": (geo >= 100).astype(float),
            "springs_offmapped": (off > 5).astype(float),
            "springs_hot_offmapped": ((tc >= 40) & (off > 5)).astype(float),
        }
        for nm, w in sets.items():
            p = _points(shape, rows, cols, w)
            if int((p > 0).sum()) < 5:
                continue
            d = distance_transform_edt(~(p > 0), sampling=(PIXEL_M, PIXEL_M)).astype(np.float32)
            n = normalise(1.0 / (1.0 + d / PIXEL_M), domain)
            if n is not None:
                yield f"{nm}_invdist", n
            n = normalise(uniform_filter((p > 0).astype(np.float64), 15), domain)
            if n is not None:
                yield f"{nm}_dens15", n
            del p, d

    vv = os.path.join(EXT, "gdr_volcanic_vents_in_footprint.csv")
    if os.path.exists(vv):
        rows, cols = [], []
        with open(vv) as fh:
            for r in csv.DictReader(fh):
                try:
                    rows.append(int(float(r["row"]))); cols.append(int(float(r["col"])))
                except Exception:
                    pass
        if rows:
            p = _points(shape, rows, cols)
            d = distance_transform_edt(~(p > 0), sampling=(PIXEL_M, PIXEL_M)).astype(np.float32)
            n = normalise(1.0 / (1.0 + d / PIXEL_M), domain)
            if n is not None:
                yield "vents_invdist", n
