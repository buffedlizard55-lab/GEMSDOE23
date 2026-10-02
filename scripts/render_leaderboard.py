#!/usr/bin/env python3
"""Render the client-side leaderboard table and save the resulting HTML.

Why this exists: `https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/`
returns a 30 KB page shell in which the board is built by JavaScript. A plain HTTP GET - which is
all `scripts/update_leaderboard.py` can do with the standard library - receives
`tables: 0, rows: 0, user_links: 0, loading_placeholder: true` (measured from a GitHub Actions
runner on 2026-10-02 and recorded in `docs/data/leaderboard-status.json`). DrivenData exposes no
anonymous JSON endpoint for the board: `/api/competitions/306/leaderboard/` answers 404 with
"please make sure that you are signed in and signed up for that competition", and signed-in
endpoints are out of scope for this repository (no credential use, no bypassing access controls).

So the only dependency-free way to see the same public page a visitor sees is to execute its
public JavaScript. This script does that with Playwright/Chromium when Playwright is installed and
writes the *rendered* HTML to a file, which `update_leaderboard.py --from-file` then parses and
validates exactly as it would a server-rendered page. Rendering is a thin, replaceable front end;
the parser stays the single authority on what counts as a leaderboard.

Usage:
    python scripts/render_leaderboard.py --output /tmp/leaderboard.html
    python scripts/update_leaderboard.py --render        # plain GET first, then this if needed

Exits 3 with an actionable message when Playwright is unavailable, so callers can degrade to the
plain-HTTP path instead of crashing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_URL = "https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/"
# The board shows 50 rows; require a clear majority before trusting that rendering finished.
DEFAULT_MIN_ROWS = 25
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
PLAYWRIGHT_HINT = (
    "Playwright is not installed. Install it with:\n"
    "    pip install playwright && playwright install --with-deps chromium\n"
    "or run scripts/update_leaderboard.py without --render to use the plain-HTTP path "
    "(which cannot see the client-rendered table)."
)


def render(url: str, timeout_ms: int, min_rows: int) -> str:
    """Load the page in headless Chromium and return the HTML after the board has rendered."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(3)

    with sync_playwright() as driver:
        browser = driver.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Wait for the table to exist, then for it to be populated; the shell contains a
            # "Loading..." placeholder that would otherwise be captured.
            page.wait_for_selector("table tr", timeout=timeout_ms)
            page.wait_for_function(
                "document.querySelectorAll('table tr').length >= %d" % min_rows,
                timeout=timeout_ms,
            )
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--min-rows", type=int, default=DEFAULT_MIN_ROWS)
    args = parser.parse_args()

    try:
        html = render(args.url, args.timeout_ms, args.min_rows)
    except SystemExit as error:
        if error.code == 3:
            print(PLAYWRIGHT_HINT, file=sys.stderr)
            return 3
        raise
    except Exception as error:  # rendering is best effort; report and let the caller degrade
        print("render failed: %s: %s" % (type(error).__name__, error), file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print("rendered %d bytes of HTML to %s" % (len(html), args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
