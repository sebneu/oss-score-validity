#!/usr/bin/env python3
"""The bus factor against maintenance failure, read as documented and as implemented.

Same statistics as simple.py. Added after the results and descriptive: the registered reading is the stored value.
`same` restricts a reading to the projects with a stored value.

Output: data/probes/validity_bus_documented.csv

Usage:
    python analysis/04_validity/bus_documented.py --t0 2024-08-01 --resamples 2000
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import simple
import validity as v

READINGS = [
    ("stored", None, False),
    ("implemented_6", "implemented_6", False),
    ("implemented_6_same", "implemented_6", True),
    ("documented_6", "documented_6", False),
    ("documented_6_same", "documented_6", True),
    ("documented_1_same", "documented_1", True),
]


class WithReadings:
    """The study data, with the bus factor readings as a further instrument."""

    def __init__(self, data: v.Data, readings: pd.DataFrame) -> None:
        self.data = data
        self.readings = readings.set_index("project").reindex(data.projects)

    def event_mask(self, outcome: str) -> tuple[np.ndarray, np.ndarray]:
        return self.data.event_mask(outcome)

    def values(self, instrument: str, component: str) -> np.ndarray:
        if instrument != "reading":
            return self.data.values(instrument, component)
        column, _, same = component.partition(":")
        values = self.readings[column].to_numpy(dtype=float)
        return np.where(np.isnan(self.data.values("crossd", "bus_factor")), np.nan, values) if same else values


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--resamples", type=int, default=2000)
    args = ap.parse_args()
    data = WithReadings(v.Data(args.t0), pd.read_parquet(v.PROCESSED / f"bus_factor_readings_{args.t0}.parquet"))
    rng = np.random.default_rng([v.SEED, 5])
    rows = []
    for name, column, same in READINGS:
        spec = (name, "crossd", "bus_factor", "O1", -1) if column is None else (name, "reading", f"{column}:same" if same else column, "O1", -1)
        rows.append(simple.binary_row(data, spec, args.resamples, rng))
    table = pd.DataFrame(rows)
    table.to_csv(v.PROBES / "validity_bus_documented.csv", index=False)
    print(table[["score", "n", "events", "auroc", "auroc_lo", "auroc_hi", "within_commits", "within_commits_lo", "within_commits_hi", "holds", "within_days", "within_days_lo"]].round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
