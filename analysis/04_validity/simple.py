#!/usr/bin/env python3
"""Simple comparisons with naive measures: no model, no multiple-comparison procedure.

A deviation from the registered analysis, made after the results were known (DECISIONS.md, section 6,
deviation 4). These readings are descriptive. The registered analysis stays in validity.py.

For each primary pair, on the projects where the score and the baseline measures are known:
  - AUROC of the score and of each single baseline measure, with a paired bootstrap interval for the difference;
  - AUROC among projects of similar activity: within quartiles of commits in the 90 days before t0, with ties kept
    together, averaged with weights by the number of event and non-event pairs. Quartiles of the days since the last
    commit are the check on that choice;
  - for later dependents, the same with rank correlations, within quartiles of dependents at t0, weighted by projects.

Output: data/probes/validity_simple.csv

Usage:
    python analysis/04_validity/simple.py --t0 2024-08-01 --resamples 2000
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import validity as v


def bins(values: np.ndarray) -> np.ndarray:
    """Quartile groups; tied projects stay together, so a heavily tied measure can give fewer than four groups."""
    return np.searchsorted(np.unique(np.quantile(values, [0.25, 0.5, 0.75])), values, side="left")


def within_auroc(score: np.ndarray, y: np.ndarray, group: np.ndarray) -> float:
    total, weight = 0.0, 0.0
    for g in np.unique(group):
        here = group == g
        pairs = y[here].sum() * (~y[here]).sum()
        if pairs:
            total += v.auroc(score[here], y[here]) * pairs
            weight += pairs
    return total / weight if weight else np.nan


def within_rho(score: np.ndarray, later: np.ndarray, group: np.ndarray) -> float:
    total, weight = 0.0, 0
    for g in np.unique(group):
        here = group == g
        if here.sum() >= 5 and len(np.unique(score[here])) > 1 and len(np.unique(later[here])) > 1:
            total += v.spearman(score[here], later[here]) * here.sum()
            weight += here.sum()
    return total / weight if weight else np.nan


def binary_row(data: v.Data, spec: tuple, count: int, rng: np.random.Generator) -> dict:
    name, instrument, component, outcome, sign = spec
    event, base = data.event_mask(outcome)
    values = sign * data.values(instrument, component)
    measures = {b: (1 if b == "days_since_last_commit" else -1) * data.values("baselines", b) for b in v.BASELINE}
    known = base & ~np.isnan(values) & ~np.isnan(np.column_stack(list(measures.values()))).any(axis=1)
    s, y = values[known], event[known]
    row = {"score": name, "outcome": outcome, "n": len(y), "events": int(y.sum()), "auroc": v.auroc(s, y)}
    draws = v.resamples(len(y), count, rng)
    aucs = np.array([v.auroc(s[i], y[i]) for i in draws])
    row["auroc_lo"], row["auroc_hi"] = v.interval(aucs)
    for b, measure in measures.items():
        m = measure[known]
        row[f"{b}_auroc"] = v.auroc(m, y)
        row[f"{b}_diff"] = row["auroc"] - row[f"{b}_auroc"]
        row[f"{b}_diff_lo"], row[f"{b}_diff_hi"] = v.interval(aucs - np.array([v.auroc(m[i], y[i]) for i in draws]))
    for label, measure in (("commits", data.values("baselines", "commits_90d")), ("days", data.values("baselines", "days_since_last_commit"))):
        group = bins(measure[known])
        row[f"within_{label}"] = within_auroc(s, y, group)
        row[f"within_{label}_lo"], row[f"within_{label}_hi"] = v.interval(np.array([within_auroc(s[i], y[i], group[i]) for i in draws]))
        row[f"groups_{label}"] = len(np.unique(group))
    row["holds"] = row["within_commits_lo"] > 0.60
    row["holds_days"] = row["within_days_lo"] > 0.60
    return row


def dependents_row(data: v.Data, spec: tuple, count: int, rng: np.random.Generator) -> dict:
    name, instrument, component, outcome, _ = spec
    values = data.values(instrument, component)
    later = pd.to_numeric(data.labels.I1b, errors="coerce").to_numpy(dtype=float)
    at_t0 = pd.to_numeric(data.labels.I1b_t0, errors="coerce").to_numpy(dtype=float)
    known = ~np.isnan(values) & ~np.isnan(later) & ~np.isnan(at_t0)
    s, l, d = values[known], later[known], at_t0[known]
    group = bins(d)
    row = {"score": name, "outcome": outcome, "n": len(s), "rho": v.spearman(s, l), "rho_t0": v.spearman(d, l), "within_rho": within_rho(s, l, group), "groups": len(np.unique(group))}
    draws = v.resamples(len(s), count, rng)
    rhos = np.array([v.spearman(s[i], l[i]) for i in draws])
    row["rho_diff"] = row["rho"] - row["rho_t0"]
    row["rho_diff_lo"], row["rho_diff_hi"] = v.interval(rhos - np.array([v.spearman(d[i], l[i]) for i in draws]))
    row["within_rho_lo"], row["within_rho_hi"] = v.interval(np.array([within_rho(s[i], l[i], group[i]) for i in draws]))
    row["holds"] = row["within_rho_lo"] > 0
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--resamples", type=int, default=2000)
    args = ap.parse_args()
    data = v.Data(args.t0)
    rng = np.random.default_rng([v.SEED, 3])
    rows = [dependents_row(data, spec, args.resamples, rng) if spec[3] == "I1b" else binary_row(data, spec, args.resamples, rng) for spec in v.PRIMARY]
    table = pd.DataFrame(rows)
    table.to_csv(v.PROBES / "validity_simple.csv", index=False)
    pd.set_option("display.width", 220)
    print(table[["score", "outcome", "n", "auroc", "days_since_last_commit_auroc", "commits_90d_auroc", "days_since_last_commit_diff_lo", "days_since_last_commit_diff_hi", "within_commits", "within_commits_lo", "within_commits_hi", "groups_commits", "holds", "within_days", "within_days_lo", "groups_days", "holds_days", "rho", "rho_t0", "within_rho", "within_rho_lo", "within_rho_hi", "groups"]].round(3).T.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
