"""Translation analysis: what does a concept get bound to over time?

A concept that stays a slogan sits next to adjectives. A concept that becomes
policy sits next to money, people, platforms, and pilots.

Primary measure is **sentence-level co-occurrence**: a sentence either contains
the concept and a tool word, or it does not. That has a defensible boundary and
no free parameters, unlike a character window. Window mode is kept only as a
sensitivity check.

Usage:
    python scripts/translation.py                 # sentence mode
    python scripts/translation.py --mode window --window 20
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_DIR = ROOT / "data" / "interim" / "text"
OUT = ROOT / "data" / "processed" / "translation.csv"

CONCEPT = "新质生产力"

TOOLS = {
    "funding": ["资金", "基金", "财政", "投入", "融资", "贷款", "专项债", "补贴", "奖补"],
    "talent": ["人才", "引育", "招引", "高层次", "团队", "用工"],
    "platform": ["平台", "实验室", "中心", "园区", "基地", "示范区", "集群"],
    "industry": ["产业", "制造业", "战略性新兴产业", "未来产业", "链条", "企业"],
    "institution": ["改革", "机制", "试点", "政策", "制度", "规划", "方案"],
    "digital": ["数据", "算力", "人工智能", "数字化", "智能", "场景"],
}
MODIFIERS = ["因地制宜", "加快发展", "培育", "壮大", "布局", "打造", "推动"]
CONCRETE = ("funding", "talent", "platform")

SENT_SPLIT = re.compile(r"[。！？；\n]+")


def load_docs() -> list[dict]:
    docs = []
    for path in sorted(TEXT_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        doc_id = record["doc_id"]
        docs.append({
            "doc_id": doc_id,
            "code": doc_id[:6],
            "year": int(doc_id[-4:]),
            "text": record["text"],
        })
    return docs


def contexts(text: str, mode: str, width: int) -> list[str]:
    if mode == "sentence":
        return [s for s in SENT_SPLIT.split(text) if CONCEPT in s]
    out = []
    start = 0
    while True:
        idx = text.find(CONCEPT, start)
        if idx < 0:
            break
        out.append(text[max(0, idx - width): idx + len(CONCEPT) + width])
        start = idx + len(CONCEPT)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["sentence", "window"], default="sentence")
    ap.add_argument("--window", type=int, default=20, help="only used in window mode")
    args = ap.parse_args()

    docs = load_docs()
    per_year: dict[int, dict] = defaultdict(
        lambda: {"contexts": 0, "docs": 0, "docs_with": 0, **{k: 0 for k in TOOLS},
                 "modifier": 0, "concrete": 0}
    )
    first_year: dict[str, int] = {}

    for doc in docs:
        spans = contexts(doc["text"], args.mode, args.window)
        bucket = per_year[doc["year"]]
        bucket["docs"] += 1
        bucket["contexts"] += len(spans)
        if spans:
            bucket["docs_with"] += 1
            if doc["code"] not in first_year or doc["year"] < first_year[doc["code"]]:
                first_year[doc["code"]] = doc["year"]
        for span in spans:
            hits = {name for name, words in TOOLS.items() if any(w in span for w in words)}
            for name in hits:
                bucket[name] += 1
            if hits & set(CONCRETE) or "industry" in hits:
                bucket["concrete"] += 1
            if any(m in span for m in MODIFIERS):
                bucket["modifier"] += 1

    years = sorted(per_year)
    header = ["year", "docs", "with", "spans"] + list(TOOLS) + ["concrete", "modifier"]
    print("\t".join(f"{h:>9}" for h in header))
    rows = []
    for year in years:
        b = per_year[year]
        total = b["contexts"]
        shares = {k: (b[k] / total if total else 0.0) for k in list(TOOLS) + ["concrete", "modifier"]}
        cells = [str(year), str(b["docs"]), str(b["docs_with"]), str(total)]
        cells += [f"{shares[n]:9.2f}" for n in TOOLS]
        cells += [f"{shares['concrete']:9.2f}", f"{shares['modifier']:9.2f}"]
        print("\t".join(cells))
        rows.append({
            "year": year, "docs": b["docs"], "docs_with_concept": b["docs_with"],
            "contexts": total,
            **{f"share_{k}": round(v, 4) for k, v in shares.items()},
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["year"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {OUT}")

    if first_year:
        print("\nfirst mention year by province:")
        for code, year in sorted(first_year.items(), key=lambda kv: (kv[1], kv[0])):
            print(f"  {code} {year}")


if __name__ == "__main__":
    main()
