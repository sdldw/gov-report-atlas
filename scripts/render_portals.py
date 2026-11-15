"""Render JavaScript-heavy portals with a headless browser.

Seventeen provincial portals publish their work-report archives through JS, so
static requests see an empty shell. This script drives Chromium and does a small
breadth-first crawl: from the homepage it follows links that look like a
disclosure section, at most two levels deep, until enough year-tagged report
links are collected.

Usage:
    python scripts/render_portals.py --codes 440000 --dump
    python scripts/render_portals.py --all --rate 2
    python scripts/render_portals.py --all --merge
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from probe_portals import find_report_links

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config" / "portals_seed.yaml"
PROBE = ROOT / "data" / "probe" / "portals.csv"
OUT = ROOT / "data" / "probe" / "rendered.csv"
DUMP_DIR = ROOT / "data" / "probe" / "dump"

COLUMNS = ["code", "name", "home", "archive", "n_links", "n_years", "years", "error"]
MAX_DEPTH = 2
MAX_PAGES = 8
SECTION_RE = re.compile(r"(zfgzbg|zfgb|gzbg|工作报告|xxgk|govopen)", re.IGNORECASE)
YEAR_TEXT = re.compile(r"(20\d{2})\s*年")
YEAR_URL = re.compile(r"/(20\d{2})[/_\-]")


def render(page, url: str, timeout: int) -> bytes:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(1200)
    return page.content().encode("utf-8")


def years_from(links: list[tuple[str, str]]) -> dict[int, str]:
    out: dict[int, str] = {}
    for text, url in links:
        match = YEAR_TEXT.search(text)
        year = int(match.group(1)) if match else None
        if year is None:
            match = YEAR_URL.search(url)
            year = int(match.group(1)) if match else None
        if year is not None and 2015 <= year <= 2026:
            out.setdefault(year, url)
    return out


def year_entries(html: bytes, base_url: str) -> dict[int, str]:
    """Archive pages often list entries as bare "2025年" anchors.

    find_report_links requires the phrase 政府工作报告, so those entries are
    invisible to it; this picks them up by shape instead.
    """
    from lxml import html as LH

    try:
        doc = LH.fromstring(html.decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[int, str] = {}
    for anchor in doc.xpath("//a[@href]"):
        text = "".join(anchor.itertext()).strip()
        match = re.fullmatch(r"(20\d{2})\s*年(度)?", text)
        if not match:
            continue
        year = int(match.group(1))
        if 2015 <= year <= 2026:
            out.setdefault(year, urljoin(base_url, anchor.get("href")))
    return out


def registrable(url: str) -> str:
    host = urlparse(url).netloc.split(":")[0]
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 else host


def section_links(html: bytes, base_url: str, limit: int = 4) -> list[str]:
    from lxml import html as LH

    try:
        doc = LH.fromstring(html.decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001
        return []
    site = registrable(base_url)
    out: list[str] = []
    seen: set[str] = set()
    for anchor in doc.xpath("//a[@href]"):
        href = (anchor.get("href") or "").strip()
        if not href or href.lower().startswith(("javascript:", "#", "mailto:")):
            continue
        absolute = urljoin(base_url, href)
        if registrable(absolute) != site or absolute in seen:
            continue
        text = "".join(anchor.itertext()).strip()
        if SECTION_RE.search(href) or "工作报告" in text:
            seen.add(absolute)
            out.append(absolute)
        if len(out) >= limit:
            break
    return out


def crawl(page, start: str, timeout: int, dump: Path | None = None):
    """Breadth-first from ``start``; returns (links, years, pages, final_home)."""
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(start, 0)]
    links: list[tuple[str, str]] = []
    years: dict[int, str] = {}
    archive = ""
    pages = 0
    home = start

    while queue and pages < MAX_PAGES:
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = render(page, url, timeout)
        except Exception:  # noqa: BLE001
            continue
        pages += 1
        if pages == 1:
            home = page.url
        if dump is not None:
            dump.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^\w]+", "_", url)[:80]
            (dump / f"{safe}.html").write_bytes(html)

        page_links = find_report_links(html, page.url)
        links.extend(page_links)
        for year, target in years_from(page_links).items():
            years.setdefault(year, target)
        found = year_entries(html, page.url)
        if found and archive == "":
            archive = page.url
        for year, target in found.items():
            years.setdefault(year, target)

        if len(years) >= 3:
            break
        if depth < MAX_DEPTH:
            for cand in section_links(html, page.url):
                if cand not in seen:
                    queue.append((cand, depth + 1))
    return links, years, archive, pages, home


def main() -> None:
    import yaml
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codes", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=30000)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    seed = yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        seed = [p for p in seed if p["code"] in wanted]
    if not args.all and not args.codes:
        ap.error("give --codes or --all")

    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        )
        page = context.new_page()

        for item in seed:
            record = {k: "" for k in COLUMNS}
            record.update(code=item["code"], name=item["name"])
            home = f"https://{item['domain']}/"
            try:
                dump = (DUMP_DIR / item["code"]) if args.dump else None
                links, years, archive, pages, final_home = crawl(page, home, args.timeout, dump)
                record.update(
                    home=final_home,
                    n_links=str(len(links)),
                    n_years=str(len(years)),
                    years="|".join(str(y) for y in sorted(years)),
                    archive=archive,
                )
                record["error"] = f"pages={pages}" if pages else ""
            except Exception as exc:  # noqa: BLE001
                record["error"] = f"{type(exc).__name__}: {exc}"[:100]
            rows.append(record)
            print(f"{record['code']} {record['name']:<8} links={record['n_links'] or '-':<3} "
                  f"years={record['years'] or '-'} {record['error']}")
            time.sleep(args.rate)

        browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    hit = [r for r in rows if int(r["n_years"] or 0) >= 3]
    print(f"\nprovinces_with_3plus_years={len(hit)}/{len(rows)}")
    print(f"wrote {OUT}")

    if args.merge:
        with open(PROBE, encoding="utf-8") as fh:
            probe = list(csv.DictReader(fh))
        best = {r["code"]: r["archive"] for r in rows if int(r["n_years"] or 0) > 0}
        for row in probe:
            if row["code"] in best:
                row["sample_link"] = best[row["code"]]
        with open(PROBE, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(probe[0].keys()))
            writer.writeheader()
            writer.writerows(probe)
        print(f"merged archive urls into {PROBE}")


if __name__ == "__main__":
    main()
