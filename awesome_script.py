#!/usr/bin/env python3
"""Refresh the Awesome tab's "All Awesome Lists on GitHub" section.

Fetches every repository tagged `topic:awesome` on GitHub (top 1,000 by
stars, the search API's hard cap) via the `gh` CLI, prepends them as a
section in front of the existing sindresorhus/awesome content, and
updates meta.json plus the tab catalog (public/data/index.json).

Safe to re-run: the generated section is replaced, not duplicated.

Usage:  python3 awesome_script.py
"""
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "public" / "data" / "awesome"
CATALOG = ROOT / "public" / "data" / "index.json"
SECTION = "Awesome / All Awesome Lists on GitHub"
PAGES = 10  # 100 per page -> top 1,000 by stars


def gh(path):
    out = subprocess.check_output(["gh", "api", path], text=True)
    return json.loads(out)


def fetch_repos():
    repos = []
    for page in range(1, PAGES + 1):
        q = f"topic:awesome+fork:false&sort=stars&order=desc&per_page=100&page={page}"
        items = gh("search/repositories?q=" + q).get("items", [])
        repos.extend(items)
        print(f"  page {page}: +{len(items)} (total {len(repos)})")
        if len(items) < 100:
            break
        time.sleep(0.6)
    return repos


def build_section(repos):
    links = [
        [
            "Track Awesome List",
            "https://www.trackawesomelist.com/",
            "Daily-updated mirror of hundreds of awesome lists with a browsable table of contents.",
        ],
        [
            "GitHub topic: awesome",
            "https://github.com/topics/awesome",
            "The live index of every repository tagged awesome on GitHub.",
        ],
    ]
    for r in repos:
        desc = (r.get("description") or "").strip()
        if r.get("archived"):
            desc = (desc + " (archived)").strip()
        if len(desc) > 150:
            desc = desc[:147].rstrip() + "…"
        bits = [f"★ {r['stargazers_count']:,}"]
        if r.get("language"):
            bits.append(r["language"])
        head = " · ".join(bits)
        links.append([r["full_name"], r["html_url"], f"{head} · {desc}" if desc else head])
    return {"p": SECTION, "l": links}


def main():
    sections = json.loads(gzip.open(DATA / "data.json.gz", "rt", encoding="utf-8").read())
    sections = [s for s in sections if s["p"] != SECTION]  # idempotent re-runs

    print("Fetching topic:awesome repositories from GitHub…")
    repos = fetch_repos()
    sections.insert(0, build_section(repos))

    payload = json.dumps(sections, ensure_ascii=False, separators=(",", ":"))
    with gzip.GzipFile(DATA / "data.json.gz", "wb", mtime=0, compresslevel=9) as f:
        f.write(payload.encode("utf-8"))

    total = sum(len(s["l"]) for s in sections)
    meta = json.loads((DATA / "meta.json").read_text())
    meta["subtitle"] = "sindresorhus/awesome + every list tagged awesome on GitHub"
    meta["license"] = (meta.get("license", "") + " · topic index via the GitHub API").strip(" ·")
    meta["topic_fetched"] = time.strftime("%Y-%m-%d")
    meta["totals"] = {**meta.get("totals", {}), "sections": len(sections), "links": total}
    if meta.get("pages"):
        meta["pages"][0]["links"] = total
        meta["pages"][0]["sections"] = [s["p"] for s in sections]
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    catalog = json.loads(CATALOG.read_text())
    for src in catalog.get("sources", []):
        if src.get("id") == "awesome":
            src["links"] = total
            src["subtitle"] = meta["subtitle"]
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1))

    print(f"Done: {len(repos)} repos + 2 pointers -> '{SECTION}'")
    print(f"Awesome tab now reports {total} links across {len(sections)} sections.")


if __name__ == "__main__":
    sys.exit(main())
