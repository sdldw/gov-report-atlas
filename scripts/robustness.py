"""Robustness checks reported in section 5.

1. alternative denominator: mentions per 1,000 sentences instead of characters
2. leave-one-province-out: does the rising trend survive dropping each province?
3. variant merging: is the trend sensitive to counting only the exact string?

Usage:
    python scripts/robustness.py
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_DIR = ROOT / "data" / "interim" / "text"
PANEL = ROOT / "data" / "processed" / "panel.csv"

CONCEPT = "新质生产力"
VARIANTS = ["新质生产力", "新质生产力发展", "新质生产力布局"]
SENT_SPLIT = re.compile(r"[。！？；\n]+")
YEARS = [2024, 2025, 2026]


def load() -> list[dict]:
    docs = []
    for path in sorted(TEXT_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        doc_id = record["doc_id"]
        text = record["text"]
        sents = [s for s in SENT_SPLIT.split(text) if len(s.strip()) >= 8]
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        docs.append({
            "doc_id": doc_id,
            "code": doc_id[:6],
            "year": int(doc_id[-4:]),
            "chars": cjk,
            "sents": len(sents),
            "mentions": text.count(CONCEPT),
            "mentions_variants": sum(text.count(v) for v in VARIANTS),
        })
    return docs


def balanced(docs: list[dict]) -> set[str]:
    by_year: dict[int, set[str]] = defaultdict(set)
    for d in docs:
        by_year[d["year"]].add(d["code"])
    years = sorted(by_year)
    return set.intersection(*(by_year[y] for y in years))


def means(docs: list[dict], field: str, ratio: str) -> dict[int, float]:
    out = {}
    for year in YEARS:
        group = [d for d in docs if d["year"] == year]
        out[year] = sum(d[field] / max(1, d[ratio]) * 1000 for d in group) / max(1, len(group))
    return out


def main() -> None:
    docs = load()
    codes = balanced(docs)
    core = [d for d in docs if d["code"] in codes]

    print(f"balanced provinces={len(codes)} docs={len(core)}")

    print("\n[A] denominators: per 1,000 chars vs per 1,000 sentences")
    per_char = means(core, "mentions", "chars")
    per_sent = means(core, "mentions", "sents")
    for year in YEARS:
        print(f"  {year}  per_chars={per_char[year]:6.3f}  per_sentences={per_sent[year]:7.3f}")

    print("\n[B] leave-one-province-out (per 1,000 chars)")
    kept = 0
    for drop in sorted(codes):
        subset = [d for d in core if d["code"] != drop]
        series = means(subset, "mentions", "chars")
        monotone = series[YEARS[0]] < series[YEARS[1]] < series[YEARS[2]]
        kept += monotone
        flag = "ok" if monotone else "BREAKS"
        print(f"  drop {drop}: {series[2024]:.3f} -> {series[2025]:.3f} -> {series[2026]:.3f}  {flag}")
    print(f"  monotone in {kept}/{len(codes)} leave-one-out samples")


if __name__ == "__main__":
    main()
