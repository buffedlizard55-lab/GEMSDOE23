import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_submission", ROOT / "scripts/build_submission.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def passing_gate():
    deltas = [0.02, 0.02, 0.02, -0.01]
    return {
        "eligible_for_submission": True,
        "spatial_design": {"folds": 4, "prediction_type": "out_of_fold"},
        "fold_results": [
            {"fold_id": i, "delta": delta}
            for i, delta in enumerate(deltas)
        ],
        "gate": {
            "minimum_mean_delta": 0.002,
            "minimum_fold_wins": 3,
            "mean_delta": sum(deltas) / 4,
            "fold_wins": 3,
            "eligible_for_submission": True,
        },
    }


class SubmissionGateTests(unittest.TestCase):
    def test_accepts_consistent_four_fold_gate(self):
        MODULE.validate_gate_report(passing_gate())

    def test_rejects_boolean_only_or_inconsistent_gate(self):
        gate = passing_gate()
        gate["fold_results"][3]["delta"] = -0.2
        with self.assertRaises(ValueError):
            MODULE.validate_gate_report(gate)

    def test_rejects_non_oof_validation(self):
        gate = passing_gate()
        gate["spatial_design"]["prediction_type"] = "random-split"
        with self.assertRaises(ValueError):
            MODULE.validate_gate_report(gate)


if __name__ == "__main__":
    unittest.main()
