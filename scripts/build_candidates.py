"""Derive per-province report candidates from the saved portal snapshots.

For every province we scan all dumped pages and keep, per year, the most
article-like link. A link is only accepted when

  * its anchor text contains a four-digit year,
  * its href resolves to http(s) — never javascript:,
  * it looks like an article (a numeric id or a /post_ style path).

The output is a candidate list, not a manifest: URLs may have rotted, so they
must be probed before being trusted.

Output: data/probe/candidates.csv  (code, name, year, url, page)
Usage:  python scripts/build_candidates.py
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from lxml import html as LH

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "data" / "probe" / "dump"
OUT = ROOT / "data" / "probe" / "candidates.csv"
SEED = ROOT / "config" / "portals_seed.yaml"

YEAR_RE = re.compile(r"(20\d{2})\s*年")
ARTICLE_RE = re.compile(r"(post_|/t20\d{4}|/\d{5,}|content_\d+|\.s?html?)", re.IGNORECASE)


def base_from_name(stem: str, domain: str) -> str:
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
    path = re.sub(r"/(s?html?|pdf)$", r".\1", path)
    base = f"{scheme}://{domain}/{path}"
    return base.rstrip("/") + "/" if trailing else base


def valid(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and "." in parsed.netloc


def score(url: str) -> int:
    """Higher is better: prefer links that look like individual articles."""
    points = 0
    if "post_" in url:
        points += 3
    if re.search(r"/t20\d{4}", url):
        points += 2
    if re.search(r"\d{5,}", url):
        points += 1
    if url.lower().endswith((".shtml", ".html", ".htm")):
        points += 1
    return points


def main() -> None:
    import yaml

    seed = yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]
    names = {p["code"]: p["name"] for p in seed}
    domains = {p["code"]: p["domain"] for p in seed}

    rows = []
    for code_dir in sorted(p for p in DUMP.iterdir() if p.is_dir()):
        code = code_dir.name
        fallback = f"https://{domains[code]}/" if code in domains else ""
        best: dict[int, tuple[int, str, str]] = {}

        for page in sorted(code_dir.glob("*.html")):
            base = base_from_name(page.stem, domains.get(code, "")) or fallback
            if not base:
                continue
            try:
                doc = LH.parse(str(page)).getroot()
            except Exception:  # noqa: BLE001
                continue
            report_anchors = sum(1 for a in doc.xpath("//a[@href]")
                                 if "工作报告" in "".join(a.itertext()))
            for anchor in doc.xpath("//a[@href]"):
                text = "".join(anchor.itertext()).strip()
                match = YEAR_RE.search(text)
                if not match:
                    continue
                href = (anchor.get("href") or "").strip()
                if not href or href.lower().startswith(("javascript:", "#", "mailto:")):
                    continue
                url = urljoin(base, href)
                if not valid(url) or not ARTICLE_RE.search(url):
                    continue
                year = int(match.group(1))
                if not 2015 <= year <= 2026:
                    continue
                # a page that genuinely lists reports gives a small bonus
                points = score(url) + (2 if report_anchors >= 2 else 0)
                if year not in best or points > best[year][0]:
                    best[year] = (points, url, page.stem)

        for year, (_points, url, page) in sorted(best.items()):
            rows.append({"code": code, "name": names.get(code, ""),
                         "year": year, "url": url, "page": page})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "year", "url", "page"])
        writer.writeheader()
        writer.writerows(rows)

    by_code: dict[str, list[int]] = {}
    for row in rows:
        by_code.setdefault(row["code"], []).append(row["year"])
    print(f"{'code':<8}{'name':<10}{'years':>6}")
    for code, years in sorted(by_code.items(), key=lambda kv: -len(kv[1])):
        print(f"{code:<8}{names.get(code, ''):<10}{len(years):>6}")
    ready = [c for c, y in by_code.items() if len(y) >= 3]
    print(f"\nprovinces={len(by_code)} with_3plus_years={len(ready)} links={len(rows)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
