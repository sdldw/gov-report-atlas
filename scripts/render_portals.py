"""Render JavaScript-heavy portals with a headless browser.

Seventeen provincial portals publish their work-report archives through JS, so
static requests see an empty shell. This script drives Chromium, waits for the
page to settle, and then reuses the same extraction logic as the static probe.

Usage:
    python scripts/render_portals.py --codes 440000,320000,330000
    python scripts/render_portals.py --all --rate 2
    python scripts/render_portals.py --all --merge      # write back into portals.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path

from probe_portals import find_report_links, nav_links

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config" / "portals_seed.yaml"
PROBE = ROOT / "data" / "probe" / "portals.csv"
OUT = ROOT / "data" / "probe" / "rendered.csv"

COLUMNS = ["code", "name", "home", "archive", "n_links", "n_years", "years", "error"]
MAX_NAV = 6
DUMP_DIR = ROOT / "data" / "probe" / "dump"


def render(page, url: str, timeout: int) -> bytes:
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(1500)  # let async content land
    return page.content().encode("utf-8")


def years_from(links: list[tuple[str, str]]) -> dict[int, str]:
    import re

    out: dict[int, str] = {}
    for text, url in links:
        match = re.search(r"(20\d{2})\s*年", text)
        year = int(match.group(1)) if match else None
        if year is None:
            match = re.search(r"/(20\d{2})[/_\-]", url)
            year = int(match.group(1)) if match else None
        if year is not None and 2015 <= year <= 2026:
            out.setdefault(year, url)
    return out


def main() -> None:
    import yaml
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codes", default="", help="comma-separated codes, e.g. 440000,320000")
    ap.add_argument("--all", action="store_true", help="every province in the seed")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=30000)
    ap.add_argument("--merge", action="store_true", help="write archive URLs into portals.csv")
    ap.add_argument("--dump", action="store_true", help="save rendered html for inspection")
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
                html = render(page, home, args.timeout)
                record["home"] = page.url
                if args.dump:
                    DUMP_DIR.mkdir(parents=True, exist_ok=True)
                    (DUMP_DIR / f"{item['code']}_home.html").write_bytes(html)
                links = find_report_links(html, page.url)
                if not links:
                    for nav in nav_links(html, page.url, limit=MAX_NAV):
                        try:
                            sub = render(page, nav, args.timeout)
                        except Exception:  # noqa: BLE001
                            continue
                        if args.dump:
                            DUMP_DIR.mkdir(parents=True, exist_ok=True)
                            safe = re.sub(r"[^\w]+", "_", nav)[:80]
                            (DUMP_DIR / f"{item['code']}_nav_{safe}.html").write_bytes(sub)
                        links.extend(find_report_links(sub, page.url))
                        if len(years_from(links)) >= 5:
                            break
                years = years_from(links)
                record.update(
                    n_links=str(len(links)),
                    n_years=str(len(years)),
                    years="|".join(str(y) for y in sorted(years)),
                    archive=next(iter(years.values())) if years else "",
                )
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
