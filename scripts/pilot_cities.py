"""Pilot: can we guess a city portal domain and find its report section?

Run on a small sample first. The hit rate decides whether 333 cities are
feasible in the remaining weeks or whether the sample must shrink.

Usage:
    python scripts/pilot_cities.py --sample 30
    python scripts/pilot_cities.py --sample 30 --seed 7
"""
from __future__ import annotations

import argparse
import csv
import random
import time
from pathlib import Path

from probe_portals import find_report_links, page_title, short_name

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ROOT / "data" / "regions.csv"
OUT = ROOT / "data" / "probe" / "cities_pilot.csv"

# common disclosure paths on Chinese government portals
COMMON_PATHS = [
    "/zfxxgk/zfgzbg/",
    "/zwgk/zfgzbg/",
    "/zfxxgk/zfgzbg/index.html",
    "/zwgk/zfgzbg/index.html",
    "/zfgzbg/",
    "/zfgb/",
]
COLUMNS = ["code", "name", "province", "home", "title_ok",
           "report_path", "n_links", "error"]


ETHNIC = (
    "土家族|苗族|藏族|羌族|彝族|白族|傣族|景颇族|傈僳族|壮族|回族|蒙古族|朝鲜族|"
    "哈萨克族|柯尔克孜族|哈尼族|布依族|侗族|瑶族|水族|仡佬族|黎族|畲族|满族|"
    "锡伯族|达斡尔族|鄂温克族|鄂伦春族|东乡族|撒拉族|土族|裕固族|保安族|俄罗斯族|塔吉克族"
)


def city_stem(name: str) -> str:
    """石家庄市 -> 石家庄; 湘西土家族苗族自治州 -> 湘西; 锡林郭勒盟 -> 锡林郭勒."""
    import re

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
        title = page_title(resp.content)
        if short_name(name) in title:
            return resp.url, title
    return None, ""


def main() -> None:
    import requests

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rate", type=float, default=1.2)
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
    domain_hits = path_hits = 0

    for row in sample:
        record = {k: "" for k in COLUMNS}
        record.update(code=row["code"], name=row["name"], province=row["province"])

        home, title = None, ""
        for domain in domain_candidates(row["name"]):
            home, title = probe_home(session, domain, row["name"], args.timeout)
            time.sleep(args.rate)
            if home:
                break
        record["home"] = home or ""
        record["title_ok"] = str(bool(home)).lower()
        if home:
            domain_hits += 1
            # try the report section directly
            for path in COMMON_PATHS:
                try:
                    resp = session.get(home.rstrip("/") + path, timeout=args.timeout)
                except Exception:  # noqa: BLE001
                    continue
                finally:
                    time.sleep(args.rate * 0.5)
                if resp.status_code >= 400:
                    continue
                links = find_report_links(resp.content, resp.url)
                if links:
                    record["report_path"] = path
                    record["n_links"] = str(len(links))
                    path_hits += 1
                    break
        records.append(record)
        print(f"{record['code']} {record['name']:<8} {record['title_ok']:<5} "
              f"{record['report_path'] or '-':<24} links={record['n_links'] or '-'}")

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    print(f"\ndomain_hit={domain_hits}/{len(sample)}  report_path_hit={path_hits}/{len(sample)}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
