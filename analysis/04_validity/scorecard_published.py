#!/usr/bin/env python3
"""The rebuilt Scorecard against the published scan before the freeze date.

Agreement of the values, and the same statistics on the same projects. Added after the results and descriptive. The
published values cover part of the cohort, unevenly across the lists, so they test the rebuild and do not replace it.
A score of -1 means inconclusive and counts as missing.

Outputs: data/probes/scorecard_published_agreement.csv, data/probes/validity_scorecard_published.csv

Usage:
    python analysis/04_validity/scorecard_published.py --t0 2024-08-01 --scan 2024-07-29 --resamples 2000
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import simple
import validity as v


class WithPublished:
    """The study data, with the published scan as a further instrument."""

    def __init__(self, data: v.Data, published: pd.DataFrame) -> None:
        self.data = data
        self.published = published

    def event_mask(self, outcome: str) -> tuple[np.ndarray, np.ndarray]:
        return self.data.event_mask(outcome)

    def values(self, instrument: str, component: str) -> np.ndarray:
        if instrument == "published":
            return self.published[component].to_numpy(dtype=float)
        if instrument.endswith(":same"):
            ours = self.data.values(instrument.removesuffix(":same"), component)
            name = "aggregate" if component.endswith("aggregate_t0") else component.removeprefix("scorecard_")
            return np.where(np.isnan(self.published[name].to_numpy(dtype=float)), np.nan, ours)
        return self.data.values(instrument, component)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--scan", default="2024-07-29")
    ap.add_argument("--resamples", type=int, default=2000)
    args = ap.parse_args()
    base = v.Data(args.t0)
    raw = pd.read_parquet(v.PROCESSED / f"scorecard_published_{args.scan}.parquet").set_index("project")
    checks = [c for c in raw.columns if c not in ("scan", "commit", "version", "aggregate")]
    numbers = raw[["aggregate", *checks]].astype(float).replace(-1, np.nan).reindex(base.projects)
    data = WithPublished(base, numbers)
    rng = np.random.default_rng([v.SEED, 6])

    cohort = pd.read_csv(v.ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv")
    ours_m = base.values("scorecard", "scorecard_Maintained")
    pub_m = numbers["Maintained"].to_numpy()
    both = ~np.isnan(ours_m) & ~np.isnan(pub_m)
    ours_a = base.values("scorecard", "scorecard_aggregate_t0")
    pub_a = numbers["aggregate"].to_numpy()
    both_a = ~np.isnan(ours_a) & ~np.isnan(pub_a)
    agreement = {
        "published": len(raw), "cohort": len(cohort),
        "published_most_starred": int(cohort[cohort.project.isin(raw.index)].stratum.eq("most_starred").sum()), "most_starred": int(cohort.stratum.eq("most_starred").sum()),
        "published_filtered": int(cohort[cohort.project.isin(raw.index)].stratum.eq("random_sample").sum()), "filtered": int(cohort.stratum.eq("random_sample").sum()),
        "maintained_n": int(both.sum()), "maintained_exact": float((ours_m[both] == pub_m[both]).mean()),
        "maintained_within_1": float((np.abs(ours_m[both] - pub_m[both]) <= 1).mean()), "maintained_rho": v.spearman(ours_m[both], pub_m[both]),
        "aggregate_n": int(both_a.sum()), "aggregate_rho": v.spearman(ours_a[both_a], pub_a[both_a]),
        "versions": "|".join(sorted(raw.version.dropna().unique())),
    }
    pd.Series(agreement).to_csv(v.PROBES / "scorecard_published_agreement.csv", header=["value"])

    specs = [
        ("published Maintained", "published", "Maintained", "O1", -1),
        ("rebuilt Maintained", "scorecard:same", "scorecard_Maintained", "O1", -1),
        ("published aggregate", "published", "aggregate", "O2b", -1),
        ("rebuilt aggregate", "scorecard:same", "scorecard_aggregate_t0", "O2b", -1),
    ]
    rows = [simple.binary_row(data, spec, args.resamples, rng) for spec in specs]
    event, in_base = data.event_mask("O2b")
    for check in checks:
        values = -numbers[check].to_numpy()
        known = in_base & ~np.isnan(values)
        y = event[known]
        if y.sum() < v.MIN_EVENTS:
            rows.append({"score": f"check {check}", "outcome": "O2b", "n": int(known.sum()), "events": int(y.sum())})
            continue
        draws = v.resamples(int(known.sum()), args.resamples, rng)
        lo, hi = v.interval(np.array([v.auroc(values[known][i], y[i]) for i in draws]))
        rows.append({"score": f"check {check}", "outcome": "O2b", "n": int(known.sum()), "events": int(y.sum()), "auroc": v.auroc(values[known], y), "auroc_lo": lo, "auroc_hi": hi})
    table = pd.DataFrame(rows)
    table.to_csv(v.PROBES / "validity_scorecard_published.csv", index=False)
    print(pd.Series(agreement).to_string())
    print(table[["score", "outcome", "n", "events", "auroc", "auroc_lo", "auroc_hi", "within_commits", "within_commits_lo"]].round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
