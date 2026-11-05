#!/usr/bin/env python3
"""The frozen feature table at t0: every instrument, one long table.

Reads the adapter outputs and no outcome. Fails if a value rests on data after t0 or a project lies outside the cohort.
The published Criticality values and the rule-based rebuild stay apart by component name, and the evidence class of
each value comes along.

Outputs:
  data/processed/features_<t0>.parquet       project, instrument, component, value, evidence, as_of
  data/probes/feature_coverage_<t0>.csv      values per component and stratum, with the evidence class

Usage:
    python analysis/03_instruments/freeze_features.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import hashlib
import sys

import pandas as pd

from base import FEATURES, ROOT, AfterFreezeDate, cohort, freeze


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    members = cohort(args.t0).set_index("project")
    limit = freeze(args.t0).timestamp()
    parts = []
    for path in sorted(FEATURES.glob(f"*_{args.t0}.parquet")):
        part = pd.read_parquet(path)
        part.insert(1, "instrument", path.name.removesuffix(f"_{args.t0}.parquet"))
        parts.append(part)
    table = pd.concat(parts, ignore_index=True).sort_values(["instrument", "component", "project"], ignore_index=True)
    late = table[table.as_of.notna() & (table.as_of > limit)]
    if len(late):
        raise AfterFreezeDate(f"{len(late)} values rest on data after the freeze date")
    outside = set(table.project) - set(members.index)
    if outside:
        raise SystemExit(f"{len(outside)} projects outside the cohort, for example {sorted(outside)[:3]}")
    path = ROOT / "data" / "processed" / f"features_{args.t0}.parquet"
    table.to_parquet(path, index=False)

    known = table[table.value.notna()].assign(stratum=lambda t: t.project.map(members.stratum))
    coverage = known.groupby(["instrument", "component", "evidence", "stratum"]).project.nunique().unstack("stratum", fill_value=0).reset_index()
    coverage.to_csv(ROOT / "data" / "probes" / f"feature_coverage_{args.t0}.csv", index=False)
    print(f"{path.relative_to(ROOT)}: {len(table)} rows, {table.component.nunique()} components, {table.project.nunique()} projects")
    print(hashlib.sha256(path.read_bytes()).hexdigest())
    print(coverage.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
