#!/usr/bin/env python3
"""Rebuild the Awesome tab's two subtabs.

Page 1 — "Awesome": the sindresorhus/awesome content plus a flat
"All Awesome Lists on GitHub" section (top 1,000 `topic:awesome` repos
by stars, fetched via the `gh` CLI).

Page 2 — "All Tracked List" (trackawesomelist.com style): the same
repos grouped into categories, where each repo inherits the
sindresorhus section it is listed under (Platforms, Back-End
Development, …) and shows stars + last-push date + description.

Updates meta.json (now two pages) and the tab catalog. Safe to re-run:
generated sections are replaced, not duplicated.

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
FLAT = "Awesome / All Awesome Lists on GitHub"
TRACKED = "All Tracked List"
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


def norm(url):
    return (url or "").split("#")[0].rstrip("/").lower()


def repo_link(r):
    desc = (r.get("description") or "").strip()
    if r.get("archived"):
        desc = (desc + " (archived)").strip()
    if len(desc) > 150:
        desc = desc[:147].rstrip() + "…"
    bits = [f"★ {r['stargazers_count']:,}", f"updated {(r.get('pushed_at') or '')[:7]}"]
    if r.get("language"):
        bits.append(r["language"])
    head = " · ".join(bits)
    return [r["full_name"], r["html_url"], f"{head} · {desc}" if desc else head]


def build_flat(repos):
    links = [
        ["Track Awesome List", "https://www.trackawesomelist.com/",
         "Daily-updated mirror of hundreds of awesome lists with a browsable table of contents."],
        ["GitHub topic: awesome", "https://github.com/topics/awesome",
         "The live index of every repository tagged awesome on GitHub."],
    ]
    links.extend(repo_link(r) for r in repos)
    return {"p": FLAT, "l": links}


def build_tracked(repos, source_sections):
    """Group repos by the sindresorhus section each repo is listed under."""
    url_cat, cat_order = {}, []
    for s in source_sections:
        if s["p"] == FLAT or not s["p"].startswith("Awesome / "):
            continue
        cat = s["p"].split(" / ", 1)[1]
        if cat not in cat_order:
            cat_order.append(cat)
        for entry in s["l"]:
            url_cat.setdefault(norm(entry[1]), cat)

    groups = {}
    for r in repos:
        cat = url_cat.get(norm(r["html_url"]), "General & Misc")
        groups.setdefault(cat, []).append(repo_link(r))
    # keep the fetch order (star-desc) inside each group
    order = {r["full_name"].lower(): i for i, r in enumerate(repos)}
    for cat in groups:
        groups[cat].sort(key=lambda l: order.get(l[0].lower(), 10 ** 9))

    ordered = [c for c in cat_order if c in groups]
    if "General & Misc" in groups:
        ordered.append("General & Misc")
    return [{"p": f"{TRACKED} / {cat}", "l": groups[cat]} for cat in ordered]


def main():
    sections = json.loads(gzip.open(DATA / "data.json.gz", "rt", encoding="utf-8").read())
    sections = [s for s in sections
                if s["p"] != FLAT and not s["p"].startswith(TRACKED + " / ")]  # idempotent

    print("Fetching topic:awesome repositories from GitHub…")
    repos = fetch_repos()
    sections.insert(0, build_flat(repos))
    tracked = build_tracked(repos, sections)
    all_sections = sections + tracked

    payload = json.dumps(all_sections, ensure_ascii=False, separators=(",", ":"))
    with gzip.GzipFile(DATA / "data.json.gz", "wb", mtime=0, compresslevel=9) as f:
        f.write(payload.encode("utf-8"))

    page1 = sum(len(s["l"]) for s in sections)
    page2 = sum(len(s["l"]) for s in tracked)
    meta = json.loads((DATA / "meta.json").read_text())
    meta["subtitle"] = "sindresorhus/awesome + every list tagged awesome on GitHub — flat & tracked views"
    meta["license"] = (meta.get("license", "") + " · topic index via the GitHub API").strip(" ·")
    meta["topic_fetched"] = time.strftime("%Y-%m-%d")
    meta["totals"] = {"pages": 2, "sections": len(all_sections), "links": page1 + page2}
    meta["pages"] = [
        {"id": "awesome", "title": "Awesome", "links": page1,
         "sections": [s["p"] for s in sections]},
        {"id": "tracked", "title": "All Tracked List", "links": page2,
         "sections": [s["p"] for s in tracked]},
    ]
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    catalog = json.loads(CATALOG.read_text())
    for src in catalog.get("sources", []):
        if src.get("id") == "awesome":
            src["links"] = page1 + page2
            src["subtitle"] = meta["subtitle"]
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1))

    print(f"Done: flat section {len(repos) + 2} links; tracked view "
          f"{len(tracked)} categories / {page2} links.")
    print(f"Awesome tab now reports {page1 + page2} links on 2 subtabs.")


if __name__ == "__main__":
    sys.exit(main())
