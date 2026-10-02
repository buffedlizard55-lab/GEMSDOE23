import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_submission", ROOT / "scripts/build_submission.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


TRUTH_SHA = "c" * 64
BASELINE_SPEC_SHA = "a" * 64
BASELINE_OOF_SHA = "b" * 64
VALIDATION_SHA = "d" * 64


def current_best():
    return {
        "status": "VERIFIED",
        "truth_semantics": "independent_uncatalogued_faults",
        "folds": [0, 1, 2, 3],
        "holdout_id": "sgmc-gap-quadrants-v1",
        "candidate_id": "baseline-unet",
        "candidate_spec_sha256": BASELINE_SPEC_SHA,
        "oof_prediction_sha256": BASELINE_OOF_SHA,
        "validation_report_sha256": VALIDATION_SHA,
        "truth_sha256": TRUTH_SHA,
    }


def passing_gate():
    deltas = [0.02, 0.02, 0.02, -0.01]
    return {
        "status": "PASSED",
        "eligible_for_submission": True,
        "truth_semantics": "independent_uncatalogued_faults",
        "truth_sha256": TRUTH_SHA,
        "current_best_holdout_id": "sgmc-gap-quadrants-v1",
        "incumbent_id": "baseline-unet",
        "incumbent_spec_sha256": BASELINE_SPEC_SHA,
        "incumbent_prediction_sha256": BASELINE_OOF_SHA,
        "spatial_design": {"folds": 4, "prediction_type": "out_of_fold"},
        "fold_results": [{"fold_id": i, "delta": delta} for i, delta in enumerate(deltas)],
        "gate": {
            "minimum_mean_delta": 0.002,
            "minimum_fold_wins": 3,
            "mean_delta": sum(deltas) / 4,
            "fold_wins": 3,
            "eligible_for_submission": True,
        },
    }


class SubmissionGateTests(unittest.TestCase):
    def test_accepts_consistent_four_fold_gate_against_registered_best(self):
        MODULE.validate_gate_report(passing_gate(), current_best())

    def test_rejects_boolean_only_or_inconsistent_gate(self):
        gate = passing_gate()
        gate["fold_results"][3]["delta"] = -0.2
        with self.assertRaises(ValueError):
            MODULE.validate_gate_report(gate, current_best())

    def test_rejects_non_oof_validation(self):
        gate = passing_gate()
        gate["spatial_design"]["prediction_type"] = "random-split"
        with self.assertRaises(ValueError):
            MODULE.validate_gate_report(gate, current_best())

    def test_rejects_proxy_only_known_catalogue_validation(self):
        gate = passing_gate()
        gate["status"] = "PROXY_ONLY"
        gate["truth_semantics"] = "known_catalogue_faults; proxy-only"
        gate["eligible_for_submission"] = False
        with self.assertRaisesRegex(ValueError, "status must be PASSED"):
            MODULE.validate_gate_report(gate, current_best())

    def test_rejects_withdrawn_report_even_if_old_flags_claim_eligibility(self):
        gate = passing_gate()
        gate["status"] = "WITHDRAWN"
        with self.assertRaisesRegex(ValueError, "status must be PASSED"):
            MODULE.validate_gate_report(gate, current_best())

    def test_rejects_comparison_against_non_current_incumbent(self):
        gate = passing_gate()
        gate["incumbent_id"] = "some-other-model"
        with self.assertRaisesRegex(ValueError, "registered current holdout best"):
            MODULE.validate_gate_report(gate, current_best())

    def test_rejects_unavailable_current_best_registry(self):
        record = current_best()
        record["status"] = "BLOCKED"
        with self.assertRaisesRegex(ValueError, "No verified current holdout best"):
            MODULE.validate_gate_report(passing_gate(), record)


if __name__ == "__main__":
    unittest.main()
