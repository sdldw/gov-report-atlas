"""Probe provincial portals for a usable "government work report" hub.

Read-only reconnaissance: at most two GETs per province (https, then http
fallback). No crawling, no recursion. The result decides the whole crawl
architecture:

  * if most provinces expose a hub page listing their cities -> ~32 adapters
  * if not -> 364 portal-level adapters, a much bigger job

Usage:
    python scripts/probe_portals.py
    python scripts/probe_portals.py --rate 2.0 --timeout 20
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "config" / "portals_seed.yaml"
OUT_DIR = ROOT / "data" / "probe"

KEYWORD = "政府工作报告"
UA = "gov-report-atlas/0.1 (academic course project; contact via repository)"
CHARSET_RE = re.compile(rb'charset\s*=\s*["\']?\s*([\w-]+)', re.IGNORECASE)
COLUMNS = ["code", "name", "domain", "scheme", "status", "title_ok",
           "n_report_links", "sample_link", "error"]


def _decode(raw: bytes) -> str:
    """Government portals still ship gb2312 pages; lxml guesses wrong on bytes."""
    match = CHARSET_RE.search(raw[:4096])
    declared = match.group(1).decode("ascii", "ignore") if match else None
    for enc in (declared, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "ignore")


def find_report_links(html: bytes, base_url: str) -> list[tuple[str, str]]:
    """Return (anchor text, absolute url) for links that look like work reports."""
    from lxml import html as LH

    doc = LH.fromstring(_decode(html))
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in doc.xpath("//a[@href]"):
        text = re.sub(r"\s+", "", "".join(anchor.itertext()))
        href = (anchor.get("href") or "").strip()
        if KEYWORD not in text or not href:
            continue
        if href.lower().startswith(("javascript:", "#", "mailto:")):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append((text[:60], absolute))
    return out


def page_title(html: bytes) -> str:
    match = re.search(rb"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    raw = match.group(1)
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc).strip()[:80]
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore").strip()[:80]


def short_name(name: str) -> str:
    for suffix in ("壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "省", "市"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def probe_one(session, row: dict, timeout: int) -> dict:
    record = {k: "" for k in COLUMNS}
    record.update(code=row["code"], name=row["name"], domain=row["domain"])
    last_error = ""
    for scheme in ("https", "http"):
        url = f"{scheme}://{row['domain']}"
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"[:120]
            continue
        record.update(scheme=scheme, status=str(resp.status_code))
        if resp.status_code >= 400:
            last_error = f"HTTP {resp.status_code}"
            continue
        title = page_title(resp.content)
        links = find_report_links(resp.content, resp.url)
        record.update(
            title_ok=str(short_name(row["name"]) in title).lower(),
            n_report_links=str(len(links)),
            sample_link=links[0][1] if links else "",
        )
        return record
    record["error"] = last_error
    return record


def main() -> None:
    import requests
    import yaml

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rate", type=float, default=1.5)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "portals.csv")
    args = ap.parse_args()

    seed = yaml.safe_load(SEED.read_text(encoding="utf-8"))["portals"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = UA

    records = []
    for row in seed:
        record = probe_one(session, row, args.timeout)
        records.append(record)
        print(f"{record['code']} {record['name']:<8} {record['scheme'] or '-':<5} "
              f"{record['status'] or '-':<4} links={record['n_report_links'] or '-':<3} "
              f"{record['error']}")
        time.sleep(args.rate)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    alive = [r for r in records if r["status"] and int(r["status"]) < 400]
    with_hub = [r for r in alive if int(r["n_report_links"] or 0) > 0]
    print(f"\nreachable={len(alive)}/{len(records)}  with_report_links={len(with_hub)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
