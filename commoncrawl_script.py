#!/usr/bin/env python3
"""Build the Common Crawl tab: a live sample of the open crawl.

Streams the head of a few WET (plain-text extraction) segments from the
latest Common Crawl, pulling (title, URL, snippet) triples — the
download is aborted as soon as the record quota is met, so only a few
megabytes per segment are transferred.

Output: public/data/commoncrawl/{data.json.gz,meta.json} in the standard
list-source format, plus a catalog entry in public/data/index.json.

Usage:  python3 commoncrawl_script.py
"""
import gzip
import json
import sys
import time
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "public" / "data" / "commoncrawl"
CATALOG = ROOT / "public" / "data" / "index.json"
CC = "https://data.commoncrawl.org"
RECORDS_PER_SEGMENT = 3000
SEGMENTS = 5
MAX_MB_PER_SEGMENT = 16
ADULT_DOMAINS = {
    "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com", "redtube.com",
    "youporn.com", "onlyfans.com", "chaturbate.com", "stripchat.com",
    "brazzers.com", "spankbang.com", "porntube.com", "tube8.com",
    "adultfriendfinder.com", "ashley-madison.com", "f95zone.to", "nhentai.net",
    "hitomi.la", "hentai2read.com", "rule34video.com", "literotica.com",
    "sex.com", "4chan.org", "8kun.top", "e-hentai.org", "javlibrary.com",
}
# The raw crawl is unfiltered; these substrings (checked against the host
# and the title) keep the obvious adult results out of the sample.
ADULT_TERMS = [
    "porn", "xxx", "hentai", "xnxx", "xvideos", "xhamster", "redtube",
    "youporn", "onlyfans", "chaturbate", "stripchat", "spankbang", "jav",
    "sukebei", "erome", "nsfw", "nudes", "sexvideo", "sex-video", "camwhore",
    "麻豆", "国产av", "91制片厂", "巨乳", "爆乳", "おっぱい", "色情", "成人视频",
    "女优", "a片", "淫", "erro-manga", "caribbeancom", "全裸", "一本道",
    "javhd", "无码", "有码", "黄色网站", "狼友", "熟女", "巨根", "偷拍",
]


def is_adult(link):
    title, url, _ = link
    host = ""
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").removeprefix("www.")
    except ValueError:
        pass
    if host in ADULT_DOMAINS:
        return True
    for term in ADULT_TERMS:
        if term in host or term in title.lower():
            return True
    return False

UA = {"User-Agent": "HumanWeb/1.0 (open directory; github.com/adineo-cmd)"}


def fetch_bytes(url, tries=3):
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=240).read()
        except Exception as e:  # the crawl mirror is slow — retry patiently
            last = e
            time.sleep(5 * (i + 1))
    raise last


def latest_crawl():
    info = json.loads(fetch_bytes("https://index.commoncrawl.org/collinfo.json"))
    return info[0]["id"]


def parse_segment(crawl, seg_path, want):
    """Stream the head of one WET segment; return (links, stats)."""
    url = f"{CC}/{seg_path}"
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=240)
    d = zlib.decompressobj(31)
    buf = tail = b""
    links, seen = [], set()
    seg_id = seg_path.rsplit("-", 1)[-1].split(".")[0]
    date = seg_path.split("/")[3].split("-")
    label = f"{date[4][:4]}-{date[4][4:6]} ({seg_path.split('/')[2].split('-')[-1]} · part {seg_id})" if False else f"Segment {seg_id}"
    downloaded = 0
    cur_url = None
    body_lines = []
    t0 = time.time()
    while len(links) < want:
        if time.time() - t0 > 300 or downloaded > MAX_MB_PER_SEGMENT << 20:
            break
        chunk = raw.read(1 << 16)
        if not chunk:
            break
        downloaded += len(chunk)
        try:
            data = d.decompress(chunk)
            if d.eof:
                # multi-member gzip: re-arm at each member boundary
                rest = d.unused_data
                d = zlib.decompressobj(31)
                data += d.decompress(rest)
        except zlib.error:
            break
        buf = tail + data
        lines = buf.split(b"\n")
        tail = lines.pop()
        for line in lines:
            s = line.decode("utf-8", "replace").rstrip("\r\n")
            if s.startswith("WARC-Target-URI:"):
                cur_url, body_lines = s[16:].strip(), None  # headers first; body starts at the blank line
            elif s == "" and cur_url is not None:
                body_lines = []          # end of headers — body follows
            elif s.startswith("WARC/1.0"):
                cur_url = None           # next record began without our capture
            elif body_lines is not None and cur_url and s.strip():
                body_lines.append(s.strip())
                if len(body_lines) >= 2:
                    host = ""
                    try:
                        from urllib.parse import urlparse
                        h = urlparse(cur_url).hostname or ""
                        host = h.removeprefix("www.")
                    except ValueError:
                        host = ""
                    if (cur_url.startswith("http") and host and host not in seen
                            and host not in ADULT_DOMAINS
                            and len(body_lines[0]) >= 8
                            and not cur_url.lower().endswith((".pdf", ".jpg", ".png", ".gif", ".zip"))):
                        seen.add(host)
                        title = body_lines[0][:110]
                        snippet = body_lines[1][:150]
                        links.append([title, cur_url, f"{snippet} ({host})"])
                    cur_url = None
                    body_lines = None  # rest of this record is body text
    raw.close()
    return links, downloaded


def write_output(crawl, sections):
    total = sum(len(s["l"]) for s in sections)
    payload = json.dumps(sections, ensure_ascii=False, separators=(",", ":"))
    with gzip.GzipFile(DATA / "data.json.gz", "wb", mtime=0, compresslevel=9) as f:
        f.write(payload.encode("utf-8"))

    meta = {
        "source": "commoncrawl",
        "title": "Common Crawl",
        "subtitle": "A live sample of the open Common Crawl — machine-extracted, not human-vetted",
        "homepage": "https://commoncrawl.org",
        "license": "CC0 1.0 — source: Common Crawl petabyte web crawl",
        "crawl": crawl,
        "fetched": time.strftime("%Y-%m-%d"),
        "totals": {"pages": 1, "sections": len(sections), "links": total},
        "pages": [{"id": "commoncrawl", "title": "Common Crawl", "links": total,
                   "sections": [s["p"] for s in sections]}],
    }
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    catalog = json.loads(CATALOG.read_text())
    entry = next((s for s in catalog["sources"] if s["id"] == "commoncrawl"), None)
    if entry is None:
        entry = {"id": "commoncrawl", "title": "Common Crawl", "links": total}
        catalog["sources"].append(entry)
    entry.update({"subtitle": meta["subtitle"], "homepage": meta["homepage"],
                  "links": total, "note": f"sample of {crawl}"})
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=1))
    print(f"Done: {total} links across {len(sections)} segments.")


def main():
    if "--refilter" in sys.argv:
        # re-apply the adult filter to an already-downloaded sample
        sections = json.loads(gzip.open(DATA / "data.json.gz", "rt", encoding="utf-8").read())
        meta = json.loads((DATA / "meta.json").read_text())
        before = sum(len(s["l"]) for s in sections)
        sections = [{"p": s["p"], "l": [x for x in s["l"] if not is_adult(x)]} for s in sections]
        after = sum(len(s["l"]) for s in sections)
        print(f"Refiltered: {before} -> {after} links")
        write_output(meta["crawl"], sections)
        return

    crawl = latest_crawl()
    print(f"Latest crawl: {crawl}")
    paths = gzip.decompress(fetch_bytes(f"{CC}/crawl-data/{crawl}/wet.paths.gz")).decode().split()
    print(f"{len(paths)} WET segments available")
    step = max(1, len(paths) // (SEGMENTS * 3))
    picks = [paths[i] for i in range(0, len(paths), step)][:SEGMENTS]

    sections = []
    total = 0
    for seg in picks:
        t0 = time.time()
        try:
            links, downloaded = parse_segment(crawl, seg, RECORDS_PER_SEGMENT)
        except Exception as e:
            print(f"  {seg.rsplit('/', 1)[-1]}: FAILED ({e}) — skipping")
            continue
        seg_id = seg.rsplit("-", 1)[-1].split(".")[0]
        total += len(links)
        sections.append({"p": f"Common Crawl / Segment {seg_id}", "l": links})
        print(f"  {seg.rsplit('/', 1)[-1]}: {len(links)} links, "
              f"{downloaded / 1e6:.1f} MB, {time.time() - t0:.0f}s")

    sections = [{"p": s["p"], "l": [x for x in s["l"] if not is_adult(x)]} for s in sections]
    write_output(crawl, sections)


if __name__ == "__main__":
    main()
