import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StaticSiteTests(unittest.TestCase):
    def test_all_local_site_links_resolve(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_site.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_top_of_page_tif_download_on_docs_and_root_pages(self):
        manifest = json.loads((ROOT / "docs" / "data" / "submission-manifest.json").read_text(encoding="utf-8"))
        primary_name = manifest["primary"]["name"]
        comp_name = manifest["compatibility"]["name"]
        self.assertTrue((ROOT / "docs" / "downloads" / primary_name).exists())
        self.assertTrue((ROOT / "docs" / "downloads" / comp_name).exists())

        for page_path, dl_prefix in (
            (ROOT / "docs" / "index.html", "downloads/"),
            (ROOT / "index.html", "docs/downloads/"),
            (ROOT / "docs" / "executive-summary.html", "downloads/"),
            (ROOT / "executive-summary.html", "docs/downloads/"),
        ):
            text = page_path.read_text(encoding="utf-8")
            self.assertIn("header-download-bar", text)
            self.assertIn(f'href="{dl_prefix}{primary_name}" download', text)
            self.assertIn(f'href="{dl_prefix}{comp_name}" download', text)
            dl_pos = text.find('id="download"')
            hero_pos = text.find('<section class="hero">')
            self.assertGreater(dl_pos, 0, f"missing #download in {page_path}")
            self.assertGreater(hero_pos, 0, f"missing .hero in {page_path}")
            self.assertLess(dl_pos, hero_pos, f"#download must appear BEFORE .hero in {page_path}")
            self.assertIn('id="submission-filename"', text)
            self.assertIn('id="submission-note"', text)

        forbidden = (
            "missing from this checkout",
            "could not be re-run in this checkout",
            "not re-run here",
            "exact sample-template comparison unavailable",
            "no fresh Phase 2 ensemble maps or coverage mask were reproduced",
        )
        for html_file in list((ROOT / "docs").glob("*.html")) + list(ROOT.glob("*.html")):
            body = html_file.read_text(encoding="utf-8")
            for phrase in forbidden:
                self.assertNotIn(phrase, body, f"stale contradictory phrase {phrase!r} found in {html_file}")


if __name__ == "__main__":
    unittest.main()
