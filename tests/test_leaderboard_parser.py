import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADER_HTML = ("<tr><th>Rank</th><th>Team members</th><th>Participant</th>"
               "<th>Best public DW-Tversky (in descending order)</th><th>Shared work</th></tr>")
LIVE_HEADER_HTML = ("<tr><th>Rank</th><th>Team members</th><th>Participant</th><th>Best<br> <br>public<br> <br>"
                    "<br>DW-Tversky<br> <br>(in descending order)</th><th>Shared work</th></tr>")


def ROW_HTML(rank, name, slug, score):
    """One row shaped like the official page: avatar link, name link, <br> metadata, score cell."""
    return ("<tr><td>#%d</td>"
            "<td><a href='https://www.drivendata.org/users/%s/'><img src='g.jpg?s=64' alt=''></a></td>"
            "<td><a href='https://www.drivendata.org/users/%s/'>%s</a><br>2d 9h ago<br> <br>&#183;<br>"
            "19 submissions</td><td>%.4f</td><td></td></tr>") % (rank, slug, slug, name, score)


ROWS = 12
_BODY = [(1, "DARD", "dard", 0.3195), (2, "alexoktaba", "alexoktaba", 0.3042),
         (3, "Batik Shirt Brothers", "rariwa", 0.2998), (4, "joeyfezster", "joeyfezster", 0.2919),
         (5, "xiaofanhu", "xiaofanhu", 0.2901), (6, "mzoorob", "mzoorob", 0.2862),
         (7, "HardcoreTechGod", "hardcoretechgod", 0.2854), (8, "GrigorSargsyan", "grigorsargsyan", 0.2742),
         (9, "op01", "op01", 0.2710), (10, "kinghorton42", "kinghorton42", 0.2635),
         (11, "user_1 team", "user_1", 0.2627), (12, "dmitry_v", "dmitry_v", 0.2013)]
BODY_HTML = "".join(ROW_HTML(*row) for row in _BODY)
TABLE_HTML = "<table>%s%s</table>" % (HEADER_HTML, BODY_HTML)

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
        parsed = MODULE.parse_leaderboard(html, "https://example.test/leaderboard", min_rows=2)
        self.assertEqual(parsed["rows"][0]["rank"], 1)
        self.assertEqual(parsed["rows"][0]["participant"], "DARD")
        self.assertAlmostEqual(parsed["rows"][0]["score"], 0.3168)
        self.assertEqual(parsed["rows"][1]["participant"], "alexoktaba")
        self.assertIn("SHA-256", parsed["attribution_caveat"])
        self.assertIn("Phase 1", parsed["phase_caveat"])
        self.assertIn("Phase 2", parsed["phase_caveat"])

    def test_parses_a_table_nested_inside_a_layout_table(self):
        """The depth-1-only collector used to see the wrapper and report 'no leaderboard table'."""
        html = "<table><tr><td><div class='lb'>%s</div></td></tr></table>" % TABLE_HTML
        parsed = MODULE.parse_leaderboard(html)
        self.assertEqual(len(parsed["rows"]), ROWS)
        self.assertEqual(parsed["rows"][0]["participant"], "DARD")

    def test_parses_live_header_spelling_split_by_breaks(self):
        html = "<table>%s%s</table>" % (LIVE_HEADER_HTML, BODY_HTML)
        parsed = MODULE.parse_leaderboard(html)
        self.assertEqual(parsed["rows"][0]["score"], 0.3195)
        self.assertEqual(len(parsed["rows"]), ROWS)
        self.assertIn("DW-Tversky", LIVE_HEADER_HTML)

    def test_falls_back_to_a_row_scan_when_the_header_is_unrecognisable(self):
        html = "<table><tr><th>Place</th><th>Who</th><th>Value</th></tr>%s</table>" % BODY_HTML
        parsed = MODULE.parse_leaderboard(html)
        self.assertEqual(len(parsed["rows"]), ROWS)
        self.assertIn("fallback", parsed["parse_strategy"])

    def test_prefers_the_displayed_team_name_over_the_profile_slug(self):
        """The board shows "Batik Shirt Brothers" at /users/rariwa/ - the slug must never leak through."""
        html = "<table>%s<tr><td>#13</td><td><a href='/users/rariwa/'><img src='g.jpg' alt=''></a>" \
               "<a href='/users/masterozone0617/'><img src='h.jpg' alt=''></a></td>" \
               "<td>Batik Shirt Brothers<br>1d 7h ago<br> <br>&#183;<br>17 submissions</td>" \
               "<td>0.2998</td><td></td></tr>%s</table>" % (HEADER_HTML, BODY_HTML)
        parsed = MODULE.parse_leaderboard(html)
        row = next(r for r in parsed["rows"] if r["rank"] == 13)
        self.assertEqual(row["participant"], "Batik Shirt Brothers")
        self.assertNotIn("rariwa", json.dumps(parsed["rows"]))

    def test_collapses_a_board_rendered_twice_but_rejects_conflicting_duplicates(self):
        html = "<table>%s%s%s</table>" % (HEADER_HTML, BODY_HTML, BODY_HTML)
        parsed = MODULE.parse_leaderboard(html)
        self.assertEqual(len(parsed["rows"]), ROWS)

        other = BODY_HTML.replace("0.3195", "0.9999")
        with self.assertRaises(ValueError):
            MODULE.parse_leaderboard("<table>%s%s%s</table>" % (HEADER_HTML, BODY_HTML, other))

    def test_fallback_does_not_read_a_score_out_of_a_team_name(self):
        """`user_1 ... 19 submissions` must not become a score of 1.0."""
        html = "<table>%s</table>" % BODY_HTML
        parsed = MODULE.parse_leaderboard(html)
        self.assertTrue(all(row["score"] < 1.0 for row in parsed["rows"]))
        self.assertEqual(parsed["rows"][0]["score"], 0.3195)

    def test_rejects_a_board_that_is_too_short(self):
        html = "<table>%s%s</table>" % (HEADER_HTML, ROW_HTML(1, "DARD", "dard", 0.3195))
        with self.assertRaises(ValueError):
            MODULE.parse_leaderboard(html)

    def test_fails_closed_on_unrecognized_page(self):
        with self.assertRaises(ValueError):
            MODULE.parse_leaderboard("<html><body>sign in</body></html>")

    def test_attribution_caveat_is_computed_from_the_rows_not_hard_coded(self):
        rows = [{"rank": 26, "participant": "smrtdoog5", "score": 0.1922}]
        caveat = MODULE.build_attribution_caveat(rows)
        self.assertIn("rank 26 (smrtdoog5)", caveat)
        self.assertIn("H19-4 (0.1894) is not on the currently displayed rows", caveat)
        self.assertEqual(caveat.count("not artifact, account, or team attribution"), 1)

    def test_diagnostics_explain_a_page_without_a_board(self):
        diag = MODULE._diagnostics("<html><head><title>Just a moment...</title></head>"
                                   "<body><p>Enable JavaScript and reload.</p></body></html>")
        self.assertIn("moment", diag["title"])
        self.assertEqual(diag["tables"], 0)
        self.assertEqual(diag["user_links"], 0)
        self.assertIn("JavaScript", diag["text_excerpt"])


class RenderFallbackTests(unittest.TestCase):
    """--render must recover the board when a plain GET returns only the JavaScript shell."""

    STUB = '''import sys, pathlib
out = pathlib.Path(sys.argv[sys.argv.index("--output") + 1])
rows = "".join(
    "<tr><td>#%d</td><td><a href='/users/u%d/'><img src='g' alt=''></a></td>"
    "<td><a href='/users/u%d/'>Team %d</a><br>2d ago</td><td>0.%04d</td></tr>"
    % (i, i, i, i, 4000 - 7 * i) for i in range(1, 13))
out.write_text("<table><tr><th>Rank</th><th>Team members</th><th>Participant</th>"
               "<th>Best public DW-Tversky</th></tr>" + rows + "</table>", encoding="utf-8")
'''

    def _run(self, tmp, stub_body, extra_args=()):
        stub = tmp / "stub_render.py"
        stub.write_text(stub_body, encoding="utf-8")
        output, status = tmp / "lb.json", tmp / "st.json"
        argv = ["update_leaderboard.py", "--url", "http://127.0.0.1:1/unreachable", "--timeout", "3",
                "--output", str(output), "--status", str(status), *extra_args]
        previous_script, previous_argv = MODULE.RENDER_SCRIPT, sys.argv
        MODULE.RENDER_SCRIPT = stub
        sys.argv = argv
        try:
            code = MODULE.main()
        finally:
            MODULE.RENDER_SCRIPT, sys.argv = previous_script, previous_argv
        return code, output, status

    def test_render_path_publishes_a_live_board(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            code, output, status = self._run(tmp, self.STUB, ("--render", "--strict"))
            self.assertEqual(code, 0)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["source_status"], "live")
            self.assertEqual(written["capture_path"], "headless-render")
            self.assertEqual(len(written["rows"]), ROWS)
            self.assertEqual(written["rows"][0]["participant"], "Team 1")
            self.assertIn("headless Chromium", written["capture_method"])
            sidecar = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual(sidecar["status"], "live")
            self.assertEqual(sidecar["diagnostics"]["render"]["returncode"], 0)

    def test_a_renderer_without_a_browser_degrades_instead_of_crashing(self):
        """Playwright missing -> renderer exits 3 -> snapshot retained, diagnostics recorded."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            (tmp / "lb.json").write_text(json.dumps({
                "rows": [{"rank": 1, "participant": "Kept", "score": 0.5}],
                "retrieved_utc": "2026-10-02T00:00:00+00:00",
            }), encoding="utf-8")
            code, output, status = self._run(tmp, "import sys; sys.exit(3)", ("--render",))
            self.assertEqual(code, 0)  # publication must survive a missing browser
            retained = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(retained["rows"][0]["participant"], "Kept")
            self.assertEqual(retained["source_status"], "snapshot")
            sidecar = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual(sidecar["status"], "stale-snapshot-retained")
            self.assertTrue(sidecar["render_attempted"])
            self.assertEqual(sidecar["diagnostics"]["render"]["returncode"], 3)

    def test_strict_mode_still_fails_when_nothing_can_be_parsed(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            code, _output, _status = self._run(tmp, "import sys; sys.exit(3)", ("--render", "--strict"))
            self.assertEqual(code, 1)

    def test_renderer_reports_a_missing_browser_with_an_actionable_exit_code(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/render_leaderboard.py"), "--output", "/tmp/x.html"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertIn(result.returncode, (0, 3))  # 3 here (no Playwright), 0 where it is installed
        if result.returncode == 3:
            self.assertIn("playwright install", result.stderr)


if __name__ == "__main__":
    unittest.main()
