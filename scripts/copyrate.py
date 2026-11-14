"""Copy rate: how much of a provincial report is lifted from the central one?

Method
------
1. Split the central reports (2024-2026) into sentences; precompute shingles.
2. Build a 4x16-bit simhash banding index over them.
3. For each provincial sentence, collect candidates sharing a band, keep those
   with Hamming distance <= max-distance, then verify with 3-gram Jaccard.
4. Copy rate = matched sentences / eligible sentences.

Boilerplate (salutations, procedural formulae) is filtered out first: it is
technically copied by everyone and would swamp the signal.

Usage:
    python scripts/copyrate.py
    python scripts/copyrate.py --limit-docs 20      # quick sanity check
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from gra.attention import hamming, shingles, simhash
from gra.parse import parse_one

ROOT = Path(__file__).resolve().parents[1]
CENTRAL_DIR = ROOT / "data" / "raw" / "central"
TEXT_DIR = ROOT / "data" / "interim" / "text"
OUT = ROOT / "data" / "processed" / "copyrate.csv"

SENT_SPLIT = re.compile(r"[。！？；\n]+")
YEAR_RE = re.compile(r"(20\d{2})")
MIN_LEN, MAX_LEN = 15, 200
N_BANDS, BAND_BITS = 4, 16

BOILERPLATE = (
    "各位代表", "请予审议", "我代表", "致以", "衷心感谢", "在此",
    "向大会报告", "请各位", "列席", "政治协商", "代表大会第",
)


def sentences(text: str) -> list[str]:
    out = []
    for raw in SENT_SPLIT.split(text):
        sent = raw.strip()
        if not (MIN_LEN <= len(sent) <= MAX_LEN):
            continue
        if any(token in sent for token in BOILERPLATE):
            continue
        out.append(sent)
    return out


def band_keys(h: int):
    for b in range(N_BANDS):
        yield b, (h >> (b * BAND_BITS)) & ((1 << BAND_BITS) - 1)


class CentralIndex:
    def __init__(self) -> None:
        self.bands: dict[tuple[int, int], list[int]] = {}
        self.hashes: list[int] = []
        self.shingles: list[set[str]] = []

    def add(self, sent: str) -> None:
        ref = len(self.hashes)
        h = simhash(sent)
        self.hashes.append(h)
        self.shingles.append(shingles(sent))
        for key in band_keys(h):
            self.bands.setdefault(key, []).append(ref)

    def match(self, sent: str, max_distance: int, min_jaccard: float) -> bool:
        h = simhash(sent)
        grams = shingles(sent)
        seen: set[int] = set()
        for key in band_keys(h):
            for ref in self.bands.get(key, ()):
                if ref in seen:
                    continue
                seen.add(ref)
                if hamming(h, self.hashes[ref]) > max_distance:
                    continue
                other = self.shingles[ref]
                union = len(grams | other)
                if union and len(grams & other) / union >= min_jaccard:
                    return True
        return False


def load_central() -> CentralIndex:
    if not CENTRAL_DIR.exists():
        raise SystemExit(
            f"missing {CENTRAL_DIR}\n"
            "把中央报告放进去，文件名含年份，例如 central_2024.pdf"
        )
    files = [p for p in sorted(CENTRAL_DIR.iterdir())
             if p.suffix.lower() in {".pdf", ".html", ".htm"}]
    if not files:
        raise SystemExit(f"no .pdf/.html found in {CENTRAL_DIR}")

    index = CentralIndex()
    for path in files:
        match = YEAR_RE.search(path.stem)
        if not match:
            print(f"[skip] {path.name}: filename has no year")
            continue
        record = parse_one(path)
        sents = sentences(record["text"])
        for sent in sents:
            index.add(sent)
        print(f"central {match.group(1)}: {record['n_chars']} chars, {len(sents)} sentences")
    if not index.hashes:
        raise SystemExit("central index is empty")
    return index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-distance", type=int, default=3)
    ap.add_argument("--jaccard", type=float, default=0.7)
    ap.add_argument("--limit-docs", type=int, default=0)
    args = ap.parse_args()

    index = load_central()
    print(f"central sentences indexed: {len(index.hashes)}")

    paths = sorted(TEXT_DIR.glob("*.json"))
    if args.limit_docs:
        paths = paths[: args.limit_docs]

    rows = []
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        doc_id = record["doc_id"]
        local = sentences(record["text"])
        if not local:
            continue
        matched = sum(1 for sent in local if index.match(sent, args.max_distance, args.jaccard))
        rows.append({
            "doc_id": doc_id,
            "code": doc_id[:6],
            "year": int(doc_id[-4:]),
            "sentences": len(local),
            "matched": matched,
            "copy_rate": round(matched / len(local), 4),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {OUT} ({len(rows)} documents)")
    for year in sorted({r["year"] for r in rows}):
        group = [r for r in rows if r["year"] == year]
        mean = sum(r["copy_rate"] for r in group) / len(group)
        print(f"  {year}: mean copy_rate={mean:.3f}  docs={len(group)}")

    print("\ntop 5 by copy_rate:")
    for row in sorted(rows, key=lambda r: -r["copy_rate"])[:5]:
        print(f"  {row['doc_id']}  {row['copy_rate']:.3f}  ({row['matched']}/{row['sentences']})")


if __name__ == "__main__":
    main()
