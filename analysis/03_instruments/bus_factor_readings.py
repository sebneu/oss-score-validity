#!/usr/bin/env python3
"""The bus factor as documented and as implemented, over three windows, from dated commits.

The documentation defines it as the smallest number of people contributing 50% of the commits, at least 1, over six
months. The implementation stops at a running 80%, so one identity holding that share reads 0, and the stored values
match a window of one month (`rebuild_bus_factor.py`). The stored value stays the registered reading. These readings
were added after the results, to see how far the result for the bus factor belongs to the implementation.
Each value is dated by the CrOSSD reading of the project. No outcomes are read.

Output: data/processed/bus_factor_readings_<t0>.parquet

Usage:
    python analysis/03_instruments/bus_factor_readings.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime

import pandas as pd

from base import PROCESSED, add_months, assert_not_after, cohort, freeze
from rebuild_bus_factor import WEB_FLOW

WINDOWS = (1, 6, 12)


def contributions(commits: pd.DataFrame) -> list[int]:
    people: list[str] = []
    for r in commits.itertuples():
        people.append(r.author if r.committer == WEB_FLOW else r.committer)
        if r.co_authors:
            people += r.co_authors.split("|")
    return sorted(Counter(people).values(), reverse=True)


def implemented(counts: list[int]) -> int:
    half, stop = sum(counts) * 0.5, sum(counts) * 0.8
    running, reached, value = 0, 0, 0
    for n in counts:
        running += n
        if running >= stop:
            break
        if reached <= half:
            reached += n
            value += 1
    return value


def documented(counts: list[int]) -> int:
    half = sum(counts) * 0.5
    running, value = 0, 0
    for n in counts:
        running += n
        value += 1
        if running >= half:
            break
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = freeze(args.t0)
    stored = pd.read_parquet(PROCESSED / "features" / f"crossd_{args.t0}.parquet")
    stored = stored[stored.component == "bus_factor"].set_index("project")
    rows = []
    for m in cohort(args.t0).itertuples():
        row = {"project": m.project}
        path = PROCESSED / "git" / f"{m.project.replace('/', '__')}.parquet"
        observed = float(stored.loc[m.project, "as_of"])
        assert_not_after(observed, t0, m.project)
        if path.exists():
            commits = pd.read_parquet(path)
            commits = commits[commits.committed <= observed]
            moment = datetime.fromtimestamp(observed, UTC)
            for months in WINDOWS:
                window = commits[commits.committed > add_months(moment, -months).timestamp()]
                if len(window):
                    counts = contributions(window)
                    row[f"implemented_{months}"] = implemented(counts)
                    row[f"documented_{months}"] = documented(counts)
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_parquet(PROCESSED / f"bus_factor_readings_{args.t0}.parquet", index=False)
    print(table.notna().sum().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
