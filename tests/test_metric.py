import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

HAS_GEO = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy geospatial dependencies are not installed")
class MetricTests(unittest.TestCase):
    def test_exact_pixel_prediction_scores_one(self):
        import numpy as np
        from gems.metric import distance_weighted_tversky

        truth = np.zeros((11, 11), dtype=bool)
        truth[5, 5] = True
        prediction = truth.astype(float)
        result = distance_weighted_tversky(prediction, truth)
        self.assertAlmostEqual(result["dti"], 1.0, places=10)

    def test_one_pixel_offset_uses_triangular_distance_weight(self):
        import numpy as np
        from gems.metric import distance_weighted_tversky

        truth = np.zeros((11, 11), dtype=bool)
        truth[5, 5] = True
        prediction = np.zeros((11, 11), dtype=float)
        prediction[5, 6] = 1.0
        result = distance_weighted_tversky(prediction, truth)
        self.assertAlmostEqual(result["tp_weighted"], 2.0 / 3.0)
        self.assertAlmostEqual(result["fn_weighted"], 1.0 / 3.0)
        self.assertAlmostEqual(result["fp_weighted"], 1.0 / 3.0)
        self.assertAlmostEqual(result["dti"], 2.0 / 3.0)

    def test_four_pixel_offset_is_not_matched(self):
        import numpy as np
        from gems.metric import distance_weighted_tversky

        truth = np.zeros((15, 15), dtype=bool)
        truth[7, 7] = True
        prediction = np.zeros((15, 15), dtype=float)
        prediction[7, 11] = 1.0
        result = distance_weighted_tversky(prediction, truth)
        self.assertAlmostEqual(result["tp_weighted"], 0.0)
        self.assertAlmostEqual(result["dti"], 0.0)

    def test_range_is_checked(self):
        import numpy as np
        from gems.metric import distance_weighted_tversky

        truth = np.zeros((3, 3), dtype=bool)
        truth[1, 1] = True
        with self.assertRaises(ValueError):
            distance_weighted_tversky(np.full((3, 3), 1.1), truth)


if __name__ == "__main__":
    unittest.main()
