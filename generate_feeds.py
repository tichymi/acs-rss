#!/usr/bin/env python3
"""Generate RSS feeds for selected ACS journals from Crossref metadata."""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from feedgen.feed import FeedGenerator

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "journals.json"
OUTPUT_DIR = ROOT / "docs"
CROSSREF_API = "https://api.crossref.org/journals/{issn}/works"
ROWS = 100
USER_AGENT = os.getenv(
    "CROSSREF_USER_AGENT",
    "acs-rss-generator/1.0 (mailto:replace-with-your-email@example.com)",
)


@dataclass(frozen=True)
class Journal:
    slug: str
    title: str
    issn: str
    homepage: str


def load_journals() -> list[Journal]:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return [Journal(**item) for item in raw]


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(value or "")).strip()


def date_parts_to_datetime(parts: Any) -> datetime | None:
    try:
        values = parts[0]
        year = int(values[0])
        month = int(values[1]) if len(values) > 1 else 1
        day = int(values[2]) if len(values) > 2 else 1
        return datetime(year, month, day, tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def publication_date(item: dict[str, Any]) -> datetime:
    for key in ("published-online", "published-print", "published", "issued", "created"):
        value = item.get(key, {})
        if "date-parts" in value:
            parsed = date_parts_to_datetime(value["date-parts"])
            if parsed:
                return parsed
        if key == "created" and value.get("date-time"):
            try:
                return datetime.fromisoformat(value["date-time"].replace("Z", "+00:00"))
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def authors_text(item: dict[str, Any]) -> str:
    names: list[str] = []
    for author in item.get("author", []):
        name = " ".join(part for part in (author.get("given", ""), author.get("family", "")) if part)
        if name:
            names.append(name)
    if not names:
        return ""
    if len(names) <= 8:
        return ", ".join(names)
    return ", ".join(names[:8]) + ", et al."


def fetch_works(journal: Journal) -> list[dict[str, Any]]:
    params = {
        "filter": "type:journal-article",
        "sort": "indexed",
        "order": "desc",
        "rows": ROWS,
        "select": "DOI,title,author,abstract,published,published-online,published-print,issued,created,URL,type",
    }
    response = requests.get(
        CROSSREF_API.format(issn=journal.issn),
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=45,
    )
    response.raise_for_status()
    items = response.json()["message"]["items"]

    # Crossref can occasionally return records from a related ISSN. ACS DOI prefix
    # provides a useful additional guard against unrelated content.
    items = [item for item in items if item.get("DOI", "").lower().startswith("10.1021/")]

    # Stable newest-first ordering and DOI deduplication.
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        doi = item.get("DOI", "").lower()
        if doi:
            unique[doi] = item
    return sorted(unique.values(), key=publication_date, reverse=True)


def add_entries(feed: FeedGenerator, items: list[dict[str, Any]], journal_title: str) -> None:
    for item in items:
        doi = item["DOI"]
        url = f"https://doi.org/{doi}"
        title_values = item.get("title") or [doi]
        title = strip_tags(title_values[0]) or doi
        authors = authors_text(item)
        abstract = strip_tags(item.get("abstract", ""))

        description_parts = []
        if authors:
            description_parts.append(f"<p><strong>Authors:</strong> {html.escape(authors)}</p>")
        description_parts.append(f"<p><strong>Journal:</strong> {html.escape(journal_title)}</p>")
        if abstract:
            description_parts.append(f"<p>{html.escape(abstract)}</p>")
        description_parts.append(f'<p><a href="{html.escape(url)}">Open via DOI</a></p>')

        entry = feed.add_entry(order="append")
        entry.id(f"doi:{doi.lower()}")
        entry.title(title)
        entry.link(href=url)
        entry.guid(url, permalink=True)
        entry.pubDate(publication_date(item))
        entry.description("".join(description_parts))
        if authors:
            entry.author({"name": authors})


def make_feed(title: str, link: str, feed_url: str, description: str, items: list[dict[str, Any]]) -> FeedGenerator:
    fg = FeedGenerator()
    fg.id(feed_url)
    fg.title(title)
    fg.link(href=link, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.description(description)
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.generator("acs-rss-generator using Crossref metadata")
    return fg


def write_feed(feed: FeedGenerator, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    feed.rss_file(str(path), pretty=True)


def main() -> int:
    journals = load_journals()
    base_url = os.getenv("FEED_BASE_URL", "https://USERNAME.github.io/acs-rss").rstrip("/")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    combined: list[tuple[dict[str, Any], str]] = []
    failures: list[str] = []

    for index, journal in enumerate(journals):
        try:
            items = fetch_works(journal)
            feed_url = f"{base_url}/{journal.slug}.xml"
            feed = make_feed(
                journal.title,
                journal.homepage,
                feed_url,
                f"Recent articles from {journal.title}; generated from Crossref DOI metadata.",
                items,
            )
            add_entries(feed, items, journal.title)
            write_feed(feed, OUTPUT_DIR / f"{journal.slug}.xml")
            combined.extend((item, journal.title) for item in items)
            print(f"Generated {journal.slug}.xml with {len(items)} entries")
        except Exception as exc:  # Keep other journals updating if one endpoint fails.
            failures.append(f"{journal.title}: {exc}")
            print(f"ERROR: {journal.title}: {exc}", file=sys.stderr)
        if index < len(journals) - 1:
            time.sleep(1)

    combined.sort(key=lambda pair: publication_date(pair[0]), reverse=True)
    combined = combined[:200]
    combined_url = f"{base_url}/all-acs-medchem.xml"
    combined_feed = make_feed(
        "ACS medicinal chemistry journals",
        "https://pubs.acs.org/",
        combined_url,
        "Combined feed for selected ACS medicinal chemistry and infectious-disease journals.",
        [item for item, _ in combined],
    )
    for item, journal_title in combined:
        add_entries(combined_feed, [item], journal_title)
    write_feed(combined_feed, OUTPUT_DIR / "all-acs-medchem.xml")

    (OUTPUT_DIR / "index.html").write_text(build_index(journals), encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").touch()

    if failures:
        print("Some feeds failed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    return 0


def build_index(journals: list[Journal]) -> str:
    base_url = os.getenv("FEED_BASE_URL", "https://USERNAME.github.io/acs-rss").rstrip("/")
    rows = "\n".join(
        f'<li><a href="{journal.slug}.xml">{html.escape(journal.title)}</a></li>' for journal in journals
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ACS RSS feeds</title></head>
<body>
<h1>ACS RSS feeds</h1>
<p>Generated from Crossref DOI metadata. Feed base: <code>{html.escape(base_url)}</code></p>
<ul>{rows}
<li><a href="all-acs-medchem.xml">Combined feed</a></li></ul>
</body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
