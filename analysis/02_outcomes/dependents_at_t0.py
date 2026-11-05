#!/usr/bin/env python3
"""Dependents at t0 of the packages with an attached advisory, for I1.

One scan of one `Dependents` partition, about 225 GB of the 1 TB free tier, as agreed in the
freeze. The dry run stops the query above `--max-gb`. A package's count is the number of rows
whose dependent is at its highest release, summed over the package's versions, so a dependent
resolving to two versions counts twice. It is a size measure, not an exact count.

Output: data/raw/depsdev/dependents_<snapshot>.parquet

Usage:
    python analysis/02_outcomes/dependents_at_t0.py --t0 2024-08-01
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--snapshot", default="2024-07-29T21:00:43.758331+00:00")
    ap.add_argument("--max-gb", type=float, default=230.0)
    args = ap.parse_args()

    attached = pd.read_parquet(
        ROOT / "data" / "processed" / f"attached_advisories_{args.t0}.parquet"
    )
    attached = attached[attached.route != "via_repo"]
    systems = {v: k for k, v in count_events.SYSTEMS.items()}
    names = sorted(
        {count_events.query_name(e, p) for e, p in zip(attached.package_ecosystem, attached.package)
         if e in systems}
    )
    print(f"{len(names)} packages", flush=True)

    sql = f"""SELECT System, Name, COUNT(*) AS dependents_all,
                     COUNTIF(MinimumDepth = 1) AS dependents_direct
              FROM `{DATASET}.Dependents`
              WHERE SnapshotAt = TIMESTAMP('{args.snapshot}')
                AND DependentIsHighestReleaseWithResolution
                AND Name IN UNNEST(@names)
              GROUP BY System, Name"""
    params = [bigquery.ArrayQueryParameter("names", "STRING", names)]
    client = bigquery.Client(project=probe_depsdev_bq.calling_project())
    dry = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, query_parameters=params
        ),
    )
    gigabytes = dry.total_bytes_processed / 1e9
    print(f"scanning {gigabytes:.1f} GB", flush=True)
    if gigabytes > args.max_gb:
        raise SystemExit(f"above --max-gb {args.max_gb}")

    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    table = job.result().to_dataframe(create_bqstorage_client=False)
    out = ROOT / "data" / "raw" / "depsdev" / f"dependents_{args.snapshot[:10]}.parquet"
    table.to_parquet(out, index=False)
    print(f"{out.relative_to(ROOT)}: {len(table)} packages, billed {job.total_bytes_billed / 1e9:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
