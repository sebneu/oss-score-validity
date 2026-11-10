#!/usr/bin/env python3
"""Table, figure and macros of the case panel, from the fixed readings (see DECISIONS.md).

Outputs:
  paper/generated/t_cases.tex, paper/generated/cases.tex, paper/figures/case_minio.pdf

Usage:
    python analysis/05_cases/case_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "data" / "processed" / "cases"
GENERATED = ROOT / "paper" / "generated"
FIGURES = ROOT / "paper" / "figures"
ORDER = [("axios/axios", "axios"), ("Lightning-AI/pytorch-lightning", "Lightning"), ("ultralytics/ultralytics", "Ultralytics"),
         ("facebook/react", "React"), ("mongodb/mongo", "MongoDB"), ("minio/minio", "MinIO")]
INK, INK_2, GRID, SHADE = "#0b0b0b", "#52514e", "#e4e3df", "#f1f0ec"
SERIES = [("maturity_level", "maturity level", "#1baf7a"), ("criticality_score", "criticality", "#2a78d6"), ("support_rate", "support rate", "#eb6834")]


def fmt(value, digits: int = 0) -> str:
    return "--" if pd.isna(value) else f"{value:.{digits}f}"


def main() -> int:
    readings = pd.read_csv(CASES / "readings.csv", parse_dates=["observed"])
    series = pd.read_parquet(CASES / "series.parquet")
    outcomes_meta = pd.read_parquet(ROOT / "data" / "processed" / "github_meta_2024-08-01.parquet", columns=["project", "archivedAt"])
    GENERATED.mkdir(parents=True, exist_ok=True)

    def at(project: str, mark: str):
        return readings[(readings.project == project) & (readings.mark == mark)].iloc[0]

    rows = []
    lines = ["\\setlength{\\tabcolsep}{4pt}", "\\begin{tabular}{llrrrr}", "\\toprule",
             "Project & Event & Age & Criticality & Bus factor & Support rate \\\\", "\\midrule"]
    current = None
    for project, label in ORDER:
        before, after = at(project, "before"), at(project, "4w_after")
        if before.mechanism != current:
            current = before.mechanism
            lines.append(f"\\multicolumn{{6}}{{l}}{{\\textit{{{current.capitalize()}}}}} \\\\")
        age = (pd.Timestamp(before.event).date() - before.observed.date()).days

        def pair(column: str) -> str:
            return f"{fmt(before[column])} $\\to$ {fmt(after[column])}"

        row = [label, before.event, str(age), pair("criticality_score"), pair("bus_factor"), pair("support_rate")]
        rows.append(row)
        lines.append(" & ".join(row) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    (GENERATED / "t_cases.tex").write_text("\n".join(lines) + "\n")

    minio = series[(series.project == "minio/minio") & (series.block == "metrics")].sort_values("observed")
    announced = pd.Timestamp("2025-12-03", tz="UTC")
    archived = pd.to_datetime(outcomes_meta[outcomes_meta.project == "minio/minio"].archivedAt.iloc[0], utc=True, format="ISO8601")
    pre, post = minio[minio.observed < announced], minio[minio.observed >= announced]
    days = series[series.project.isin(["axios/axios", "minio/minio"])].observed.dropna().dt.normalize().drop_duplicates().sort_values()
    gap_end = days[days.diff().dt.days.idxmax()]
    gap_start = days[days < gap_end].max()
    macros = {
        "CaseGapFrom": gap_start.date().isoformat(), "CaseGapTo": gap_end.date().isoformat(),
        "CaseReactCrit": fmt(at("facebook/react", "before").criticality_score), "CaseMongoCrit": fmt(at("mongodb/mongo", "before").criticality_score),
        "CaseMinioArchived": archived.date().isoformat(),
        "CaseMinioSupportPeak": fmt(pre.support_rate.max()), "CaseMinioSupportPre": fmt(pre.support_rate.iloc[-1]), "CaseMinioSupportLast": fmt(minio.support_rate.iloc[-1]),
        "CaseMinioBusPre": fmt(pre.bus_factor.iloc[-1]), "CaseMinioBusPost": fmt(post.bus_factor.iloc[0]),
        "CaseMinioCritPre": fmt(pre.criticality_score.iloc[-1]), "CaseMinioCritLast": fmt(minio.criticality_score.iloc[-1]),
        "CaseMinioMatPre": fmt(pre.maturity_level.iloc[-1]), "CaseMinioMatPost": fmt(post.maturity_level.iloc[0]), "CaseMinioMatLast": fmt(minio.maturity_level.iloc[-1]),
    }
    (GENERATED / "cases.tex").write_text("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in macros.items()))

    fig, ax = plt.subplots(figsize=(3.5, 2.5), constrained_layout=True)
    ax.axvspan(gap_start, gap_end, color=SHADE, linewidth=0)
    for column, label, color in SERIES:
        part = minio[["observed", column]].dropna()
        middle = gap_start + (gap_end - gap_start) / 2
        for side in (part[part.observed <= middle], part[part.observed >= middle]):
            ax.plot(side.observed, side[column], color=color, linewidth=1.6)
        first = part.iloc[0]
        ax.annotate(label, (first.observed, part[column].iloc[:6].max()), xytext=(0, 4), textcoords="offset points", ha="left", fontsize=7.5, color=INK)
    for date, text in ((announced, "maintenance mode"), (archived, "archived")):
        ax.axvline(date, color=INK_2, linewidth=0.9, linestyle=(0, (3, 2)))
        ax.annotate(text, (date, 103), xytext=(0, 0), textcoords="offset points", ha="center", va="bottom", fontsize=7, color=INK_2, annotation_clip=False)
    ax.set_ylim(0, 100)
    ax.set_ylabel("value (0 to 100)", fontsize=8, color=INK_2)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_2, labelsize=7)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "case_minio.pdf")
    fig.savefig(CASES / "case_minio.png", dpi=170)

    for row in rows:
        print(" | ".join(row))
    print(macros)
    return 0


if __name__ == "__main__":
    sys.exit(main())
