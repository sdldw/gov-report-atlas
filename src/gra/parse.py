"""HTML/PDF -> plain text, with encoding repair and boilerplate removal.

Government portals are a zoo: GBK pages, table-based layouts, PDF scans.
Strategy: decode by declared charset, fall back to gb18030, strip chrome,
prefer <p> blocks, fall back to the densest block.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "interim" / "text"
LOGS = ROOT / "logs"

CHARSET_RE = re.compile(rb'charset\s*=\s*["\']?\s*([\w-]+)', re.IGNORECASE)
CHROME = ("script", "style", "nav", "header", "footer", "noscript", "form", "iframe")
MIN_BLOCK = 20

LOG = logging.getLogger(__name__)


def decode(raw: bytes) -> str:
    declared = None
    match = CHARSET_RE.search(raw[:4096])
    if match:
        declared = match.group(1).decode("ascii", "ignore")
    for enc in (declared, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "ignore")


def html_to_text(raw: bytes) -> str:
    from lxml import html as LH

    doc = LH.fromstring(decode(raw))
    for tag in CHROME:
        for node in doc.xpath(f"//{tag}"):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)

    paras: list[str] = []
    seen: set[str] = set()
    for node in doc.xpath("//p|//div[@class='TRS_Editor']|//div[@id='zoom']"):
        text = " ".join(node.itertext()).strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) >= MIN_BLOCK and text not in seen:
            seen.add(text)
            paras.append(text)
    joined = "\n".join(paras)
    if len(joined) >= 300:
        return joined

    body = doc.find("body")
    text = " ".join(body.itertext()) if body is not None else " ".join(doc.itertext())
    return re.sub(r"[ \t]+", " ", text).strip()


def pdf_to_text(path: Path) -> tuple[str, int]:
    import fitz

    doc = fitz.open(path)
    pages = [page.get_text("text") or "" for page in doc]
    empty = sum(1 for p in pages if len(p.strip()) < 40)
    doc.close()
    return "\n".join(pages), empty


def parse_one(path: Path) -> dict:
    if path.suffix.lower() == ".pdf":
        text, empty_pages = pdf_to_text(path)
        meta = {"source_type": "pdf", "empty_pages": empty_pages}
    else:
        text = html_to_text(path.read_bytes())
        meta = {"source_type": "html"}
    return {"doc_id": path.stem, "text": text, "n_chars": len(text), **meta}


def run() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOGS / "parse.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    files = [p for p in sorted(RAW.iterdir()) if p.suffix.lower() in {".html", ".pdf", ".bin"}]
    LOG.info("parsing %d files", len(files))
    empty = 0
    for path in files:
        target = OUT / f"{path.stem}.json"
        if target.exists():
            continue
        try:
            record = parse_one(path)
        except Exception:
            LOG.exception("parse failed for %s", path.name)
            continue
        if record["n_chars"] < 200:
            empty += 1
            LOG.warning("short text (%d chars): %s", record["n_chars"], path.name)
        target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    LOG.info("done, short=%d", empty)


if __name__ == "__main__":
    run()
