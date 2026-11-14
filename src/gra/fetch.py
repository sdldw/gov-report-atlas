"""Manifest-driven, polite, resumable downloader.

manifest.csv is the single source of truth. Every finished document is
checkpointed immediately, so a crash never loses more than one row.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import random
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifest.csv"
RAW = ROOT / "data" / "raw"
LOGS = ROOT / "logs"

COLUMNS = [
    "doc_id", "code", "name", "level", "year", "kind",
    "url", "path", "sha256", "bytes", "status", "http_code", "fetched_at",
]


def setup_logging() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOGS / "fetch.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        raise SystemExit(f"missing {MANIFEST}; run scripts/build_regions.py first")
    with open(MANIFEST, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_manifest(rows: list[dict]) -> None:
    with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def guess_ext(url: str, content_type: str) -> str:
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        return ".pdf"
    if "html" in content_type.lower() or url.lower().endswith((".html", ".htm", ".shtml")):
        return ".html"
    return ".bin"


def download(session: requests.Session, url: str, dest_stem: Path,
             retries: int = 3) -> tuple[bool, int, Path | None]:
    last_code = 0
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=60, stream=True)
            last_code = resp.status_code
            resp.raise_for_status()
            dest = dest_stem.with_suffix(
                guess_ext(url, resp.headers.get("Content-Type", ""))
            )
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(1 << 16):
                    fh.write(chunk)
            tmp.replace(dest)
            return True, last_code, dest
        except Exception as exc:  # noqa: BLE001
            logging.warning("attempt %d/%d failed (%s): %s", attempt, retries, url, exc)
            time.sleep(min(2 ** attempt, 30) + random.random())
    return False, last_code, None


def run(rate: float = 1.5, limit: int = 0, retries: int = 3) -> None:
    setup_logging()
    RAW.mkdir(parents=True, exist_ok=True)
    rows = read_manifest()
    session = requests.Session()
    session.headers["User-Agent"] = (
        "gov-report-atlas/0.1 (academic course project; contact via repository)"
    )

    todo = [r for r in rows if not (r.get("status") == "ok" and r.get("sha256"))]
    if limit:
        todo = todo[:limit]
    logging.info("manifest=%d pending=%d", len(rows), len(todo))

    ok = failed = 0
    for row in todo:
        stem = RAW / row["doc_id"]
        if row.get("path") and row.get("sha256"):
            existing = ROOT / row["path"]
            if existing.exists() and sha256_of(existing) == row["sha256"]:
                row["status"] = "ok"
                ok += 1
                continue
        good, code, dest = download(session, row["url"], stem, retries=retries)
        row["http_code"] = str(code)
        if good and dest and dest.stat().st_size > 512:
            row.update(
                status="ok",
                path=str(dest.relative_to(ROOT)),
                sha256=sha256_of(dest),
                bytes=str(dest.stat().st_size),
                fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            ok += 1
        else:
            row["status"] = "failed"
            failed += 1
            logging.error("failed %s -> %s", row["doc_id"], row["url"])
        write_manifest(rows)
        time.sleep(rate + random.random() * 0.5)

    write_manifest(rows)
    logging.info("done ok=%d failed=%d", ok, failed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rate", type=float, default=1.5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()
    run(rate=args.rate, limit=args.limit, retries=args.retries)


if __name__ == "__main__":
    main()
