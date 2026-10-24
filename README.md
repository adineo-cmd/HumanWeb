# HumanWeb

A human-curated map of the web. Eleven directory sources, one tab each — **never mixed**:

| Tab | Source | Links |
| --- | --- | --- |
| Curlie | [curlie.org](https://curlie.org) full dump (2026-02-02) — adult & anime excluded | ~2.62 M |
| FMHY | [r/FREEMEDIAHECKYEAH](https://fmhy.net) | ~23.9 k |
| Awesome | [sindresorhus/awesome](https://github.com/sindresorhus/awesome) | ~0.7 k |
| Self-Hosted | [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted) | ~2.9 k |
| Free for Dev | [ripienaar/free-for-dev](https://github.com/ripienaar/free-for-dev) | ~1.4 k |
| VLib | [WWW Virtual Library](https://vlib.org) | ~2.6 k |
| Public APIs | [public-apis/public-apis](https://github.com/public-apis/public-apis) | ~2.2 k |
| Dev Books | [EbookFoundation/free-programming-books](https://github.com/EbookFoundation/free-programming-books) | ~2.5 k |
| Build Your Own X | [danistefanovic/build-your-own-x](https://github.com/danistefanovic/build-your-own-x) | ~0.4 k |
| Privacy Tools | [pluja/awesome-privacy](https://github.com/pluja/awesome-privacy) | ~0.7 k |
| Useful Sites | [sdmg15/Best-websites-a-programmer-should-visit](https://github.com/sdmg15/Best-websites-a-programmer-should-visit) | ~0.7 k |

Tap a tab and that source's data loads underneath it — each tab fetches only its
own files under `public/data/<source>/`, so the datasets can't mix.

## The site

Static [Astro](https://astro.build) app (`src/pages/index.astro`). All data lives
in `public/data/` and is fetched + gunzipped in the browser
(`DecompressionStream`), so no server is needed — GitHub Pages / Netlify / any
static host works.

- **Curlie tab** — browse 528 k categories: the ~0.1 MB `tree.json.gz` index
  loads instantly; clicking a category lazy-loads one chunk file from
  `public/data/curlie/c/` (per second-level category, recursively split so no
  file is huge). A breadcrumb bar, per-category filter, and "show more" keep it
  usable at 2.6 M links. Deep links work: `#curlie/Arts/Animation/Anime`.
- **Other tabs** — whole source loads once (~7–440 KB gz); page chips + sections
  + instant client-side search.

## Data pipeline

Requires Python 3.10+.

```sh
# 1. download the official curlie dump (see https://curlie.org/download)
curl -LO https://share.innkube.fim.uni-passau.de/curlie-rdf/curlie-rdf-all.tar.gz
mkdir -p ~/curlie_data/extracted && tar -xzf curlie-rdf-all.tar.gz -C ~/curlie_data/extracted

# 2. extract everything (excludes Adult tree + any anime category)
python3 scripts/parse_curlie.py ~/curlie_data/extracted/curlie-rdf

# 3. re-chunk for the web UI (per-depth-2 files, recursive split)
python3 scripts/rechunk_curlie.py

# 4. other sources (downloads markdown lists + scrapes vlib.org into sources_raw/)
python3 scripts/fetch_sources.py
python3 scripts/parse_sources.py

# 5. tab catalog
python3 scripts/make_sources_index.py
```

Verification numbers for every run land in `data-reports/curlie_report.json`
(records parsed, duplicates dropped, excluded adult/anime counts, unknown ids…).

### Content policy

- The entire `Adult` top-level tree is excluded, as is **any category whose path
  contains "anime"** (in any language), per project requirements.
- Filtered counts are in the report (`excluded_links_adult`, `excluded_links_anime`,
  `cats_excluded_*`).
- Section-level filtering (same terms) is applied to the markdown sources too.

### Licenses

Each source keeps its own license, shown in the site footer: Curlie Directory
License, FMHY community terms, CC0 (Awesome), CC-BY-SA (Self-Hosted), ©
contributors (free-for-dev), © The WWW Virtual Library (VLib). Raw copies of the
fetched sources are kept in `sources_raw/` for provenance.

## Development

```sh
npm install
npm run dev        # http://localhost:4321
npm run build      # static output in dist/
```
