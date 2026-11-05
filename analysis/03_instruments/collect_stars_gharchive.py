#!/usr/bin/env python3
"""Stars given by t0, counted from dated events in GH Archive.

GitHub no longer serves the dated stargazer list to outside accounts (404 over REST, FORBIDDEN over GraphQL), so the
count comes from the WatchEvent rows before t0. Rows match on the repository id, which survives renames, or on the name
for early rows without an id. Limits: a star removed later still counts, GH Archive has gaps
and starts in 2011, so older projects are undercounted. The check against the deps.dev snapshot is in the output.

Scans 170 GB in BigQuery, capped below.

Outputs:
  data/raw/gharchive/stars_<t0>.parquet
  data/probes/stars_gharchive_check.csv

Usage:
    python analysis/03_instruments/collect_stars_gharchive.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_probes"))

import probe_depsdev_bq  # noqa: E402

from base import PROCESSED, RAW, ROOT, cohort  # noqa: E402

CAP = 175 * 10**9
# The tables end before t0, so no date column is read. Only 2011 to 2014 hold rows without an id.
# Three queries, because a union of the wildcard tables scans twice as much.
QUERIES = [
    """SELECT repo.id AS id, CAST(NULL AS STRING) AS name, COUNT(*) AS events FROM `githubarchive.year.20*`
       WHERE _TABLE_SUFFIX BETWEEN '15' AND '23' AND type = 'WatchEvent' AND repo.id IN UNNEST(@ids) GROUP BY 1""",
    """SELECT repo.id AS id, CAST(NULL AS STRING) AS name, COUNT(*) AS events FROM `githubarchive.month.2024*`
       WHERE _TABLE_SUFFIX BETWEEN '01' AND '07' AND type = 'WatchEvent' AND repo.id IN UNNEST(@ids) GROUP BY 1""",
    """SELECT IF(repo.id IN UNNEST(@ids), repo.id, -1) AS id, IF(repo.id IN UNNEST(@ids), NULL, LOWER(repo.name)) AS name, COUNT(*) AS events
       FROM `githubarchive.year.20*`
       WHERE _TABLE_SUFFIX BETWEEN '11' AND '14' AND type = 'WatchEvent'
         AND (repo.id IN UNNEST(@ids) OR (repo.id IS NULL AND LOWER(repo.name) IN UNNEST(@names))) GROUP BY 1, 2""",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    if args.t0 != "2024-08-01":
        raise SystemExit("the table range above is written for t0 = 2024-08-01")
    members = cohort(args.t0)
    meta = pd.read_parquet(PROCESSED / f"github_meta_{args.t0}.parquet", columns=["project", "databaseId"]).dropna()
    meta = meta[meta.project.isin(members.project)]
    meta["databaseId"] = meta.databaseId.astype("int64")
    names = sorted({str(p).lower() for p in members.project} | {str(c).lower() for c in members.canonical.dropna()})
    params = [bigquery.ArrayQueryParameter("ids", "INT64", meta.databaseId.tolist()),
              bigquery.ArrayQueryParameter("names", "STRING", names)]
    client = bigquery.Client(project=probe_depsdev_bq.calling_project())
    scan = sum(client.query(q, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params)).total_bytes_processed for q in QUERIES)
    print(f"scan: {scan / 1e9:.1f} GB", flush=True)
    if scan > CAP:
        raise SystemExit("above the cap")
    result = pd.concat([client.query(q, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=CAP, query_parameters=params)).to_dataframe() for q in QUERIES])

    by_id = result[result.id != -1].groupby("id").events.sum()
    by_name = result[result.id == -1].groupby("name").events.sum()
    rows = []
    canonical = members.set_index("project").canonical
    ids = meta.set_index("project").databaseId
    for project in members.project:
        count = int(by_id.get(ids.get(project, -2), 0))
        spellings = {project.lower()} | ({str(canonical[project]).lower()} if pd.notna(canonical[project]) else set())
        count += int(sum(by_name.get(s, 0) for s in spellings))
        rows.append({"project": project, "star_events": count, "has_id": project in ids.index})
    table = pd.DataFrame(rows)
    out = RAW / "gharchive" / f"stars_{args.t0}.parquet"
    table.to_parquet(out, index=False)

    snapshot = pd.read_parquet(RAW / "depsdev" / "projects_2024-07-29.parquet", columns=["Name", "StarsCount"]).dropna()
    known = dict(zip(snapshot.Name.str.lower(), snapshot.StarsCount))
    table["stars"] = [known.get(str(canonical[p]).lower(), known.get(p.lower())) for p in table.project]
    both = table[table.stars.notna() & (table.stars > 0)]
    ratio = both.star_events / both.stars
    check = {"n": len(both), "spearman": spearmanr(both.star_events, both.stars).statistic, "ratio_median": ratio.median(),
             "ratio_p10": ratio.quantile(0.1), "ratio_p90": ratio.quantile(0.9), "no_snapshot": int(table.stars.isna().sum())}
    pd.DataFrame([check]).to_csv(ROOT / "data" / "probes" / "stars_gharchive_check.csv", index=False)
    print(check, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
