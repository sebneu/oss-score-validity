#!/usr/bin/env python3
"""AUROC with intervals for the primary pairs, pooled and per list, against the rule of 0.60.

Output: paper/figures/validity_auroc.pdf and data/probes/validity_auroc.png

Usage:
    python analysis/04_validity/fig_validity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / "data" / "probes"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
LISTS = {"most_starred": ("most-starred", "#2a78d6", "s"), "random_sample": ("filtered sample", "#eb6834", "D")}
LABELS = {"Scorecard Maintained": "Scorecard Maintained", "openCode maintenance": "openCode maintenance", "CrOSSD maturity": "CrOSSD maturity", "CrOSSD bus factor": "CrOSSD bus factor",
          "CrOSSD elephant factor": "CrOSSD elephant factor", "CrOSSD support rate": "CrOSSD support rate", "openCode issue response": "openCode response", "Scorecard aggregate": "Scorecard aggregate",
          "openCode security": "openCode security"}
GROUPS = {"O1": "Maintenance failure", "O1c_share": "Unanswered issues", "O2b": "Unfixed advisory"}


def main() -> int:
    primary = pd.read_csv(PROBES / "validity_primary.csv")
    strata = pd.read_csv(PROBES / "validity_strata.csv").set_index(["score", "stratum"])
    fig, ax = plt.subplots(figsize=(3.5, 3.5), constrained_layout=True)
    y, ticks, labels = 0.0, [], []
    for outcome, title in GROUPS.items():
        ax.text(0.205, y - 0.1, title, fontsize=7, color=INK_2, fontstyle="italic", va="center")
        y += 0.75
        for row in primary[primary.outcome == outcome].itertuples():
            ax.plot([row.auroc_lo, row.auroc_hi], [y, y], color=INK, linewidth=1.6, solid_capstyle="round", zorder=3)
            ax.plot(row.auroc, y, "o", color=INK, markersize=4.5, zorder=4)
            for offset, (stratum, (_, color, marker)) in zip((0.27, 0.54), LISTS.items()):
                s = strata.loc[(row.score, stratum)]
                own = bool(s.own_statistics)
                ax.plot([s.auroc_lo, s.auroc_hi], [y + offset] * 2, color=color, linewidth=0.9, alpha=1 if own else 0.45, zorder=2)
                ax.plot(s.auroc, y + offset, marker, markersize=3, markerfacecolor=color if own else "white", markeredgecolor=color, markeredgewidth=0.8, zorder=3)
            ticks.append(y)
            labels.append(LABELS[row.score])
            y += 1.0
        y += 0.15
    ax.axvline(0.5, color=INK_2, linewidth=0.8, zorder=1)
    ax.axvline(0.6, color=INK_2, linewidth=0.8, linestyle=(0, (3, 2)), zorder=1)
    ax.text(0.5, -0.8, "no separation", fontsize=6, color=INK_2, ha="right", va="center")
    ax.text(0.605, -0.8, "rule: 0.60", fontsize=6, color=INK_2, ha="left", va="center")
    ax.set_yticks(ticks, labels, fontsize=7, color=INK)
    ax.set_ylim(y - 0.2, -1.2)
    ax.set_xlim(0.2, 0.92)
    ax.set_xlabel("AUROC, with 95% interval", fontsize=7, color=INK_2)
    ax.tick_params(axis="x", labelsize=7, colors=INK_2)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)
    handles = [plt.Line2D([], [], color=INK, marker="o", markersize=4, linewidth=1.4, label="pooled")]
    handles += [plt.Line2D([], [], color=c, marker=mk, markersize=3, linewidth=0.9, label=label) for label, c, mk in LISTS.values()]
    ax.legend(handles=handles, fontsize=6, frameon=False, loc="lower right", handlelength=1.6, labelcolor=INK_2)
    fig.savefig(ROOT / "paper" / "figures" / "validity_auroc.pdf")
    fig.savefig(PROBES / "validity_auroc.png", dpi=200)
    return 0


if __name__ == "__main__":
    sys.exit(main())
