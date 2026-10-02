"""Tests for the prediction audit (src/gems/audit.py) and the emission tie-break (src/gems/emission.py)."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

HAS_GEO = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None
HAS_SHP = importlib.util.find_spec("shapefile") is not None and importlib.util.find_spec("rasterio") is not None


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class SurveyLineDetectorTests(unittest.TestCase):
    def test_periodic_signal_is_flagged_and_noise_is_not(self):
        import numpy as np
        from gems import audit

        rng = np.random.default_rng(0)
        n = np.arange(3000)
        sig = 0.3 * np.cos(2 * np.pi * 0.25 * n + 0.7) + rng.standard_normal(n.size)
        r = audit.periodicity_test(sig, 0.25, harmonics=(1.0, 2.0))
        self.assertLessEqual(r["p_rank"], 0.05)
        self.assertGreater(r["strength"], 5 * r["control_median"])
        noise = rng.standard_normal(n.size)
        rn = audit.periodicity_test(noise, 0.25, harmonics=(1.0, 2.0))
        self.assertGreater(rn["p_rank"], 0.05)

    def test_raster_with_a_four_row_comb_is_detected(self):
        import numpy as np
        from gems import audit

        rng = np.random.default_rng(1)
        H, W = 800, 400
        base = rng.random((H, W)) < 0.02
        comb = np.zeros((H, W), bool)
        comb[2::4, :] = rng.random((H // 4, W)) < 0.05
        reg = np.ones((H, W), bool)
        flags = audit.survey_flags(audit.survey_line_test((base | comb).astype(float), reg))
        self.assertTrue(flags["traverse_400m_along_y"])
        clean = audit.survey_flags(audit.survey_line_test(base.astype(float), reg))
        self.assertFalse(clean["traverse_400m_along_y"])

    def test_equalisation_removes_the_comb_with_minimal_movement(self):
        import numpy as np
        from gems import audit

        rng = np.random.default_rng(2)
        H, W = 600, 600
        domain = np.ones((H, W), bool)
        mask = np.zeros((H, W), bool)
        # dots on a loose lattice, 60 % of them forced onto rows = 2 (mod 4)
        for r in range(2, H - 2, 6):
            for c in range(2, W - 2, 6):
                rr = r + (2 - r % 4) if rng.random() < 0.6 else r
                if 0 <= rr < H:
                    mask[rr, c + int(rng.integers(0, 2))] = True
        before = audit.row_phase_hist(mask)
        self.assertGreater(before.max(), 0.35)
        res = audit.equalize_row_phase(mask, domain, period=4, block=300, min_sep_px=3.0, max_shift=2, seed=0)
        after = np.array(res["hist_after"])
        self.assertLess(after.max() - after.min(), 0.04)
        self.assertEqual(int(res["mask"].sum()), int(mask.sum()))
        # fewest moves: only the excess over the uniform share has to move (plus a small block-edge slack)
        excess = float(np.clip(before - 0.25, 0, None).sum())
        self.assertLessEqual(res["share_moved"], excess + 0.04)
        self.assertLessEqual(res["mean_abs_shift_px"], 2.0)
        self.assertFalse(audit.survey_flags(audit.survey_line_test(res["mask"].astype(float), domain))["traverse_400m_along_y"])


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class BoundaryTests(unittest.TestCase):
    def test_edge_jump_index_is_one_when_prediction_follows_reference(self):
        import numpy as np
        from gems import audit

        H, W = 200, 400
        region = np.zeros((H, W), bool)
        region[:, 200:] = True
        domain = np.ones((H, W), bool)
        rng = np.random.default_rng(0)
        dens = np.where(region, 0.04, 0.02)
        ref = rng.random((H, W)) < dens
        same = rng.random((H, W)) < dens
        j = audit.edge_jump(same, domain, region, ref, domain, width_km=1.5)
        self.assertAlmostEqual(j["jump_index"], 1.0, delta=0.35)
        flat = rng.random((H, W)) < 0.03
        j2 = audit.edge_jump(flat, domain, region, ref, domain, width_km=1.5)
        self.assertLess(j2["jump_index"], 0.7)

    def test_signed_distance_is_positive_inside(self):
        import numpy as np
        from gems import audit

        region = np.zeros((20, 20), bool)
        region[5:15, 5:15] = True
        sd = audit.distance_to_boundary_km(region)
        self.assertGreater(sd[10, 10], 0)
        self.assertLess(sd[0, 0], 0)

    @unittest.skipUnless(HAS_SHP and (ROOT / "data/external/GeoDAWN_area1_outline.zip").exists(), "needs pyshp, rasterio and the external outline")
    def test_area1_outline_matches_the_official_area(self):
        import rasterio
        from gems import audit

        with rasterio.open(ROOT / "data/sample_submission.tif") as s:
            tm, shape = s.transform, (s.height, s.width)
        m = audit.rasterize_polygon_zip(str(ROOT / "data/external/GeoDAWN_area1_outline.zip"), tm, shape)
        self.assertAlmostEqual(m.sum() / 100.0, 2411.7, delta=15.0)        # official 'ENCLOSED_A' 2411.7 km2


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class EmissionTieBreakTests(unittest.TestCase):
    def test_plateau_scores_violate_separation_unless_ties_are_broken(self):
        import numpy as np
        from scipy.spatial import cKDTree
        from gems.emission import disperse_select

        domain = np.ones((60, 60), bool)
        score = np.zeros((60, 60))               # a flat plateau: every pixel is an equal 'local maximum'
        plain = disperse_select(score, domain, 40, 4)
        broken = disperse_select(score, domain, 40, 4, break_ties=True)

        def min_nn(mask):
            rr, cc = np.nonzero(mask)
            P = np.column_stack([rr, cc]).astype(float)
            d, _ = cKDTree(P).query(P, k=2)
            return d[:, 1].min()

        self.assertLess(min_nn(plain), 4.0)      # the shipped H24 behaviour: adjacent dots accepted together
        self.assertGreaterEqual(min_nn(broken), 4.0 - 1e-9)
        self.assertEqual(int(broken.sum()), 40)

    def test_integer_radius_behaviour_is_unchanged(self):
        import numpy as np
        from gems.emission import disperse_select

        rng = np.random.default_rng(0)
        score = rng.random((80, 80))
        domain = np.ones((80, 80), bool)
        a = disperse_select(score, domain, 30, 4)
        b = disperse_select(score, domain, 30, 4.0)
        self.assertTrue(np.array_equal(a, b))


if __name__ == "__main__":
    unittest.main()
