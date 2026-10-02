import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems.submission import validate_submission, write_submission_raster


class SubmissionRasterTests(unittest.TestCase):
    def make_template(self, path: Path) -> tuple[np.ndarray, dict]:
        profile = {
            "driver": "GTiff",
            "width": 8,
            "height": 7,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:32611",
            "transform": Affine(100, 0, 500000, 0, -100, 4200000),
            "nodata": -9999.0,
        }
        data = np.ones((7, 8), dtype=np.float32)
        data[0, :2] = -9999.0
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)
        return data, profile

    def test_writer_produces_exact_template_grid_range_and_nan_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "template.tif"
            prediction_path = Path(tmp) / "prediction.tif"
            _, _ = self.make_template(template_path)
            probabilities = np.full((7, 8), 0.4, dtype=np.float32)
            write_submission_raster(probabilities, template_path, prediction_path)
            report = validate_submission(prediction_path, template_path)
            self.assertTrue(report["passed"], report)
            with rasterio.open(prediction_path) as prediction, rasterio.open(template_path) as template:
                output = prediction.read(1)
                valid = template.read_masks(1) > 0
                self.assertEqual(prediction.count, 1)
                self.assertEqual(prediction.dtypes, ("float32",))
                self.assertEqual(prediction.crs, template.crs)
                self.assertEqual(prediction.transform, template.transform)
                self.assertTrue(np.all(output[valid] == np.float32(0.4)))
                self.assertTrue(np.isnan(output[~valid]).all())
                self.assertTrue(np.isnan(prediction.nodata))

    def test_writer_refuses_out_of_range_in_footprint_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "template.tif"
            prediction_path = Path(tmp) / "prediction.tif"
            self.make_template(template_path)
            probabilities = np.full((7, 8), 0.4, dtype=np.float32)
            probabilities[3, 3] = 1.01
            with self.assertRaisesRegex(ValueError, r"range \[0, 1\]"):
                write_submission_raster(probabilities, template_path, prediction_path)
            self.assertFalse(prediction_path.exists())

    def test_validator_rejects_non_null_values_outside_footprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "template.tif"
            prediction_path = Path(tmp) / "bad-prediction.tif"
            _, profile = self.make_template(template_path)
            output = np.full((7, 8), 0.4, dtype=np.float32)
            # Deliberately leave zeros in two template-nodata pixels.
            with rasterio.open(prediction_path, "w", **profile) as dst:
                dst.write(output, 1)
            report = validate_submission(prediction_path, template_path)
            self.assertFalse(report["passed"])
            check = next(item for item in report["checks"] if item["check"] == "outside-footprint is null/NaN")
            self.assertFalse(check["passed"])


if __name__ == "__main__":
    unittest.main()
