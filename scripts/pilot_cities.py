"""Pilot: from a guessed city domain, how far can we get toward real reports?

Three measurements per city:
  1. domain_hit   - did we guess a live portal whose title contains the city name?
  2. link_hit     - did we find at least one anchor that looks like a work report?
  3. year_hit     - how many distinct years appear in those anchors? (>=3 is usable)

Paths are tried first because they are cheap; if they fail we follow the
disclosure navigation, which is what worked for the provincial portals.

Usage:
    python scripts/pilot_cities.py --sample 30
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import time
from pathlib import Path

from probe_portals import find_report_links, nav_links, page_title, short_name

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ROOT / "data" / "regions.csv"
OUT = ROOT / "data" / "probe" / "cities_pilot.csv"

COMMON_PATHS = [
    "/zfxxgk/zfgzbg/",
    "/zwgk/zfgzbg/",
    "/zfxxgk/zfgzbg/index.html",
    "/zwgk/zfgzbg/index.html",
    "/xxgk/zfgzbg/",
    "/xxgk/",
    "/zfxxgk/",
    "/zfxxgkpt/",
    "/zfgzbg/",
    "/zfgb/",
    "/govopen/zfgzbg/",
]
SUBDOMAIN_PREFIXES = ["xxgk.", "zfxxgk.", "govopen."]
YEAR_RE = re.compile(r"20\d{2}")
COLUMNS = ["code", "name", "province", "home", "method",
           "n_links", "n_years", "years", "sample_link"]

ETHNIC = (
    "土家族|苗族|藏族|羌族|彝族|白族|傣族|景颇族|傈僳族|壮族|回族|蒙古族|朝鲜族|"
    "哈萨克族|柯尔克孜族|哈尼族|布依族|侗族|瑶族|水族|仡佬族|黎族|畲族|满族|"
    "锡伯族|达斡尔族|鄂温克族|鄂伦春族|东乡族|撒拉族|土族|裕固族|保安族|俄罗斯族|塔吉克族"
)


def city_stem(name: str) -> str:
    """石家庄市 -> 石家庄; 湘西土家族苗族自治州 -> 湘西; 锡林郭勒盟 -> 锡林郭勒."""
    stem = re.sub(rf"(?:{ETHNIC})+", "", name)
    for suffix in ("自治州", "地区", "市", "盟"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def domain_candidates(name: str) -> list[str]:
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "需要 pypinyin 才能猜域名，先装：\n"
            '  .\\.venv\\Scripts\\python.exe -m pip install -e ".[dev]"'
        ) from exc

    stem = city_stem(name)
    full = "".join(lazy_pinyin(stem)).lower()
    abbr = "".join(lazy_pinyin(stem, style=Style.FIRST_LETTER)).lower()
    out = []
    for token in (full, abbr):
        if token and f"www.{token}.gov.cn" not in out:
            out.append(f"www.{token}.gov.cn")
    return out


def probe_home(session, domain: str, name: str, timeout: int):
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
        except Exception:  # noqa: BLE001
            continue
        if resp.status_code >= 400:
            continue
        if short_name(name) in page_title(resp.content):
            return resp
    return None


def links_via_paths(session, home, timeout: int, rate: float):
    for path in COMMON_PATHS:
        try:
            resp = session.get(home.url.rstrip("/") + path, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        finally:
            time.sleep(rate * 0.5)
        if resp.status_code >= 400:
            continue
        links = find_report_links(resp.content, resp.url)
        if links:
            return links, path
    return [], ""


def links_via_subdomains(session, home, timeout: int, rate: float):
    """Disclosure platforms often live on xxgk./zfxxgk./govopen. subdomains."""
    links: list[tuple[str, str]] = []
    if "://www." not in home.url:
        return links
    for prefix in SUBDOMAIN_PREFIXES:
        url = home.url.replace("://www.", f"://{prefix}", 1).rstrip("/") + "/"
        try:
            resp = session.get(url, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        finally:
            time.sleep(rate * 0.5)
        if resp.status_code >= 400:
            continue
        links.extend(find_report_links(resp.content, resp.url))
    return links


def links_via_nav(session, home, timeout: int, rate: float, max_pages: int = 6):
    links: list[tuple[str, str]] = []
    for nav in nav_links(home.content, home.url, limit=max_pages):
        try:
            resp = session.get(nav, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        finally:
            time.sleep(rate * 0.5)
        if resp.status_code >= 400:
            continue
        links.extend(find_report_links(resp.content, resp.url))
    return links


def main() -> None:
    import requests

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=15)
    args = ap.parse_args()

    with open(REGIONS, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["level"] == "prefecture"]
    if args.seed:
        random.Random(args.seed).shuffle(rows)
    sample = rows[: args.sample]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "gov-report-atlas/0.1 (academic course project)",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    domain_hits = link_hits = year_hits = 0

    for row in sample:
        record = {k: "" for k in COLUMNS}
        record.update(code=row["code"], name=row["name"], province=row["province"])

        home = None
        for domain in domain_candidates(row["name"]):
            home = probe_home(session, domain, row["name"], args.timeout)
            time.sleep(args.rate)
            if home:
                break
        record["home"] = home.url if home else ""
        record["method"] = "-"

        if home:
            domain_hits += 1
            links, path = links_via_paths(session, home, args.timeout, args.rate)
            if links:
                record["method"] = f"path{path}"
            else:
                links = links_via_subdomains(session, home, args.timeout, args.rate)
                if links:
                    record["method"] = "subdomain"
                else:
                    links = links_via_nav(session, home, args.timeout, args.rate)
                    if links:
                        record["method"] = "nav"

            if links:
                link_hits += 1
                years = sorted({m.group(0) for text, _ in links
                                for m in [YEAR_RE.search(text)] if m})
                record["n_links"] = str(len(links))
                record["n_years"] = str(len(years))
                record["years"] = "|".join(years)
                record["sample_link"] = links[0][1]
                if len(years) >= 3:
                    year_hits += 1

        records.append(record)
        print(f"{record['code']} {record['name']:<8} {record['method']:<12} "
              f"links={record['n_links'] or '-':<3} years={record['years'] or '-'}")

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    total = len(sample)
    print(f"\ndomain_hit={domain_hits}/{total}  link_hit={link_hits}/{total}  "
          f"year3_hit={year_hits}/{total}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
