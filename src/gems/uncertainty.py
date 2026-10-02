"""Predictive-uncertainty decomposition and survey-aware review priority.

For a uniformly sampled ensemble member M and Bernoulli outcome Y, the law of
total variance is exact:
    Var(Y) = Var_M(E[Y | M]) + E_M(Var(Y | M))
           = Var_M(p_M) + E_M[p_M (1 - p_M)].

The second term is a *conditional Bernoulli* uncertainty estimate. Interpreting
it as intrinsic geological or label ambiguity requires calibrated probabilities
and a defensible label-observation model; the function deliberately makes no
stronger causal claim.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Sequence


def _numpy_module():
    try:
        import numpy as np  # type: ignore
    except ImportError:
        return None
    return np


def _as_probability_members(values: Any):
    """Convert a sequence/array of member probability rasters to NumPy when available."""
    np = _numpy_module()
    if hasattr(values, "detach") and hasattr(values, "cpu"):
        values = values.detach().cpu().numpy()
    if np is not None:
        arr = np.asarray(values, dtype=np.float64)
        if arr.ndim < 2:
            raise ValueError("Expected shape (ensemble_members, ...spatial_dims), with at least 2 members")
        if arr.shape[0] < 2:
            raise ValueError("A deep ensemble requires at least two independently trained members")
        if not np.isfinite(arr).all():
            raise ValueError("Ensemble probabilities contain NaN or infinity")
        if ((arr < 0.0) | (arr > 1.0)).any():
            raise ValueError("Ensemble probabilities must be in [0, 1]")
        return np, arr

    try:
        members = [list(member) for member in values]
    except TypeError as exc:
        raise ValueError("Without NumPy, provide a two-dimensional sequence of member vectors") from exc
    if len(members) < 2:
        raise ValueError("A deep ensemble requires at least two independently trained members")
    lengths = {len(member) for member in members}
    if len(lengths) != 1:
        raise ValueError("Ensemble members must have the same flattened spatial length")
    for member in members:
        for p in member:
            if not math.isfinite(float(p)) or not 0.0 <= float(p) <= 1.0:
                raise ValueError("Ensemble probabilities must be finite and in [0, 1]")
    return None, members


def decompose_binary_ensemble(member_probabilities: Any) -> dict[str, Any]:
    """Return mean, epistemic, conditional/aleatoric, and total variance.

    Args:
        member_probabilities: probabilities with ensemble-member dimension first.
            Supported shape is `(M, ...)`, where `M >= 2` and every value is in
            `[0, 1]`. NumPy arrays are used for raster-sized data. A pure-Python
            `(M, N)` sequence is supported for small tests and reports.

    The ensemble variance uses `ddof=0`: an ensemble is treated as a finite,
    uniformly weighted predictive mixture, so the returned components satisfy
    `predictive_variance = epistemic_variance + aleatoric_variance` exactly up
    to floating-point precision.
    """
    np, members = _as_probability_members(member_probabilities)
    if np is not None:
        mean_probability = members.mean(axis=0)
        epistemic_variance = members.var(axis=0, ddof=0)
        aleatoric_variance = (members * (1.0 - members)).mean(axis=0)
        predictive_variance = mean_probability * (1.0 - mean_probability)
        if not np.allclose(
            predictive_variance,
            epistemic_variance + aleatoric_variance,
            rtol=1e-10,
            atol=1e-12,
        ):
            raise ArithmeticError("Law-of-total-variance check failed")
        return {
            "mean_probability": mean_probability,
            "epistemic_variance": epistemic_variance,
            "aleatoric_variance": aleatoric_variance,
            "predictive_variance": predictive_variance,
            "member_count": int(members.shape[0]),
            "decomposition": "Var(member means) + mean(member Bernoulli variance)",
        }

    count = len(members)
    width = len(members[0])
    mean = []
    epistemic = []
    aleatoric = []
    predictive = []
    for j in range(width):
        ps = [float(member[j]) for member in members]
        pbar = sum(ps) / count
        epi = sum((p - pbar) ** 2 for p in ps) / count
        alea = sum(p * (1.0 - p) for p in ps) / count
        total = pbar * (1.0 - pbar)
        if not math.isclose(total, epi + alea, rel_tol=1e-10, abs_tol=1e-12):
            raise ArithmeticError("Law-of-total-variance check failed")
        mean.append(pbar)
        epistemic.append(epi)
        aleatoric.append(alea)
        predictive.append(total)
    return {
        "mean_probability": mean,
        "epistemic_variance": epistemic,
        "aleatoric_variance": aleatoric,
        "predictive_variance": predictive,
        "member_count": count,
        "decomposition": "Var(member means) + mean(member Bernoulli variance)",
    }


def survey_gap_priority(
    mean_probability: Any,
    epistemic_variance: Any,
    survey_coverage: Any | None,
    *,
    strength: float,
) -> dict[str, Any]:
    """Create a review-priority score, not a submission probability.

    `survey_coverage` is a validated proxy in `[0, 1]` (0 = low mapped coverage,
    1 = high mapped coverage). The signed epistemic adjustment is
    `strength * normalized_epistemic_sd * (1 - 2 * coverage)`: disagreement
    raises priority under low coverage and lowers priority under high coverage.
    When coverage is unavailable, the adjustment is exactly zero. The strength
    must be selected using spatially blocked validation before operational use.
    """
    if not math.isfinite(float(strength)) or not 0.0 <= float(strength) <= 1.0:
        raise ValueError("strength must be a finite number in [0, 1]")
    np = _numpy_module()
    if np is not None:
        p = np.asarray(mean_probability, dtype=np.float64)
        epi = np.asarray(epistemic_variance, dtype=np.float64)
        if p.shape != epi.shape:
            raise ValueError("mean_probability and epistemic_variance must have matching shapes")
        if not np.isfinite(p).all() or not np.isfinite(epi).all():
            raise ValueError("probability and epistemic variance must be finite")
        if ((p < 0) | (p > 1)).any() or (epi < 0).any():
            raise ValueError("probability must be [0,1] and epistemic variance non-negative")
        if survey_coverage is None:
            adjustment = np.zeros_like(p)
            return {
                "priority_score": p.copy(),
                "adjustment": adjustment,
                "coverage_known": False,
                "interpretation": "No coverage proxy; no uncertainty adjustment applied",
            }
        coverage = np.asarray(survey_coverage, dtype=np.float64)
        if coverage.shape != p.shape:
            raise ValueError("survey_coverage must have the same shape as probabilities")
        if not np.isfinite(coverage).all() or ((coverage < 0) | (coverage > 1)).any():
            raise ValueError("survey coverage must be finite and in [0, 1]")
        normalized_sd = np.clip(np.sqrt(epi) / 0.5, 0.0, 1.0)
        adjustment = float(strength) * normalized_sd * (1.0 - 2.0 * coverage)
        return {
            "priority_score": p + adjustment,
            "adjustment": adjustment,
            "coverage_known": True,
            "interpretation": "Review priority only; not a calibrated submission probability",
        }

    def as_vector(value: Any, name: str) -> list[float]:
        try:
            result = [float(item) for item in value]
        except TypeError as exc:
            raise ValueError(f"{name} must be a vector without NumPy") from exc
        return result

    p_vec = as_vector(mean_probability, "mean_probability")
    epi_vec = as_vector(epistemic_variance, "epistemic_variance")
    if len(p_vec) != len(epi_vec):
        raise ValueError("mean_probability and epistemic_variance must have matching lengths")
    if any(not math.isfinite(p) or not 0.0 <= p <= 1.0 for p in p_vec):
        raise ValueError("mean_probability must be finite and in [0, 1]")
    if any(not math.isfinite(v) or v < 0.0 for v in epi_vec):
        raise ValueError("epistemic_variance must be finite and non-negative")
    if survey_coverage is None:
        adjustment = [0.0] * len(p_vec)
        return {
            "priority_score": p_vec[:],
            "adjustment": adjustment,
            "coverage_known": False,
            "interpretation": "No coverage proxy; no uncertainty adjustment applied",
        }
    c_vec = as_vector(survey_coverage, "survey_coverage")
    if len(c_vec) != len(p_vec):
        raise ValueError("survey_coverage must have the same length as probabilities")
    if any(not math.isfinite(c) or not 0.0 <= c <= 1.0 for c in c_vec):
        raise ValueError("survey_coverage must be finite and in [0, 1]")
    adjustment = [
        float(strength) * min(math.sqrt(v) / 0.5, 1.0) * (1.0 - 2.0 * c)
        for v, c in zip(epi_vec, c_vec)
    ]
    return {
        "priority_score": [p + d for p, d in zip(p_vec, adjustment)],
        "adjustment": adjustment,
        "coverage_known": True,
        "interpretation": "Review priority only; not a calibrated submission probability",
    }


def write_candidate_review_csv(
    path: str | Path,
    candidate_ids: Sequence[str],
    mean_probability: Sequence[float],
    epistemic_variance: Sequence[float],
    aleatoric_variance: Sequence[float],
    survey_coverage: Sequence[float | None] | None,
    *,
    priority_strength: float,
    calibration_status: str,
    source_note: str,
) -> None:
    """Write an auditable per-candidate uncertainty handoff for human reviewers."""
    n = len(candidate_ids)
    fields = (mean_probability, epistemic_variance, aleatoric_variance)
    if any(len(values) != n for values in fields):
        raise ValueError("Every uncertainty vector must have one value per candidate")
    if survey_coverage is not None and len(survey_coverage) != n:
        raise ValueError("survey_coverage must have one value per candidate or be None")

    for i in range(n):
        p = float(mean_probability[i])
        epi = float(epistemic_variance[i])
        alea = float(aleatoric_variance[i])
        if not (math.isfinite(p) and 0.0 <= p <= 1.0):
            raise ValueError(f"candidate {candidate_ids[i]} has invalid mean probability")
        if not (math.isfinite(epi) and epi >= 0.0 and math.isfinite(alea) and alea >= 0.0):
            raise ValueError(f"candidate {candidate_ids[i]} has invalid uncertainty")

    adjustments: list[float] = []
    priority_values: list[float] = []
    for i in range(n):
        coverage_value = None if survey_coverage is None else survey_coverage[i]
        result = survey_gap_priority(
            [float(mean_probability[i])],
            [float(epistemic_variance[i])],
            None if coverage_value is None else [float(coverage_value)],
            strength=priority_strength,
        )
        adjustments.append(float(result["adjustment"][0]))
        priority_values.append(float(result["priority_score"][0]))
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "candidate_id",
        "mean_probability",
        "epistemic_variance",
        "aleatoric_variance",
        "total_predictive_variance",
        "survey_coverage_proxy",
        "survey_gap_adjustment",
        "review_priority_score",
        "uncertainty_readout",
        "calibration_status",
        "survey_source_note",
        "score_is_submission_probability",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for i, candidate_id in enumerate(candidate_ids):
            epi, alea, p = (
                float(epistemic_variance[i]),
                float(aleatoric_variance[i]),
                float(mean_probability[i]),
            )
            coverage = survey_coverage[i] if survey_coverage is not None else None
            if epi > alea:
                readout = "ensemble disagreement is larger; inspect evidence/coverage"
            elif alea > epi:
                readout = "members agree more; conditional Bernoulli ambiguity is larger"
            else:
                readout = "epistemic and conditional variance are equal"
            if coverage is None:
                readout += "; coverage unavailable, no gap adjustment"
            writer.writerow(
                {
                    "candidate_id": candidate_id,
                    "mean_probability": f"{p:.8g}",
                    "epistemic_variance": f"{epi:.8g}",
                    "aleatoric_variance": f"{alea:.8g}",
                    "total_predictive_variance": f"{p * (1.0 - p):.8g}",
                    "survey_coverage_proxy": "" if coverage is None else f"{float(coverage):.8g}",
                    "survey_gap_adjustment": f"{float(adjustments[i]):.8g}",
                    "review_priority_score": f"{float(priority_values[i]):.8g}",
                    "uncertainty_readout": readout,
                    "calibration_status": calibration_status,
                    "survey_source_note": source_note,
                    "score_is_submission_probability": "false",
                }
            )
