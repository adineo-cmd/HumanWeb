#!/usr/bin/env python3
"""Parse fetched markdown directory sources (FMHY, Awesome lists) + VLib JSON
into per-source client-ready data files:

  public/data/<source>/meta.json     page/section structure + counts
  public/data/<source>/data.json.gz  flat sections: [{p: "Page / Section", l: [[title, url, desc], ...]}]

Adult- and anime-focused sections are dropped (same policy as the Curlie tab).
"""
import gzip
import json
import re
from collections import OrderedDict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "sources_raw"
OUT = BASE / "public" / "data"

LINK_RE = re.compile(r"\[([^\]]+)\]\(\s*([^)\s]+)[^)]*\)")
MIRROR_TITLES = {"2", "3", "4", "5", "6", "7", "8", "here", "this", "source",
                 "discord", "telegram", "status", "invite", "mirror", "mirrors",
                 "back", "faq", "changelog", "download", "reddit", "github"}
IMG_URL_RE = re.compile(
    r"\.(svg|png|jpe?g|gif|webp|ico|bmp)([?#].*)?$|shields\.io|travis-ci\.org|badge", re.I)
ANYLINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
CODE_RE = re.compile(r"`([^`]*)`")
EMPH_RE = re.compile(r"\*([^*]+)\*")
WS_RE = re.compile(r"\s+")

DROP_SECTION_RE = re.compile(
    r"\b(nsfw|adult|porn|18\+|hentai|erotic|sex)\b|anime|manga", re.I)

FMHY_TITLES = {
    "ai": "AI", "audio": "Audio & Music", "beginners-guide": "Beginners Guide",
    "developer-tools": "Developer Tools", "downloading": "Downloading",
    "educational": "Educational", "file-tools": "File Tools",
    "gaming-tools": "Gaming Tools", "gaming": "Gaming", "image-tools": "Image Tools",
    "internet-tools": "Internet Tools", "linux-macos": "Linux & MacOS",
    "misc": "Misc", "mobile": "Mobile", "non-english": "Non-English",
    "privacy": "Privacy & Security", "reading": "Reading",
    "social-media-tools": "Social Media Tools", "storage": "Storage",
    "system-tools": "System Tools", "text-tools": "Text Tools",
    "torrenting": "Torrenting", "video-tools": "Video Tools", "video": "Video",
}

SOURCES = {
    "fmhy": {
        "title": "FMHY",
        "subtitle": "r/FREEMEDIAHECKYEAH — the big list of free media & tools",
        "homepage": "https://fmhy.net",
        "license": "© FMHY community — source: github.com/nbats/FMHYedit",
        "resolve_base": "https://github.com/nbats/FMHYedit/blob/main/docs/",
    },
    "awesome": {
        "title": "Awesome",
        "subtitle": "sindresorhus/awesome — awesome lists about all things awesome",
        "homepage": "https://awesome.selfhosted.app",
        "license": "CC0 1.0 — source: github.com/sindresorhus/awesome",
        "resolve_base": "https://github.com/sindresorhus/awesome/blob/main/",
    },
    "selfhosted": {
        "title": "Self-Hosted",
        "subtitle": "awesome-selfhosted — free software network services you can self-host",
        "homepage": "https://awesome-selfhosted.net",
        "license": "CC BY-SA — source: github.com/awesome-selfhosted/awesome-selfhosted",
        "resolve_base": "https://github.com/awesome-selfhosted/awesome-selfhosted/blob/master/",
    },
    "freefordev": {
        "title": "Free for Dev",
        "subtitle": "Software (SaaS, PaaS, IaaS...) with free tiers for developers",
        "homepage": "https://free-for.dev",
        "license": "© contributors — source: github.com/ripienaar/free-for-dev",
        "resolve_base": "https://github.com/ripienaar/free-for-dev/blob/master/",
    },
    "vlib": {
        "title": "VLib",
        "subtitle": "The WWW Virtual Library — the oldest web directory (est. 1991)",
        "homepage": "https://vlib.org",
        "license": "© The WWW Virtual Library — vlib.org",
        "resolve_base": None,
    },
    "apis": {
        "title": "Public APIs",
        "subtitle": "public-apis — hundreds of free APIs for developers",
        "homepage": "https://github.com/public-apis/public-apis",
        "license": "© contributors — source: github.com/public-apis/public-apis",
        "resolve_base": "https://github.com/public-apis/public-apis/blob/master/",
        "titles": {"public-apis": "Public APIs"},
    },
    "devbooks": {
        "title": "Dev Books",
        "subtitle": "free-programming-books — free programming books & courses",
        "homepage": "https://ebookfoundation.github.io/free-programming-books/",
        "license": "CC BY — source: github.com/EbookFoundation/free-programming-books",
        "resolve_base": "https://github.com/EbookFoundation/free-programming-books/blob/main/",
        "titles": {"free-programming-books-langs": "Books by Language",
                   "free-programming-books-subjects": "Books by Subject"},
    },
    "buildyourownx": {
        "title": "Build Your Own X",
        "subtitle": "step-by-step guides to build your own database, bot, compiler, OS…",
        "homepage": "https://github.com/danistefanovic/build-your-own-x",
        "license": "© contributors — source: github.com/danistefanovic/build-your-own-x",
        "resolve_base": "https://github.com/danistefanovic/build-your-own-x/blob/master/",
        "titles": {"build-your-own-x": "Build Your Own X"},
    },
    "privacy": {
        "title": "Privacy Tools",
        "subtitle": "awesome-privacy — services & alternatives that respect your privacy",
        "homepage": "https://github.com/pluja/awesome-privacy",
        "license": "© contributors — source: github.com/pluja/awesome-privacy",
        "resolve_base": "https://github.com/pluja/awesome-privacy/blob/main/",
        "titles": {"awesome-privacy": "Privacy Tools"},
    },
    "usefulsites": {
        "title": "Useful Sites",
        "subtitle": "the best websites a programmer should visit — study, tools, news",
        "homepage": "https://github.com/sdmg15/Best-websites-a-programmer-should-visit",
        "license": "© contributors — source: github.com/sdmg15/Best-websites-a-programmer-should-visit",
        "resolve_base": "https://github.com/sdmg15/Best-websites-a-programmer-should-visit/blob/master/",
        "titles": {"best-websites": "Useful Sites"},
    },
}


def clean_desc(s: str) -> str:
    s = ANYLINK_RE.sub(r"\1", s or "")
    s = BOLD_RE.sub(r"\1", s)
    s = CODE_RE.sub(r"\1", s)
    s = EMPH_RE.sub(r"\1", s)
    s = s.replace("<br>", " ").replace("<br/>", " ")
    s = s.replace("**", " ").replace("`", " ")
    s = WS_RE.sub(" ", s).strip(" -–—:|,\t *►▷◄")
    return s[:400]


def resolve(url: str, base: str | None) -> str | None:
    if url.startswith(("http://", "https://", "mailto:")):
        if url.startswith("mailto:"):
            return None
        if IMG_URL_RE.search(url):
            return None                         # badges / images
        return url
    if url.startswith("#"):
        return None
    if base and not url.startswith("http"):
        return base + url.lstrip("./")
    return None


def strip_md(s: str) -> str:
    return clean_desc(s)


def parse_markdown(text: str, page_title: str, resolve_base: str | None):
    """Return OrderedDict {section_path: [[title, url, desc], ...]}."""
    sections: OrderedDict[str, list] = OrderedDict()
    stack: list[str] = [page_title]      # stack[0] = page title; stack[i] = heading level i

    def cur_path() -> str:
        return " / ".join(x for x in stack if x)

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip() in {"***", "---"} or line.lstrip().startswith(("<div", "<br", "</", "<img")):
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            level, title = len(m.group(1)), strip_md(m.group(2)).strip("►▷▸◄ ")
            del stack[level + 1:]        # drop deeper headings
            if len(stack) < level + 1:
                stack.extend([""] * (level + 1 - len(stack)))
            stack[level] = title
            continue
        links = []
        if line.lstrip().startswith("|"):                      # table row
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "--") for c in cells):
                continue                                       # separator row
            for ci, cell in enumerate(cells):
                lm = LINK_RE.search(cell)
                if lm:
                    url = resolve(lm.group(2), resolve_base)
                    if url:
                        title = strip_md(lm.group(1)).strip() or cell[:80]
                        tail = [c for c in cells[ci + 1:]
                                if len(c) > 3 and c.lower() not in
                                {"yes", "no", "varies", "api key", "apikey", "unknown"}]
                        desc = clean_desc(" — ".join(tail)) or clean_desc(cell)
                        links.append([title[:200], url, desc])
                    break
        else:                                                  # bullet / plain
            bullets = re.split(r"(?:^|\s)(?:[-*•]\s+)", line)
            for b in (bullets if len(bullets) > 1 else [line]):
                entries = []
                first = None
                for lm in LINK_RE.finditer(b):
                    url = resolve(lm.group(2), resolve_base)
                    if not url:
                        continue
                    title = strip_md(lm.group(1)).strip()
                    if not title or title.lower() in MIRROR_TITLES:
                        continue                       # mirror / meta link
                    tl = title.lower()
                    if tl.startswith(("back to", "◄", "◄◄", "back to wiki")) or "back to wiki" in tl:
                        continue                       # wiki navigation links
                    if first is None:
                        first = lm
                    entries.append([title[:200], url, ""])
                if not entries:
                    continue
                if re.match(r"^\s*\*+\s*\**\s*(note|⚠|❗)", b, re.I):
                    continue                           # FMHY "Note -" lines
                if first is not None:
                    entries[0][2] = clean_desc(b[first.end():])
                links.extend(entries)
        if links:
            sections.setdefault(cur_path(), []).extend(links)
    # drop sections that matched the filter (checked again post-hoc for safety)
    out: OrderedDict[str, list] = OrderedDict()
    removed_links = 0
    for path, links in sections.items():
        if DROP_SECTION_RE.search(path):
            removed_links += len(links)
            continue
        # per-link dedupe by (url)
        seen, uniq = set(), []
        for t, u, d in links:
            if u in seen:
                continue
            seen.add(u)
            uniq.append([t, u, d])
        out[path] = uniq
    return out, removed_links


def load_source_pages(source: str, cfg: dict):
    """Yield (page_id, page_title, text_or_vlibjson)."""
    d = RAW / source
    if source == "vlib":
        for fp in sorted(d.glob("*.json")):
            yield fp.stem, fp.stem, json.loads(fp.read_text(encoding="utf-8"))
        return
    title_map = cfg.get("titles") or (FMHY_TITLES if source == "fmhy" else {})
    for fp in sorted(d.glob("*.md")):
        pid = fp.stem
        yield pid, title_map.get(pid, pid.replace("-", " ").title()), fp.read_text(encoding="utf-8", errors="replace")


def build_source(source: str, cfg: dict) -> None:
    out_dir = OUT / source
    out_dir.mkdir(parents=True, exist_ok=True)
    all_sections: OrderedDict[str, list] = OrderedDict()
    pages, removed_total = [], 0
    for pid, ptitle, payload in load_source_pages(source, cfg):
        if source == "vlib":
            secs: OrderedDict[str, list] = OrderedDict()
            for item in payload:
                path = f"{ptitle} / {item['s']}" if item["s"] and item["s"] != ptitle else ptitle
                secs.setdefault(path, []).append([item["t"][:200], item["u"], ""])
            removed = 0
        else:
            secs, removed = parse_markdown(payload, ptitle, cfg["resolve_base"])
        removed_total += removed
        pages.append({"id": pid, "title": ptitle,
                      "links": sum(len(v) for v in secs.values()),
                      "sections": list(secs.keys())})
        all_sections.update(secs)

    total_links = sum(len(v) for v in all_sections.values())
    meta = {
        "source": source, "title": cfg["title"], "subtitle": cfg["subtitle"],
        "homepage": cfg["homepage"], "license": cfg["license"],
        "fetched": "2026-10-24",
        "totals": {"pages": len(pages), "sections": len(all_sections),
                   "links": total_links, "filtered_section_links": removed_total},
        "pages": pages,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    with gzip.open(out_dir / "data.json.gz", "wt", encoding="utf-8", compresslevel=9) as gz:
        json.dump([{"p": p, "l": links} for p, links in all_sections.items()],
                  gz, ensure_ascii=False, separators=(",", ":"))
    gz_size = (out_dir / "data.json.gz").stat().st_size
    print(f"[{source}] {len(pages)} pages, {len(all_sections)} sections, "
          f"{total_links:,} links ({removed_total:,} removed by filter), "
          f"data.json.gz {gz_size/1024:.0f} KB")


def main() -> None:
    for source, cfg in SOURCES.items():
        if not (RAW / source).exists():
            print(f"[{source}] SKIP — no raw data")
            continue
        build_source(source, cfg)


if __name__ == "__main__":
    main()
