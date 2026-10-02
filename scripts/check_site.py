#!/usr/bin/env python3
"""Check that every local HTML href/src resolves inside the static Pages site."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs) -> None:
        attrs = dict(attrs)
        for key in ("href", "src"):
            value = attrs.get(key)
            if value:
                self.links.append(value)
        if attrs.get("id"):
            self.ids.add(attrs["id"])


def main() -> int:
    failures: list[str] = []
    html_files = sorted(SITE.rglob("*.html"))
    parsed: dict[Path, LinkParser] = {}
    for page in html_files:
        parser = LinkParser()
        parser.feed(page.read_text(encoding="utf-8"))
        parsed[page] = parser
    for page, parser in parsed.items():
        for link in parser.links:
            parts = urlsplit(link)
            if parts.scheme or link.startswith("//"):
                continue
            if not parts.path:
                target_path = page
            elif parts.path.startswith("/"):
                target_path = (SITE / unquote(parts.path.lstrip("/"))).resolve()
            else:
                target_path = (page.parent / unquote(parts.path)).resolve()
            try:
                target_path.relative_to(SITE.resolve())
            except ValueError:
                failures.append(f"{page.relative_to(ROOT)}: local path escapes docs/: {link}")
                continue
            if not target_path.exists():
                failures.append(f"{page.relative_to(ROOT)}: missing local target: {link}")
                continue
            if parts.fragment and target_path.suffix == ".html":
                target_parser = parsed.get(target_path)
                if target_parser and unquote(parts.fragment) not in target_parser.ids:
                    failures.append(f"{page.relative_to(ROOT)}: missing fragment #{parts.fragment} in {target_path.relative_to(ROOT)}")
    if failures:
        print("Site link check failed:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 2
    print(f"PASS: {len(html_files)} HTML pages; all local href/src targets and fragments resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
