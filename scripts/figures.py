"""Figures for the report (Chinese labels, publication-ish defaults).

fig1  attention over time on a balanced panel, with benchmarks and the
      proposal date marked
fig2  what the concept is bound to, by year (sentence-level co-occurrence)
fig3  diffusion: coverage saturates while intensity keeps rising

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
TRANSLATION = ROOT / "data" / "processed" / "translation_sentence.csv"
COPYRATE = ROOT / "data" / "processed" / "copyrate.csv"
OUT_DIR = ROOT / "docs" / "figs"

PRIMARY = "新质生产力"
BENCHMARKS = ["双碳", "全国统一大市场"]
PROPOSAL = 2023.75


def setup_style() -> None:
    names = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if candidate in names:
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    else:
        print("[warn] no CJK font found, labels may render as boxes")
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams.update({
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fig1() -> None:
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

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=200)
    ax.plot(years, series(PRIMARY), marker="o", linewidth=2.4, label=PRIMARY, zorder=3)
    for bench in BENCHMARKS:
        ax.plot(years, series(bench), marker="s", linewidth=1.1, alpha=0.55, label=bench)

    ax.axvline(PROPOSAL, color="grey", linestyle="--", linewidth=1)
    ax.text(PROPOSAL - 0.12, 0.355, "2023年9月提出", rotation=90, fontsize=8,
            color="grey", ha="right", va="top")

    ax.set_xlabel("年份")
    ax.set_ylabel("每千汉字提及次数", labelpad=8)
    ax.set_title(f"概念注意力趋势（平衡面板，{len(codes)} 省）")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig1_attention_trend.png", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print(f"fig1: balanced n={len(codes)}, years={years[0]}-{years[-1]}")


def fig2() -> None:
    rows = [r for r in read_csv(TRANSLATION) if int(r["contexts"]) > 0]
    years = [int(r["year"]) for r in rows]
    series = [("industry", "产业"), ("platform", "平台"), ("talent", "人才"),
              ("funding", "资金")]

    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)
    for key, label in series:
        ax.plot(years, [float(r[f"share_{key}"]) for r in rows],
                marker="o", linewidth=1.7, label=label)
    ax.plot(years, [float(r["share_concrete"]) for r in rows],
            linestyle="--", color="black", linewidth=1.3, label="任一具体工具")

    ax.set_xticks(years)
    ax.set_xlabel("年份")
    ax.set_ylabel("含工具词的概念句占比")
    ax.set_title("概念被绑定到什么上（句级共现）")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8, ncol=3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig2_translation.png", bbox_inches="tight")
    plt.close(fig)
    print(f"fig2: years={years}")


def fig3() -> None:
    rows = read_csv(TRANSLATION)
    years = [int(r["year"]) for r in rows]
    coverage = [int(r["docs_with_concept"]) / max(1, int(r["docs"])) for r in rows]
    intensity = [int(r["contexts"]) / max(1, int(r["docs"])) for r in rows]

    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)
    ax.bar(years, coverage, color="#9ecae1", width=0.6,
           label="提及该概念的省份报告占比")
    ax.set_ylim(0, 1.12)
    ax.set_xlim(2020.5, 2026.5)
    ax.set_ylabel("覆盖率")
    ax.set_xlabel("年份")

    ax2 = ax.twinx()
    ax2.plot(years, intensity, color="#d62728", marker="o", linewidth=2, label="平均提及次数（次/份）")
    ax2.set_ylabel("次/份")
    ax2.set_ylim(0, max(intensity) * 1.15)
    ax2.spines["right"].set_visible(True)

    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    ax.legend(handles, [h.get_label() for h in handles],
              frameon=False, fontsize=8, loc="upper left")
    ax.set_title("扩散：覆盖率一年饱和，强度持续上升")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig3_diffusion.png", bbox_inches="tight")
    plt.close(fig)
    print(f"fig3: coverage={[round(c, 2) for c in coverage[-3:]]} "
          f"intensity={[round(i, 2) for i in intensity[-3:]]}")


def fig4() -> None:
    rows = read_csv(COPYRATE)
    years = sorted({int(r["year"]) for r in rows})
    overall = []
    concept = []
    for year in years:
        group = [r for r in rows if int(r["year"]) == year]
        overall.append(sum(float(r["gram8_overall"]) for r in group) / len(group))
        with_c = [r for r in group if int(r["concept_sentences"]) > 0]
        concept.append(
            sum(float(r["gram8_concept"]) for r in with_c) / len(with_c) if with_c else float("nan")
        )

    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)
    ax.plot(years, overall, marker="o", linewidth=1.8, label="全篇 8 字片段重合率")
    ax.plot(years, concept, marker="s", linewidth=2.2, color="#d62728",
            label="含「新质生产力」的句子")
    ax.set_xlabel("年份")
    ax.set_ylabel("与中央报告的 8 字片段重合率")
    ax.set_title("话语层面的借用：整句不抄，措辞趋同")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig4_copy.png", bbox_inches="tight")
    plt.close(fig)
    print(f"fig4: overall={[round(v, 3) for v in overall[-3:]]} "
          f"concept={[round(v, 3) for v in concept[-3:]]}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    setup_style()
    fig1()
    fig2()
    fig3()
    fig4()


if __name__ == "__main__":
    main()
