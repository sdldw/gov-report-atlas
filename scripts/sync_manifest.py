"""Rebuild data/manifest.csv so it matches exactly the documents we actually parsed.

Rules:
  * keep rows whose doc_id has a parsed text file
  * drop rows without text (failed downloads, moved pages)
  * pull in any parsed doc missing from the manifest (from the backup copy)
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.csv"
BACKUP = Path("/tmp/head_manifest.csv")
TEXT_DIR = ROOT / "data" / "interim" / "text"

COLUMNS = [
    "doc_id", "code", "name", "level", "year", "kind",
    "url", "path", "sha256", "bytes", "status", "http_code", "fetched_at",
]


def main() -> None:
    text_ids = {p.stem for p in TEXT_DIR.glob("*.json")}

    with open(MANIFEST, encoding="utf-8") as fh:
        current = {r["doc_id"]: r for r in csv.DictReader(fh)}
    backup: dict[str, dict] = {}
    if BACKUP.exists():
        with open(BACKUP, encoding="utf-8") as fh:
            backup = {r["doc_id"]: r for r in csv.DictReader(fh)}

    kept = {k: v for k, v in current.items() if k in text_ids}
    dropped = sorted(set(current) - set(kept))
    added = sorted(text_ids - set(kept))
    for doc_id in added:
        if doc_id in backup:
            kept[doc_id] = backup[doc_id]

    missing = sorted(text_ids - set(kept))
    rows = sorted(kept.values(), key=lambda r: (r["code"], r["year"]))
    with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"dropped={len(dropped)} {dropped[:5]}")
    print(f"added={len(added)} {added[:5]}")
    print(f"still missing={missing}")
    print(f"documents={len(rows)} provinces={len({r['code'] for r in rows})}")


if __name__ == "__main__":
    main()
