"""Build data/manifest.csv from province report archives.

For each province we try several candidate entry points and keep the one that
yields the most year-tagged report links:

  1. the URL the probe found
  2. its parent directory (probe sometimes lands on a single article)
  3. well-known disclosure paths on the same domain

Pagination links (index_2.shtml, ?page=2) are followed a couple of steps.

Existing rows in the manifest are preserved by doc_id, so re-running does not
force a re-download of files already fetched.

Usage:
    python scripts/build_manifest.py
    python scripts/build_manifest.py --deep
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from probe_portals import find_report_links

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "data" / "probe" / "portals.csv"
SEED = ROOT / "config" / "portals_seed.yaml"
MANIFEST = ROOT / "data" / "manifest.csv"

COLUMNS = [
    "doc_id", "code", "name", "level", "year", "kind",
    "url", "path", "sha256", "bytes", "status", "http_code", "fetched_at",
]
YEAR_RE = re.compile(r"(20\d{2})\s*年")
YEAR_IN_URL = re.compile(r"/(20\d{2})[/_\-]")
PAGE_RE = re.compile(r"(index[_\-]\d+\.(?:s?html?))|([?&]page=\d+)", re.IGNORECASE)
DISCLOSURE_PATHS = ["/zfxxgk/zfgzbg/", "/zwgk/zfgzbg/", "/xxgk/zfgzbg/", "/zfgzbg/"]
MIN_YEAR, MAX_YEAR = 2015, 2026


def years_from(html: bytes, base_url: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for text, url in find_report_links(html, base_url):
        match = YEAR_RE.search(text)
        year = int(match.group(1)) if match else None
        if year is None:
            # many portals put the year in the path, not in the anchor text
            fallback = YEAR_IN_URL.search(url)
            year = int(fallback.group(1)) if fallback else None
        if year is None or not MIN_YEAR <= year <= MAX_YEAR:
            continue
        out.setdefault(year, url)
    return out


def pagination_urls(html: bytes, base_url: str, limit: int = 3) -> list[str]:
    from lxml import html as LH

    doc = LH.fromstring(html)
    out: list[str] = []
    seen: set[str] = set()
    for anchor in doc.xpath("//a[@href]"):
        href = (anchor.get("href") or "").strip()
        if not href or not PAGE_RE.search(href):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
        if len(out) >= limit:
            break
    return out


def candidates(row: dict, domain: str) -> list[str]:
    out: list[str] = []
    sample = row.get("sample_link", "")
    if sample:
        out.append(sample)
        parent = sample.rstrip("/").rsplit("/", 1)[0] + "/"
        if parent not in out:
            out.append(parent)
    if domain:
        base = f"https://{domain}"
        for path in DISCLOSURE_PATHS:
            url = base + path
            if url not in out:
                out.append(url)
    return out


def fetch_years(session, url: str, timeout: int) -> dict[int, str]:
    try:
        resp = session.get(url, timeout=timeout)
    except Exception:  # noqa: BLE001
        return {}
    if resp.status_code >= 400:
        return {}
    found = years_from(resp.content, resp.url)
    for page in pagination_urls(resp.content, resp.url):
        try:
            extra = session.get(page, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        if extra.status_code < 400:
            for year, link in years_from(extra.content, extra.url).items():
                found.setdefault(year, link)
    return found


def main() -> None:
    import requests
    import yaml

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", type=Path, default=PROBE)
    ap.add_argument("--out", type=Path, default=MANIFEST)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    with open(args.probe, encoding="utf-8") as fh:
        probes = list(csv.DictReader(fh))
    domains = {p["code"]: p["domain"]
               for p in yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]}

    existing: dict[str, dict] = {}
    if args.out.exists():
        with open(args.out, encoding="utf-8") as fh:
            existing = {r["doc_id"]: r for r in csv.DictReader(fh)}

    session = requests.Session()
    session.headers.update({
        "User-Agent": "gov-report-atlas/0.1 (academic course project)",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    manifest: dict[str, dict] = {}
    for row in probes:
        code, name = row["code"], row["name"]
        best: dict[int, str] = {}
        best_url = ""
        for url in candidates(row, domains.get(code, "")):
            found = fetch_years(session, url, args.timeout)
            if len(found) > len(best):
                best, best_url = found, url
            if len(best) >= 8:
                break
        print(f"{code} {name:<8} years={len(best):2d}  <- {best_url or 'none'}")
        for year, url in best.items():
            doc_id = f"{code}_{year}"
            old = existing.get(doc_id, {})
            keep = old.get("status") == "ok" and old.get("url") == url
            manifest[doc_id] = {
                "doc_id": doc_id,
                "code": code,
                "name": name,
                "level": "province",
                "year": str(year),
                "kind": "work_report",
                "url": url,
                "path": old.get("path", "") if keep else "",
                "sha256": old.get("sha256", "") if keep else "",
                "bytes": old.get("bytes", "") if keep else "",
                "status": "ok" if keep else "pending",
                "http_code": old.get("http_code", "") if keep else "",
                "fetched_at": old.get("fetched_at", "") if keep else "",
            }

    rows = sorted(manifest.values(), key=lambda r: (r["code"], r["year"]))
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    covered = {r["code"] for r in rows}
    print(f"\nprovinces_with_any_year={len(covered)}/{len(probes)}")
    print(f"documents={len(rows)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
