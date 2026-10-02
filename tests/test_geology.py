import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

HAS_GEO = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy geospatial dependencies are not installed")
class GeologyFeatureTests(unittest.TestCase):
    def test_edge_consensus_is_bounded_and_polarity_invariant(self):
        import numpy as np
        from gems.geology import multiscale_geophysical_edge_consensus

        y, x = np.mgrid[:64, :64]
        layers = {
            "tmi": x.astype(float),
            "reduced_to_pole": -2.0 * x.astype(float),
            "isostatic_gravity": 3.0 * x.astype(float),
            "surface_conductivity": -x.astype(float),
            "conductive_base_depth": 2.0 * x.astype(float),
        }
        mask = np.ones(x.shape, dtype=bool)
        result = multiscale_geophysical_edge_consensus(layers, mask)
        self.assertEqual(result.shape, x.shape)
        self.assertTrue(np.isfinite(result).all())
        self.assertGreater(float(result[32, 32]), 0.8)
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)

    def test_requires_named_layers_and_fails_closed(self):
        import numpy as np
        from gems.geology import multiscale_geophysical_edge_consensus

        with self.assertRaises(ValueError):
            multiscale_geophysical_edge_consensus({}, np.ones((8, 8), dtype=bool))


if __name__ == "__main__":
    unittest.main()
