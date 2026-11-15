"""Rebuild data/manifest.csv so it matches exactly the documents we actually parsed.

Rules:
  * keep rows whose parsed text is at least ``--min-chars`` long
  * drop rows without text (failed downloads, moved pages, empty stubs)
  * pull in any parsed doc missing from the manifest (from the backup copy)

Usage:
    python scripts/sync_manifest.py
    python scripts/sync_manifest.py --min-chars 3000
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.csv"
BACKUP = ROOT / "data" / "probe" / "head_manifest.csv"
TEXT_DIR = ROOT / "data" / "interim" / "text"

COLUMNS = [
    "doc_id", "code", "name", "level", "year", "kind",
    "url", "path", "sha256", "bytes", "status", "http_code", "fetched_at",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-chars", type=int, default=3000,
                    help="drop documents whose parsed text is shorter than this")
    args = ap.parse_args()

    chars = {p.stem: json.loads(p.read_text(encoding="utf-8"))["n_chars"]
             for p in TEXT_DIR.glob("*.json")}
    usable = {k for k, v in chars.items() if v >= args.min_chars}

    with open(MANIFEST, encoding="utf-8") as fh:
        current = {r["doc_id"]: r for r in csv.DictReader(fh)}
    backup: dict[str, dict] = {}
    if BACKUP.exists():
        with open(BACKUP, encoding="utf-8") as fh:
            backup = {r["doc_id"]: r for r in csv.DictReader(fh)}

    kept = {k: v for k, v in current.items() if k in usable}
    dropped = sorted(set(current) - set(kept))
    added = sorted(usable - set(kept))
    for doc_id in added:
        if doc_id in backup:
            kept[doc_id] = backup[doc_id]

    missing = sorted(usable - set(kept))
    rows = sorted(kept.values(), key=lambda r: (r["code"], r["year"]))
    with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"dropped={len(dropped)} {dropped[:6]}")
    print(f"added={len(added)} {added[:5]}")
    print(f"still missing={missing}")
    print(f"documents={len(rows)} provinces={len({r['code'] for r in rows})}")


if __name__ == "__main__":
    main()
