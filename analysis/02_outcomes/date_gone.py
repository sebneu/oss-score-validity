#!/usr/bin/env python3
"""Look for public events of repositories gone from GitHub after the window closed (Amendment 1, A4).

GitHub cannot say when a repository went away. An event in GH Archive under its name after the window
shows it still existed then, which excludes it from O1a. No event proves nothing either way.

Scans only the columns needed and only the months after the window, about 7 GB.

Output: data/raw/gharchive/gone_events_<t0>.parquet

Usage:
    python analysis/02_outcomes/date_gone.py --t0 2024-08-01
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--first-month", default="2608", help="first month after the window, YYMM")
    ap.add_argument("--last-month", default="2611", help="month of the data freeze, YYMM")
    ap.add_argument("--max-gb", type=float, default=20.0)
    args = ap.parse_args()

    meta = pd.read_parquet(
        ROOT / "data" / "processed" / f"github_meta_{args.t0}.parquet", columns=["project", "resolved"]
    )
    names = sorted(meta[~meta.resolved].project.str.lower())
    sql = f"""SELECT LOWER(repo.name) AS repo, MAX(created_at) AS last_event, COUNT(*) AS events
              FROM `githubarchive.month.20*`
              WHERE _TABLE_SUFFIX BETWEEN '{args.first_month}' AND '{args.last_month}'
                AND LOWER(repo.name) IN UNNEST(@names)
              GROUP BY repo"""
    params = [bigquery.ArrayQueryParameter("names", "STRING", names)]
    client = bigquery.Client(project=probe_depsdev_bq.calling_project())
    dry = client.query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params)
    )
    gigabytes = dry.total_bytes_processed / 1e9
    print(f"{len(names)} repositories, scanning {gigabytes:.1f} GB", flush=True)
    if gigabytes > args.max_gb:
        raise SystemExit(f"above --max-gb {args.max_gb}")
    table = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    frame = table.to_dataframe(create_bqstorage_client=False)
    out = ROOT / "data" / "raw" / "gharchive" / f"gone_events_{args.t0}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(frame)} of {len(names)} have an event after the window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
