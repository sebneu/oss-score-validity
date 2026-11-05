#!/usr/bin/env python3
"""Dependents at both ends of the window for every package of the cohort (Amendment 1, A5).

I1b is the count at the last snapshot before the window closes; the count at the snapshot before t0
is its required baseline, because criticality scores use dependents as an input. Two partitions of
`Dependents`, about 450 GB. The dry run stops the query above `--max-gb`. Counted as in
`dependents_at_t0.py`: a size measure, not an exact count.

Output: data/raw/depsdev/dependents_i1b_<t0>.parquet

Usage:
    python analysis/02_outcomes/dependents_i1b.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import count_events  # noqa: E402
import probe_depsdev_bq  # noqa: E402

DATASET = "bigquery-public-data.deps_dev_v1"
SNAPSHOT_T0 = "2024-07-29T21:00:43.758331+00:00"
SNAPSHOT_T1 = "2026-07-27T21:01:02.499118+00:00"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--link-snapshot", default="2024-07-29")
    ap.add_argument("--max-gb", type=float, default=600.0)
    args = ap.parse_args()

    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv")
    known = set(cohort.project.str.lower()) | set(cohort.canonical.dropna().str.lower())
    links = count_events.plausible_links(args.link_snapshot)
    links = links[links.ProjectName.str.lower().isin(known)]
    attached = pd.read_parquet(ROOT / "data" / "processed" / f"attached_advisories_{args.t0}.parquet")
    attached = attached[attached.route != "via_repo"]
    systems = {v: k for k, v in count_events.SYSTEMS.items()}
    names = set(links.Name) | {
        count_events.query_name(e, p)
        for e, p in zip(attached.package_ecosystem, attached.package)
        if e in systems
    }
    print(f"{len(names)} packages", flush=True)

    sql = f"""SELECT SnapshotAt, System, Name, COUNT(*) AS dependents_all,
                     COUNTIF(MinimumDepth = 1) AS dependents_direct
              FROM `{DATASET}.Dependents`
              WHERE SnapshotAt IN (TIMESTAMP('{SNAPSHOT_T0}'), TIMESTAMP('{SNAPSHOT_T1}'))
                AND DependentIsHighestReleaseWithResolution
                AND Name IN UNNEST(@names)
              GROUP BY SnapshotAt, System, Name"""
    params = [bigquery.ArrayQueryParameter("names", "STRING", sorted(names))]
    client = bigquery.Client(project=probe_depsdev_bq.calling_project())
    dry = client.query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False, query_parameters=params)
    )
    gigabytes = dry.total_bytes_processed / 1e9
    print(f"scanning {gigabytes:.1f} GB", flush=True)
    if gigabytes > args.max_gb:
        raise SystemExit(f"above --max-gb {args.max_gb}")
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    table = job.result().to_dataframe(create_bqstorage_client=False)
    out = ROOT / "data" / "raw" / "depsdev" / f"dependents_i1b_{args.t0}.parquet"
    table.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(table)} rows, billed {job.total_bytes_billed / 1e9:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
