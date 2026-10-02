"""scripts/record_score.py: locate the uploaded file by SHA-256 prefix and log the score as a refit anchor."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("record_score", ROOT / "scripts" / "record_score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RecordScoreTests(unittest.TestCase):
    def test_file_is_found_by_hash_prefix_and_log_is_idempotent_per_id(self):
        rs = _load()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "docs" / "downloads").mkdir(parents=True)
            (root / "docs" / "data").mkdir(parents=True)
            payload = b"II*\x00fake raster bytes"
            f = root / "docs" / "downloads" / "demo-nan.tif"
            f.write_bytes(payload)
            full = hashlib.sha256(payload).hexdigest()
            rel, got = rs.find_file(full[:8], str(root))
            self.assertEqual(Path(rel), Path("docs/downloads/demo-nan.tif"))
            self.assertEqual(got, full)
            self.assertEqual(rs.find_file("deadbeef", str(root)), (None, None))
            # the manifest and candidates indexes resolve to the same file without double counting
            (root / "docs" / "data" / "submission-manifest.json").write_text(json.dumps(dict(primary=dict(sha256=full, href="downloads/demo-nan.tif"))))
            (root / "docs" / "data" / "candidates.json").write_text(json.dumps(dict(candidates=[dict(nan=dict(sha256=full, href="downloads/demo-nan.tif"))])))
            self.assertEqual(rs.find_file(full[:10], str(root))[1], full)
            log = root / "docs" / "data" / "score-log.json"
            e1 = dict(recorded_utc="2026-10-02T00:00:00Z", content_id=full[:8], name="demo", public_dti=0.10, file=rel, family="x", sha256=full)
            rs.add_entry(str(log), e1)
            rs.add_entry(str(log), dict(e1, public_dti=0.12, recorded_utc="2026-10-03T00:00:00Z"))
            entries = json.loads(log.read_text(encoding="utf-8"))["entries"]
            self.assertEqual(len(entries), 1)                       # re-recording the same file replaces the entry
            self.assertAlmostEqual(entries[0]["public_dti"], 0.12)

    def test_ambiguous_prefix_is_refused(self):
        rs = _load()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "docs" / "downloads").mkdir(parents=True)
            seen = {}
            i = 0
            while True:                                             # two files whose hashes share a one-character prefix
                data = f"file-{i}".encode()
                h = hashlib.sha256(data).hexdigest()
                if h[0] in seen:
                    (root / "docs" / "downloads" / "a.tif").write_bytes(seen[h[0]])
                    (root / "docs" / "downloads" / "b.tif").write_bytes(data)
                    prefix = h[0]
                    break
                seen[h[0]] = data
                i += 1
            with self.assertRaises(SystemExit):
                rs.find_file(prefix, str(root))


if __name__ == "__main__":
    unittest.main()
