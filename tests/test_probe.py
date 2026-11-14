"""Offline tests for the portal probe's pure helpers (no network)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "probe_portals", ROOT / "scripts" / "probe_portals.py"
)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

HTML = """
<html><head><title>河北省人民政府</title></head><body>
  <a href="/col/col123/index.html">2025年政府工作报告</a>
  <a href="/col/col123/index.html">2025年政府工作报告</a>
  <a href="javascript:void(0)">政府工作报告</a>
  <a href="/other/">政府信息公开</a>
  <a href="report/2024.html">2024年政府工作报告</a>
</body></html>
""".encode()

BASE = "https://www.hebei.gov.cn/"


def test_finds_and_dedupes_report_links():
    links = probe.find_report_links(HTML, BASE)
    urls = [u for _, u in links]
    assert len(urls) == 2
    assert "https://www.hebei.gov.cn/col/col123/index.html" in urls
    assert "https://www.hebei.gov.cn/report/2024.html" in urls


def test_ignores_javascript_and_unrelated_anchors():
    links = probe.find_report_links(HTML, BASE)
    assert all("javascript" not in u for _, u in links)
    assert all("政府信息公开" not in t for t, _ in links)


def test_page_title_decodes_utf8():
    assert "河北省" in probe.page_title(HTML)


def test_short_name_strips_admin_suffixes():
    assert probe.short_name("河北省") == "河北"
    assert probe.short_name("广西壮族自治区") == "广西"
    assert probe.short_name("北京市") == "北京"
    assert probe.short_name("新疆维吾尔自治区") == "新疆"
