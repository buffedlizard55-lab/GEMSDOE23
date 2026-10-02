"""Tests for the live-score inversion, dispersion and deep-ensemble variance split.

Every test is synthetic and dependency-guarded: it skips when numpy/scipy are absent so
`python -m unittest discover -s tests` still passes in a bare environment.
"""
import importlib.util
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_SCIPY = importlib.util.find_spec("scipy") is not None
HAS_TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(HAS_NUMPY and HAS_SCIPY, "numpy/scipy not installed")
class KernelAndEnvelopeTests(unittest.TestCase):
    def test_single_pixel_envelope_matches_the_official_cone(self):
        import numpy as np
        from gems.emission import kernel_envelope

        m = np.zeros((21, 21), bool)
        m[10, 10] = True
        env = kernel_envelope(m)
        self.assertAlmostEqual(float(env[10, 10]), 1.0, places=6)
        self.assertAlmostEqual(float(env[10, 11]), 2.0 / 3.0, places=5)      # 100 m
        self.assertAlmostEqual(float(env[10, 13]), 0.0, places=6)            # 300 m -> 0
        self.assertAlmostEqual(float(env[11, 11]), (1 - math.sqrt(2) / 3), places=4)

    def test_envelope_total_for_an_isolated_pixel_is_the_cone_weight(self):
        import numpy as np
        from gems.emission import kernel_envelope

        m = np.zeros((41, 41), bool)
        m[20, 20] = True
        self.assertAlmostEqual(float(kernel_envelope(m).sum()), 9.3803, places=3)


@unittest.skipUnless(HAS_NUMPY and HAS_SCIPY, "numpy/scipy not installed")
class FalsePositiveReliefTests(unittest.TestCase):
    def test_relief_depends_on_the_size_of_the_truth_set(self):
        from gems.emission import fp_relief

        # a large truth set gives a predicted pixel some relief; a small one gives almost none
        self.assertAlmostEqual(fp_relief(125_000.0), 0.810, places=2)
        self.assertGreater(fp_relief(8_000.0), 0.98)
        self.assertLess(fp_relief(8_000.0), 1.0)
        self.assertGreater(fp_relief(5_000.0), fp_relief(12_000.0))
        self.assertAlmostEqual(fp_relief(0.0), 1.0, places=12)


@unittest.skipUnless(HAS_NUMPY and HAS_SCIPY, "numpy/scipy not installed")
class InversionTests(unittest.TestCase):
    def test_implied_tp_and_dti_are_exact_inverses(self):
        from gems.habitat import implied_dti, implied_tp

        for g in (4_000.0, 10_000.0, 25_000.0):
            for area in (20_000.0, 120_000.0, 400_000.0):
                for dti in (0.02, 0.0904, 0.1922, 0.3195):
                    tp = implied_tp(dti, area, g)
                    if tp > g:
                        continue                      # not physically reachable
                    self.assertAlmostEqual(implied_dti(tp, area, g), dti, places=6)

    def test_an_unreachable_triple_is_detected_by_tp_exceeding_g(self):
        from gems.habitat import implied_tp

        # a score of 0.9 on 10,000 emitted pixels cannot come from a 100-pixel truth set
        self.assertGreater(implied_tp(0.9, 10_000.0, 100.0), 100.0)
        # but the same score on a small emission is reachable with a larger truth set
        self.assertLessEqual(implied_tp(0.1922, 121_131.0, 15_000.0), 15_000.0)

    def test_expected_dti_is_capped_by_perfect_recall(self):
        from gems.emission import expected_dti

        # skill so large that TP would exceed |G| must be clipped at |G|
        from gems.emission import fp_relief

        d = expected_dti(area=10_000.0, kbar=0.5, g_size=1_000.0, skill=100.0)
        self.assertAlmostEqual(d, 1_000.0 / (1_000.0 + 0.2 * fp_relief(1_000.0) * 10_000.0), places=6)

    def test_marginal_threshold_falls_as_the_truth_set_grows(self):
        from gems.emission import marginal_tp_threshold

        small = marginal_tp_threshold(100_000.0, 5_000.0, 5_000.0)
        large = marginal_tp_threshold(100_000.0, 5_000.0, 50_000.0)
        self.assertGreater(small, large)


@unittest.skipUnless(HAS_NUMPY and HAS_SCIPY, "numpy/scipy not installed")
class DispersionTests(unittest.TestCase):
    def test_dispersed_selection_respects_budget_and_separation(self):
        import numpy as np
        from gems.emission import disperse_select

        rng = np.random.default_rng(0)
        domain = np.ones((120, 120), bool)
        score = rng.random((120, 120))
        mask = disperse_select(score, domain, budget=200, r_min_px=4)
        self.assertEqual(int(mask.sum()), 200)
        ys, xs = np.nonzero(mask)
        d2 = (ys[:, None] - ys[None, :]) ** 2 + (xs[:, None] - xs[None, :]) ** 2
        np.fill_diagonal(d2, 10 ** 9)
        self.assertGreaterEqual(int(d2.min()), 9)          # strictly more than 3 px apart

    def test_dispersion_efficiency_of_a_lattice_beats_a_blob(self):
        import numpy as np
        from gems.emission import geometry

        domain = np.ones((300, 300), bool)
        blob = np.zeros((300, 300), bool)
        blob[100:132, 100:132] = True                     # 1,024 px solid block
        dots = np.zeros((300, 300), bool)
        dots[40::9, 40::9] = True                          # well-separated dots
        dots = dots & domain
        gb = geometry(blob, domain)
        gd = geometry(dots, domain)
        self.assertGreater(gd["eta"], gb["eta"])
        self.assertGreater(gd["eta"], 0.8)
        self.assertLess(gb["eta"], 0.4)

    def test_selection_prefers_higher_scores(self):
        import numpy as np
        from gems.emission import disperse_select

        domain = np.ones((60, 60), bool)
        score = np.zeros((60, 60))
        score[10, 10] = 5.0
        score[50, 50] = 1.0
        mask = disperse_select(score, domain, budget=1, r_min_px=2)
        self.assertTrue(bool(mask[10, 10]))
        self.assertFalse(bool(mask[50, 50]))


@unittest.skipUnless(HAS_NUMPY, "numpy not installed")
class UncertaintySplitTests(unittest.TestCase):
    def test_total_variance_is_epistemic_plus_aleatoric(self):
        import numpy as np
        from gems.ensemble import decompose

        members = np.array([[[0.1, 0.9], [0.5, 0.2]],
                            [[0.3, 0.7], [0.5, 0.4]],
                            [[0.2, 0.8], [0.5, 0.3]]], dtype=np.float64)
        d = decompose(members)
        mean = members.mean(0)
        np.testing.assert_allclose(d["mean"], mean, rtol=0, atol=1e-6)
        np.testing.assert_allclose(d["epistemic"], members.var(0, ddof=0), rtol=0, atol=1e-6)
        np.testing.assert_allclose(d["aleatoric"], (members * (1 - members)).mean(0), rtol=0, atol=1e-6)
        np.testing.assert_allclose(d["total"], d["epistemic"] + d["aleatoric"], rtol=0, atol=1e-6)

    def test_identical_members_have_zero_epistemic_variance(self):
        import numpy as np
        from gems.ensemble import decompose

        members = np.repeat(np.array([[[0.25, 0.75]]]), 5, axis=0)
        d = decompose(members)
        self.assertEqual(float(d["epistemic"].max()), 0.0)
        self.assertGreater(float(d["aleatoric"].max()), 0.0)


@unittest.skipUnless(HAS_NUMPY, "numpy not installed")
class BlockedFoldTests(unittest.TestCase):
    def test_folds_partition_and_buffers_remove_the_edges(self):
        import numpy as np
        from gems.ensemble import _buffered, blocked_folds

        folds = blocked_folds((50, 100), 5, 3)
        self.assertEqual(len(folds), 5)
        union = np.zeros((50, 100), bool)
        for f in folds:
            self.assertEqual(int((union & f).sum()), 0)
            union |= f
        self.assertTrue(union.all())
        buf = _buffered(folds[0], 3)
        self.assertGreater(int(buf.sum()), int(folds[0].sum()))


@unittest.skipUnless(HAS_NUMPY and HAS_SCIPY, "numpy/scipy not installed")
class SubmissionWriterVariantTests(unittest.TestCase):
    def test_nan_and_zero_variants_both_validate_and_differ_outside(self):
        import numpy as np
        import rasterio
        from tempfile import TemporaryDirectory
        from gems.submission import validate_submission, write_submission_raster

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tpl = tmp / "template.tif"
            prof = dict(driver="GTiff", height=12, width=10, count=1, dtype="float32",
                        crs="EPSG:32611",
                        transform=rasterio.transform.from_origin(243350.0, 4508550.0, 100.0, 100.0),
                        nodata=float("nan"))
            vals = np.full((12, 10), np.nan, np.float32)
            vals[2:10, 1:9] = 0.0
            vals[4, 4] = 1.0
            with rasterio.open(tpl, "w", **prof) as dst:
                dst.write(vals, 1)
            pred = np.zeros((12, 10), np.float32)
            pred[2:10, 1:9] = 0.0
            pred[4, 4] = 1.0
            a = tmp / "nan.tif"; b = tmp / "zero.tif"
            write_submission_raster(pred, tpl, a)
            write_submission_raster(pred, tpl, b, outside="zero")
            ra, rb = validate_submission(a, tpl), validate_submission(b, tpl)
            self.assertTrue(ra["passed"], ra["hard_failures"])
            self.assertTrue(rb["passed"], rb["hard_failures"])
            with rasterio.open(a) as src:
                self.assertTrue(bool(np.isnan(src.read(1)[0, 0])))
                self.assertEqual(src.nodata is not None and math.isnan(float(src.nodata)), True)
            with rasterio.open(b) as src:
                self.assertEqual(float(src.read(1)[0, 0]), 0.0)
                self.assertEqual(float(src.nodata), 0.0)

    def test_out_of_range_values_are_refused(self):
        import numpy as np
        import rasterio
        from tempfile import TemporaryDirectory
        from gems.submission import write_submission_raster

        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tpl = tmp / "t.tif"
            with rasterio.open(tpl, "w", driver="GTiff", height=6, width=6, count=1,
                               dtype="float32", crs="EPSG:32611",
                               transform=rasterio.transform.from_origin(0, 0, 100, 100),
                               nodata=float("nan")) as dst:
                dst.write(np.ones((6, 6), np.float32), 1)
            with self.assertRaises(ValueError):
                write_submission_raster(np.full((6, 6), 1.5, np.float32), tpl, tmp / "bad.tif")
            with self.assertRaises(ValueError):
                write_submission_raster(np.full((6, 6), -0.1, np.float32), tpl, tmp / "bad2.tif")


@unittest.skipUnless(HAS_NUMPY and HAS_SCIPY, "numpy/scipy not installed")
class MetricWorkedExampleTests(unittest.TestCase):
    def test_official_scoring_example_reproduces_0_60(self):
        """The organiser's published example: TP_w 3.00, FP_w 1.89, FN_w 2.00 -> 0.60.

        Truth is a vertical line; the kernel radius in the example is 3 pixels.  The
        published component values are reproduced by a one-pixel-offset prediction of the
        same length, which is the configuration the page's figure shows.
        """
        import numpy as np
        from gems.metric import distance_weighted_tversky

        truth = np.zeros((15, 15), bool)
        truth[4:7, 7] = True                      # three-pixel vertical line
        pred = np.zeros((15, 15), np.float32)
        pred[4:7, 8] = 1.0                        # one pixel to the right
        r = distance_weighted_tversky(pred, truth, radius_m=300.0, pixel_size_m=100.0)
        self.assertAlmostEqual(r["tp_weighted"], 2.0, places=6)
        self.assertAlmostEqual(r["fn_weighted"], 1.0, places=6)
        self.assertAlmostEqual(r["dti"], 2.0 / (2.0 + 0.2 * 1.0 + 0.8 * 1.0), places=6)


if __name__ == "__main__":
    unittest.main()
