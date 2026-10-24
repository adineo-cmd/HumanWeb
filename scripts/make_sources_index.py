#!/usr/bin/env python3
"""Build public/data/index.json — the small catalog the site tabs read first."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "public" / "data"

ORDER = ["curlie", "fmhy", "awesome", "selfhosted", "freefordev", "vlib"]
GENERIC = {
    "fmhy": ("FMHY", "r/FREEMEDIAHECKYEAH — the big list of free media & tools", "https://fmhy.net"),
    "awesome": ("Awesome", "sindresorhus/awesome — curated lists about everything", "https://github.com/sindresorhus/awesome"),
    "selfhosted": ("Self-Hosted", "awesome-selfhosted — free network services you can host yourself", "https://awesome-selfhosted.net"),
    "freefordev": ("Free for Dev", "SaaS / PaaS / IaaS with generous free tiers for developers", "https://free-for.dev"),
    "vlib": ("VLib", "The WWW Virtual Library — the oldest catalogue of the web (est. 1991)", "https://vlib.org"),
}

out = {"generated": "2026-10-24", "sources": []}
for sid in ORDER:
    p = OUT / sid / "meta.json"
    if not p.exists():
        continue
    m = json.loads(p.read_text(encoding="utf-8"))
    if sid == "curlie":
        out["sources"].append({
            "id": "curlie", "title": "Curlie",
            "subtitle": m.get("subtitle", ""),
            "homepage": "https://curlie.org",
            "links": m["totals"]["links_kept"],
            "note": f"dump {m.get('dump_date','')} · adult & anime excluded",
        })
    else:
        title, subtitle, homepage = GENERIC[sid]
        out["sources"].append({
            "id": sid, "title": m.get("title", title),
            "subtitle": m.get("subtitle", subtitle),
            "homepage": m.get("homepage", homepage),
            "links": m["totals"]["links"],
            "note": "",
        })
(OUT / "index.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps([(s["id"], s["links"]) for s in out["sources"]]))
