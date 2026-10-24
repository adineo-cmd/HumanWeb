#!/usr/bin/env python3
"""Curlie full-dataset extraction pipeline (replaces curlie_script.py).

Reads the official Curlie directory dump (rdf-*-s.tsv structure + rdf-*-c.tsv
content files), merges ALL files by category id, EXCLUDES the Adult top-level
tree and anime-related categories, then writes client-ready data:

  public/data/curlie/meta.json           totals, top-levels, chunk map
  public/data/curlie/index.json.gz       full category tree (path/counts/desc)
  public/data/curlie/chunk_*.ndjson.gz   links grouped by category path
  data-reports/curlie_report.json        verification numbers

Memory-safe: links are spooled to disk per top-level category before packing.
"""
import csv
import gzip
import html
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
IN_DIR = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.home() / "curlie_data" / "extracted" / "curlie-rdf"
OUT_DIR = BASE / "public" / "data" / "curlie"
REPORT_DIR = BASE / "data-reports"
CHUNK_TARGET_BYTES = 14 * 1024 * 1024   # uncompressed budget per chunk
DESC_MAX = 600

EXCLUDED_TOPLEVELS = {"adult"}                     # whole tree dropped
ANIME_SEG_RE = re.compile(r"anime|アニメ", re.I)   # any path segment match

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(s: str, limit: int = 0) -> str:
    s = html.unescape(s or "")
    s = TAG_RE.sub(" ", s)
    s = WS_RE.sub(" ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def is_excluded(path: str):
    segs = path.split("/")
    if segs[0].lower() in EXCLUDED_TOPLEVELS:
        return "adult"
    if any(ANIME_SEG_RE.search(seg) for seg in segs):
        return "anime"
    return None


def open_any(path: Path):
    if path.suffix == ".gz":
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def sniff_delimiter(path: Path) -> str:
    with open_any(path) as f:
        sample = f.read(8192)
    return "\t" if sample.count("\t") >= sample.count(",") else ","


def load_structure(cats: dict, stats: Counter) -> None:
    files = sorted(p for p in IN_DIR.glob("rdf-*-s.ts*"))
    if not files:
        sys.exit(f"no rdf-*-s.tsv structure files found in {IN_DIR}")
    print(f"structure files ({len(files)}): {[f.name for f in files]}")
    for fp in files:
        n = 0
        with open_any(fp) as f:
            for row in csv.reader(f, delimiter=sniff_delimiter(fp)):
                if len(row) < 3:
                    stats["struct_short_rows"] += 1
                    continue
                cid, path = row[0].strip(), row[1].strip()
                if not (cid.isdigit() and path):
                    stats["struct_skipped"] += 1
                    continue
                if cid in cats:
                    stats["struct_dup_catid"] += 1
                    continue
                cats[cid] = {
                    "path": path,
                    "count": int(row[2]) if row[2].strip().isdigit() else 0,
                    "desc": clean_text(row[3], 400) if len(row) > 3 else "",
                }
                n += 1
        stats["struct_loaded"] += n
        print(f"  {fp.name}: {n:,} categories")


def spool_content(cats: dict, spools: dict, stats: Counter, excluded_paths: set) -> None:
    files = sorted(p for p in IN_DIR.glob("rdf-*-c.ts*"))
    if not files:
        sys.exit(f"no rdf-*-c.tsv content files found in {IN_DIR}")
    print(f"content files ({len(files)}): {[f.name for f in files]}")
    col_dist = Counter()
    seen = set()
    for fp in files:
        n = dup = 0
        with open_any(fp) as f:
            for row in csv.reader(f, delimiter=sniff_delimiter(fp)):
                col_dist[len(row)] += 1
                if len(row) < 4:
                    stats["content_short_rows"] += 1
                    continue
                url, title = row[0].strip(), clean_text(row[1], 250)
                desc = clean_text("\t".join(row[2:-1]), DESC_MAX)
                cid = row[-1].strip()
                if not url.lower().startswith(("http://", "https://")):
                    stats["content_bad_url"] += 1
                    continue
                if not cid.isdigit():
                    stats["content_bad_catid"] += 1
                    continue
                path = cats.get(cid, {}).get("path") if cid in cats else None
                if path is None:
                    # content row whose category is absent from every -s file
                    stats["content_unknown_catid"] += 1
                    continue
                reason = is_excluded(path)
                if reason:
                    excluded_paths.add(path)
                    stats[f"excluded_links_{reason}"] += 1
                    continue
                key = (cid, url)
                if key in seen:
                    dup += 1
                    continue
                seen.add(key)
                top = path.split("/")[0]
                if top not in spools:
                    spools[top] = open(BASE / f".spool_{top}.ndjson", "w", encoding="utf-8")
                spools[top].write(json.dumps([path, url, title, desc],
                                             ensure_ascii=False, separators=(",", ":")) + "\n")
                n += 1
        stats["links_kept"] += n
        stats["links_dup"] += dup
        print(f"  {fp.name}: kept {n:,} links ({dup:,} exact dupes dropped)")
    stats["content_col_dist"] = dict(col_dist)
    for s in spools.values():
        s.close()


def write_chunks(spools: dict, chunk_map: dict, stats: Counter) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for top in sorted(spools):
        groups: dict[str, list] = {}
        with open(BASE / f".spool_{top}.ndjson", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                key = "/".join(rec[0].split("/")[:2]) if "/" in rec[0] else rec[0]
                groups.setdefault(key, []).append(rec)
        packed, cur, cur_bytes = [], [], 0
        for key in sorted(groups):
            gb = sum(len(r[0]) + len(r[1]) + len(r[2]) + len(r[3]) + 24 for r in groups[key])
            if cur and cur_bytes + gb > CHUNK_TARGET_BYTES:
                packed.append(cur)
                cur, cur_bytes = [], 0
            cur.append((key, groups[key]))
            cur_bytes += gb
        if cur:
            packed.append(cur)
        for part, pack in enumerate(packed, 1):
            name = f"chunk_{top[:24].replace('/', '_')}_{part}.ndjson.gz"
            by_cat: dict[str, list] = {}
            for _key, recs in pack:
                for path, url, title, desc in recs:
                    by_cat.setdefault(path, []).append([url, title, desc])
            with gzip.open(OUT_DIR / name, "wt", encoding="utf-8", compresslevel=9) as gz:
                for path in sorted(by_cat):
                    gz.write(json.dumps([path, by_cat[path]], ensure_ascii=False,
                                        separators=(",", ":")) + "\n")
            size = (OUT_DIR / name).stat().st_size
            stats["chunks"] += 1
            stats["chunk_gz_bytes"] += size
            for key, recs in pack:
                chunk_map[key] = {"file": name, "links": len(recs)}
            print(f"  {name}: {sum(len(r) for _, r in pack):,} links, {size/1e6:.1f} MB gz")
        (BASE / f".spool_{top}.ndjson").unlink()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    cats: dict = {}
    stats: Counter = Counter()
    excluded_paths: set = set()

    print("=== pass 1: structure ===")
    load_structure(cats, stats)
    stats["cats_total_in_dump"] = len(cats)
    stats["cats_excluded_adult"] = sum(1 for c in cats.values() if is_excluded(c["path"]) == "adult")
    stats["cats_excluded_anime"] = sum(1 for c in cats.values() if is_excluded(c["path"]) == "anime")
    print(f"categories: {len(cats):,} total | excl adult {stats['cats_excluded_adult']:,} | excl anime {stats['cats_excluded_anime']:,}")

    print("=== pass 2: content ===")
    spools: dict = {}
    spool_content(cats, spools, stats, excluded_paths)

    print("=== pass 3: count kept links per category ===")
    actual = Counter()
    for sp in BASE.glob(".spool_*.ndjson"):
        with open(sp, encoding="utf-8") as f:
            for line in f:
                actual[json.loads(line)[0]] += 1
    print(f"kept links: {sum(actual.values()):,} across {len(actual):,} categories")

    print("=== pass 4: build tree ===")
    # first-wins on duplicate paths (e.g. "Arts" defined in both rdf-Arts and rdf-Top)
    nodes: dict[str, dict] = {}
    for cid, c in cats.items():
        if is_excluded(c["path"]):
            continue
        nodes.setdefault(c["path"], {
            "id": cid, "t": c["path"].split("/")[-1].replace("_", " "),
            "d": c["desc"], "n": actual.get(c["path"], 0), "c": []})

    # order-independent tree assembly: map parent-path -> child paths first,
    # then link nodes (never mutate `nodes` while resolving parents)
    root_paths, children = [], {}
    for path in nodes:
        parent = path.rsplit("/", 1)[0] if "/" in path else None
        if parent and parent in nodes:
            children.setdefault(parent, []).append(path)
        else:
            root_paths.append(path)
    for parent, kids in children.items():
        nodes[parent]["c"] = [nodes[k] for k in kids]
    roots = [nodes[p] for p in root_paths]

    def rollup(node) -> int:
        node["tot"] = node["n"] + sum(rollup(ch) for ch in node["c"])
        return node["tot"]

    roots = [r for r in roots if r["c"] or r["n"]]   # drop empty artifacts (e.g. "Top", "AOL")
    for r in roots:
        rollup(r)
    # the dump contains a few path fragments missing their parent prefix
    # (e.g. a root "Localities" with 41 links) — hide anything that small
    fragments = [r["t"] for r in roots if r["tot"] < 100]
    roots = [r for r in roots if r["tot"] >= 100]
    stats["fragment_roots_dropped"] = len(fragments)
    if fragments:
        print(f"dropped fragment roots (<100 links): {fragments}")
    print(f"tree roots: {len(roots)} -> {[r['t'] for r in roots][:25]}")

    print("=== pass 5: chunks ===")
    chunk_map: dict = {}
    write_chunks(spools, chunk_map, stats)

    meta = {
        "source": "curlie",
        "title": "Curlie",
        "subtitle": "The largest human-edited web directory (excl. adult & anime)",
        "dump_date": "2026-02-02",
        "homepage": "https://curlie.org",
        "license": "Curlie Directory License — attribution required, see data-reports/",
        "toplevels": [{"title": r["t"], "links": r["tot"]} for r in sorted(roots, key=lambda x: -x["tot"])],
        "chunks": chunk_map,
        "totals": {
            "categories_in_dump": stats["cats_total_in_dump"],
            "categories_kept": stats["cats_total_in_dump"] - stats["cats_excluded_adult"] - stats["cats_excluded_anime"],
            "categories_excluded_adult": stats["cats_excluded_adult"],
            "categories_excluded_anime": stats["cats_excluded_anime"],
            "links_kept": stats["links_kept"],
            "unique_urls_approx": stats["links_kept"],
        },
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    with gzip.open(OUT_DIR / "index.json.gz", "wt", encoding="utf-8", compresslevel=9) as gz:
        json.dump(roots, gz, ensure_ascii=False, separators=(",", ":"))
    print(f"index.json.gz: {(OUT_DIR / 'index.json.gz').stat().st_size / 1e6:.1f} MB")

    report = {k: int(v) for k, v in stats.items() if k != "content_col_dist"}
    report["content_col_dist"] = stats["content_col_dist"]
    report["excluded_category_count"] = len(excluded_paths)
    report["excluded_category_examples"] = sorted(excluded_paths)[:40]
    (REPORT_DIR / "curlie_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("DONE — data-reports/curlie_report.json")


if __name__ == "__main__":
    main()
