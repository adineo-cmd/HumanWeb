#!/usr/bin/env python3
"""Build the OpenWebSearch tab — a curated map of Europe's open web index.

The Open Web Index (OWI) itself sits behind free-but-authenticated
LEXIS/iRODS access, so link extraction needs an account; this tab maps
the project, its public remote index (anonymously readable Parquet on
S3), the tooling, and the sibling open datasets.

If you later obtain LEXIS credentials, extend this script to pull a
sample of URLs from the remote index (endpoint a3s.fi, bucket
2006391-owi-remote-index) and append a "Sample" section.

Usage:  python3 openwebsearch_script.py
"""
import gzip
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "public" / "data" / "openwebsearch"
CATALOG = ROOT / "public" / "data" / "index.json"
BUCKET = "https://a3s.fi/2006391-owi-remote-index"
BOOK = "https://openwebsearcheu-public.pages.it4i.eu/ows-the-book"

SECTIONS = [
    ("OpenWebSearch / Start here", [
        ["OpenWebSearch.eu", "https://openwebsearch.eu/",
         "The EU project building an open, sovereign web index for Europe — no big-tech gatekeepers."],
        ["Open Web Index data portal", "https://www.openwebindex.net/docs",
         "Where the index lives: data shards, daily statistics, licences and documentation."],
        ["Getting the data, step by step", "https://www.openwebindex.net/docs/getting-the-data",
         "Download instructions — every shard needs a free LEXIS portal account."],
        ["Daily-updated statistics", "https://www.openwebindex.net/",
         "Watch the index grow: pages crawled, languages, daily slices."],
    ]),
    ("OpenWebSearch / Query it today (no account)", [
        ["The public remote index", f"{BOOK}/content/dnt/remote-index.html",
         "A Parquet inverted index on public S3 (endpoint a3s.fi) — query it with DuckDB, anonymously."],
        ["owilake.ducklake — catalog", f"{BUCKET}/owilake.ducklake",
         "DuckLake catalog listing every documents/postings shard in the public lake."],
        ["Documents table schema", f"{BUCKET}/documents_schema.parquet",
         "Columns docid, id and URL — one row per page in the index."],
        ["Example: query a daily slice", f"{BUCKET}?list-type=2&prefix=year=2026/&max-keys=20",
         "Browse the daily shards: year=…/month=…/day=…/collection=…/index/representation=…/language=…"],
        [" owilix — the OWI CLI", f"{BOOK}/",
         "The Open Web Search Book: tutorials for owilix (list, pull, slice, query) and MOSAIC."],
    ]),
    ("OpenWebSearch / How it is built", [
        ["The Open Web Index (ECIR 2024 paper)", "https://dl.acm.org/doi/10.1007/978-3-031-56069-9_10",
         "The research paper defining the openly accessible index structure."],
        ["Neural crawling — the FUN project", "https://openwebsearch.eu/fun-results",
         "How the project's crawler decides what to crawl next using neural predictions."],
        ["Remote index research paper", f"{BOOK}/content/dnt/remote-index.html",
         "Design of the remotely queryable inverted file (paper HHdV26), with BM25 in pure SQL."],
    ]),
    ("OpenWebSearch / Sibling open data", [
        ["Common Crawl", "https://commoncrawl.org",
         "The petabyte open crawl behind this site's Common Crawl tab — HumanWeb samples its WET extracts."],
        ["Web Data Commons", "https://webdatacommons.io/",
         "Structured-data (schema.org) extracts built from Common Crawl — microdata, tables, hyperlinks."],
        ["Internet Archive Wayback Machine", "https://web.archive.org",
         "Two decades of page history — the rescue source for dead links everywhere."],
    ]),
    # Real links extracted once from the public DuckLake (owilake.ducklake):
    # documents/language=fry/checkpoint-75.parquet, read with @duckdb/node-api,
    # 1,200 rows sampled → 519 unique hosts. Regenerate with the same recipe.
    ("OpenWebSearch / Live sample — pages in the index", None),
]


def main():
    sections = []
    for p, l in SECTIONS:
        if l is None:  # the live-sample section comes from the extracted slice
            sample = DATA / "fry-sample.json"
            if sample.exists():
                l = json.loads(sample.read_text())
            else:
                continue
        sections.append({"p": p, "l": l})
    total = sum(len(s["l"]) for s in sections)

    DATA.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sections, ensure_ascii=False, separators=(",", ":"))
    with gzip.GzipFile(DATA / "data.json.gz", "wb", mtime=0, compresslevel=9) as f:
        f.write(payload.encode("utf-8"))

    meta = {
        "source": "openwebsearch",
        "title": "OpenWebSearch",
        "subtitle": "Europe's open web index — the project, its public remote index and the tooling around it",
        "homepage": "https://openwebsearch.eu",
        "license": "Links only — OWI data is available under its own licence via the LEXIS portal",
        "fetched": time.strftime("%Y-%m-%d"),
        "totals": {"pages": 1, "sections": len(sections), "links": total},
        "pages": [{"id": "openwebsearch", "title": "OpenWebSearch", "links": total,
                   "sections": [s["p"] for s in sections]}],
    }
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    catalog = json.loads(CATALOG.read_text())
    entry = next((s for s in catalog["sources"] if s["id"] == "openwebsearch"), None)
    if entry is None:
        entry = {"id": "openwebsearch", "title": "OpenWebSearch", "links": total}
        catalog["sources"].append(entry)
    entry.update({"subtitle": meta["subtitle"], "homepage": meta["homepage"], "links": total})
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1))
    print(f"Done: {total} links across {len(sections)} sections.")


if __name__ == "__main__":
    main()
