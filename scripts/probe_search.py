"""Pilot: can a search engine find city work reports directly?

If this works, discovery stops being a crawling problem: we query
`site:gov.cn "<year>年政府工作报告" <city>` and take the top hit.
If it does not, the city tier is not collectible at scale and the design
must move to the provincial level.

Usage:
    python scripts/probe_search.py --sample 10
"""
from __future__ import annotations

import argparse
import csv
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ROOT / "data" / "regions.csv"
OUT = ROOT / "data" / "probe" / "search_pilot.csv"
COLUMNS = ["code", "name", "query", "n_results", "n_good", "sample_url"]
UA = "gov-report-atlas/0.1 (academic course project; contact via repository)"


def bing(session, query: str, timeout: int = 15) -> list[tuple[str, str]]:
    """Return (anchor text, href) pairs from a Bing results page."""
    from lxml import html as LH

    resp = session.get(
        "https://www.bing.com/search",
        params={"q": query, "count": 10, "setlang": "zh-CN"},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        return []
    doc = LH.fromstring(resp.text)
    out: list[tuple[str, str]] = []
    for anchor in doc.xpath('//li[contains(@class,"b_algo")]//h2//a[@href]'):
        href = anchor.get("href") or ""
        text = "".join(anchor.itertext()).strip()
        if href.startswith("http"):
            out.append((text, href))
    return out


def main() -> None:
    import requests

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--rate", type=float, default=3.0)
    ap.add_argument("--timeout", type=int, default=15)
    args = ap.parse_args()

    with open(REGIONS, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["level"] == "prefecture"]
    if args.seed:
        random.Random(args.seed).shuffle(rows)
    sample = rows[: args.sample]

    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    good_total = 0

    for row in sample:
        query = f'site:gov.cn "{args.year}年政府工作报告" {row["name"]}'
        results = bing(session, query, args.timeout)
        good = [(t, u) for t, u in results if "政府工作报告" in t]
        record = {
            "code": row["code"],
            "name": row["name"],
            "query": query,
            "n_results": str(len(results)),
            "n_good": str(len(good)),
            "sample_url": good[0][1] if good else "",
        }
        records.append(record)
        if good:
            good_total += 1
        print(f"{row['code']} {row['name']:<8} results={len(results):<3} good={len(good)}")
        time.sleep(args.rate)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    print(f"\nsearch_hit={good_total}/{len(sample)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
