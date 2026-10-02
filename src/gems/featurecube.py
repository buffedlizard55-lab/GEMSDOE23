"""Build the compact uint8 feature cube the deep ensemble trains on.

The official 19-band stack is 418 MB, LZW-compressed with blockysize=1 and pixel
interleave, so random 64x64 window reads decompress ~16 MB each.  Patch training
therefore needs a pre-normalised cube in a random-access layout.  Every channel is
rank-normalised to 1..255 over its valid in-footprint pixels (1st-99th percentile
clip), 0 = invalid, plus one explicit validity channel per source, mirroring the
convention of the USGS GeoDAWN uint8 products in ``data/external``.

No catalogue-derived channel is included: the training target is a set of faults the
catalogue does NOT contain, and a distance-to-catalogue channel leaks the held-out
object (audit flag F-10 in the sibling forensic review measured fold DTI 0.977 with it
and 0.033 without).
"""
from __future__ import annotations

import os
from typing import List, Tuple

import numpy as np

from .layers import EXT, SENTINEL, load_domain

OFFICIAL = ["det_elev", "det_elev_slope", "iso_grav_anom", "iso_grav_anom_hg", "iso_grav_anom_slope",
            "iso_grav_anom_vg", "tmi", "tmi_hg", "tmi_vg", "mag_anom", "rtp", "tc",
            "cond_surf", "depth_to_base_surf", "geod_2ndinv", "geod_shearrate", "geod_dilaterate",
            "deq_n100a15", "ieq_n100a15"]
LIDAR = ["ex_max", "ex_mean", "step_max", "lapneg_max", "lappos_max", "downface_max",
         "upface_max", "cross_max", "relief", "coh100", "strike", "valid"]
RAD = ["K", "Th", "U", "TC"]
EXTCH = ["ThK", "UK", "UTh", "TMI_up150"]


def channel_names() -> List[str]:
    return ([f"of_{n}" for n in OFFICIAL] + ["of_valid"]
            + [f"lid_{n}" for n in LIDAR] + ["lid_valid_flag"]
            + [f"rad_{n}" for n in RAD] + [f"ext_{n}" for n in EXTCH]
            + ["footprint"])


def _q8(a: np.ndarray, good: np.ndarray) -> np.ndarray:
    out = np.zeros(a.shape, np.uint8)
    if good.sum() < 100:
        return out
    v = a[good]
    lo, hi = np.percentile(v, [1, 99])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return out
    out[good] = (1 + np.round(254 * np.clip((a[good] - lo) / (hi - lo), 0, 1))).astype(np.uint8)
    return out


def build_cube(out_path: str, data_dir: str | None = None) -> dict:
    """Write ``out_path`` as a (C, H, W) uint8 memmap-able .npy and return its metadata."""
    import rasterio

    dd = data_dir or os.environ.get("GEMS_DATA_DIR", "data")
    footprint, catalogue, domain, _ = load_domain(dd)
    shape = footprint.shape
    names = channel_names()
    cube = np.zeros((len(names),) + shape, np.uint8)
    meta = dict(shape=list(shape), channels=names, crs="EPSG:32611", pixel_m=100.0,
                transform=[100.0, 0.0, 243350.0, 0.0, -100.0, 4508550.0])

    pos = {n: i for i, n in enumerate(names)}
    with rasterio.open(os.path.join(dd, "training_features.tif")) as src:
        desc = [str(d).split(" - ")[0] for d in src.descriptions]
        anygood = np.zeros(shape, bool)
        for b in range(1, src.count + 1):
            nm = desc[b - 1]
            if nm not in OFFICIAL:
                continue
            raw = src.read(b).astype(np.float32)
            good = footprint & np.isfinite(raw) & (np.abs(raw) < SENTINEL)
            cube[pos[f"of_{nm}"]] = _q8(raw, good)
            anygood |= good
            meta.setdefault("invalid_px", {})[f"of_{nm}"] = int((footprint & ~good).sum())
            del raw
        cube[pos["of_valid"]] = (255 * anygood).astype(np.uint8)
    p = os.path.join(EXT, "lidar_scarp_features_u8.tif")
    if os.path.exists(p):
        with rasterio.open(p) as src:
            for b in range(1, src.count + 1):
                a = src.read(b)
                cube[pos[f"lid_{LIDAR[b-1]}"]] = a
            cube[pos["lid_valid_flag"]] = (255 * (src.read(LIDAR.index("valid") + 1) > 0)).astype(np.uint8)
    p = os.path.join(EXT, "geodawn_rad_u8.tif")
    if os.path.exists(p):
        with rasterio.open(p) as src:
            for b in range(1, src.count + 1):
                cube[pos[f"rad_{RAD[b-1]}"]] = src.read(b)
    p = os.path.join(EXT, "geodawn_extensions_u8.tif")
    if os.path.exists(p):
        with rasterio.open(p) as src:
            for b in range(1, src.count + 1):
                cube[pos[f"ext_{EXTCH[b-1]}"]] = src.read(b)
    cube[pos["footprint"]] = (255 * footprint).astype(np.uint8)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    np.save(out_path, cube)
    meta["path"] = out_path
    meta["bytes"] = int(cube.nbytes)
    meta["lidar_coverage_frac_of_footprint"] = float((cube[pos["lid_valid_flag"]] > 0)[footprint].mean())
    return meta


def load_target(data_dir: str | None = None, min_d_cat_m: float = 300.0) -> Tuple[np.ndarray, dict]:
    """Independent-compilation faults that the competition catalogue does NOT contain.

    Target = USGS State Geologic Map Compilation structure (DS 1052, DOI 10.3133/ds1052)
    rasterised on the competition grid, minus the catalogue pixels, minus everything
    within ``min_d_cat_m`` of a catalogued fault.  This is the same population the staff
    defined for scoring - "any fault pixel not already captured by USGS/INGENIOUS"
    (forum 11536) - drawn from a source that is independent of the labels' provenance.
    """
    import rasterio
    from scipy.ndimage import distance_transform_edt

    dd = data_dir or os.environ.get("GEMS_DATA_DIR", "data")
    footprint, catalogue, domain, _ = load_domain(dd)
    with rasterio.open(os.path.join(EXT, "derived_sgmc_faults_100m_u8.tif")) as src:
        sgmc = (src.read(1) > 0) & footprint
    d_cat = distance_transform_edt(~catalogue, sampling=(100.0, 100.0))
    target = sgmc & domain & (d_cat > min_d_cat_m)
    info = dict(sgmc_px=int(sgmc.sum()), catalogue_px=int(catalogue.sum()),
                target_px=int(target.sum()), min_d_cat_m=min_d_cat_m,
                source="USGS SGMC_Structure (Horton, San Juan & Stoeser 2017, DS 1052, DOI 10.3133/ds1052)",
                target_frac_of_domain=float(target.sum() / domain.sum()))
    return target, info
