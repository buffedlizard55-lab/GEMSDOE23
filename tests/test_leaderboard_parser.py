import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_leaderboard", ROOT / "scripts/update_leaderboard.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LeaderboardParserTests(unittest.TestCase):
    def test_parses_official_style_table_rows(self):
        html = """
        <table>
          <tr><th>Rank</th><th>Team members</th><th>Participant</th><th>Best public DW-Tversky (in descending order)</th><th>Shared work</th></tr>
          <tr><td>#1</td><td></td><td><a href='/users/DARD/'>DARD</a><br>4d ago · 11 submissions</td><td>0.3168</td><td></td></tr>
          <tr><td>#2</td><td></td><td><a href='/users/alexoktaba/'>alexoktaba</a><br>1d ago · 18 submissions</td><td>0.3042</td><td></td></tr>
        </table>
        """
        parsed = MODULE.parse_leaderboard(html, "https://example.test/leaderboard")
        self.assertEqual(parsed["rows"][0]["rank"], 1)
        self.assertEqual(parsed["rows"][0]["participant"], "DARD")
        self.assertAlmostEqual(parsed["rows"][0]["score"], 0.3168)
        self.assertEqual(parsed["rows"][1]["participant"], "alexoktaba")

    def test_fails_closed_on_unrecognized_page(self):
        with self.assertRaises(ValueError):
            MODULE.parse_leaderboard("<html><body>sign in</body></html>")


if __name__ == "__main__":
    unittest.main()
