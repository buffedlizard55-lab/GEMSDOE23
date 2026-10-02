import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gems.uncertainty import decompose_binary_ensemble, survey_gap_priority, write_candidate_review_csv


class UncertaintyTests(unittest.TestCase):
    def test_total_variance_identity_and_interpretation(self):
        result = decompose_binary_ensemble([[0.1], [0.9]])
        self.assertAlmostEqual(result["mean_probability"][0], 0.5)
        self.assertAlmostEqual(result["epistemic_variance"][0], 0.16)
        self.assertAlmostEqual(result["aleatoric_variance"][0], 0.09)
        self.assertAlmostEqual(result["predictive_variance"][0], 0.25)
        self.assertAlmostEqual(
            result["epistemic_variance"][0] + result["aleatoric_variance"][0],
            result["predictive_variance"][0],
        )

    def test_agreement_has_zero_epistemic_but_high_conditional_variance(self):
        result = decompose_binary_ensemble([[0.5, 0.02], [0.5, 0.02], [0.5, 0.02]])
        self.assertAlmostEqual(result["epistemic_variance"][0], 0.0)
        self.assertAlmostEqual(result["aleatoric_variance"][0], 0.25)
        self.assertAlmostEqual(result["epistemic_variance"][1], 0.0)
        self.assertLess(result["aleatoric_variance"][1], 0.03)

    def test_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            decompose_binary_ensemble([[0.4]])
        with self.assertRaises(ValueError):
            decompose_binary_ensemble([[0.2], [1.1]])
        with self.assertRaises(ValueError):
            decompose_binary_ensemble([[float("nan")], [0.5]])

    def test_survey_gap_adjustment_changes_sign_with_coverage(self):
        result = survey_gap_priority([0.5, 0.5], [0.16, 0.16], [0.0, 1.0], strength=0.10)
        self.assertAlmostEqual(result["adjustment"][0], 0.08)
        self.assertAlmostEqual(result["adjustment"][1], -0.08)
        self.assertGreater(result["priority_score"][0], 0.5)
        self.assertLess(result["priority_score"][1], 0.5)
        self.assertEqual(result["interpretation"], "Review priority only; not a calibrated submission probability")

    def test_unknown_coverage_applies_no_adjustment(self):
        result = survey_gap_priority([0.8], [0.2], None, strength=0.5)
        self.assertEqual(result["priority_score"], [0.8])
        self.assertEqual(result["adjustment"], [0.0])
        self.assertFalse(result["coverage_known"])

    def test_candidate_csv_reports_partial_coverage_and_marks_priority_not_probability(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "review.csv"
            write_candidate_review_csv(
                out,
                ["A", "B"],
                [0.5, 0.5],
                [0.16, 0.16],
                [0.09, 0.09],
                [0.0, None],
                priority_strength=0.1,
                calibration_status="not calibrated",
                source_note="test map proxy",
            )
            with out.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["survey_gap_adjustment"], "0.08")
        self.assertEqual(rows[1]["survey_gap_adjustment"], "0")
        self.assertEqual(rows[1]["survey_coverage_proxy"], "")
        self.assertEqual(rows[1]["score_is_submission_probability"], "false")
        self.assertIn("coverage unavailable", rows[1]["uncertainty_readout"])


if __name__ == "__main__":
    unittest.main()
