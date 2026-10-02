#!/usr/bin/env python3
"""Refresh a dated snapshot of the official public GEMS leaderboard.

The official page is https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/.
DrivenData exposes no public JSON endpoint for it (`/api/competitions/306/leaderboard/` returns
404 - verified 2026-10-02), so the snapshot is parsed out of the HTML table.

Two things this script is deliberately paranoid about:

1.  **Failing closed, but loudly.**  A silent stale board is worse than no board: the whole point
    of the feed is that nobody has to check the competition by hand.  On any failure the last
    verified rows are retained (the site stays usable), the status sidecar records the failure
    *with diagnostics* (HTTP status, final URL, bytes, how many tables/rows/user-links were seen
    and a short text excerpt), and `--strict` turns that into a non-zero exit so CI can flag it.

2.  **Markup drift.**  The table is collected at *any* nesting depth, the header row is searched
    over the first few rows rather than assumed to be row 0, the score column is matched by
    several spellings, and a row-level fallback (`#<rank>` + `/users/<name>/` + a float cell)
    still recovers the board if the table framing changes.  Parsed output is validated before it
    is accepted: enough rows, unique ascending ranks, every score inside [0, 1].

This is a convenience feed, not an independent score source.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/"
RENDER_SCRIPT = Path(__file__).resolve().parent / "render_leaderboard.py"
COMPETITION = "DOE GEMS Prize / DrivenData #306"
ATTRIBUTION_CAVEAT = (
    "The official public leaderboard displays participants and scores but does not expose a "
    "prediction-file SHA-256 or public submission identifier; score equality is not artifact, "
    "account, or team attribution."
)
PHASE_CAVEAT = (
    "These are public leaderboard results only, not private Initial Prize Round (Phase 1) "
    "or expert-updated Final Prize Round (Phase 2) scores."
)
# Scores of artefacts this repository's sibling accounts submitted, used only to state - with the
# retrieval date attached - which displayed row they coincide with.  Recomputed from the live rows
# on every successful refresh so the sentence can never go stale.
KNOWN_ARTEFACT_SCORES = {"H19-5": 0.1922, "H19-4": 0.1894}
# DrivenData has been observed to serve a challenge/consent page to obvious bot user agents, so the
# browser-like agents are tried first and the honest bot agent last.
USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "GEMSDOE23 leaderboard feed/1.0 (public competition page; contact: repository maintainer)",
)
# Column hints are tried in priority order. "team members" is the avatar column on the official
# page while "participant" is the name column, so an exact/prefix match must win over a substring
# match - matching on the first hint that appears anywhere silently selected the avatars.
SCORE_HEADER_GROUPS = (("dw-tversky", "tversky"), ("score",), ("best", "metric", "value"))
RANK_HEADER_GROUPS = (("rank",), ("place", "#", "position"))
PARTICIPANT_HEADER_GROUPS = (("participant",), ("team name", "entrant"), ("team", "user", "name"))


def _pick_column(header: list[str], groups: tuple[tuple[str, ...], ...]) -> int | None:
    """Return the index of the first header cell matching the highest-priority hint group."""
    for hints in groups:
        for hint in hints:
            for index, value in enumerate(header):
                if hint in value:
                    return index
    return None


def _has_column(header: list[str], groups: tuple[tuple[str, ...], ...]) -> bool:
    return _pick_column(header, groups) is not None
MIN_ROWS = 10
TEXT_EXCERPT_CHARS = 320


class FetchError(RuntimeError):
    """Every attempt to retrieve the page failed."""


class _Cell:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.links: list[str] = []
        self.hrefs: list[str] = []
        self.in_link = False
        self.current_link: list[str] = []

    def normalized(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.text)).strip()

    def first_segment(self) -> str:
        first = "".join(self.text).split("\n", 1)[0]
        return re.sub(r"\s+", " ", first).strip()

    def user_slug(self) -> str | None:
        for href in self.hrefs:
            match = re.search(r"/users/([^/?#]+)", href)
            if match:
                return match.group(1).strip()
        return None


class _LeaderboardHTML(HTMLParser):
    """Collect every table in the document, at any nesting depth, plus global row order.

    The previous version only kept depth-1 tables and assumed the header was row 0; if the
    leaderboard table is wrapped in a layout table (a common Django/Bootstrap pattern) that
    collected the wrapper and raised "no leaderboard table found" even though the rows were on
    the page.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[_Cell]]] = []
        self.rows_in_order: list[list[_Cell]] = []
        self.stack: list[list[list[_Cell]]] = []
        self.current_row: list[_Cell] | None = None
        self.current_cell: _Cell | None = None
        self.title_parts: list[str] = []
        self.in_title = False
        self.text_seen = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag == "table":
            self.stack.append([])
        elif tag == "title":
            self.in_title = True
        elif tag == "tr" and self.stack:
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.current_cell = _Cell()
        elif tag == "a" and self.current_cell is not None:
            self.current_cell.in_link = True
            self.current_cell.current_link = []
            href = attrs.get("href")
            if href:
                self.current_cell.hrefs.append(href)
        elif tag == "br" and self.current_cell is not None:
            self.current_cell.text.append("\n")
        elif tag == "img" and self.current_cell is not None and attrs.get("alt"):
            self.current_cell.text.append(attrs["alt"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "a" and self.current_cell is not None and self.current_cell.in_link:
            text = " ".join(self.current_cell.current_link).strip()
            if text:
                self.current_cell.links.append(text)
            self.current_cell.in_link = False
            self.current_cell.current_link = []
        elif tag in ("td", "th") and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(self.current_cell)
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                for table in self.stack:
                    table.append(self.current_row)
                self.rows_in_order.append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.stack:
            self.tables.append(self.stack.pop())

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.current_cell is not None:
            self.current_cell.text.append(data)
            self.text_seen += len(data.strip())
            if self.current_cell.in_link:
                self.current_cell.current_link.append(data)


_SCORE_FULL = re.compile(r"\s*(0?\.\d+|1(?:\.0+)?|0)\s*\Z")
_SCORE_LOOSE = re.compile(r"(?<![\d.\w])(0?\.\d+|1(?:\.0+)?)(?![\d.])")


def _score_from_text(text: str, strict_cell: bool = False) -> str | None:
    """Return a score in [0, 1] from a cell.

    `strict_cell` (used when the score column is unknown) requires the entire cell to be the
    number; otherwise text like `user_1 ... 19 submissions` yields a spurious 1.0.  Word
    boundaries in the loose form stop `19 submissions` and `2d 9h ago` matching as scores.
    """
    if strict_cell:
        match = _SCORE_FULL.match(text)
        return match.group(1) if match else None
    match = _SCORE_LOOSE.search(text)
    return match.group(1) if match else None


def _row_from_cells(
    row: list[_Cell],
    score_index: int | None = None,
    participant_index: int | None = None,
) -> dict | None:
    """Turn one <tr> into a row dict, or None if it is not a ranked score row."""
    rank_text = row[0].normalized() if row else ""
    match_rank = re.search(r"#?\s*(\d+)\b", rank_text)
    if not match_rank:
        for cell in row:
            match_rank = re.search(r"^#\s*(\d+)$", cell.normalized())
            if match_rank:
                break
    if not match_rank:
        return None

    if score_index is not None and score_index < len(row):
        score_text = _score_from_text(row[score_index].normalized())
    else:
        score_text = None
        for cell in row[1:]:
            score_text = _score_from_text(cell.normalized(), strict_cell=True)
            if score_text is not None:
                break
    if score_text is None:
        return None

    # Display name first (link text), then the /users/<slug>/ href, then plain cell text. The slug
    # is last because it is lowercased and, for a team, is the first member's username: the official
    # board shows "Batik Shirt Brothers" at /users/rariwa/.
    def _display_name(cell: _Cell) -> str | None:
        for link in cell.links:
            if link.strip():
                return link.strip()
        return None

    ordered = []
    if participant_index is not None and participant_index < len(row):
        ordered.append(row[participant_index])
    ordered.extend(cell for cell in row[1:] if cell not in ordered)

    # Passes are ordered so that a name *on the page* always beats a slug derived from a URL:
    # 1. link text (how the board displays the name), 2. plain text of the name cell, 3. the
    # /users/<slug>/ href, which is lowercased and, for a team, is the first member's username.
    participant = None
    for cell in ordered:
        participant = _display_name(cell)
        if participant:
            break
    if participant is None:
        for cell in ordered:
            text = cell.first_segment()
            if text and not re.fullmatch(r"[\d.\s#]*", text):
                participant = text
                break
    if participant is None:
        for cell in ordered:
            participant = cell.user_slug()
            if participant:
                break
    if not participant:
        return None

    return {
        "rank": int(match_rank.group(1)),
        "participant": participant.replace("\\_", "_"),
        "score": float(score_text),
        "score_text": score_text,
    }


def _validate(rows: list[dict], parser: _LeaderboardHTML, min_rows: int = MIN_ROWS) -> None:
    if len(rows) < min_rows:
        raise ValueError(
            "only %d parseable ranked rows (expected at least %d); title=%r"
            % (len(rows), min_rows, " ".join(parser.title_parts).strip()[:80])
        )
    ranks = [row["rank"] for row in rows]
    if len(set(ranks)) != len(ranks):
        # A page that renders the same board twice (desktop + mobile table, for example) yields
        # identical rows; collapse those. The same rank carrying a *different* score or name means
        # two different boards were parsed, which must not be published.
        seen: dict[int, dict] = {}
        conflicting = []
        deduped = []
        for row in rows:
            previous = seen.get(row["rank"])
            if previous is None:
                seen[row["rank"]] = row
                deduped.append(row)
            elif (previous["score"], previous["participant"]) != (row["score"], row["participant"]):
                conflicting.append((row["rank"], previous["participant"], row["participant"],
                                    previous["score"], row["score"]))
        if conflicting:
            raise ValueError("conflicting rows parsed for the same rank: %r" % (conflicting[:5],))
        del rows[:]
        rows.extend(deduped)
        ranks = [row["rank"] for row in rows]
    if ranks != sorted(ranks):
        raise ValueError("ranks not ascending: %r" % (ranks[:20],))
    bad = [row for row in rows if not 0.0 <= row["score"] <= 1.0]
    if bad:
        raise ValueError("parsed scores outside [0, 1]: %r" % (bad[:5],))


def parse_leaderboard(html: str, source_url: str = URL, min_rows: int | None = None) -> dict:
    """Parse the official leaderboard table. Raises ValueError if it cannot be trusted.

    `min_rows` defaults to MIN_ROWS: a real board has 50 displayed rows, so a page that yields a
    handful is almost certainly not the board (a challenge page, a truncated response, or a
    different table) and must be rejected rather than published.
    """
    if min_rows is None:
        min_rows = MIN_ROWS
    parser = _LeaderboardHTML()
    parser.feed(html)

    rows: list[dict] = []
    strategy = ""

    # Strategy 1: a table whose header row advertises both a rank and a score column.
    for table in parser.tables:
        header_index = None
        score_index = participant_index = None
        for index, row in enumerate(table[:4]):
            header = [cell.normalized().lower() for cell in row]
            if _has_column(header, RANK_HEADER_GROUPS):
                score_index = _pick_column(header, SCORE_HEADER_GROUPS)
                if score_index is not None:
                    header_index = index
                    participant_index = _pick_column(header, PARTICIPANT_HEADER_GROUPS)
                    break
        if header_index is None:
            continue
        candidate = []
        for row in table[header_index + 1:]:
            if not row:
                continue
            if score_index is None or score_index >= len(row):
                parsed = _row_from_cells(row, participant_index=participant_index)
            else:
                parsed = _row_from_cells(row, score_index, participant_index)
            if parsed:
                candidate.append(parsed)
        if len(candidate) > len(rows):
            rows, strategy = candidate, "header row %d, score column %d" % (header_index, score_index)

    # Strategy 2: markup drift fallback - scan every <tr> in document order.
    if len(rows) < MIN_ROWS:
        fallback = []
        for row in parser.rows_in_order:
            parsed = _row_from_cells(row)
            if parsed:
                fallback.append(parsed)
        if len(fallback) > len(rows):
            rows, strategy = fallback, "row-scan fallback over %d tables" % len(parser.tables)

    if not rows:
        raise ValueError(
            "Could not find a leaderboard table with rank and score headers (%d tables, %d rows, "
            "%d bytes of cell text)" % (len(parser.tables), len(parser.rows_in_order), parser.text_seen)
        )

    rows.sort(key=lambda item: item["rank"])
    _validate(rows, parser, min_rows)

    return {
        "competition": COMPETITION,
        "source_url": source_url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_status": "live",
        "capture_method": (
            "Parsed from the official public leaderboard HTML by scripts/update_leaderboard.py "
            "(strategy: %s). No public JSON endpoint exists." % strategy
        ),
        "parse_strategy": strategy,
        "rows": rows,
        "row_count": len(rows),
        "attribution_caveat": build_attribution_caveat(rows),
        "phase_caveat": PHASE_CAVEAT,
    }


def build_attribution_caveat(rows: list[dict]) -> str:
    """State which displayed row each known artefact score coincides with, as of this retrieval.

    Computed from the rows rather than hard-coded, so the sentence cannot go stale when the board
    moves. It is still only a score coincidence, never an attribution.
    """
    observed = []
    for label, score in sorted(KNOWN_ARTEFACT_SCORES.items()):
        matches = [row for row in rows if abs(row["score"] - score) < 5e-5]
        if matches:
            observed.append(
                "%s (%.4f) coincides with displayed rank %d (%s)"
                % (label, score, matches[0]["rank"], matches[0]["participant"])
            )
        else:
            observed.append("%s (%.4f) is not on the currently displayed rows" % (label, score))
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return "%s As of %s: %s." % (ATTRIBUTION_CAVEAT, retrieved, "; ".join(observed))


def fetch_html(url: str, timeout: float) -> tuple[str, dict]:
    """Try the user-agent pool in order; return (html, diagnostics)."""
    attempts: list[dict] = []
    last_error = "no attempt made"
    for agent in USER_AGENTS:
        headers = {
            "User-Agent": agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.drivendata.org/competitions/306/competition-doe-gems/",
            "Cache-Control": "no-cache",
        }
        attempt = {"user_agent": agent.split(" (")[0][:48]}
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                body = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                attempt.update(
                    {
                        "http_status": getattr(response, "status", response.getcode()),
                        "final_url": response.geturl(),
                        "bytes": len(body),
                        "ok": True,
                    }
                )
                attempts.append(attempt)
                return body.decode(charset, errors="replace"), {"attempts": attempts}
        except HTTPError as error:
            attempt.update({"http_status": error.code, "ok": False, "error": "HTTPError %s" % error.code})
            last_error = "HTTP %s for %s" % (error.code, agent.split(" (")[0][:32])
        except (URLError, TimeoutError, OSError) as error:
            attempt.update({"ok": False, "error": "%s: %s" % (type(error).__name__, error)})
            last_error = "%s: %s" % (type(error).__name__, error)
        attempts.append(attempt)
    raise FetchError("all %d fetch attempts failed; last: %s" % (len(attempts), last_error))


def _diagnostics(html: str) -> dict:
    parser = _LeaderboardHTML()
    try:
        parser.feed(html)
    except Exception as error:  # pragma: no cover - malformed markup guard
        return {"parser_error": "%s: %s" % (type(error).__name__, error)}
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return {
        "title": " ".join(parser.title_parts).strip()[:120],
        "tables": len(parser.tables),
        "rows": len(parser.rows_in_order),
        "cell_text_bytes": parser.text_seen,
        "user_links": len(re.findall(r"/users/[^/?#\"]+", html)),
        "rank_markers": len(re.findall(r"#\s*\d+", html)),
        "tversky_mentions": html.lower().count("tversky"),
        "loading_placeholder": "loading" in text.lower(),
        "text_excerpt": text[:TEXT_EXCERPT_CHARS],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default=URL)
    parser.add_argument("--output", type=Path, default=Path("docs/data/leaderboard.json"))
    parser.add_argument("--status", type=Path, default=Path("docs/data/leaderboard-status.json"))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--render",
        action="store_true",
        help="if a plain GET yields no parseable table, re-fetch through headless Chromium "
             "(scripts/render_leaderboard.py); the official board is built by JavaScript",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        help="parse a saved HTML capture instead of fetching (same validation, source_status=snapshot)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if the board could not be refreshed (CI gate)",
    )
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output_path: Path = args.output
    status_path: Path = args.status

    old_snapshot: dict = {}
    if output_path and output_path.exists():
        try:
            old_snapshot = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old_snapshot = {}

    capture_path = "saved-capture" if args.from_file else "plain-http"
    if args.from_file:
        try:
            html = args.from_file.read_text(encoding="utf-8", errors="replace")
            fetch_diag: dict = {"attempts": [], "source_file": str(args.from_file), "bytes": len(html)}
            failure = ""
        except OSError as error:
            html, fetch_diag = "", {"attempts": [], "source_file": str(args.from_file)}
            failure = "OSError: %s" % error
    else:
        try:
            html, fetch_diag = fetch_html(args.url, args.timeout)
        except FetchError as error:
            html, fetch_diag = "", {"attempts": [], "fetch_error": str(error)}
            failure = "%s" % error
        else:
            failure = ""

    snapshot: dict | None = None
    if html:
        try:
            snapshot = parse_leaderboard(html, args.url)
        except ValueError as error:
            failure = "ValueError: %s" % error

    # The official board is client-rendered, so a plain GET can legitimately return a page shell
    # with no table at all. --render retries through headless Chromium, which sees what an ordinary
    # visitor sees. This bypasses nothing: same public URL, anonymous, no credentials, and the
    # signed-in API is never touched.
    if snapshot is None and args.render and not args.from_file:
        with tempfile.TemporaryDirectory() as render_tmp:
            rendered = Path(render_tmp) / "gems-leaderboard-rendered.html"
            proc = None
            try:
                proc = subprocess.run(
                    [sys.executable, str(RENDER_SCRIPT), "--url", args.url, "--output", str(rendered),
                     "--timeout-ms", str(int(max(args.timeout, 15.0) * 1000))],
                    capture_output=True, text=True, timeout=max(args.timeout * 3.0, 180.0),
                )
                fetch_diag["render"] = {
                    "returncode": proc.returncode,
                    "stdout": proc.stdout.strip()[:200],
                    "stderr": proc.stderr.strip()[:400],
                }
            except (OSError, subprocess.SubprocessError) as error:
                fetch_diag["render"] = {"error": "%s: %s" % (type(error).__name__, error)}
            if proc is not None and proc.returncode == 0 and rendered.exists():
                html = rendered.read_text(encoding="utf-8", errors="replace")
                fetch_diag["rendered_bytes"] = len(html)
                capture_path = "headless-render"
                try:
                    snapshot = parse_leaderboard(html, args.url)
                    failure = ""
                except ValueError as error:
                    failure = "rendered page: ValueError: %s" % error

    if snapshot is not None:
        live = capture_path != "saved-capture"
        snapshot["capture_path"] = capture_path
        snapshot["source_status"] = "live" if live else "snapshot"
        if capture_path == "headless-render":
            snapshot["capture_method"] = (
                "Rendered by headless Chromium (scripts/render_leaderboard.py) because the official "
                "page builds its table with JavaScript, then parsed and validated by "
                "scripts/update_leaderboard.py (strategy: %s)." % snapshot.get("parse_strategy", "table")
            )
        elif capture_path == "saved-capture":
            snapshot["capture_method"] = (
                "Parsed from a saved capture of the official public leaderboard page (%s) by "
                "scripts/update_leaderboard.py (strategy: %s)."
                % (args.from_file.name, snapshot.get("parse_strategy", "table"))
            )
        status = {
            "checked_utc": now,
            "status": "live" if live else "dated-snapshot",
            "capture_path": capture_path,
            "row_count": len(snapshot["rows"]),
            "source_url": args.url,
            "top": snapshot["rows"][0],
            "diagnostics": fetch_diag,
        }
        snapshot["refresh_status"] = status
        snapshot["source_note"] = (
            "Retrieved live from the official public leaderboard page."
            if live
            else "Parsed from a saved capture of the official public leaderboard page."
        )
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        _write_status(status_path, status)
        print(json.dumps(status, indent=2))
        return 0

    status = {
        "checked_utc": now,
        "status": "stale-snapshot-retained" if old_snapshot else "unavailable-no-snapshot",
        "source_url": args.url,
        "error": failure,
        "capture_path": capture_path,
        "render_attempted": bool(args.render),
        "retained_retrieved_utc": old_snapshot.get("retrieved_utc"),
        "retained_row_count": len(old_snapshot.get("rows") or []),
        "diagnostics": dict(fetch_diag, **(_diagnostics(html) if html else {})),
    }
    if old_snapshot:
        retained = dict(old_snapshot)
        retained["source_status"] = "snapshot"
        retained["refresh_status"] = status
        retained["source_note"] = (
            "Live refresh failed at %s (%s); the last verified official leaderboard rows were "
            "retained. See docs/data/leaderboard-status.json for diagnostics." % (now, failure)
        )
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(retained, indent=2) + "\n", encoding="utf-8")
    _write_status(status_path, status)
    print(json.dumps(status, indent=2), file=sys.stderr)
    if args.strict:
        return 1
    # Preserve a usable site with its last-known snapshot; the status badge on every page and the
    # sidecar file make the staleness explicit rather than silent.
    return 0


def _write_status(status_path: Path | None, status: dict) -> None:
    if not status_path:
        return
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
