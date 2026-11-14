"""Validate and merge the region sample frame.

Input:
  data/regions_seed.csv   provinces (complete) + a few prefecture samples
  optional --extra CSV    prefecture rows, either in canonical columns
                          (code,name,level,province,...) or in the raw
                          国家统计局 style (行政区划代码,名称,所属省级行政区)

Output:
  data/regions.csv        validated, deduplicated

Usage:
  python scripts/build_regions.py --extra data/prefectures_raw.csv
  python scripts/build_regions.py --check
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "regions_seed.csv"
OUT = ROOT / "data" / "regions.csv"
COLUMNS = ["code", "name", "level", "province", "portal_url", "adapter"]
LEVELS = {"province", "prefecture"}

# raw header -> canonical column
ALIASES = {
    "行政区划代码": "code",
    "代码": "code",
    "名称": "name",
    "地区": "name",
    "所属省级行政区": "province",
    "所属省": "province",
    "省份": "province",
    "级别": "level",
}


def read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            row = {}
            for key, value in raw.items():
                if key is None:
                    continue
                col = ALIASES.get(key.strip(), key.strip())
                row[col] = (value or "").strip()
            if not row.get("code"):
                continue
            for col in COLUMNS:
                row.setdefault(col, "")
            if not row["level"]:
                # province codes end with 0000, everything else is prefecture
                row["level"] = "province" if row["code"].endswith("0000") else "prefecture"
            rows.append(row)
    return rows


def score(row: dict) -> int:
    """Prefer the richer duplicate (e.g. the seed row that already has an adapter)."""
    return sum(1 for col in COLUMNS if row.get(col))


def validate(rows: list[dict], province_names: set[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for i, row in enumerate(rows, start=2):
        code = row["code"]
        if not (len(code) == 6 and code.isdigit()):
            errors.append(f"line {i}: bad code {code!r}")
        if row["level"] not in LEVELS:
            errors.append(f"line {i}: bad level {row['level']!r}")
        if code in seen:
            errors.append(f"line {i}: duplicate code {code}")
        seen.add(code)
        if row["level"] == "prefecture":
            if not row["province"]:
                errors.append(f"line {i}: {row['name']} missing province")
            elif row["province"] not in province_names:
                errors.append(f"line {i}: unknown province {row['province']!r}")
        if not row["name"].endswith(("省", "市", "自治区", "自治州", "地区", "盟")):
            errors.append(f"line {i}: suspicious name {row['name']!r}")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=Path, default=SEED)
    ap.add_argument("--extra", type=Path, default=None)
    ap.add_argument("--check", action="store_true", help="validate only")
    args = ap.parse_args()

    seed_rows = read_rows(args.seed)
    province_names = {r["name"] for r in seed_rows if r["level"] == "province"}
    print(f"seed provinces={len(province_names)}")

    rows = seed_rows + (read_rows(args.extra) if args.extra else [])

    merged: dict[str, dict] = {}
    for row in rows:
        current = merged.get(row["code"])
        if current is None or score(row) > score(current):
            merged[row["code"]] = row
    merged_rows = sorted(merged.values(), key=lambda r: r["code"])

    errors = validate(merged_rows, province_names)
    provinces = [r for r in merged_rows if r["level"] == "province"]
    prefectures = [r for r in merged_rows if r["level"] == "prefecture"]
    print(f"rows={len(merged_rows)} provinces={len(provinces)} prefectures={len(prefectures)}")

    dist = Counter(r["province"] for r in prefectures)
    missing = sorted(province_names - set(dist))
    print(f"provinces_without_prefectures={missing or 'none'}")

    if errors:
        for err in errors[:20]:
            print("[error]", err)
        raise SystemExit(f"{len(errors)} validation errors")
    if args.check:
        print("[ok] validation passed")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(merged_rows)
    print(f"wrote {OUT} ({len(merged_rows)} rows)")


if __name__ == "__main__":
    main()
