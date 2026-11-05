#!/usr/bin/env python3
"""CrOSSD components at t0, read from the stored snapshot of each cohort project.

The manifest names the snapshot whose values count for a project. Values are recorded at the time
and dated by their reading, so this adapter computes nothing beyond picking fields.

Output: data/processed/features/crossd_<t0>.parquet

Usage:
    python analysis/03_instruments/crossd_adapter.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys

from base import RAW, RECORDED, assert_not_after, cohort, freeze, row, write_features


def unwrap(value):
    if isinstance(value, dict) and len(value) == 1 and next(iter(value)).isdigit():
        return next(iter(value.values()))
    return value


def number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = freeze(args.t0)
    members = cohort(args.t0)
    wanted = {(r.project, r.snapshot_ts): r.observed_ts for r in members.itertuples()}

    rows = []
    found = 0
    with gzip.open(RAW / "crossd" / "metrics.jsonl.gz", "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            key = (rec["project"], rec["snapshot_ts"])
            if key not in wanted:
                continue
            observed = wanted.pop(key)
            assert_not_after(observed, t0, rec["project"])
            found += 1
            bak = (rec["response"] or {}).get("bak") or {}
            top = (rec["response"] or {}).get("metrics") or {}

            def field(name):
                return unwrap(bak.get(name)) if bak.get(name) is not None else top.get(name)

            contrib = field("contributions_distributions") or {}
            velocity = field("project_velocity") or {}
            health = field("github_community_health_percentage") or {}
            issues = field("issues") or {}
            values = {
                "maturity_level": number(field("maturity_level")),
                "elephant_factor": number(field("elephant_factor")),
                "support_rate": number(field("support_rate")),
                "criticality_score": number(field("criticality_score")),
                "bus_factor": number(contrib.get("bus_factor_score")) if isinstance(contrib, dict) else None,
                "project_velocity_ratio_closed": number(velocity.get("ratio_closed_total")) if isinstance(velocity, dict) else None,
                "community_health": number(health.get("custom_health_score")) if isinstance(health, dict) else None,
                "first_response_days": number(issues.get("average_first_response_time_days")) if isinstance(issues, dict) else None,
                "dependents_count": number(top.get("dependents_count")),
            }
            for component, value in values.items():
                rows.append(row(rec["project"], component, value, RECORDED, observed))
    if wanted:
        raise SystemExit(f"{len(wanted)} cohort snapshots are not in the cache")
    write_features("crossd", args.t0, rows)
    print(f"{found} projects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
