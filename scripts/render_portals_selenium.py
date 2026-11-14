"""Same probe as render_portals.py, but driven by Selenium + local Edge/Chrome.

Why this exists: Playwright ships a Node driver that creates its own temp
directories, which some antivirus setups block outright (EPERM on mkdtemp,
in any directory). Selenium drives an already-installed browser from Python
and never spawns Node.

Edge is present on every Windows 10/11 machine, so no browser download is
needed. Selenium Manager may still fetch a driver (~10 MB) on first run; set
SE_CACHE_PATH to a writable directory if the default cache misbehaves.

Usage:
    python scripts/render_portals_selenium.py --codes 440000
    python scripts/render_portals_selenium.py --all --merge
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from probe_portals import find_report_links, nav_links

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config" / "portals_seed.yaml"
PROBE = ROOT / "data" / "probe" / "portals.csv"
OUT = ROOT / "data" / "probe" / "rendered_selenium.csv"

COLUMNS = ["code", "name", "home", "archive", "n_links", "n_years", "years", "error"]
MAX_NAV = 6


def make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions

    errors = []
    for name, options_cls, factory in (
        ("edge", EdgeOptions, webdriver.Edge),
        ("chrome", ChromeOptions, webdriver.Chrome),
    ):
        try:
            options = options_cls()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--lang=zh-CN")
            driver = factory(options=options)
            print(f"[engine] {name}")
            return driver
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}"[:120])
    raise SystemExit("no usable browser driver\n" + "\n".join(errors))


def render(driver, url: str, timeout_ms: int = 30000) -> tuple[str, str]:
    driver.set_page_load_timeout(timeout_ms / 1000)
    driver.get(url)
    time.sleep(1.5)  # let async content land; no reliable networkidle here
    return driver.page_source, driver.current_url


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

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--codes", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    seed = yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]
    if args.codes:
        wanted = {c.strip() for c in args.codes.split(",") if c.strip()}
        seed = [p for p in seed if p["code"] in wanted]
    if not args.all and not args.codes:
        ap.error("give --codes or --all")

    driver = make_driver()
    rows = []
    try:
        for item in seed:
            record = {k: "" for k in COLUMNS}
            record.update(code=item["code"], name=item["name"])
            try:
                html, final_url = render(driver, f"https://{item['domain']}/")
                record["home"] = final_url
                links = find_report_links(html.encode("utf-8"), final_url)
                if not links:
                    for nav in nav_links(html.encode("utf-8"), final_url, limit=MAX_NAV):
                        try:
                            sub, sub_url = render(driver, nav)
                        except Exception:  # noqa: BLE001
                            continue
                        links.extend(find_report_links(sub.encode("utf-8"), sub_url))
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
    finally:
        driver.quit()

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
