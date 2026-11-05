#!/usr/bin/env python3
"""All published Criticality Score lists, for the cohort, from BigQuery.

The GCS bucket no longer serves files since the project's turn-down (ossf/criticality_score#833), but the table
`openssf.criticality_score_cron.criticality-score-v0` still answers and holds every list. These values were recorded at
the time. Scans 3.7 GB at most, capped below.

Outputs:
  data/raw/criticality/history_cohort_<t0>.parquet   one row per cohort repository and list
  data/probes/criticality_lists.csv                  per list: rows and the share of zero issue signals

Usage:
    python analysis/03_instruments/collect_criticality_history.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_probes"))

import probe_depsdev_bq  # noqa: E402

from base import RAW, ROOT, cohort  # noqa: E402

TABLE = "`openssf.criticality_score_cron.criticality-score-v0`"
CAP = 5 * 10**9
PER_LIST = f"""
SELECT DATE(collection_date) AS list_date, COUNT(*) AS rows_total,
       COUNTIF(legacy.closed_issues_count = 0) / COUNT(*) AS zero_closed,
       COUNTIF(legacy.updated_issues_count = 0) / COUNT(*) AS zero_updated,
       COUNTIF(legacy.issue_comment_frequency = 0) / COUNT(*) AS zero_comments,
       COUNTIF(legacy.closed_issues_count = 0 AND legacy.updated_issues_count = 0 AND legacy.issue_comment_frequency = 0) / COUNT(*) AS zero_all
FROM {TABLE} GROUP BY 1 ORDER BY 1
"""
COHORT = f"""
SELECT collection_date, default_score, LOWER(repo.url) AS url, repo.star_count AS star_count, repo.created_at AS created_at, repo.updated_at AS updated_at,
       legacy.created_since AS created_since, legacy.updated_since AS updated_since, legacy.contributor_count AS contributor_count,
       legacy.org_count AS org_count, legacy.commit_frequency AS commit_frequency, legacy.recent_release_count AS recent_release_count,
       legacy.updated_issues_count AS updated_issues_count, legacy.closed_issues_count AS closed_issues_count,
       legacy.issue_comment_frequency AS issue_comment_frequency, legacy.github_mention_count AS github_mention_count,
       depsdev.dependent_count AS dependent_count
FROM {TABLE} WHERE LOWER(repo.url) IN UNNEST(@urls)
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    members = cohort(args.t0)
    spellings = {}
    for m in members.itertuples():
        spellings[f"https://github.com/{m.project}".lower()] = m.project
        if isinstance(m.canonical, str):
            spellings[f"https://github.com/{m.canonical}".lower()] = m.project
    client = bigquery.Client(project=probe_depsdev_bq.calling_project())
    lists = client.query(PER_LIST, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=CAP)).to_dataframe()
    lists.to_csv(ROOT / "data" / "probes" / "criticality_lists.csv", index=False)
    params = [bigquery.ArrayQueryParameter("urls", "STRING", sorted(spellings))]
    rows = client.query(COHORT, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=CAP, query_parameters=params)).to_dataframe()
    rows["project"] = rows.url.map(spellings)
    rows.to_parquet(RAW / "criticality" / f"history_cohort_{args.t0}.parquet", index=False)
    print(lists.round(3).to_string())
    print(f"{len(rows)} rows, {rows.project.nunique()} of {len(members)} projects", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
