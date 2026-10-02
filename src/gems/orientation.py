"""Orientation-coherence and source-depth hypotheses (H-38, H-39).

H-38 - cross-family azimuth agreement
-------------------------------------
A fault is a *linear* structure.  Every existing evidence layer in this repository
(and the sibling H19 "multi-line corroboration") fires on **magnitude** overlap:
families vote where their amplitudes coincide.  But two fields can both be locally
strong at a place where their linear features strike in *different* directions -
that is a coincidence, not a fault.  A true fault corridor should show locally
anisotropic texture in several independent fields **and** those fields' dominant
lineament azimuths should agree.

The structure tensor (gradient-second-moment smoothed over a neighbourhood) gives
both quantities at once: its major eigenvector is the dominant gradient direction
(the lineament azimuth is perpendicular to it) and
``(lambda1 - lambda2)/(lambda1 + lambda2)`` is a 0..1 orientation coherence.
Eigenvalue-based structure-tensor edge analysis of potential fields is
established practice (Sertcelik & Kafadar, *J. Appl. Geophys.* 2012;
DOI 10.1016/j.jappgeo.2012.06.004), and Blakely & Simpson (1986,
DOI 10.1190/1.1442103) established the horizontal-gradient ridge family it
generalises.

Agreement of two families i, j at a pixel is

    A_ij = coh_i * coh_j * cos^2(theta_i - theta_j)

which is 1 only when both families are locally anisotropic AND strike parallel,
and falls to 0 at 90 degrees disagreement.  The 1 m lidar scarp product already
ships its own structure-tensor derived ``strike`` (azimuth, degrees) and
``coh100`` channels, so the lidar family enters without re-derivation.

H-39 - shallow-residual potential-field edges
---------------------------------------------
Upward continuation attenuates short wavelengths (shallow sources) relative to
long wavelengths (deep sources) - the standard separation filter of
potential-field theory (Jacobsen 1987, DOI 10.1190/1.1442376; Blakely 1995,
*Potential Theory in Gravity and Magnetic Applications*).  The complement -
``residual = field - upward_continued(field, h)`` - enhances anomalies from
approximately the uppermost crust: the USGS applied exactly
``[M_pole]_residual = M_pole - [M_pole]_up(100 m)`` to Great-Basin-adjacent
aeromagnetics at Fort Irwin to "enhance anomalies produced by shallow or exposed
magnetic sources" (USGS OFR 2013-1024, https://pubs.usgs.gov/of/2013/1024/i/).
A young fault cutting sedimentary cover is a shallow, short-wavelength source;
the deep basement fabric it would have to be confused with is exactly what the
subtraction removes.  Where the residual field has strong edges *and* the
sedimentary cover is thick (official ``depth_to_base_surf`` band), a magnetic
lineament is more likely to be a young cover-cutting structure than recycled
basement grain - and the catalogue is dominated by mapped (bedrock) structure.

Neither transform uses the competition labels, so both layers are leak-free by
construction for any held-out fold.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Tuple

import numpy as np

PIXEL_M = 100.0


def structure_tensor(field: np.ndarray, sigma_px: float = 3.0, good: np.ndarray | None = None):
    """Smoothed structure tensor of a scalar field.

    Returns ``(theta_lineament_deg, coherence)`` where theta is the dominant
    *lineament* azimuth in degrees in [0, 180) (perpendicular to the dominant
    gradient) and coherence = (l1-l2)/(l1+l2) in [0, 1].
    ``good`` masks valid pixels; invalid input becomes coherence 0.
    """
    from scipy.ndimage import gaussian_filter, sobel

    f = np.asarray(field, np.float64)
    gy = sobel(f, axis=0, mode="nearest") / 8.0
    gx = sobel(f, axis=1, mode="nearest") / 8.0
    sxx = gaussian_filter(gx * gx, sigma_px, mode="nearest")
    syy = gaussian_filter(gy * gy, sigma_px, mode="nearest")
    sxy = gaussian_filter(gx * gy, sigma_px, mode="nearest")
    tr = sxx + syy
    # eigenvalues of [[sxx, sxy], [sxy, syy]]
    disc = np.sqrt(np.maximum((sxx - syy) ** 2 / 4.0 + sxy * sxy, 0.0))
    l1 = tr / 2.0 + disc
    l2 = tr / 2.0 - disc
    coh = np.where(tr > 1e-12, (l1 - l2) / np.maximum(tr, 1e-12), 0.0)
    coh = np.clip(coh, 0.0, 1.0)
    # grad_theta is the dominant gradient's math angle in the (x=east, y=south)
    # frame, mod 180.  A vector at math angle phi there has compass azimuth
    # 90 + phi, and the lineament (perpendicular) therefore has compass azimuth
    # mod(phi + 180, 180) = mod(phi, 180) - no +90 is needed.
    grad_theta = 0.5 * np.arctan2(2.0 * sxy, sxx - syy)
    line_deg = np.mod(np.degrees(grad_theta), 180.0)
    if good is not None:
        coh = np.where(good, coh, 0.0)
    return line_deg.astype(np.float32), coh.astype(np.float32)


def azimuth_agreement(theta_a: np.ndarray, coh_a: np.ndarray,
                      theta_b: np.ndarray, coh_b: np.ndarray,
                      coh_floor: float = 0.10) -> np.ndarray:
    """A_ij = coh_a * coh_b * cos^2(dtheta) where both coherences exceed the floor.

    cos^2 of the angle difference (NOT the doubled angle) is the correct kernel
    for unoriented lines: parallel lines agree (cos^2 0 = 1), perpendicular lines
    disagree (cos^2 90 = 0) and the 180-degree wrap of an azimuth is automatic
    (cos^2 180 = 1).  Using cos^2(2 dtheta) instead would score perpendicular
    lines as perfect agreement - a bug the unit test catches.
    """
    d = np.radians(theta_a.astype(np.float64) - theta_b.astype(np.float64))
    agree = np.cos(d) ** 2
    ok = (coh_a >= coh_floor) & (coh_b >= coh_floor)
    out = np.where(ok, coh_a.astype(np.float64) * coh_b.astype(np.float64) * agree, 0.0)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def upward_continuation(field: np.ndarray, height_m: float, pixel_m: float = PIXEL_M) -> np.ndarray:
    """FFT upward continuation to ``height_m`` above the observation plane.

    Multiplies the spectrum by exp(-|k| h) (Blakely 1995; the continuation
    filter; attenuation of a wavelength L is exp(-2 pi h / L)).  The input is
    reflect-padded so the padded field is continuous at the seams (edge-padding a
    non-constant boundary injects low-frequency leakage), filtered, and the pad
    cropped again.  No spatial window is applied: windowing followed by spectral
    filtering does not commute, and dividing back out by the window amplifies
    edge artefacts.
    """
    from scipy.fft import fft2, ifft2

    f = np.asarray(field, np.float64)
    pad = 128
    fp = np.pad(f, pad, mode="reflect")
    spec = fft2(fp)
    h_px = height_m / pixel_m
    ky = np.fft.fftfreq(fp.shape[0])
    kx = np.fft.fftfreq(fp.shape[1])
    ky = np.broadcast_to(ky[:, None], spec.shape)
    kx = np.broadcast_to(kx[None, :], spec.shape)
    k = np.sqrt(kx * kx + ky * ky)
    cont = spec * np.exp(-2.0 * np.pi * k * h_px)
    out = np.real(ifft2(cont))
    return out[pad:-pad, pad:-pad]


def residual_edges(field: np.ndarray, height_m: float, edge_sigma_px: float = 2.0,
                   pixel_m: float = PIXEL_M) -> np.ndarray:
    """Edge magnitude of the shallow residual (field minus its upward continuation)."""
    from scipy.ndimage import gaussian_filter, sobel

    res = np.asarray(field, np.float64) - upward_continuation(field, height_m, pixel_m)
    gy = sobel(res, axis=0, mode="nearest") / 8.0
    gx = sobel(res, axis=1, mode="nearest") / 8.0
    return gaussian_filter(np.hypot(gx, gy), edge_sigma_px, mode="nearest").astype(np.float32)


# ---------------------------------------------------------------------------------------------
# domain-level layer builders (used by scripts/validate_new_hypotheses.py)
# ---------------------------------------------------------------------------------------------

H38_FIELDS = ("det_elev", "rtp", "iso_grav_anom", "cond_surf", "depth_to_base_surf")


def build_orientation_layers(domain: np.ndarray, data_dir: str | None = None,
                             keep_pairs: bool = False) -> Dict[str, np.ndarray]:
    """H-38 layers on the official grid: per-pair and combined azimuth agreement.

    Returns a dict with ``h38_agree_mean`` (mean over the 10 field-field pairs,
    lidar excluded because it covers only 75 % of the footprint) and
    ``h38_agree_with_lidar`` (mean over the 5 field x lidar pairs where lidar is
    valid), all in [0, 1], 0 outside the domain.  ``keep_pairs=True`` also
    returns each pair separately (10 extra 49 MB arrays - only for analysis).
    """
    import rasterio

    from .layers import SENTINEL, load_domain

    dd = data_dir or os.environ.get("GEMS_DATA_DIR", "data")
    footprint, catalogue, dom, _ = load_domain(dd)
    tensors: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    with rasterio.open(os.path.join(dd, "training_features.tif")) as src:
        names = [str(d).split(" - ")[0] for d in src.descriptions]
        for nm in H38_FIELDS:
            b = names.index(nm) + 1
            raw = src.read(b).astype(np.float64)
            good = footprint & np.isfinite(raw) & (np.abs(raw) < SENTINEL)
            med = float(np.median(raw[good])) if good.any() else 0.0
            f = np.where(good, raw, med)
            theta, coh = structure_tensor(f, sigma_px=3.0, good=good & domain)
            tensors[nm] = (theta, coh)
            del raw, f

    fields = list(tensors.keys())
    # incremental mean over pairs - never materialise the (n_pairs, H, W) stack (RAM)
    pair_sum = None
    n_pairs = 0
    for i in range(len(fields)):
        for j in range(i + 1, len(fields)):
            a = azimuth_agreement(*tensors[fields[i]], *tensors[fields[j]]).astype(np.float64)
            pair_sum = a if pair_sum is None else pair_sum + a
            n_pairs += 1
            del a
    mean_field_field = pair_sum / max(1, n_pairs)
    del pair_sum
    out: Dict[str, np.ndarray] = {"h38_agree_mean": np.clip(mean_field_field, 0, 1).astype(np.float32)}
    del mean_field_field

    # lidar family: the product ships its own structure-tensor strike/coherence
    lid_path = os.path.join(dd, "external", "lidar_scarp_features_u8.tif")
    if os.path.exists(lid_path):
        with rasterio.open(lid_path) as src:
            LID = ["ex_max", "ex_mean", "step_max", "lapneg_max", "lappos_max", "downface_max",
                   "upface_max", "cross_max", "relief", "coh100", "strike", "valid"]
            strike_u8 = src.read(LID.index("strike") + 1)
            coh_u8 = src.read(LID.index("coh100") + 1)
        # quantisation: q = 1 + round(254 * clip(x/xmax, 0, 1)), xmax=180 deg / 1.0
        lid_valid = (strike_u8 > 0) & (coh_u8 > 0) & domain
        theta_lid = ((strike_u8.astype(np.float32) - 1) / 254.0 * 180.0)
        coh_lid = ((coh_u8.astype(np.float32) - 1) / 254.0)
        del strike_u8, coh_u8
        lid_sum = None
        n_lid = 0
        for nm in fields:
            a = azimuth_agreement(tensors[nm][0], tensors[nm][1], theta_lid, coh_lid)
            a = np.where(lid_valid, a, 0.0).astype(np.float64)
            lid_sum = a if lid_sum is None else lid_sum + a
            n_lid += 1
            del a
        out["h38_agree_with_lidar"] = np.clip(lid_sum / max(1, n_lid), 0, 1).astype(np.float32)
        del lid_sum, theta_lid, coh_lid, lid_valid
    return out


def build_residual_layers(domain: np.ndarray, data_dir: str | None = None) -> Dict[str, np.ndarray]:
    """H-39 layers: edge magnitude of the shallow magnetic residual, in cover context.

    ``h39_resid_edge_500m`` / ``h39_resid_edge_2000m``: edge magnitude of
    (rtp - upward_continued rtp); ``h39_resid_edge_thickcover`` multiplies the
    500 m variant by the normalised sedimentary-cover thickness so the layer
    expresses "shallow magnetic edge inside thick cover".
    """
    import rasterio

    from .layers import SENTINEL, load_domain

    dd = data_dir or os.environ.get("GEMS_DATA_DIR", "data")
    footprint, catalogue, dom, _ = load_domain(dd)
    with rasterio.open(os.path.join(dd, "training_features.tif")) as src:
        names = [str(d).split(" - ")[0] for d in src.descriptions]
        raw_rtp = src.read(names.index("rtp") + 1).astype(np.float64)
        raw_cov = src.read(names.index("depth_to_base_surf") + 1).astype(np.float64)
    good_rtp = footprint & np.isfinite(raw_rtp) & (np.abs(raw_rtp) < SENTINEL)
    good_cov = footprint & np.isfinite(raw_cov) & (np.abs(raw_cov) < SENTINEL)
    med_rtp = float(np.median(raw_rtp[good_rtp])) if good_rtp.any() else 0.0
    med_cov = float(np.median(raw_cov[good_cov])) if good_cov.any() else 0.0
    rtp = np.where(good_rtp, raw_rtp, med_rtp)
    cov = np.where(good_cov, raw_cov, med_cov)
    del raw_rtp, raw_cov

    out: Dict[str, np.ndarray] = {}
    for h_m, key in ((500.0, "h39_resid_edge_500m"), (2000.0, "h39_resid_edge_2000m")):
        e = residual_edges(rtp, h_m)
        out[key] = e
    # cover thickness normalised over the domain (thicker cover -> closer to 1)
    v = cov[domain]
    lo, hi = np.percentile(v, [1, 99])
    covn = np.clip((cov - lo) / max(hi - lo, 1e-9), 0, 1)
    out["h39_resid_edge_thickcover"] = (out["h39_resid_edge_500m"] * covn).astype(np.float32)
    return out
