#!/usr/bin/env python3
"""Fetch raw data for non-Curlie directory sources (FMHY, Awesome lists, VLib).

Downloads markdown lists from GitHub and scrapes the WWW Virtual Library.
Raw files are stored in ./sources_raw/<source>/ so parsing can be re-run
without re-downloading.
"""
import os
import re
import sys
import json
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "sources_raw"

MD_SOURCES = {
    "fmhy": [
        (f"https://raw.githubusercontent.com/nbats/FMHYedit/main/docs/{p}.md", p)
        for p in [
            "ai", "audio", "beginners-guide", "developer-tools", "downloading",
            "educational", "file-tools", "gaming-tools", "gaming", "image-tools",
            "internet-tools", "linux-macos", "misc", "mobile", "non-english",
            "privacy", "reading", "social-media-tools", "storage", "system-tools",
            "text-tools", "torrenting", "video-tools", "video",
        ]
    ],
    "awesome": [
        ("https://raw.githubusercontent.com/sindresorhus/awesome/main/readme.md", "awesome"),
    ],
    "selfhosted": [
        ("https://raw.githubusercontent.com/awesome-selfhosted/awesome-selfhosted/master/README.md", "selfhosted"),
    ],
    "freefordev": [
        ("https://raw.githubusercontent.com/ripienaar/free-for-dev/master/README.md", "free-for-dev"),
    ],
    "apis": [
        ("https://raw.githubusercontent.com/public-apis/public-apis/master/README.md", "public-apis"),
    ],
    "devbooks": [
        ("https://raw.githubusercontent.com/EbookFoundation/free-programming-books/main/books/free-programming-books-langs.md", "free-programming-books-langs"),
        ("https://raw.githubusercontent.com/EbookFoundation/free-programming-books/main/books/free-programming-books-subjects.md", "free-programming-books-subjects"),
    ],
    "buildyourownx": [
        ("https://raw.githubusercontent.com/danistefanovic/build-your-own-x/master/README.md", "build-your-own-x"),
    ],
    "privacy": [
        ("https://raw.githubusercontent.com/pluja/awesome-privacy/main/README.md", "awesome-privacy"),
    ],
    "usefulsites": [
        ("https://raw.githubusercontent.com/sdmg15/Best-websites-a-programmer-should-visit/master/README.md", "best-websites"),
    ],
}

VLIB_CATEGORIES = [
    "Agriculture", "Archaeology", "Art", "AsianStudies", "Biosciences",
    "BusinessEconomics", "Communication", "Computing", "Development",
    "EarthScience", "Education", "Engineering", "History", "Humanities",
    "InformationManagement", "InternationalAffairs", "Languages", "Law",
    "Medicine", "Museums", "Peoples", "Physics", "Recreation", "Regional",
    "Religion", "Science", "SocialSciences", "Society", "Transportation",
]

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HumanWeb-Directory/1.0"}


def fetch(url: str, tries: int = 3) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print(f"  retry {i+1}/{tries} {url}: {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def fetch_markdown_sources() -> None:
    for source, pages in MD_SOURCES.items():
        d = RAW / source
        d.mkdir(parents=True, exist_ok=True)
        for url, name in pages:
            out = d / f"{name}.md"
            if out.exists() and out.stat().st_size > 0:
                print(f"[{source}] {name}: cached")
                continue
            data = fetch(url)
            out.write_bytes(data)
            print(f"[{source}] {name}: {len(data):,} bytes")
            time.sleep(0.4)


class VlibParser(HTMLParser):
    """Collect external links (with nearest heading) and internal sub-page links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []          # (section, title, url)
        self.subpages = []       # (title, slug)
        self.section = ""
        self._in_heading = False
        self._in_a = False
        self._a_url = ""
        self._a_internal = False
        self._a_text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in ("h1", "h2", "h3", "h4"):
            self._in_heading = True
            self._heading_text = []
        elif tag == "a" and not self._skip:
            href = dict(attrs).get("href", "")
            if href.startswith("http") and "vlib.org" not in href:
                self._in_a, self._a_internal = True, False
                self._a_url = href
                self._a_text = []
            elif href and not href.startswith(("http", "#", "/", "mailto:")):
                slug = href.split("#")[0].split("?")[0]
                if slug.endswith((".es", ".fr", ".zh", ".html", ".css", ".png", ".jpg")):
                    return
                self._in_a, self._a_internal = True, True
                self._a_url = slug
                self._a_text = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        elif tag in ("h1", "h2", "h3", "h4") and self._in_heading:
            self._in_heading = False
            text = "".join(self._heading_text).strip()
            if text:
                self.section = text
        elif tag == "a" and self._in_a:
            self._in_a = False
            text = "".join(self._a_text).strip()
            if self._a_internal:
                if text and len(text) > 1 and len(self.subpages) < 80:
                    self.subpages.append((text, self._a_url))
            elif text and len(text) > 1:
                self.links.append((self.section, text, self._a_url))

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_a:
            self._a_text.append(data)
        if self._in_heading:
            self._heading_text.append(data)


def parse_vlib_page(html: str) -> VlibParser:
    p = VlibParser()
    p.feed(html)
    return p


def dedupe(links: list) -> list:
    seen, out = set(), []
    for section, title, url in links:
        if (title, url) in seen:
            continue
        seen.add((title, url))
        out.append((section, title, url))
    return out


def fetch_vlib() -> None:
    d = RAW / "vlib"
    d.mkdir(parents=True, exist_ok=True)
    for cat in VLIB_CATEGORIES:
        out = d / f"{cat}.json"
        if out.exists():
            print(f"[vlib] {cat}: cached")
            continue
        try:
            html = fetch(f"https://vlib.org/{cat}", tries=2).decode("utf-8", "replace")
        except RuntimeError as e:
            print(f"[vlib] {cat}: FAILED {e}", file=sys.stderr)
            continue
        p = parse_vlib_page(html)
        collected = list(p.links)
        # crawl one level of subcategory pages
        sub_done = set()
        for title, slug in p.subpages:
            if slug in sub_done or slug == cat:
                continue
            sub_done.add(slug)
            try:
                sub_html = fetch(f"https://vlib.org/{slug}", tries=1).decode("utf-8", "replace")
            except Exception:
                continue
            sp = parse_vlib_page(sub_html)
            for section, t, u in sp.links:
                collected.append((f"{title}" if not section else f"{title} / {section}", t, u))
            time.sleep(0.25)
        links = [{"s": s or cat, "t": t, "u": u} for s, t, u in dedupe(collected)]
        out.write_text(json.dumps(links, ensure_ascii=False), encoding="utf-8")
        print(f"[vlib] {cat}: {len(links)} links ({len(sub_done)} subpages)")
        time.sleep(0.4)


def main() -> None:
    fetch_markdown_sources()
    fetch_vlib()
    print("ALL SOURCES FETCHED")


if __name__ == "__main__":
    main()
