"""Concept attention, first appearance, and sentence-level copying rate.

Denominator is always total CJK characters, never raw length: work reports
differ hugely in size and absolute counts are not comparable.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_DIR = ROOT / "data" / "interim" / "text"
OUT = ROOT / "data" / "processed"
CONCEPTS = ROOT / "config" / "concepts.yaml"

CJK = re.compile(r"[\u4e00-\u9fff]")
SENT_SPLIT = re.compile(r"[。！？；\n]+")


def cjk_count(text: str) -> int:
    return len(CJK.findall(text))


def load_concepts(path: Path = CONCEPTS) -> dict:
    import yaml

    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["concepts"]


def count_concept(text: str, variants: list[str]) -> int:
    """Count non-overlapping matches, longest variant first.

    Summing ``text.count(v)`` for each variant double-counts when one variant is
    a substring of another (「新质生产力」inside「新质生产力发展」), so we scan once
    with a single alternation ordered by length.
    """
    if not variants:
        return 0
    pattern = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    return len(re.findall(pattern, text))


def attention_share(text: str, variants: list[str], per: int = 1000) -> float:
    total = cjk_count(text)
    if total == 0:
        return 0.0
    return count_concept(text, variants) / total * per


def split_sentences(text: str, min_len: int = 12) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text) if len(s.strip()) >= min_len]


def simhash(text: str, bits: int = 64) -> int:
    """Character 3-gram simhash; stable across runs (blake2b, not hash())."""
    grams = [text[i:i + 3] for i in range(max(0, len(text) - 2))]
    if not grams:
        return 0
    vector = [0] * bits
    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for i in range(bits):
            vector[i] += 1 if (value >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if vector[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class SimhashIndex:
    """4 x 16-bit banding index so lookup stays O(1) instead of O(n)."""

    N_BANDS = 4
    BAND_BITS = 16

    def __init__(self) -> None:
        self.bands: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def _keys(self, h: int):
        for b in range(self.N_BANDS):
            yield (b, (h >> (b * self.BAND_BITS)) & ((1 << self.BAND_BITS) - 1))

    def add(self, h: int, ref: int) -> None:
        """Index hash ``h`` under reference id ``ref``."""
        for key in self._keys(h):
            self.bands.setdefault(key, []).append((ref, h))

    def query(self, h: int, max_distance: int = 3) -> bool:
        for key in self._keys(h):
            for _ref, stored in self.bands.get(key, []):
                if hamming(h, stored) <= max_distance:
                    return True
        return False


def copying_rate(local_sents: list[str], index: SimhashIndex, max_distance: int = 3) -> float:
    if not local_sents:
        return 0.0
    hits = sum(1 for s in local_sents if index.query(simhash(s), max_distance))
    return hits / len(local_sents)


def build_panel() -> None:
    concepts = load_concepts()
    rows = []
    for path in sorted(TEXT_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        text = record["text"]
        row = {"doc_id": record["doc_id"], "n_chars": cjk_count(text)}
        for name, spec in concepts.items():
            row[f"share_{name}"] = round(attention_share(text, spec["variants"]), 4)
        rows.append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "panel.csv"
    header = list(rows[0].keys()) if rows else ["doc_id", "n_chars"]
    with open(target, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(header) + "\n")
        for row in rows:
            fh.write(",".join(str(row.get(k, "")) for k in header) + "\n")
    print(f"wrote {target} rows={len(rows)}")


def main() -> None:
    build_panel()


if __name__ == "__main__":
    main()
