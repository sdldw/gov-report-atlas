"""How much of a provincial report comes from the central one?

Two measures, because they answer different questions:

* **copy_rate** (sentence level): share of provincial sentences that are
  near-verbatim copies of a central sentence (simhash <= 3 bits, 3-gram
  Jaccard >= 0.7). Strict: catches whole-sentence lifting.
* **gram8** (phrase level): share of a document's character 8-grams that also
  occur in the central reports. Loose: catches borrowed phrasing.

gram8 is reported twice: over the whole document, and restricted to sentences
containing the concept. The contrast between the two is the interesting part.

Usage:
    python scripts/copyrate.py
    python scripts/copyrate.py --limit-docs 20
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

CONCEPT = "新质生产力"
SENT_SPLIT = re.compile(r"[。！？；\n]+")
YEAR_RE = re.compile(r"(20\d{2})")
MIN_LEN, MAX_LEN = 15, 200
N_BANDS, BAND_BITS = 4, 16
NGRAM = 8

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


def load_central() -> tuple[CentralIndex, str]:
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
    texts: list[str] = []
    for path in files:
        match = YEAR_RE.search(path.stem)
        if not match:
            print(f"[skip] {path.name}: filename has no year")
            continue
        record = parse_one(path)
        sents = sentences(record["text"])
        for sent in sents:
            index.add(sent)
        texts.append(record["text"])
        print(f"central {match.group(1)}: {record['n_chars']} chars, {len(sents)} sentences")
    if not index.hashes:
        raise SystemExit("central index is empty")
    return index, "\n".join(texts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-distance", type=int, default=3)
    ap.add_argument("--jaccard", type=float, default=0.7)
    ap.add_argument("--limit-docs", type=int, default=0)
    args = ap.parse_args()

    index, central_text = load_central()
    central_grams = shingles(central_text, NGRAM)
    print(f"central sentences indexed: {len(index.hashes)}; {NGRAM}-grams: {len(central_grams)}")

    paths = sorted(TEXT_DIR.glob("*.json"))
    if args.limit_docs:
        paths = paths[: args.limit_docs]

    rows = []
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        doc_id = record["doc_id"]
        text = record["text"]
        local = sentences(text)
        if not local:
            continue

        matched = sum(1 for sent in local if index.match(sent, args.max_distance, args.jaccard))

        doc_grams = shingles(text, NGRAM)
        concept_sents = [s for s in SENT_SPLIT.split(text) if CONCEPT in s and len(s.strip()) >= 8]
        concept_grams: set[str] = set()
        for sent in concept_sents:
            concept_grams |= shingles(sent, NGRAM)

        rows.append({
            "doc_id": doc_id,
            "code": doc_id[:6],
            "year": int(doc_id[-4:]),
            "sentences": len(local),
            "matched": matched,
            "copy_rate": round(matched / len(local), 4),
            "gram8_overall": round(len(doc_grams & central_grams) / max(1, len(doc_grams)), 4),
            "concept_sentences": len(concept_sents),
            "gram8_concept": round(len(concept_grams & central_grams) / max(1, len(concept_grams)), 4),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {OUT} ({len(rows)} documents)")
    print(f"{'year':<6}{'docs':>5}{'copy':>8}{'gram8':>8}{'gram8_c':>10}")
    for year in sorted({r["year"] for r in rows}):
        group = [r for r in rows if r["year"] == year]
        copy_mean = sum(r["copy_rate"] for r in group) / len(group)
        gram_mean = sum(r["gram8_overall"] for r in group) / len(group)
        with_c = [r for r in group if r["concept_sentences"] > 0]
        gram_c = sum(r["gram8_concept"] for r in with_c) / len(with_c) if with_c else 0.0
        print(f"{year:<6}{len(group):>5}{copy_mean:>8.3f}{gram_mean:>8.3f}{gram_c:>10.3f}")


if __name__ == "__main__":
    main()
