"""Tests for the fault-population statistics (src/gems/faultstats.py).

The decisive test is the synthetic check of the Bour & Davy (1999) relation x = (a - 1)/D: it fixes the
reading of ``a`` as the DENSITY exponent (a cumulative exponent would predict (a - 2)/D) and therefore
protects every consistency statement made on the real catalogue.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

HAS_GEO = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class TraceExtractionTests(unittest.TestCase):
    def test_lengths_and_centroids_of_known_lines(self):
        import numpy as np
        from gems import faultstats as fs

        m = np.zeros((40, 40), bool)
        m[5, 3:14] = True                      # horizontal, 11 px -> Feret 10 px + 1 px
        for k in range(8):                     # diagonal, 8 px -> Feret 7*sqrt(2) + 1 px
            m[20 + k, 20 + k] = True
        m[35, 35] = True                       # isolated pixel
        tr = fs.extract_traces(m)
        self.assertEqual(tr.n, 3)
        order = np.argsort(tr.length_m)
        self.assertAlmostEqual(tr.length_m[order[0]], 100.0)
        self.assertAlmostEqual(tr.length_m[order[1]], (7 * np.sqrt(2) + 1) * 100.0, places=6)
        self.assertAlmostEqual(tr.length_m[order[2]], 1100.0)
        i = order[2]
        self.assertAlmostEqual(tr.cx[i], 8.0 * 100.0)          # mean column 3..13 = 8
        self.assertAlmostEqual(tr.cy[i], 5.0 * 100.0)
        self.assertEqual(int(tr.n_px.sum()), 11 + 8 + 1)

    def test_touching_traces_merge_under_eight_connectivity(self):
        import numpy as np
        from gems import faultstats as fs

        m = np.zeros((10, 10), bool)
        m[2, 2] = True
        m[3, 3] = True                          # diagonal neighbour -> same component
        m[7, 7] = True
        self.assertEqual(fs.extract_traces(m).n, 2)


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class LengthDistributionTests(unittest.TestCase):
    def test_mle_recovers_a_known_density_exponent(self):
        import numpy as np
        from gems import faultstats as fs

        rng = np.random.default_rng(0)
        a = 2.8
        x = 500.0 * (1.0 - rng.random(5000)) ** (-1.0 / (a - 1.0))
        est, se, n = fs.powerlaw_mle(x, 500.0)
        self.assertLess(abs(est - a), 3 * se + 0.02)
        fit = fs.fit_length_distribution(x, n_boot=60)
        self.assertAlmostEqual(fit["a_cumulative"], fit["a_density"] - 1.0)
        self.assertLess(abs(fit["a_density"] - a), 0.25)
        self.assertLessEqual(fit["a_ci95"][0], fit["a_density"] + 1e-9)
        self.assertGreaterEqual(fit["a_ci95"][1], fit["a_density"] - 1e-9)


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class NearestLargerTests(unittest.TestCase):
    def test_centroid_distance_to_strictly_longer_trace(self):
        import numpy as np
        from gems import faultstats as fs

        L = np.array([10.0, 20.0, 30.0, 40.0])
        cx = np.array([0.0, 3.0, 3.0, 100.0])
        cy = np.array([0.0, 4.0, 0.0, 0.0])
        d = fs.nearest_larger_centroid(L, cx, cy)
        self.assertTrue(np.isnan(d[3]))                          # the longest has no larger neighbour
        self.assertAlmostEqual(d[0], 3.0)                        # nearest longer one is trace 2 at (3, 0)
        self.assertAlmostEqual(d[1], 4.0)                        # trace 2 at distance 4
        self.assertAlmostEqual(d[2], 97.0)                       # only trace 3 is longer

    def test_edge_distance_uses_nearest_pixels(self):
        import numpy as np
        from gems import faultstats as fs

        m = np.zeros((30, 60), bool)
        m[10, 5] = True                         # short (1 px)
        m[10, 20:41] = True                     # long (21 px), nearest pixel is 15 px away
        tr = fs.extract_traces(m)
        d = fs.nearest_larger_edge(tr)
        short = int(np.argmin(tr.length_m))
        self.assertAlmostEqual(d[short], 15 * 100.0)

    def test_density_exponent_is_the_right_reading_of_bour_davy(self):
        import numpy as np
        from gems import faultstats as fs

        for a, D in ((2.6, 1.5), (3.0, 1.8)):
            r = [fs.bour_davy_check(n=3500, a_density=a, D=D, seed=s) for s in range(2)]
            lo = np.mean([q["x_geometric_mean"] for q in r])
            hi = np.mean([q["x_measured"] for q in r])
            pred = (a - 1.0) / D
            wrong = (a - 2.0) / D
            self.assertLessEqual(lo - 0.12, pred)
            self.assertGreaterEqual(hi + 0.12, pred)
            self.assertGreater(lo - wrong, 0.15, "a cumulative-exponent reading would be rejected by the data")


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class CorrelationTests(unittest.TestCase):
    def test_correlation_dimension_of_line_and_plane(self):
        import numpy as np
        from gems import faultstats as fs

        rng = np.random.default_rng(1)
        line = np.column_stack([rng.random(6000) * 200000.0, np.zeros(6000)])
        plane = rng.random((6000, 2)) * 200000.0
        r = np.array([500, 1000, 2000, 4000, 8000.0])
        self.assertAlmostEqual(fs.correlation_dimension(line, r)["D"], 1.0, delta=0.15)
        self.assertAlmostEqual(fs.correlation_dimension(plane, r)["D"], 2.0, delta=0.15)

    def test_ncc_2d_is_one_for_poisson_and_large_for_clusters(self):
        import numpy as np
        from gems import faultstats as fs

        yy, xx = np.mgrid[:300, :300]
        foot = (yy - 150) ** 2 + (xx - 150) ** 2 < 140 ** 2
        rng = np.random.default_rng(2)
        r = np.array([500, 1000, 2000, 4000.0])
        poisson = fs.sample_in_mask(foot, 1500, rng)
        ncc = fs.ncc_2d(poisson, foot, r, n_null=30, seed=0)
        s = np.array(ncc["sum_ratio"])
        self.assertTrue(np.all(np.abs(s - 1.0) < 0.2), s)
        centres = fs.sample_in_mask(foot, 60, rng)
        clustered = np.vstack([c + rng.normal(0, 400.0, (25, 2)) for c in centres])
        s2 = np.array(fs.ncc_2d(clustered, foot, r, n_null=30, seed=0)["sum_ratio"])
        self.assertGreater(s2[0], 2.0)
        self.assertGreater(s2[0], s2[-1])                       # clustering decays with scale

    def test_scanline_ncc_detects_regular_spacing_and_clusters(self):
        import numpy as np
        from gems import faultstats as fs

        lags = np.array([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5])
        regular = np.zeros((20, 300), bool)
        regular[:, ::6] = True                                   # perfectly periodic
        r = fs.ncc_scanline(regular, 1, lags)
        ncc = np.array(r["ncc"])
        self.assertGreater(ncc[5], 3.0)                          # lag 6 over-represented
        self.assertLess(ncc[2], 0.2)                             # lag 3 absent (anti-clustered)
        rng = np.random.default_rng(3)
        rand = rng.random((200, 300)) < 0.05
        ncc_r = np.array(fs.ncc_scanline(rand, 1, np.array([0.5, 2.5, 5.5, 10.5, 20.5]))["ncc"])
        self.assertTrue(np.all(np.abs(ncc_r - 1.0) < 0.25), ncc_r)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAS_GEO, "NumPy/SciPy are not installed")
class FootprintAndWedgeTests(unittest.TestCase):
    def test_scanline_expectation_uses_the_footprint_span(self):
        import numpy as np
        from gems import faultstats as fs

        lags = np.array([0.5, 5.5, 20.5, 60.5])
        rng = np.random.default_rng(4)
        H, W = 300, 1000
        foot = np.zeros((H, W), bool)
        foot[:, 400:520] = True                                    # lines cross only 120 px of a 1000-px raster
        mask = (rng.random((H, W)) < 0.10) & foot                  # random points inside the footprint
        with_fp = np.array(fs.ncc_scanline(mask, 1, lags, footprint=foot)["ncc"])
        without = np.array(fs.ncc_scanline(mask, 1, lags)["ncc"])
        self.assertTrue(np.all(np.abs(with_fp[:3] - 1.0) < 0.12), with_fp)     # random inside the footprint -> NCC ~ 1
        self.assertGreater(without[2], 1.5)                        # the full-width null over-states clustering

    def test_endpoints_and_wedge_enrichment_around_a_tip(self):
        import numpy as np
        from gems import clusterprior as cp
        from gems import faultstats as fs

        H, W = 400, 400
        m = np.zeros((H, W), bool)
        m[200:260, 200] = True                                      # vertical long trace, rows 200..259
        tr = fs.extract_traces(m)
        rows, cols, ur, uc, tid = cp.trace_endpoints(tr.labels, tr.ids)
        self.assertEqual(len(rows), 2)
        up = int(np.argmin(rows))
        self.assertAlmostEqual(ur[up], -1.0, places=6)              # the northern tip points north (row decreasing)
        self.assertAlmostEqual(uc[up], 0.0, places=6)
        rng = np.random.default_rng(5)
        target = np.zeros((H, W), bool)
        cont = np.zeros((H, W), bool)
        cont[140:198, 196:205] = True                               # strip 3-60 px north of the tip, +-4 px wide: the continuation wedge
        target[cont] = rng.random(int(cont.sum())) < 0.30
        target |= (rng.random((H, W)) < 0.05) & ~m                  # background elsewhere
        el = ~m
        res = cp.tip_wedge_profile(tr.labels, tr.ids, target, el, edges_m=(300, 800, 1500, 3000), n_boot=20)
        E = np.array(res["enrichment"])
        self.assertGreater(E[0][0], 3.0 * E[2][0] + 0.5)            # continuation >> lateral in the first band
        self.assertGreater(res["continuation_over_lateral"], 1.5)
        zone = cp.wedge_union_mask(tr.labels, tr.ids, (0.0, 25.0), (300.0, 1000.0))
        self.assertTrue(zone[150:195, 198:203].any())
        self.assertFalse(zone[200:260, 200].any())                  # the trace itself is never in its own wedge
