"""Config and sample-frame invariants.

These run in CI so a YAML typo or an accidental edit to the region list
fails loudly instead of surfacing at hour three of a crawl.
"""
from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_regions_yaml_loads():
    data = yaml.safe_load((ROOT / "config" / "regions.yaml").read_text(encoding="utf-8"))
    assert data["years"] == [2023, 2024, 2025, 2026]
    assert "work_report" in data["doc_type"]
    assert data["goal"]["prefecture"] == 333 * len(data["years"])


def test_concepts_yaml_shape():
    data = yaml.safe_load((ROOT / "config" / "concepts.yaml").read_text(encoding="utf-8"))
    concepts = data["concepts"]
    assert len(concepts) >= 8
    for name, spec in concepts.items():
        assert spec.get("variants"), f"{name} has no variants"
        assert spec.get("origin"), f"{name} has no origin"


def test_region_frame_is_locked():
    rows = list(csv.DictReader(open(ROOT / "data" / "regions.csv", encoding="utf-8")))
    provinces = [r for r in rows if r["level"] == "province"]
    prefectures = [r for r in rows if r["level"] == "prefecture"]
    assert len(provinces) == 31, "province frame changed"
    assert len(prefectures) == 333, "prefecture frame changed"
    assert all(len(r["code"]) == 6 for r in rows)
