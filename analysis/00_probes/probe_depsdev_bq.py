#!/usr/bin/env python3
"""Probe the deps.dev BigQuery tables for point-in-time use.

The questions: which `SnapshotAt` values exist before t0, and do the tables
hold package links, stars and dependents at t0? The answers decide whether I1 (dependents at
advisory publication) and a point-in-time package mapping are possible.

Reads:
  `Snapshots`                   the snapshot dates; a small table, free to read.
  `PackageVersionToProject`     repository to package links at the latest snapshot <= t0. This
                                replaces today's API mapping as the eligibility evidence.
  `Projects`                    stars and OSS-Fuzz coverage at t0, for the frame only. These are
                                inputs for the instruments and are not joined to any outcome here.
  `Dependents`                  dry-run only. One snapshot is about 262 GB, so it runs only
                                with `--dependents`.

Tables are partitioned by `SnapshotAt`, and every query filters on one partition. Each query is
dry-run first and refused above `--max-gb`: a query over all `Dependents` partitions would scan
8.9 TB. Costs go to the calling project.

Setup:
    gcloud auth application-default login
    GOOGLE_CLOUD_PROJECT=<project> in .env

Outputs:
  data/raw/depsdev/package_links_<snapshot>.parquet
  data/raw/depsdev/projects_<snapshot>.parquet
  data/probes/depsdev_bq.json

Usage:
    python analysis/00_probes/probe_depsdev_bq.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[2]
DATASET = "bigquery-public-data.deps_dev_v1"
OUT = ROOT / "data" / "probes" / "depsdev_bq.json"
RAW = ROOT / "data" / "raw" / "depsdev"
COVERAGE = ROOT / "data" / "probes" / "crossd_coverage.parquet"


def calling_project() -> str:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    env_file = ROOT / ".env"
    if not project and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GOOGLE_CLOUD_PROJECT="):
                project = line.split("=", 1)[1].strip()
    if not project:
        raise SystemExit("GOOGLE_CLOUD_PROJECT is not set; see the docstring")
    return project


def frame_names(t0: str) -> list[str]:
    """deps.dev names of the frame, under the panel name and the name GitHub serves now."""
    coverage = pd.read_parquet(COVERAGE, columns=["project", "snapshot_ts"])
    limit = pd.Timestamp("2024-08-11", tz="UTC").timestamp()
    names = {p.lower() for p in coverage[coverage.snapshot_ts < limit].project.unique()}
    meta = ROOT / "data" / "processed" / f"github_meta_{t0}.parquet"
    if meta.exists():
        names |= {c.lower() for c in pd.read_parquet(meta, columns=["canonical"]).canonical.dropna()}
    return sorted(names)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--max-gb", type=float, default=20.0, help="refuse queries above this scan")
    ap.add_argument("--dependents", action="store_true", help="dry-run only unless set")
    args = ap.parse_args()

    client = bigquery.Client(project=calling_project())
    log: dict = {"generated": datetime.now(UTC).isoformat(), "t0": args.t0, "scanned_gb": {}}

    def estimate(sql: str, params: list | None = None) -> float:
        config = bigquery.QueryJobConfig(
            dry_run=True, use_query_cache=False, query_parameters=params or []
        )
        return client.query(sql, job_config=config).total_bytes_processed / 1e9

    def run(label: str, sql: str, params: list | None = None) -> pd.DataFrame:
        gigabytes = estimate(sql, params)
        log["scanned_gb"][label] = round(gigabytes, 2)
        if gigabytes > args.max_gb:
            raise SystemExit(f"{label} would scan {gigabytes:.1f} GB, above --max-gb")
        print(f"{label}: scanning {gigabytes:.2f} GB", flush=True)
        job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params or []))
        return job.result().to_dataframe(create_bqstorage_client=False)

    times = [r["Time"] for r in client.query(f"SELECT Time FROM `{DATASET}.Snapshots`").result()]
    times.sort()
    before = [t for t in times if t.date().isoformat() <= args.t0]
    snapshot = before[-1]
    stamp = snapshot.date().isoformat()
    gaps = [(b - a).days for a, b in zip(times, times[1:])]
    log["snapshots"] = {
        "count": len(times),
        "first": times[0].isoformat(),
        "last": times[-1].isoformat(),
        "largest_gap_days": max(gaps),
        "latest_at_or_before_t0": snapshot.isoformat(),
    }
    print(log["snapshots"], flush=True)

    where = f"SnapshotAt = TIMESTAMP('{snapshot.isoformat()}')"
    names = frame_names(args.t0)
    in_frame = [bigquery.ArrayQueryParameter("names", "STRING", names)]

    links = run(
        "PackageVersionToProject",
        f"""SELECT System, Name, ProjectName, RelationType, RelationProvenance,
                   COUNT(*) AS n_versions,
                   LOGICAL_OR(REGEXP_CONTAINS(Version, r'^v[0-9]+[.][0-9]+[.][0-9]+$')) AS tagged
            FROM `{DATASET}.PackageVersionToProject`
            WHERE {where} AND ProjectType = 'GITHUB'
              AND LOWER(ProjectName) IN UNNEST(@names)
            GROUP BY System, Name, ProjectName, RelationType, RelationProvenance""",
        in_frame,
    )
    RAW.mkdir(parents=True, exist_ok=True)
    links.to_parquet(RAW / f"package_links_{stamp}.parquet", index=False)
    log["package_links"] = {
        "rows": len(links),
        "projects": int(links.ProjectName.str.lower().nunique()),
        "by_system": links.groupby("System").Name.nunique().to_dict(),
        "by_provenance": links.RelationProvenance.value_counts().to_dict(),
    }

    projects = run(
        "Projects",
        f"""SELECT Name, StarsCount, ForksCount, OpenIssuesCount, OSSFuzz.Date AS OSSFuzzDate,
                   OSSFuzz.ConfigURL AS OSSFuzzConfig
            FROM `{DATASET}.Projects`
            WHERE {where} AND Type = 'GITHUB' AND LOWER(Name) IN UNNEST(@names)""",
        in_frame,
    )
    projects.to_parquet(RAW / f"projects_{stamp}.parquet", index=False)
    log["projects"] = {
        "frame_names": len(names),
        "found": int(projects.Name.str.lower().nunique()),
        "with_stars": int(projects.StarsCount.notna().sum()),
        "with_ossfuzz": int(projects.OSSFuzzDate.notna().sum()),
    }

    dependents_sql = f"""SELECT System, Name, Version, MinimumDepth
        FROM `{DATASET}.Dependents` WHERE {where}"""
    log["scanned_gb"]["Dependents (dry run, not read)"] = round(estimate(dependents_sql), 1)
    if args.dependents:
        raise SystemExit("--dependents: agree on the package list and the cost first")

    OUT.write_text(json.dumps(log, indent=2, default=str))
    print(json.dumps(log, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
