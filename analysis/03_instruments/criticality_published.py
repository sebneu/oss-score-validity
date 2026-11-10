#!/usr/bin/env python3
"""The Criticality Score as published before t0, and how close our rebuild comes to it (RQ1c).

Takes each cohort project's row from the last list before t0. These values were recorded at the time, so they are the
registered reading of the instrument (docs/decision_log_full.md, 2026-11-04), with the rebuild from rule_adapters.py as the sensitivity
check and for projects no list covers. The comparison at t0 tests the signals that the list of July 2025 no longer carries.

Outputs:
  data/processed/features/criticality_published_<t0>.parquet
  data/probes/fidelity_criticality_t0.csv

Usage:
    python analysis/03_instruments/criticality_published.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
from scipy.stats import spearmanr

from base import FEATURES, RAW, RECORDED, ROOT, assert_not_after, cohort, freeze, row, write_features
from rule_adapters import criticality_score

SIGNALS = {"created_since": "created_since", "updated_since": "updated_since", "contributor_count": "contributor_count",
           "commit_frequency": "commit_frequency", "recent_releases_count": "recent_release_count", "closed_issues_count": "closed_issues_count",
           "updated_issues_count": "updated_issues_count", "comment_frequency": "issue_comment_frequency"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = freeze(args.t0)
    members = cohort(args.t0).set_index("project")
    history = pd.read_parquet(RAW / "criticality" / f"history_cohort_{args.t0}.parquet")
    history["when"] = pd.to_datetime(history.collection_date, utc=True)
    before = history[history.when <= pd.Timestamp(t0)]
    # A project can appear under two spellings in a list; the larger star count is the live repository.
    latest = before.sort_values(["when", "star_count"]).groupby("project").tail(1).set_index("project")
    # The stored history covers the cohort of the frozen date; another date keeps only its own projects.
    latest = latest[latest.index.isin(members.index)]

    rows = []
    for project, r in latest.iterrows():
        assert_not_after(r.when.to_pydatetime(), t0, f"{project} list")
        limit = r.when.timestamp()
        rows.append(row(project, "openssf_criticality_published", r.default_score, RECORDED, limit))
        rows.append(row(project, "stars_published", r.star_count, RECORDED, limit))
        rows.append(row(project, "published_age_days", (t0.timestamp() - limit) / 86400, RECORDED, limit))
    write_features("criticality_published", args.t0, rows)

    rebuilt = pd.read_parquet(FEATURES / f"criticality_{args.t0}.parquet").pivot(index="project", columns="component", values="value")
    both = rebuilt.join(latest, how="inner", rsuffix="_pub")
    out = []
    def compare(name: str, ours: pd.Series, published: pd.Series) -> None:
        pair = pd.concat([ours, published], axis=1, keys=["a", "b"]).dropna()
        out.append({"signal": name, "n": len(pair), "spearman": spearmanr(pair.a, pair.b).statistic, "median_abs_diff": (pair.a - pair.b).abs().median(), "median_ours": pair.a.median(), "median_published": pair.b.median()})
    for ours, published in SIGNALS.items():
        compare(ours, both[f"signal_{ours}"], both[published])
    compare("score", both["openssf_criticality"], both["default_score"])
    # The same score with the published mention count in the place of dependents: tests only our other signals.
    with_mentions = []
    for project, r in both.iterrows():
        if pd.isna(r.openssf_criticality):
            with_mentions.append(None)
            continue
        signals = {name: float(r[f"signal_{name}"]) for name in SIGNALS}
        signals["dependents_count"] = float(r.github_mention_count or 0)
        with_mentions.append(criticality_score(signals))
    compare("score_with_mentions", pd.Series(with_mentions, index=both.index, dtype=float), both["default_score"])
    table = pd.DataFrame(out)
    summary = {"covered": len(latest), "latest_list": int((latest.when == before.when.max()).sum()), "most_starred": int(members.loc[latest.index, "stratum"].eq("most_starred").sum()),
               "random_sample": int(members.loc[latest.index, "stratum"].eq("random_sample").sum()), "gone_now": int(members.loc[latest.index, "gone_now"].sum())}
    for key, value in summary.items():
        table.loc[len(table), ["signal", "n"]] = [f"coverage_{key}", value]
    if args.t0 != "2024-08-01":  # the fidelity table belongs to the frozen date
        return 0
    table.to_csv(ROOT / "data" / "probes" / "fidelity_criticality_t0.csv", index=False)
    print(table.round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
