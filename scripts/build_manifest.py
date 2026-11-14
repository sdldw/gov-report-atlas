"""Build data/manifest.csv from the province archives found by the probe.

Each archive page usually lists several years with titles like
"2025年河北省政府工作报告". We take every such anchor, keep the year, and
emit one manifest row per (province, year).

Output is also a coverage report: which provinces yielded which years. That
tells us exactly where manual work is still needed.

Usage:
    python scripts/build_manifest.py
    python scripts/build_manifest.py --probe data/probe/portals.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path

from probe_portals import find_report_links

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "data" / "probe" / "portals.csv"
MANIFEST = ROOT / "data" / "manifest.csv"

COLUMNS = [
    "doc_id", "code", "name", "level", "year", "kind",
    "url", "path", "sha256", "bytes", "status", "http_code", "fetched_at",
]
YEAR_RE = re.compile(r"(20\d{2})\s*年")
MIN_YEAR, MAX_YEAR = 2015, 2026


def main() -> None:
    import requests

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", type=Path, default=PROBE)
    ap.add_argument("--out", type=Path, default=MANIFEST)
    ap.add_argument("--rate", type=float, default=1.2)
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    with open(args.probe, encoding="utf-8") as fh:
        probes = list(csv.DictReader(fh))

    session = requests.Session()
    session.headers.update({
        "User-Agent": "gov-report-atlas/0.1 (academic course project)",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    found: dict[tuple[str, int], dict] = {}
    coverage: dict[str, dict[int, str]] = {}

    for row in probes:
        code, name = row["code"], row["name"]
        archive = row.get("sample_link", "")
        if not archive:
            coverage.setdefault(name, {})
            continue
        try:
            resp = session.get(archive, timeout=args.timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"{code} {name}: fetch failed ({type(exc).__name__})")
            coverage.setdefault(name, {})
            continue
        finally:
            time.sleep(args.rate)
        if resp.status_code >= 400:
            print(f"{code} {name}: HTTP {resp.status_code}")
            coverage.setdefault(name, {})
            continue

        years: dict[int, str] = {}
        for text, url in find_report_links(resp.content, resp.url):
            match = YEAR_RE.search(text)
            if not match:
                continue
            year = int(match.group(1))
            if not MIN_YEAR <= year <= MAX_YEAR:
                continue
            years.setdefault(year, url)
            found.setdefault((code, year), {
                "doc_id": f"{code}_{year}",
                "code": code,
                "name": name,
                "level": "province",
                "year": str(year),
                "kind": "work_report",
                "url": url,
                "path": "",
                "sha256": "",
                "bytes": "",
                "status": "pending",
                "http_code": "",
                "fetched_at": "",
            })
        coverage[name] = years
        print(f"{code} {name:<8} years={sorted(years)}")

    manifest_rows = sorted(found.values(), key=lambda r: (r["code"], r["year"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)

    total_years = sum(len(y) for y in coverage.values())
    print(f"\nprovinces_with_any_year={sum(1 for y in coverage.values() if y)}/{len(coverage)}")
    print(f"documents={len(manifest_rows)}  year_slots={total_years}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
