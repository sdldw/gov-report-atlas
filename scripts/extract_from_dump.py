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
import re
from pathlib import Path

from probe_portals import find_report_links
from render_portals import year_entries, years_from

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "data" / "probe" / "dump"
OUT = ROOT / "data" / "probe" / "rendered_links.csv"
SEED = ROOT / "config" / "portals_seed.yaml"


def base_from_name(stem: str, domain: str) -> str:
    """Rebuild the page URL from its sanitised filename.

    Both '.' and '/' were replaced by '_' when the file was saved, so the dots
    cannot be recovered by splitting. We anchor on the known domain instead:
    'http_www_shanxi_gov_cn_szf_zfgzbg_' -> 'http://www.shanxi.gov.cn/szf/zfgzbg/'.
    """
    key = domain.replace(".", "_")
    idx = stem.find(key)
    if idx < 0:
        return ""
    scheme = stem[:idx].rstrip("_")
    if scheme not in ("http", "https"):
        return ""
    rest = stem[idx + len(key):]
    trailing = "/" if rest.endswith("_") else ""
    path = rest.strip("_").replace("_", "/")
    path = re.sub(r"/(s?html?|pdf)$", r".\1", path)  # 'index_shtml' -> 'index.shtml'
    base = f"{scheme}://{domain}/{path}"
    return base.rstrip("/") + "/" if trailing else base


def valid(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and "." in parsed.netloc


def main() -> None:
    import yaml

    seed = yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]
    names = {p["code"]: p["name"] for p in seed}
    domains = {p["code"]: p["domain"] for p in seed}

    rows = []
    for code_dir in sorted(p for p in DUMP.iterdir() if p.is_dir()):
        code = code_dir.name
        fallback = f"https://{domains[code]}/" if code in domains else ""
        best: dict[int, str] = {}
        best_page = ""
        for page in sorted(code_dir.glob("*.html")):
            base = base_from_name(page.stem, domains.get(code, "")) or fallback
            if not base:
                continue
            raw = page.read_bytes()
            found: dict[int, str] = {}
            for year, url in year_entries(raw, base).items():
                if valid(url):
                    found.setdefault(year, url)
            for text, url in find_report_links(raw, base):
                if not valid(url):
                    continue
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
