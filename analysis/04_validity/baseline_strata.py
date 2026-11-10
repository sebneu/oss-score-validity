#!/usr/bin/env python3
"""Days since the last commit and commits in 90 days per list, for the primary outcomes.

Same statistics as the per-list rows of validity.py, with a seed of its own, so the
results of validity.py do not change. Descriptive: the two measures are reference rows
in the RQ2 table.

Output: data/probes/validity_baseline_strata.csv

Usage:
    python analysis/04_validity/baseline_strata.py --t0 2024-08-01 --resamples 2000
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import validity as v

MEASURES = ("days_since_last_commit", "commits_90d")
OUTCOMES = ("O1", "O1c_share", "O2b")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--resamples", type=int, default=2000)
    args = ap.parse_args()
    data = v.Data(args.t0)
    rng = np.random.default_rng([v.SEED, 7])
    strata = data.labels.stratum.to_numpy()
    rows = []
    for measure in MEASURES:
        for outcome in OUTCOMES:
            spec = (f"Baseline {measure}", "baselines", measure, outcome, 1 if measure == "days_since_last_commit" else -1)
            for stratum in ("most_starred", "random_sample"):
                row = v.evaluate(data, spec, strata == stratum, args.resamples, rng, gain=False, with_pr=False)
                row["stratum"] = stratum
                row["own_statistics"] = row.get("events", 0) >= v.MIN_EVENTS
                rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(v.PROBES / "validity_baseline_strata.csv", index=False)
    print(table[["score", "outcome", "stratum", "n", "events", "auroc"]].round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
