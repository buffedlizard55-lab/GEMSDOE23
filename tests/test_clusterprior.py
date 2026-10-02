"""Tests for the empirical clustering prior (src/gems/clusterprior.py)."""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

HAS_GEO = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None


def _synthetic(seed=0, shape=(400, 600), near_p=0.06, base_p=0.02, wide=False):
    """A vertical 'long fault' (column 300) with targets whose density is boosted close to it.
    ``wide=False``: a 200-600 m band; ``wide=True``: everything within 3 km (a strong, broad effect)."""
    import numpy as np
    from scipy import ndimage as ndi

    rng = np.random.default_rng(seed)
    source = np.zeros(shape, bool)
    source[:, 300] = True
    d = ndi.distance_transform_edt(~source) * 100.0
    near = (d <= 3000) if wide else ((d > 200) & (d <= 600))
    p = np.where(near, near_p, base_p)
    target = (rng.random(shape) < p) & ~source
    return source, d, target, ~source


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class EnrichmentTests(unittest.TestCase):
    def test_profile_recovers_a_planted_near_field_lift(self):
        import numpy as np
        from gems import clusterprior as cp

        _, d, target, el = _synthetic()
        edges = [0, 200, 600, 5000, 1e9]
        prof = cp.enrichment_profile(target, d, el, edges, tile=200, n_boot=60, seed=1)
        E, lo, hi = np.array(prof["enrichment"]), np.array(prof["lo"]), np.array(prof["hi"])
        self.assertGreater(E[1], 2.0 * E[2])                           # planted 3x lift in the 200-600 m band
        self.assertGreater(E[2], E[3] * 0.9)                           # mid band is not below the far field
        self.assertTrue(np.all(lo[1:3] <= E[1:3] + 1e-9) and np.all(hi[1:3] >= E[1:3] - 1e-9))

    def test_auc_of_perfect_and_null_scores(self):
        import numpy as np
        from gems import clusterprior as cp

        self.assertAlmostEqual(cp._auc_from_scores(np.array([2.0, 3.0]), np.array([0.0, 1.0])), 1.0)
        self.assertAlmostEqual(cp._auc_from_scores(np.array([1.0, 1.0]), np.array([1.0, 1.0, 1.0])), 0.5)
        self.assertAlmostEqual(cp._auc_from_scores(np.array([0.0]), np.array([1.0])), 0.0)

    def test_blocked_auc_exceeds_chance_when_the_effect_is_real(self):
        import numpy as np
        from gems import clusterprior as cp

        edges = [0, 200, 600, 1500, 3000, 6000, 1e9]
        _, d, target, el = _synthetic(seed=3, near_p=0.05, base_p=0.01, wide=True)
        res = cp.blocked_auc(target, d, el, edges_m=edges, folds=2)
        self.assertGreater(res["auc_mean"], 0.6)
        null = np.roll(target, 137, axis=1)                             # same density, relation to the fault destroyed
        res0 = cp.blocked_auc(null, d, el, edges_m=edges, folds=2)
        self.assertLess(abs(res0["auc_mean"] - 0.5), 0.08)

@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class LiftAndBonusTests(unittest.TestCase):
    def test_lift_map_interpolates_and_bonus_is_bounded_and_one_sided(self):
        import numpy as np
        from gems import clusterprior as cp

        prof = dict(edges_m=[0, 200, 400, 600, 1000, 3000, 10000], enrichment=[0.2, 2.0, 1.4, 1.2, 1.0, 0.7])
        d = np.array([[300.0, 500.0, 800.0, 2000.0, 6000.0]])
        lift = cp.lift_map(d, prof)
        self.assertTrue(np.all(np.diff(lift[0][:3]) < 0))              # decreasing with distance through the lifted bands
        self.assertLess(lift[0, 4], 1.0)                               # far band below 1
        bonus = cp.tiebreak_bonus(lift, 0.01)
        self.assertLessEqual(float(bonus.max()), 0.01 + 1e-9)
        self.assertEqual(float(bonus[0, 4]), 0.0)                       # lift <= 1: no bonus, and never a penalty
        self.assertTrue(np.all(bonus >= 0))
        self.assertEqual(float(cp.tiebreak_bonus(np.full((2, 2), 0.9, np.float32), 0.01).max()), 0.0)


if __name__ == "__main__":
    unittest.main()
