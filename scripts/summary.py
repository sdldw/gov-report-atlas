"""Summarise the panel: coverage, and mean concept attention by year.

ASCII-safe layout so it survives any Windows console codepage; concept names
are printed as-is, so run `chcp 65001` first if they look garbled.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel.csv"
CONCEPTS = ROOT / "config" / "concepts.yaml"


def main() -> None:
    import yaml

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    concepts = list(yaml.safe_load(CONCEPTS.read_text(encoding="utf-8"))["concepts"])
    with open(PANEL, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("panel.csv is empty; run `python -m gra.attention` first")

    provinces = {r["doc_id"][:6] for r in rows}
    years = sorted(r["doc_id"][-4:] for r in rows)
    chars = [int(r["n_chars"]) for r in rows]
    print(f"docs={len(rows)} provinces={len(provinces)} years={years[0]}-{years[-1]}")
    print(f"chars: min={min(chars)} median={sorted(chars)[len(chars) // 2]} max={max(chars)}")

    by_year: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_year[row["doc_id"][-4:]].append(row)

    header = ["year", "n"] + concepts
    print("\n" + "\t".join(header))
    for year in sorted(by_year):
        group = by_year[year]
        cells = [f"{mean(float(r['share_' + c]) for r in group):7.2f}" for c in concepts]
        print("\t".join([year, f"{len(group):3d}"] + cells))

    primary = concepts[0]
    ranked = sorted(rows, key=lambda r: -float(r["share_" + primary]))
    print(f"\ntop 8 by share_{primary}:")
    for row in ranked[:8]:
        print(f"  {row['doc_id']}  share={float(row['share_' + primary]):6.2f}  chars={row['n_chars']}")


if __name__ == "__main__":
    main()
