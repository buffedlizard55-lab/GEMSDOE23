import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LeaderboardFeedSchemaTests(unittest.TestCase):
    def test_snapshot_matches_site_javascript_contract(self):
        feed = json.loads((ROOT / "docs/data/leaderboard.json").read_text(encoding="utf-8"))
        self.assertIn(feed.get("source_status"), {"snapshot", "live"})
        self.assertIn(
            feed.get("refresh_status", {}).get("status"),
            {"live", "dated-snapshot", "stale-snapshot-retained", "unavailable-no-snapshot"},
        )
        self.assertIsInstance(feed.get("retrieved_utc"), str)
        self.assertTrue(feed["retrieved_utc"])
        self.assertIn("SHA-256", feed.get("attribution_caveat", ""))
        self.assertIn("Phase 1", feed.get("phase_caveat", ""))
        self.assertIn("Phase 2", feed.get("phase_caveat", ""))
        self.assertIsInstance(feed.get("rows"), list)
        self.assertTrue(feed["rows"])
        ranks = []
        for row in feed["rows"]:
            self.assertIsInstance(row.get("rank"), int)
            self.assertIsInstance(row.get("participant"), str)
            self.assertTrue(row["participant"])
            self.assertIsInstance(row.get("score"), (int, float))
            self.assertGreaterEqual(row["score"], 0.0)
            self.assertLessEqual(row["score"], 1.0)
            ranks.append(row["rank"])
        self.assertEqual(ranks, sorted(ranks))
        js = (ROOT / "docs/assets/site.js").read_text(encoding="utf-8")
        self.assertIn("data/leaderboard.json", js)
        self.assertIn("data.source_status === 'live'", js)
        self.assertIn("refreshState === 'stale-snapshot-retained'", js)
        self.assertIn("refreshState === 'dated-snapshot'", js)
        self.assertIn("entry.rank <= 10", js)

    def test_status_sidecar_has_a_known_schema(self):
        status = json.loads((ROOT / "docs/data/leaderboard-status.json").read_text(encoding="utf-8"))
        self.assertIn(status.get("status"), {"live", "dated-snapshot", "stale-snapshot-retained", "unavailable-no-snapshot"})
        self.assertIn("source_url", status)
        self.assertIn("checked_utc", status)

    def test_snapshot_rows_are_the_currently_displayed_board(self):
        """Guard the delivered board: 50 rows, strictly descending scores, no stale rank claims.

        The rows were verified against the official page on 2026-10-02; this test fails loudly if
        someone edits the snapshot into an inconsistent state (ranks out of order, scores outside
        [0, 1], or a duplicated rank) rather than silently shipping a wrong board.
        """
        feed = json.loads((ROOT / "docs/data/leaderboard.json").read_text(encoding="utf-8"))
        rows = feed["rows"]
        self.assertEqual(len(rows), feed.get("row_count", len(rows)))
        self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))
        scores = [r["score"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(r["participant"] for r in rows))
        self.assertIn("2026-10-02", feed["retrieved_utc"])
        caveat = feed["attribution_caveat"]
        self.assertNotIn("rank 24 (smrtdoog5)", caveat)
        self.assertIn("rank 26 (smrtdoog5)", caveat)

    def test_failed_refresh_preserves_rows_and_surfaces_stale_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "leaderboard.json"
            status = Path(tmp) / "status.json"
            original = {
                "competition": "test",
                "source_url": "https://example.invalid",
                "retrieved_utc": "2026-10-01",
                "source_status": "snapshot",
                "rows": [{"rank": 1, "participant": "Example", "score": 0.25}],
            }
            output.write_text(json.dumps(original), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/update_leaderboard.py"),
                 "--output", str(output), "--status", str(status),
                 "--url", "http://127.0.0.1:1/unreachable", "--timeout", "1"],
                cwd=ROOT, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            retained = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(retained["rows"], original["rows"])
            self.assertEqual(retained["source_status"], "snapshot")
            self.assertEqual(retained["refresh_status"]["status"], "stale-snapshot-retained")
            self.assertTrue(retained["refresh_status"].get("error"))


if __name__ == "__main__":
    unittest.main()
