#!/usr/bin/env python3
"""Refresh a dated snapshot of the official public GEMS leaderboard.

If the site cannot be fetched or its table changes unexpectedly, retain the last
snapshot and write a failure status. This is a convenience feed, not an
independent score source.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

URL = "https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/"
ATTRIBUTION_CAVEAT = (
    "The official public leaderboard displays participants and scores but does not expose a "
    "prediction-file SHA-256 or public submission identifier; score equality is not artifact, "
    "account, or team attribution."
)
PHASE_CAVEAT = (
    "These are public leaderboard results only, not private Initial Prize Round (Phase 1) "
    "or expert-updated Final Prize Round (Phase 2) scores."
)


class _Cell:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.links: list[str] = []
        self.in_link = False
        self.current_link: list[str] = []

    def normalized(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.text)).strip()

    def first_segment(self) -> str:
        first = "".join(self.text).split("\n", 1)[0]
        return re.sub(r"\s+", " ", first).strip()


class _LeaderboardHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[_Cell]]] = []
        self.table_depth = 0
        self.current_table: list[list[_Cell]] | None = None
        self.current_row: list[_Cell] | None = None
        self.current_cell: _Cell | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.current_table = []
        elif tag == "tr" and self.table_depth == 1 and self.current_table is not None:
            self.current_row = []
        elif tag in ("td", "th") and self.current_row is not None:
            self.current_cell = _Cell()
        elif tag == "a" and self.current_cell is not None:
            self.current_cell.in_link = True
            self.current_cell.current_link = []
        elif tag == "br" and self.current_cell is not None:
            self.current_cell.text.append("\n")
        elif tag == "img" and self.current_cell is not None and attrs.get("alt"):
            self.current_cell.text.append(attrs["alt"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_cell is not None and self.current_cell.in_link:
            text = " ".join(self.current_cell.current_link).strip()
            if text:
                self.current_cell.links.append(text)
            self.current_cell.in_link = False
            self.current_cell.current_link = []
        elif tag in ("td", "th") and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(self.current_cell)
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None and self.current_table is not None:
            if self.current_row:
                self.current_table.append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1
            if self.table_depth == 0 and self.current_table is not None:
                self.tables.append(self.current_table)
                self.current_table = None

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.text.append(data)
            if self.current_cell.in_link:
                self.current_cell.current_link.append(data)


def parse_leaderboard(html: str, source_url: str = URL) -> dict:
    parser = _LeaderboardHTML()
    parser.feed(html)
    selected = None
    for table in parser.tables:
        if not table:
            continue
        header = [cell.normalized().lower() for cell in table[0]]
        if any("rank" in value for value in header) and any("tversky" in value for value in header):
            selected = table
            break
    if selected is None:
        raise ValueError("Could not find a leaderboard table with rank and Tversky headers")

    header = [cell.normalized().lower() for cell in selected[0]]
    score_index = next((i for i, value in enumerate(header) if "tversky" in value), None)
    participant_index = next((i for i, value in enumerate(header) if "participant" in value), None)
    if score_index is None or participant_index is None:
        raise ValueError(f"Unexpected leaderboard headers: {header}")

    rows = []
    for row in selected[1:]:
        if len(row) <= max(score_index, participant_index):
            continue
        rank_text = row[0].normalized()
        match_rank = re.search(r"#\s*(\d+)", rank_text)
        if not match_rank:
            continue
        score_text = row[score_index].normalized()
        match_score = re.search(r"(?<![\d.])(0?\.\d+|1(?:\.0+)?)(?![\d.])", score_text)
        if not match_score:
            continue
        participant_cell = row[participant_index]
        # The participant name is before the <br> timestamp/submission metadata.
        participant = participant_cell.first_segment()
        if participant_cell.links:
            participant = participant_cell.links[0].strip()
        rows.append(
            {
                "rank": int(match_rank.group(1)),
                "participant": participant,
                "score": float(match_score.group(1)),
                "score_text": match_score.group(1),
            }
        )
    if not rows:
        raise ValueError("Leaderboard table had no parseable ranked score rows")
    rows.sort(key=lambda item: item["rank"])
    return {
        "competition": "DOE GEMS Prize / DrivenData #306",
        "source_url": source_url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "source_status": "live",
        "rows": rows,
        "attribution_caveat": ATTRIBUTION_CAVEAT,
        "phase_caveat": PHASE_CAVEAT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/data/leaderboard.json"))
    parser.add_argument("--status", type=Path, default=Path("docs/data/leaderboard-status.json"))
    parser.add_argument("--url", default=URL)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    status_path = args.status
    now = datetime.now(timezone.utc).isoformat()
    try:
        req = Request(args.url, headers={"User-Agent": "GEMSDOE23 leaderboard feed/1.0 (public competition page)"})
        with urlopen(req, timeout=args.timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
            final_url = response.geturl()
        if "accounts/login" in final_url:
            raise URLError("Official leaderboard unexpectedly redirected to login")
        snapshot = parse_leaderboard(html, args.url)
        snapshot["retrieved_utc"] = now
        snapshot["final_url"] = final_url
        status = {"checked_utc": now, "status": "live", "row_count": len(snapshot["rows"]), "source_url": args.url}
        snapshot["refresh_status"] = status
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        if status_path:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(status, indent=2))
        return 0
    except Exception as exc:
        old_snapshot = args.output.is_file()
        status = {
            "checked_utc": now,
            "status": "stale-snapshot-retained" if old_snapshot else "unavailable-no-snapshot",
            "source_url": args.url,
            "error": f"{type(exc).__name__}: {exc}",
        }
        if old_snapshot:
            try:
                retained = json.loads(args.output.read_text(encoding="utf-8"))
                if isinstance(retained, dict) and isinstance(retained.get("rows"), list):
                    retained["source_status"] = "snapshot"
                    retained["refresh_status"] = status
                    retained["source_note"] = "Live refresh failed; the last verified official leaderboard rows were retained."
                    args.output.write_text(json.dumps(retained, indent=2) + "\n", encoding="utf-8")
            except Exception:
                # Keep the original snapshot untouched; the separate status file still records the failure.
                pass
        if status_path:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(status, indent=2), file=sys.stderr)
        # Preserve a usable site with its last-known snapshot; the status badge
        # tells readers that the feed may be stale.
        return 0 if old_snapshot else 2


if __name__ == "__main__":
    raise SystemExit(main())
