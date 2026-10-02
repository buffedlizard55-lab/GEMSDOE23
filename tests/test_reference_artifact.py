import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/downloads/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif"


class ReferenceArtifactTests(unittest.TestCase):
    def test_independent_stdlib_decoder_rechecks_full_raster(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/audit_reference_tif.py"), str(REFERENCE)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["sha256"], "ec1f9b56b83ce33cad781ceb9f104b18fb4f2ff785263a4e89616af4aabdee8d")
        self.assertEqual(report["epsg"], 32611)
        self.assertEqual(report["finite_pixels"], 5167373)
        self.assertEqual(report["nan_pixels"], 7111787)
        self.assertTrue(report["finite_values_in_0_1"])
        self.assertEqual(report["template_match"], "NOT CHECKED; official sample_submission.tif is required")


if __name__ == "__main__":
    unittest.main()
