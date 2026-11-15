"""Config and sample-frame invariants.

These run in CI so a YAML typo or an accidental edit to the region list
fails loudly instead of surfacing at hour three of a crawl.
"""
from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_regions_yaml_describes_executed_scope():
    data = yaml.safe_load((ROOT / "config" / "regions.yaml").read_text(encoding="utf-8"))
    assert data["years"] == {"from": 2015, "to": 2026}
    assert data["scope"]["level"] == "province"
    assert data["scope"]["provinces"] == 18
    assert data["scope"]["documents"] == 150


def test_manifest_matches_declared_scope():
    data = yaml.safe_load((ROOT / "config" / "regions.yaml").read_text(encoding="utf-8"))
    with open(ROOT / "data" / "manifest.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == data["scope"]["documents"], "manifest drifted from declared scope"
    assert len({r["code"] for r in rows}) == data["scope"]["provinces"]
    assert all(r["url"].startswith(("http://", "https://")) for r in rows)


def test_concepts_yaml_shape():
    data = yaml.safe_load((ROOT / "config" / "concepts.yaml").read_text(encoding="utf-8"))
    concepts = data["concepts"]
    assert len(concepts) >= 8
    for name, spec in concepts.items():
        assert spec.get("variants"), f"{name} has no variants"
        assert spec.get("origin"), f"{name} has no origin"


def test_region_frame_is_locked():
    with open(ROOT / "data" / "regions.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    provinces = [r for r in rows if r["level"] == "province"]
    prefectures = [r for r in rows if r["level"] == "prefecture"]
    assert len(provinces) == 31, "province frame changed"
    assert len(prefectures) == 333, "prefecture frame changed"
    assert all(len(r["code"]) == 6 for r in rows)
