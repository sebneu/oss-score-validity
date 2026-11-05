#!/usr/bin/env python3
"""How old are the published values, and how much of the cohort do they cover? (RQ1d)

Reads the published results collected on the access date. Nothing here is a feature at t0.

Output: data/probes/freshness.csv

Usage:
    python analysis/03_instruments/freshness.py --accessed 2026-11-04
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from base import RAW, ROOT, cohort


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--accessed", required=True)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    access = pd.Timestamp(args.accessed, tz="UTC")
    members = cohort(args.t0)
    members = members[~members.gone_now & members.canonical.notna()]

    scorecard = pd.read_json(RAW / "scorecard" / f"published_{args.accessed}.jsonl", lines=True)
    scorecard = scorecard.merge(members[["project", "stratum"]], on="project")
    scorecard["when"] = pd.to_datetime(scorecard.date.astype("string").where(scorecard.status == 200), utc=True, format="ISO8601", errors="coerce")
    scorecard["age"] = (access - scorecard.when).dt.days

    listed = pd.read_csv(RAW / "criticality" / "20250725_all.csv.gz", compression="gzip", usecols=["repo.url", "collection_date"])
    keys = set(listed["repo.url"].str.replace("https://github.com/", "", regex=False).str.lower())
    members = members.assign(in_list=members.canonical.str.lower().isin(keys))

    rows = []
    for stratum, part in [("all", scorecard), *scorecard.groupby("stratum")]:
        has = part[part.status == 200]
        crit = members if stratum == "all" else members[members.stratum == stratum]
        rows.append({"stratum": stratum, "repositories": len(part), "scorecard_published": len(has),
                     "date_parsed": int(has.age.notna().sum()), "age_median": has.age.median(), "age_p90": has.age.quantile(0.9),
                     "age_max": has.age.max(), "within_30d": int((has.age <= 30).sum()), "over_365d": int((has.age > 365).sum()),
                     "criticality_listed": int(crit.in_list.sum())})
    table = pd.DataFrame(rows)
    table.to_csv(ROOT / "data" / "probes" / "freshness.csv", index=False)
    print(table.to_string(index=False))
    print(listed.collection_date.min(), listed.collection_date.max())
    bad = scorecard[(scorecard.status == 200) & scorecard.age.isna()].date.head(5).tolist()
    print("unparsed dates:", bad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
