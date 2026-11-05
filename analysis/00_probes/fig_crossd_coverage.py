#!/usr/bin/env python3
"""Coverage-by-date figure, from `data/probes/crossd_coverage.parquet`.

(a) Projects with a snapshot per week, by stratum. (b) How long after its snapshot a value
was actually read from GitHub, for the snapshots around the candidate freeze date.

Output: data/probes/crossd_coverage.pdf and .png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / "data" / "probes"

INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = {
    "most_starred": ("most-starred", "#2a78d6"),
    "random_sample": ("filtered sample", "#eb6834"),
    "netidee": ("netidee", "#1baf7a"),
    "added_later": ("added later", "#eda100"),
}


def style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(INK_2)
    ax.grid(axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_2, labelsize=6.5, width=0.6, length=2.5)
    ax.yaxis.label.set_color(INK_2)


def main() -> int:
    cov = pd.read_parquet(PROBES / "crossd_coverage.parquet")
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(3.5, 3.5), constrained_layout=True)

    weekly = (
        cov.assign(week=cov.snapshot_utc.dt.tz_localize(None).dt.to_period("W").dt.start_time)
        .groupby(["week", "stratum"])
        .project.nunique()
        .unstack(fill_value=0)
    )
    for stratum, (label, color) in SERIES.items():
        if stratum in weekly:
            top.plot(weekly.index, weekly[stratum], color=color, linewidth=1.2, label=label)
    top.set_ylabel("projects per week", fontsize=6.5)
    top.set_title("(a) Projects with a snapshot, by list", loc="left", fontsize=7.5, color=INK)
    top.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
    top.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    top.legend(frameon=False, fontsize=6, loc="upper center", ncols=4, labelcolor=INK_2, handlelength=1.2, columnspacing=0.9, handletextpad=0.4)
    top.set_ylim(0, weekly.max().max() * 1.22)
    style(top)

    near = cov[
        cov.observed_ts.notna()
        & (cov.snapshot_utc >= "2024-07-01")
        & (cov.snapshot_utc < "2024-08-11")
    ].copy()
    near["delay"] = (near.observed_ts - near.snapshot_ts) / 86400
    near["day"] = near.snapshot_utc.dt.tz_localize(None).dt.floor("D")
    per_day = near.groupby("day").delay.quantile([0.5, 0.9]).unstack()
    bottom.plot(per_day.index, per_day[0.5], color="#2a78d6", linewidth=1.2, marker="o",
                markersize=2.5, label="median")
    bottom.plot(per_day.index, per_day[0.9], color="#eb6834", linewidth=1.2, marker="o",
                markersize=2.5, label="90th percentile")
    bottom.set_ylabel("days to reading", fontsize=6.5)
    bottom.set_title(
        "(b) Delay from a snapshot to the reading of its values",
        loc="left", fontsize=7.5, color=INK,
    )
    bottom.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    bottom.set_ylim(bottom=0)
    bottom.legend(frameon=False, fontsize=6, loc="upper left", labelcolor=INK_2, handlelength=1.4)
    bottom.set_xlabel("snapshot date, 2024", color=INK_2, fontsize=6.5)
    style(bottom)

    for ext in ("pdf", "png"):
        fig.savefig(PROBES / f"crossd_coverage.{ext}", dpi=200)
    print(f"wrote {PROBES.relative_to(ROOT)}/crossd_coverage.pdf and .png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
