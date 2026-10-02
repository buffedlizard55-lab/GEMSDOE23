"""Offline tests of the H-40 ComCat fetcher's fail-closed contract.

The sandbox has no egress to earthquake.usgs.gov, so the real fetch runs in CI
(`.github/workflows/seismicity.yml`).  What CAN be verified offline is that the
script's parsing and validation gates behave exactly as documented:

  * a valid FDSN text response is written verbatim with sha256-pinned metadata;
  * a response that does not start with the FDSN header is rejected (exit 1);
  * any row without a magnitude is rejected;
  * an event count below the floor refuses to overwrite the existing snapshot;
  * the request URL carries the exact unbuffered AOI box and M >= 2.5.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fetch_seismicity.py"

VALID_HEADER = ("#EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|"
                "ContributorID|MagType|Magnitude|MagAuthor|EventLocationName")
VALID_ROW = "nn12345678|2020-01-01T00:00:00.000Z|38.5000|-118.1000|8.2|US|ComCat|US|700|ml|3.10|US|NEVADA"


def _load():
    spec = importlib.util.spec_from_file_location("fetch_seismicity", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResponse:
    def __init__(self, text: str):
        self._text = text.encode("utf-8")

    def read(self) -> bytes:
        return self._text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FetchSeismicityTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "seismicity"
        self.addCleanup(self.tmp.cleanup)

    def _run(self, text: str, min_events: int = 2):
        with mock.patch.object(self.mod.urllib.request, "urlopen",
                               return_value=_FakeResponse(text)) as urlopen:
            with mock.patch.object(sys, "argv", ["fetch_seismicity.py",
                                                 "--out", str(self.out),
                                                 "--min-events", str(min_events),
                                                 "--endtime", "2026-10-02T00:00"]):
                rc = self.mod.main()
        self.assertEqual(rc, 0 if rc == 0 else 1)
        return rc, urlopen.call_args[0][0].full_url

    def test_valid_response_written_verbatim_with_pinned_metadata(self):
        text = "\n".join([VALID_HEADER] + [VALID_ROW] * 3) + "\n"
        rc, url = self._run(text, min_events=3)
        self.assertEqual(rc, 0)
        data = (self.out / "comcat_m25_aoi.txt").read_text()
        self.assertEqual(data, text)
        meta = json.loads((self.out / "comcat-meta.json").read_text())
        self.assertEqual(meta["event_count"], 3)
        self.assertEqual(meta["min_magnitude"], 2.5)
        self.assertEqual(meta["starttime"], self.mod.STARTTIME)
        import hashlib
        self.assertEqual(meta["sha256"], hashlib.sha256(data.encode()).hexdigest())
        self.assertEqual(meta["bytes"], len(data.encode()))

    def test_request_url_carries_exact_box_and_magnitude_floor(self):
        rc, url = self._run("\n".join([VALID_HEADER] + [VALID_ROW] * 2) + "\n", min_events=2)
        self.assertEqual(rc, 0)
        self.assertIn("minmagnitude=2.5", url)
        self.assertIn(f"minlongitude={self.mod.LON_LO}", url)
        self.assertIn(f"maxlongitude={self.mod.LON_HI}", url)
        self.assertIn(f"minlatitude={self.mod.LAT_LO}", url)
        self.assertIn(f"maxlatitude={self.mod.LAT_HI}", url)
        self.assertIn("format=text", url)
        self.assertIn("eventtype=earthquake", url)

    def test_non_fdsn_header_rejected(self):
        rc, _ = self._run("<html>login page</html>")
        self.assertEqual(rc, 1)
        self.assertFalse(self.out.exists())

    def test_row_without_magnitude_rejected(self):
        bad = VALID_ROW.replace("|3.10|", "||")
        rc, _ = self._run("\n".join([VALID_HEADER, bad]) + "\n", min_events=1)
        self.assertEqual(rc, 1)
        self.assertFalse(self.out.exists())

    def test_below_floor_refuses_and_existing_snapshot_survives(self):
        # first, a valid snapshot exists
        rc, _ = self._run("\n".join([VALID_HEADER] + [VALID_ROW] * 3) + "\n", min_events=3)
        self.assertEqual(rc, 0)
        before = (self.out / "comcat_m25_aoi.txt").read_text()
        # then a fetch that returns fewer events than the floor must not clobber it
        rc, _ = self._run("\n".join([VALID_HEADER] + [VALID_ROW] * 2) + "\n", min_events=3)
        self.assertEqual(rc, 1)
        self.assertEqual((self.out / "comcat_m25_aoi.txt").read_text(), before)


if __name__ == "__main__":
    unittest.main()
