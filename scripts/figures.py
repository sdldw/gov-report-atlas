"""Figures for the report.

Figure 1 is the core evidence: concept attention over time on a **balanced**
panel, with the proposal date marked, plus two benchmark concepts so a reader
can tell real diffusion from general rhetorical inflation.

Usage:
    python scripts/figures.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel.csv"
OUT_DIR = ROOT / "docs" / "figs"

PRIMARY = "新质生产力"
BENCHMARKS = ["双碳", "全国统一大市场"]
PROPOSAL = (2023.75, "concept proposed (2023-09)")

zh_labels = {
    PRIMARY: "新质生产力",
    "双碳": "双碳",
    "全国统一大市场": "全国统一大市场",
}
en_labels = {
    PRIMARY: "New quality productive forces",
    "双碳": "Carbon peaking/neutrality",
    "全国统一大市场": "Unified national market",
}


def pick_cjk_font() -> str | None:
    names = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC"):
        if candidate in names:
            return candidate
    return None


def load() -> list[dict]:
    with open(PANEL, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["code"] = row["doc_id"][:6]
        row["year"] = int(row["doc_id"][-4:])
    return rows


def balanced_codes(rows: list[dict], years: list[int]) -> list[str]:
    by_year: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        by_year[row["year"]].add(row["code"])
    available = [by_year[y] for y in years if by_year.get(y)]
    if not available:
        return []
    return sorted(set.intersection(*available))


def series(rows: list[dict], codes: set[str], concept: str, years: list[int]) -> list[float]:
    out = []
    for year in years:
        vals = [float(r[f"share_{concept}"]) for r in rows
                if r["year"] == year and r["code"] in codes]
        out.append(sum(vals) / len(vals) if vals else float("nan"))
    return out


def main() -> None:
    rows = load()
    years = sorted({r["year"] for r in rows})
    codes = balanced_codes(rows, years)
    print(f"provinces total={len({r['code'] for r in rows})} balanced={len(codes)}")
    print(f"years={years[0]}-{years[-1]}  docs_in_balanced={sum(1 for r in rows if r['code'] in codes)}")

    font = pick_cjk_font()
    if font:
        plt.rcParams["font.sans-serif"] = [font]
        plt.rcParams["axes.unicode_minus"] = False
        labels = zh_labels
    else:
        labels = en_labels
        print("[warn] no CJK font found, falling back to English labels")

    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    code_set = set(codes)
    ax.plot(years, series(rows, code_set, PRIMARY, years),
            marker="o", linewidth=2.4, label=labels[PRIMARY], zorder=3)
    for bench in BENCHMARKS:
        ax.plot(years, series(rows, code_set, bench, years),
                marker="s", linewidth=1.2, alpha=0.65, label=labels[bench])

    ax.axvline(PROPOSAL[0], color="grey", linestyle="--", linewidth=1)
    ax.annotate(PROPOSAL[1], xy=(PROPOSAL[0], ax.get_ylim()[1] * 0.92),
                rotation=90, fontsize=7, color="grey", ha="right", va="top")

    ax.set_xlabel("year")
    ax.set_ylabel("mentions per 1,000 Chinese characters")
    ax.set_title("Concept attention in provincial work reports (balanced panel, n=%d)" % len(codes))
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / "fig1_attention_trend.png"
    fig.savefig(target)
    print(f"wrote {target}")

    print("\nbalanced panel, mean share by year:")
    header = ["year", "n"] + [PRIMARY] + BENCHMARKS
    print("\t".join(header))
    for year in years:
        group = [r for r in rows if r["year"] == year and r["code"] in code_set]
        if not group:
            continue
        cells = [f"{sum(float(r[f'share_{c}']) for r in group) / len(group):7.3f}"
                 for c in [PRIMARY] + BENCHMARKS]
        print("\t".join([str(year), f"{len(group):3d}"] + cells))


if __name__ == "__main__":
    main()
