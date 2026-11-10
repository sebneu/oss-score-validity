#!/usr/bin/env python3
"""Write the frozen cohort manifest (freeze in DECISIONS.md).

One row per eligible project at t0: its stratum, the snapshot whose values count for it, when
those values were read from GitHub, and the name GitHub serves now. The file holds no metric
value and no outcome, is versioned, and its checksum is recorded with the freeze.

Output: analysis/01_cohort/cohort_<t0>.csv

Usage:
    python analysis/01_cohort/build_cohort.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import count_events  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()

    members, _ = count_events.eligible_members(args.t0)
    coverage = pd.read_parquet(
        ROOT / "data" / "probes" / "crossd_coverage.parquet",
        columns=["project", "snapshot_ts", "observed_ts"],
    )
    end = pd.Timestamp(args.t0, tz="UTC").timestamp()
    start = end - count_events.ELIGIBILITY_DAYS * 86400
    seen = coverage[(coverage.observed_ts <= end) & (coverage.observed_ts > start)]
    latest = seen.sort_values("observed_ts").groupby("project").tail(1)
    meta = pd.read_parquet(
        ROOT / "data" / "processed" / f"github_meta_{args.t0}.parquet",
        columns=["project", "canonical"],
    )
    manifest = (
        members[["project", "stratum", "gone_now"]]
        .merge(latest, on="project")
        .merge(meta, on="project", how="left")
        .sort_values("project")
    )
    if len(manifest) != len(members):
        raise SystemExit("every cohort member needs exactly one snapshot")

    out = ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv"
    manifest.to_csv(out, index=False)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{out.relative_to(ROOT)}: {len(manifest)} projects, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
