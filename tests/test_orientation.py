"""Unit tests for the H-38 / H-39 orientation and residual transforms (synthetic)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import numpy as np
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


@unittest.skipUnless(HAVE_SCIPY, "scipy not installed")
class StructureTensorTests(unittest.TestCase):
    def test_recovers_lineament_azimuth_and_coherence(self):
        from gems.orientation import structure_tensor

        rng = np.random.default_rng(0)
        n = 256
        yy, xx = np.mgrid[0:n, 0:n].astype(float)
        # a valley trending at 30 degrees from north (image +x east, +y south):
        # lineament direction unit vector in (x, y): (sin30, cos30)... use d = x*cos(a) + y*sin(a)
        a = np.radians(30.0)
        d = xx * np.cos(a) + yy * np.sin(a)
        f = np.clip(1.0 - np.abs(np.mod(d, 40.0) - 20.0) / 6.0, 0, 1)  # parallel ridges
        f += 0.01 * rng.standard_normal(f.shape)
        theta, coh = structure_tensor(f, sigma_px=4.0)
        # sample where coherence is high
        m = coh > np.quantile(coh, 0.99)
        az = np.median(theta[m])
        # azimuth measured clockwise from north; lineament at 30 deg should be recovered
        # modulo the (0,180) wrapping, within a few degrees
        diff = min(abs(az - 30.0), abs(az - 30.0 - 180.0), abs(az - 30.0 + 180.0))
        self.assertLess(diff, 5.0, f"recovered azimuth {az} not within 5 deg of 30")
        self.assertGreater(np.median(coh[m]), 0.5)

    def test_isotropic_noise_has_low_coherence(self):
        from gems.orientation import structure_tensor

        rng = np.random.default_rng(1)
        f = rng.standard_normal((128, 128))
        _, coh = structure_tensor(f, sigma_px=2.0)
        self.assertLess(float(np.mean(coh)), 0.35)


@unittest.skipUnless(HAVE_SCIPY, "scipy not installed")
class AgreementTests(unittest.TestCase):
    def test_aligned_parallel_high_perpendicular_zero(self):
        from gems.orientation import azimuth_agreement

        t = np.zeros((4, 4), np.float32)
        c = np.ones((4, 4), np.float32)
        self.assertGreater(float(azimuth_agreement(t, c, t, c)[0, 0]), 0.99)
        t90 = t + 90.0
        self.assertLess(float(azimuth_agreement(t, c, t90, c)[0, 0]), 0.01)

    def test_180_degree_periodicity(self):
        from gems.orientation import azimuth_agreement

        a = np.full((2, 2), 5.0, np.float32)
        b = np.full((2, 2), 185.0, np.float32)     # same lineament, wrapped
        c = np.ones((2, 2), np.float32)
        self.assertGreater(float(azimuth_agreement(a, c, b, c)[0, 0]), 0.99)

    def test_coherence_floor_gates_weak_families(self):
        from gems.orientation import azimuth_agreement

        t = np.zeros((2, 2), np.float32)
        weak = np.full((2, 2), 0.05, np.float32)
        strong = np.ones((2, 2), np.float32)
        self.assertEqual(float(azimuth_agreement(t, weak, t, strong)[0, 0]), 0.0)


@unittest.skipUnless(HAVE_SCIPY, "scipy not installed")
class UpwardContinuationTests(unittest.TestCase):
    def test_short_wavelength_attenuated_more_than_long(self):
        from gems.orientation import upward_continuation

        n = 512
        x = np.arange(n)
        short = np.sin(2 * np.pi * x / 8.0)[None, :].repeat(n, 0)      # 800 m wavelength
        long_ = np.sin(2 * np.pi * x / 200.0)[None, :].repeat(n, 0)    # 20 km wavelength
        # attenuation of wavelength L at continuation height h is exp(-2 pi h / L):
        # 800 m at 2 km -> exp(-15.7) ~ 0; 20 km at 2 km -> exp(-0.63) ~ 0.54
        s = upward_continuation(short, 2000.0)[100:-100, 100:-100]
        l = upward_continuation(long_, 2000.0)[100:-100, 100:-100]
        amp_s = float(np.max(np.abs(s)))
        amp_l = float(np.max(np.abs(l)))
        self.assertLess(amp_s, 0.05, "800 m wavelength must be essentially removed at 2 km height")
        self.assertGreater(amp_l, 0.40, "20 km wavelength must mostly survive 2 km continuation")
        self.assertLess(amp_l, 0.70, "20 km wavelength must still be attenuated (~0.54 expected)")

    def test_residual_keeps_the_shallow_anomaly(self):
        from gems.orientation import residual_edges, upward_continuation

        n = 512
        yy, xx = np.mgrid[0:n, 0:n].astype(float)
        long_ = np.sin(2 * np.pi * xx / 300.0) * 5.0
        blob = 5.0 * np.exp(-(((xx - 256) ** 2 + (yy - 256) ** 2) / (2 * 6.0 ** 2)))
        f = long_ + blob
        res = f - upward_continuation(f, 500.0)
        # the shallow blob dominates the residual; the regional is nearly gone
        peak = float(np.max(np.abs(res)))
        at_blob = float(np.abs(res[256, 256]))
        far = float(np.abs(res[50, 50]))
        self.assertGreater(at_blob, 0.5 * peak)
        self.assertLess(far, 0.35 * peak)
        e = residual_edges(f, 500.0)
        # the edge layer must peak near the blob, not on the regional
        self.assertGreater(float(e[256, 256]) + float(e[256, 262]),
                           float(e[50, 50]) + float(e[50, 56]))


if __name__ == "__main__":
    unittest.main()
