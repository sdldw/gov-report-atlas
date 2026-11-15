"""Recover year -> article-url pairs from previously dumped portal pages.

The dumps under data/probe/dump/<code>/ were taken with --dump during a render
run. Re-parsing them offline is much cheaper than re-driving the browser, and it
lets us apply extraction fixes retroactively.

The dump filename encodes the original URL (scheme_host_path, joined by "_"), so
relative hrefs can be resolved correctly without any network access.

Output: data/probe/rendered_links.csv  (code, name, year, url)
Usage:  python scripts/extract_from_dump.py
"""
from __future__ import annotations

import csv
from pathlib import Path

from probe_portals import find_report_links
from render_portals import year_entries, years_from

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "data" / "probe" / "dump"
OUT = ROOT / "data" / "probe" / "rendered_links.csv"
SEED = ROOT / "config" / "portals_seed.yaml"


def base_from_name(stem: str) -> str:
    """'https_www_gd_gov_cn_zwgk_zfgzbg_index_html' -> 'https://www.gd.gov.cn/...'."""
    if "_" not in stem:
        return ""
    scheme, rest = stem.split("_", 1)
    if scheme not in ("http", "https"):
        return ""
    return f"{scheme}://" + rest.replace("_", "/")


def main() -> None:
    import yaml

    names = {p["code"]: p["name"]
             for p in yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]}

    rows = []
    for code_dir in sorted(p for p in DUMP.iterdir() if p.is_dir()):
        code = code_dir.name
        best: dict[int, str] = {}
        best_page = ""
        for page in sorted(code_dir.glob("*.html")):
            base = base_from_name(page.stem)
            if not base:
                continue
            raw = page.read_bytes()
            found: dict[int, str] = {}
            for year, url in year_entries(raw, base).items():
                found.setdefault(year, url)
            for text, url in find_report_links(raw, base):
                for year, target in years_from([(text, url)]).items():
                    found.setdefault(year, target)
            if len(found) > len(best):
                best, best_page = found, page.stem
        if not best:
            continue
        print(f"{code} {names.get(code, ''):<8} years={len(best):2d}  <- {best_page[:55]}")
        for year, url in sorted(best.items()):
            rows.append({"code": code, "name": names.get(code, ""),
                         "year": year, "url": url})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "year", "url"])
        writer.writeheader()
        writer.writerows(rows)

    provinces = len({r["code"] for r in rows}) if rows else 0
    print(f"\nprovinces={provinces} links={len(rows)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
