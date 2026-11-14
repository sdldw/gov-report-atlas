"""Figures for the report.

fig1  attention over time on a balanced panel, with benchmarks and the
      proposal date marked
fig2  what the concept is bound to, by year (sentence-level co-occurrence)
fig3  diffusion: how many provinces mention it, and how often per report

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
TRANSLATION = ROOT / "data" / "processed" / "translation.csv"
OUT_DIR = ROOT / "docs" / "figs"

PRIMARY = "新质生产力"
BENCHMARKS = ["双碳", "全国统一大市场"]
PROPOSAL = 2023.75

ZH = {
    PRIMARY: "新质生产力",
    "双碳": "双碳",
    "全国统一大市场": "全国统一大市场",
    "year": "年份",
    "share": "每千汉字提及次数",
    "mentions": "次/份",
}
EN = {
    PRIMARY: "New quality productive forces",
    "双碳": "Carbon peaking/neutrality",
    "全国统一大市场": "Unified national market",
    "year": "year",
    "share": "mentions per 1,000 Chinese characters",
    "mentions": "per report",
}


def setup_labels():
    names = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if candidate in names:
            plt.rcParams["font.sans-serif"] = [candidate]
            plt.rcParams["axes.unicode_minus"] = False
            return ZH
    print("[warn] no CJK font, using English labels")
    return EN


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fig1(labels: dict) -> None:
    rows = read_csv(PANEL)
    for row in rows:
        row["code"] = row["doc_id"][:6]
        row["year"] = int(row["doc_id"][-4:])

    by_year: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        by_year[row["year"]].add(row["code"])
    years = sorted(by_year)
    codes = set.intersection(*(by_year[y] for y in years))

    def series(concept: str) -> list[float]:
        out = []
        for year in years:
            vals = [float(r[f"share_{concept}"]) for r in rows
                    if r["year"] == year and r["code"] in codes]
            out.append(sum(vals) / len(vals) if vals else float("nan"))
        return out

    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    ax.plot(years, series(PRIMARY), marker="o", linewidth=2.4, label=labels[PRIMARY], zorder=3)
    for bench in BENCHMARKS:
        ax.plot(years, series(bench), marker="s", linewidth=1.2, alpha=0.6, label=labels[bench])
    ax.axvline(PROPOSAL, color="grey", linestyle="--", linewidth=1)
    ax.set_xlabel(labels["year"])
    ax.set_ylabel(labels["share"])
    ax.set_title(f"Concept attention, balanced panel (n={len(codes)} provinces)", fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig1_attention_trend.png")
    plt.close(fig)
    print(f"fig1: balanced n={len(codes)}, years={years[0]}-{years[-1]}")


def fig2(labels: dict) -> None:
    rows = [r for r in read_csv(TRANSLATION) if int(r["contexts"]) > 0]
    years = [int(r["year"]) for r in rows]
    keys = [("industry", "industry"), ("platform", "platform"),
            ("talent", "talent"), ("funding", "funding")]
    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=160)
    for key, label in keys:
        ax.plot(years, [float(r[f"share_{key}"]) for r in rows],
                marker="o", linewidth=1.8, label=label)
    ax.plot(years, [float(r["share_concrete"]) for r in rows],
            linestyle="--", color="black", linewidth=1.4, label="any concrete tool")
    ax.set_xticks(years)
    ax.set_xlabel(labels["year"])
    ax.set_ylabel("share of concept sentences")
    ax.set_title("What the concept is bound to, sentence level", fontsize=10)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig2_translation.png")
    plt.close(fig)
    print(f"fig2: years={years}")


def fig3(labels: dict) -> None:
    rows = read_csv(TRANSLATION)
    years = [int(r["year"]) for r in rows]
    coverage = [int(r["docs_with_concept"]) / max(1, int(r["docs"])) for r in rows]
    intensity = [int(r["contexts"]) / max(1, int(r["docs"])) for r in rows]

    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=160)
    ax.bar(years, coverage, color="#9ecae1", label="share of reports mentioning")
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("coverage")
    ax.set_xlabel(labels["year"])
    ax2 = ax.twinx()
    ax2.plot(years, intensity, color="#d62728", marker="o", linewidth=2,
             label=f"mentions {labels['mentions']}")
    ax2.set_ylabel(labels["mentions"])
    ax.set_title("Diffusion: coverage saturates, intensity keeps rising", fontsize=10)
    lines = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    ax.legend(lines, [ln.get_label() for ln in lines], frameon=False, fontsize=8, loc="upper left")
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3_diffusion.png")
    plt.close(fig)
    print(f"fig3: coverage={[round(c, 2) for c in coverage]} intensity={[round(i, 2) for i in intensity]}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels = setup_labels()
    fig1(labels)
    fig2(labels)
    fig3(labels)


if __name__ == "__main__":
    main()
