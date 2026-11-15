"""Probe candidate report URLs and keep the provinces that actually respond.

Candidates come from two offline extractions (rendered_links.csv and
candidates.csv); they are merged, sampled, and tested with a real request.
A province is kept only if at least one sampled URL returns a plausible
document — 404s and WAF blocks are the norm, not the exception.

Output: data/probe/viable.csv  (code, name, year, url, status, bytes)
Usage:  python scripts/probe_candidates.py
        python scripts/probe_candidates.py --sample 3 --rate 1.5
"""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE_DIR = ROOT / "data" / "probe"
MANIFEST = ROOT / "data" / "manifest.csv"
OUT = PROBE_DIR / "viable.csv"

MIN_BYTES = 3000
KEEP_YEARS = range(2015, 2027)


def load_candidates() -> dict[str, dict[int, str]]:
    merged: dict[str, dict[int, str]] = {}
    for name in ("rendered_links.csv", "candidates.csv"):
        path = PROBE_DIR / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                url = row["url"]
                if not url.startswith(("http://", "https://")):
                    continue
                year = int(row["year"])
                if year not in KEEP_YEARS:
                    continue
                merged.setdefault(row["code"], {}).setdefault(year, url)
    return merged


def existing_codes() -> set[str]:
    if not MANIFEST.exists():
        return set()
    with open(MANIFEST, encoding="utf-8") as fh:
        return {r["code"] for r in csv.DictReader(fh)}


def main() -> None:
    import requests

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=2, help="urls tested per province")
    ap.add_argument("--rate", type=float, default=1.2)
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "gov-report-atlas/0.1 (academic course project)",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    have = existing_codes()
    candidates = {c: y for c, y in load_candidates().items() if c not in have}

    kept: list[dict] = []
    summary: list[tuple[str, int, str, int]] = []

    for code, years in sorted(candidates.items()):
        newest = sorted(years, reverse=True)[: args.sample]
        ok_sizes = []
        status_note = ""
        for year in newest:
            try:
                resp = session.get(years[year], timeout=args.timeout, stream=True)
                size = len(resp.content) if resp.status_code < 400 else 0
            except Exception as exc:  # noqa: BLE001
                status_note = type(exc).__name__
                continue
            finally:
                time.sleep(args.rate)
            if resp.status_code >= 400:
                status_note = f"HTTP {resp.status_code}"
                continue
            ok_sizes.append(size)

        alive = [s for s in ok_sizes if s >= MIN_BYTES]
        summary.append((code, len(years), "ok" if alive else (status_note or "small"), max(ok_sizes or [0])))
        if not alive:
            continue
        for year, url in sorted(years.items()):
            kept.append({"code": code, "name": "", "year": year, "url": url,
                         "status": "candidate", "bytes": ""})
        print(f"{code} {len(years):2d} years  OK  largest={max(ok_sizes)}B")
        time.sleep(args.rate)

    # fill names from the seed file
    import yaml

    seed = yaml.safe_load((ROOT / "config" / "portals_seed.yaml").read_text(encoding="utf-8"))["portals"]
    names = {p["code"]: p["name"] for p in seed}
    for row in kept:
        row["name"] = names.get(row["code"], "")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["code", "name", "year", "url", "status", "bytes"])
        writer.writeheader()
        writer.writerows(kept)

    provinces = len({r["code"] for r in kept})
    print(f"\ntested={len(candidates)} viable={provinces} links={len(kept)}")
    for code, n, note, size in summary:
        if note != "ok":
            print(f"  dropped {code}: {note} (years={n}, largest={size}B)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
