#!/usr/bin/env python3
"""Published Scorecard results of the cohort at one weekly scan, from the project's BigQuery table.

The project announced in August 2026 that this dataset is no longer available, and it could still be read in November
2026, with scans up to 2026-08-24. The scan must not be later than t0. Check names and scores only. Used to test the
rebuild at the freeze date; these values are no feature of the frozen table.

Output: data/processed/scorecard_published_<scan>.parquet

Usage:
    python analysis/03_instruments/collect_scorecard_published.py --t0 2024-08-01 --scan 2024-07-29
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import probe_depsdev_bq  # noqa: E402

TABLE = "`openssf.scorecardcron.scorecard-v2`"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--scan", default="2024-07-29")
    ap.add_argument("--max-gb", type=float, default=5.0)
    args = ap.parse_args()
    if args.scan > args.t0:
        raise SystemExit("the scan is later than t0")
    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv")
    names = {f"github.com/{p.lower()}": p for p in cohort.project}
    names |= {f"github.com/{c.lower()}": p for p, c in zip(cohort.project, cohort.canonical) if isinstance(c, str) and f"github.com/{c.lower()}" not in names}
    sql = f"""SELECT repo.name AS name, repo.commit AS commit, scorecard.version AS version, score,
                     ARRAY(SELECT AS STRUCT x.name AS check_name, x.score AS check_score FROM UNNEST(checks) x) AS checks
              FROM {TABLE} WHERE date = '{args.scan}' AND LOWER(repo.name) IN UNNEST(@names)"""
    params = [bigquery.ArrayQueryParameter("names", "STRING", sorted(names))]
    client = bigquery.Client(project=probe_depsdev_bq.calling_project())
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params))
    gigabytes = dry.total_bytes_processed / 1e9
    print(f"scanning {gigabytes:.2f} GB", flush=True)
    if gigabytes > args.max_gb:
        raise SystemExit(f"above --max-gb {args.max_gb}")
    table = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result().to_dataframe(create_bqstorage_client=False)
    rows = []
    for r in table.itertuples():
        row = {"project": names[r.name.lower()], "scan": args.scan, "commit": r.commit, "version": r.version, "aggregate": r.score}
        row |= {c["check_name"]: c["check_score"] for c in r.checks}
        rows.append(row)
    out = pd.DataFrame(rows).drop_duplicates("project").sort_values("project")
    path = ROOT / "data" / "processed" / f"scorecard_published_{args.scan}.parquet"
    out.to_parquet(path, index=False)
    print(f"{path.relative_to(ROOT)}: {len(out)} of {len(cohort)} projects")
    print(out.version.value_counts().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
