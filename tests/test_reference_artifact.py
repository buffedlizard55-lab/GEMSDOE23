import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs/downloads/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif"
MANIFEST = ROOT / "docs/data/submission-manifest.json"


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

    def test_current_submission_passes_stdlib_audit_and_matches_its_manifest(self):
        """The file the site offers must be the file the manifest describes.

        Reads the current submission from docs/downloads/latest.json / submission-manifest.json
        instead of a hard-coded name, so renaming the artefact cannot silently skip the check.
        """
        if not MANIFEST.is_file():
            self.skipTest("no submission manifest built yet (scripts/build_submission_live.py)")
        man = json.loads(MANIFEST.read_text())
        for key in ("primary", "compatibility"):
            entry = man[key]
            path = ROOT / "docs/downloads" / entry["name"]
            self.assertTrue(path.is_file(), f"{key} raster missing: {path}")
            self.assertEqual(path.stat().st_size, entry["bytes"], f"{key} byte size drift")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/audit_reference_tif.py"), str(path)],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(report["sha256"], entry["sha256"], f"{key} sha256 drift")
            self.assertEqual(report["epsg"], 32611)
            self.assertEqual(report["width"], 3292)
            self.assertEqual(report["height"], 3730)
            self.assertEqual(report["samples_per_pixel"], 1)
            self.assertEqual(report["bits_per_sample"], 32)
            self.assertEqual(report["sample_format"], "IEEE float")
            self.assertTrue(report["finite_values_in_0_1"], "the [0, 1] rejection must be impossible")
            self.assertEqual(report["positive_infinity_pixels"], 0)
            self.assertEqual(report["negative_infinity_pixels"], 0)
            if key == "primary":
                self.assertEqual(report["finite_pixels"], 5167373)
                self.assertEqual(report["nan_pixels"], 7111787, "primary must be NaN outside the footprint")
                self.assertEqual(report["gdal_nodata"], "nan")
            else:
                self.assertEqual(report["finite_pixels"], 12279160)
                self.assertEqual(report["nan_pixels"], 0, "compatibility variant must be finite everywhere")
                self.assertEqual(report["gdal_nodata"], "0")

    def test_manifest_records_the_official_template_hash(self):
        if not MANIFEST.is_file():
            self.skipTest("no submission manifest built yet")
        man = json.loads(MANIFEST.read_text())
        self.assertEqual(man.get("template_sha256"),
                         "2176d08e485aa2cd2860ce8df539db4faf4d76163b38a4dd8c30a40454d35cbc")
        self.assertTrue(man.get("note"), "a submission must carry a short identifying note")
        self.assertLessEqual(len(man["note"]), 300, "the note is meant to be short")
        for key in ("primary", "compatibility"):
            self.assertTrue(man[key].get("ok_to_upload"), f"{key} failed template validation")
            for check in man["validation"]["nan" if key == "primary" else "allfinite"]["checks"]:
                if check["kind"] == "hard requirement":
                    self.assertTrue(check["passed"], check["check"])
