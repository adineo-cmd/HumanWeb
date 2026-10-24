#!/usr/bin/env python3
"""Re-chunk Curlie data for client-friendly browsing.

Reads public/data/curlie/chunk_*.ndjson.gz (records: [path, [[url,title,desc],...]])
and re-groups them into one file per depth-2 category. Oversized subtrees are
recursively split by the next path segment until every file is small enough.

Outputs:
  public/data/curlie/c/<name>.ndjson.gz   chunk files (record per category path)
  public/data/curlie/tree.json.gz         tree (depth<=3) with refs ("r") for data loading
  public/data/curlie/meta.json            updated (chunks key removed)
"""
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
D = BASE / "public" / "data" / "curlie"
LIMIT = 20 * 1024 * 1024          # max uncompressed bytes per chunk file
MAX_SPLIT_DEPTH = 4               # split recursion cap: groups at depth >= 4
                                  # are written as-is even if oversized
SAN_RE = re.compile(r"[^A-Za-z0-9]+")


def sanitize(path: str) -> str:
    s = SAN_RE.sub("_", path)[:44].strip("_") or "x"
    h = hashlib.md5(path.encode()).hexdigest()[:6]
    return f"{s}_{h}"


def child_key(path: str, depth: int) -> str:
    """Group key at the given segment depth (1-based)."""
    parts = path.split("/")
    return "/".join(parts[:depth])


def handle_group(key_path: str, lines: list[str], stats: dict, out_dirs: dict) -> dict:
    """Write one chunk (or recursively split). Returns a ref dict for tree.json."""
    total = sum(len(l) for l in lines)
    n_records = len(lines)
    depth = len(key_path.split("/"))
    if total <= LIMIT or depth >= MAX_SPLIT_DEPTH:
        if total > LIMIT:
            print(f"  WARNING oversized ({total/1e6:.0f} MB): {key_path}")
        name = f"{sanitize(key_path)}.ndjson.gz"
        with gzip.open(D / "c" / name, "wt", encoding="utf-8", compresslevel=9) as gz:
            for l in sorted(lines, key=lambda x: json.loads(x)[0]):
                gz.write(l + "\n" if not l.endswith("\n") else l)
        stats["files"] += 1
        stats["bytes_gz"] += (D / "c" / name).stat().st_size
        print(f"  c/{name}: {n_records:,} cats, {total/1e6:.1f} MB raw")
        return {"f": name, "n": n_records, "b": total}

    # split: route records by their prefix at depth+1 segments
    groups: dict[str, list[str]] = {}
    for l in lines:
        p = json.loads(l)[0]
        if p == key_path:
            groups.setdefault(key_path, []).append(l)   # exact path -> self
        else:
            child = "/".join(p.split("/")[:depth + 1])
            groups.setdefault(child, []).append(l)
    self_lines = groups.pop(key_path, [])
    ref: dict = {"s": 1, "n": n_records}
    if self_lines:
        name = f"{sanitize(key_path)}_self.ndjson.gz"
        with gzip.open(D / "c" / name, "wt", encoding="utf-8", compresslevel=9) as gz:
            for l in self_lines:
                gz.write(l + "\n" if not l.endswith("\n") else l)
        stats["files"] += 1
        ref["f"] = name
        print(f"  c/{name}: self {len(self_lines):,} cats")
    kids = {}
    for child_path, clines in sorted(groups.items()):
        kids[child_path] = handle_group(child_path, clines, stats, out_dirs)
    ref["k"] = kids
    return ref


def main() -> None:
    (D / "c").mkdir(exist_ok=True)
    stats = {"files": 0, "bytes_gz": 0, "records": 0}

    # ---- pass A: route every record to its depth-2 group -------------------
    depth2: dict[str, list[str]] = {}
    old_chunks = sorted(D.glob("c/*.ndjson.gz")) + sorted(D.glob("chunk_*.ndjson.gz"))
    print(f"reading {len(old_chunks)} input chunk files ...")
    skipped = 0
    for fp in old_chunks:
        with gzip.open(fp, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                p = json.loads(line)[0]
                if p.startswith("__unsorted__"):
                    skipped += 1
                    continue
                key = "/".join(p.split("/")[:2]) if "/" in p else p
                depth2.setdefault(key, []).append(line)
                stats["records"] += 1
    print(f"{stats['records']:,} records ({skipped} unsorted dropped) in {len(depth2)} depth-2 groups")
    for fp in old_chunks:
        fp.unlink()
    shutil.rmtree(D / "c", ignore_errors=True)
    (D / "c").mkdir(exist_ok=True)

    # ---- pass B: write files (recursive split where needed) ----------------
    print("writing chunks ...")
    refs = {}
    for key in sorted(depth2):
        refs[key] = handle_group(key, depth2.pop(key), stats, {})
    print(f"done: {stats['files']} files, {stats['bytes_gz']/1e6:.0f} MB gz total")

    # ---- pass C: build pruned tree with refs -------------------------------
    print("building tree.json ...")
    with gzip.open(D / "index.json.gz", "rt", encoding="utf-8") as f:
        roots = json.load(f)

    def slim(node, depth):
        out = {"t": node["t"], "n": node["n"], "tot": node["tot"]}
        if depth <= 2 and node.get("d"):
            out["d"] = node["d"]
        kids = [slim(ch, depth + 1) for ch in node.get("c", [])] if depth < 3 else []
        if kids:
            out["c"] = kids
        return out

    def attach_ref(node, path, depth):
        # refs live on depth-1 (if no depth-2 grouping matched) and depth-2 nodes
        r = refs.get(path)
        if r:
            node["r"] = r
        if depth < 3:
            for ch in node.get("c", []):
                attach_ref(ch, f"{path}/{ch['t'].replace(' ', '_')}", depth + 1)

    slim_roots = []
    for root in roots:
        path = root["t"].replace(" ", "_")
        s = slim(root, 1)
        attach_ref(s, path, 1)
        slim_roots.append(s)

    with gzip.open(D / "tree.json.gz", "wt", encoding="utf-8", compresslevel=9) as gz:
        json.dump(slim_roots, gz, ensure_ascii=False, separators=(",", ":"))
    size = (D / "tree.json.gz").stat().st_size
    print(f"tree.json.gz: {size/1e6:.1f} MB")

    # ---- meta.json cleanup --------------------------------------------------
    meta_p = D / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta.pop("chunks", None)
    meta["layout"] = "depth2-recursive-v1"
    meta["totals"]["chunk_files"] = stats["files"]
    meta_p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print("meta.json updated")


if __name__ == "__main__":
    main()
