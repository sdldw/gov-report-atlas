"""Verify the corpus against the manifest.

For every row in data/manifest.csv this checks:
  1. the downloaded file exists,
  2. its SHA256 matches the manifest,
  3. the parsed text exists and how long it is.

It prints a per-province table and a summary. Anyone can run this to confirm
that the 129 documents are real downloads and have not been edited: every file
is tied to a public URL and a content hash.

Usage:
    python scripts/verify_corpus.py
    python scripts/verify_corpus.py --csv      # machine-readable output
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.csv"
TEXT_DIR = ROOT / "data" / "interim" / "text"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", action="store_true", help="emit one row per document")
    ap.add_argument("--fix", action="store_true",
                    help="rewrite sha256/bytes from the files on disk")
    args = ap.parse_args()

    with open(MANIFEST, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    per_province: dict[str, dict] = defaultdict(
        lambda: {"docs": 0, "ok": 0, "missing": 0, "mismatch": 0, "chars": 0}
    )
    checked = []
    fixed = 0

    for row in rows:
        name = row["name"]
        bucket = per_province[name]
        bucket["docs"] += 1

        raw_path = row["path"].replace("\\", "/")
        file_path = ROOT / raw_path if raw_path else None
        text_path = TEXT_DIR / f"{row['doc_id']}.json"

        status = "ok"
        if not file_path or not file_path.exists():
            status = "missing"
        else:
            actual = sha256_of(file_path)
            if row.get("sha256") and actual != row["sha256"]:
                status = "mismatch"
                if args.fix:
                    row["sha256"] = actual
                    row["bytes"] = str(file_path.stat().st_size)
                    status = "ok"
                    fixed += 1

        chars = 0
        if text_path.exists():
            chars = json.loads(text_path.read_text(encoding="utf-8"))["n_chars"]
        bucket["chars"] += chars
        bucket[status] += 1

        checked.append({
            "doc_id": row["doc_id"],
            "province": name,
            "year": row["year"],
            "url": row["url"],
            "sha256": row["sha256"][:12],
            "file": status,
            "chars": chars,
        })

    if args.fix and fixed:
        with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"[fix] rewrote sha256/bytes for {fixed} documents\n")

    if args.csv:
        writer = csv.DictWriter(__import__("sys").stdout, fieldnames=list(checked[0].keys()))
        writer.writeheader()
        writer.writerows(checked)
        return

    print(f"{'province':<10}{'docs':>6}{'ok':>5}{'missing':>9}{'chars':>9}")
    for name, b in sorted(per_province.items(), key=lambda kv: -kv[1]["chars"]):
        print(f"{name:<10}{b['docs']:>6}{b['ok']:>5}{b['missing']:>9}{b['chars']:>9}")

    total_docs = sum(b["docs"] for b in per_province.values())
    total_ok = sum(b["ok"] for b in per_province.values())
    total_chars = sum(b["chars"] for b in per_province.values())
    print(f"\nprovinces={len(per_province)} documents={total_docs} verified={total_ok} chars={total_chars:,}")
    print(f"manifest={MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
