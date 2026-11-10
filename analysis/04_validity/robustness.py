#!/usr/bin/env python3
"""Robustness: the most-starred list at a second freeze date, with a 12-month window.

Registered as the second freeze date (DECISIONS.md, section 2). What this run leaves out and why is logged there:
no new Scorecard run, so no aggregate; no later-dependents outcome, because that needs two further deps.dev scans.
Measures as in simple.py, against the same list at the first freeze date.

Output: data/probes/validity_robustness.csv

Usage:
    python analysis/04_validity/robustness.py --t0 2025-01-01 --resamples 2000
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import simple
import validity as v

PAIRS = [
    ("Scorecard Maintained", "scorecard_maintained", "scorecard_maintained", "O1", -1),
    ("openCode maintenance", "opencode", "opencode_maintenance", "O1", -1),
    ("CrOSSD maturity", "crossd", "maturity_level", "O1", -1),
    ("CrOSSD bus factor", "crossd", "bus_factor", "O1", -1),
    ("CrOSSD elephant factor", "crossd", "elephant_factor", "O1", -1),
    ("CrOSSD support rate", "crossd", "support_rate", "O1c_share", -1),
    ("openCode issue response", "opencode", "opencode_response_ok", "O1c_share", -1),
    ("openCode security", "opencode", "opencode_security", "O2b", -1),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2025-01-01")
    ap.add_argument("--resamples", type=int, default=2000)
    args = ap.parse_args()
    data = v.Data(args.t0)
    first = pd.read_csv(v.PROBES / "validity_strata.csv").set_index(["score", "stratum"])
    rng = np.random.default_rng([v.SEED, 4])
    rows = []
    for spec in PAIRS:
        row = simple.binary_row(data, spec, args.resamples, rng)
        values = spec[4] * data.values(spec[1], spec[2])
        event, base = data.event_mask(spec[3])
        known = base & ~np.isnan(values)
        draws = v.resamples(int(known.sum()), args.resamples, rng)
        aucs = np.array([v.auroc(values[known][i], event[known][i]) for i in draws])
        row |= {
            "n_all": int(known.sum()), "events_all": int(event[known].sum()), "auroc_all": v.auroc(values[known], event[known]),
            "auroc_all_lo": v.interval(aucs)[0], "auroc_all_hi": v.interval(aucs)[1],
            "own_statistics": int(event[known].sum()) >= v.MIN_EVENTS,
            "first_auroc": first.loc[(spec[0], "most_starred")].auroc, "first_lo": first.loc[(spec[0], "most_starred")].auroc_lo,
        }
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(v.PROBES / "validity_robustness.csv", index=False)
    pd.set_option("display.width", 200)
    print(len(data.projects), "projects")
    print(table[["score", "outcome", "n_all", "events_all", "own_statistics", "auroc_all", "auroc_all_lo", "auroc_all_hi", "first_auroc", "first_lo", "within_commits", "within_commits_lo", "holds"]].round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
