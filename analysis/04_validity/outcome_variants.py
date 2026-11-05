#!/usr/bin/env python3
"""Sensitivity variants of the outcomes, as listed in the Freeze section and in A2 of DECISIONS.md.

Reads the cohort and the outcome sources, and no score. Primary labels stay in outcomes_<t0>.parquet.

Output: data/processed/outcome_variants_<t0>.parquet, one row per cohort project, and data/probes/outcome_variants_<t0>.csv
with events and base per variant.

Usage:
    python analysis/04_validity/outcome_variants.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import count_events  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
ROUTES = {"verified", "no_claim", "via_repo"}


def packaged(t0: str, months: int, members: pd.DataFrame, freeze: str, accessed: str, **kw) -> pd.DataFrame:
    attached = count_events.security_outcomes(t0, months, members, freeze, accessed, **kw)
    attached = attached[attached.route.isin(ROUTES)]
    return attached[attached.route != "via_repo"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--freeze", default="2026-11-03")
    ap.add_argument("--accessed", default="2026-11-03")
    args = ap.parse_args()
    base = pd.read_parquet(PROCESSED / f"outcomes_{args.t0}.parquet")
    out = base[["project", "stratum"]].copy()
    members = out[["project"]]

    long = count_events.maintenance_outcomes(args.t0, 24).set_index("project")
    short = count_events.maintenance_outcomes(args.t0, 12).set_index("project")
    out["O1_12m"] = out.project.map(short.O1).astype(bool)
    out["O1_dormant6m"] = out.project.map(long.O1a_v2 | long.O1b_6m).astype(bool)
    out["O1_archived"] = out.project.map(long.O1a_archived | long.O1b).astype(bool)
    out["O1_demand"] = (base.O1a_v2 | base.O1b_demand).astype(bool)

    def fires(table: pd.DataFrame, column: str) -> pd.Series:
        hit = table[table[column] | (table.in_kev if column == "no_fix_listed" else False)]
        return out.project.isin(hit.project)

    out["O2b_12m"] = fires(packaged(args.t0, 12, members, args.freeze, args.accessed), "no_fix_listed")
    out["O2b_cvss9"] = fires(packaged(args.t0, 24, members, args.freeze, args.accessed, cvss_cut=9.0), "no_fix_listed")
    out["O2b_drafted_30d"] = fires(packaged(args.t0, 24, members, args.freeze, args.accessed, fix_days=30), "response_failure")

    issues = pd.read_parquet(PROCESSED / f"github_issues_{args.t0}.parquet")
    for name, column in (("O1c_drafted", "unanswered_draft"), ("O1c_external", "unanswered_external")):
        out[name] = out.project.map(issues.set_index("project")[column]).ge(3).where(out.project.isin(issues.project))
    in_base = base.O1c_share.notna()
    out["O1c_share_25"] = base.share_unanswered.ge(0.25).where(in_base)
    out["O1c_share_75"] = base.share_unanswered.ge(0.75).where(in_base)
    out["O1c_share_narrow"] = base.share_unanswered_narrow.ge(0.5).where(in_base)

    path = PROCESSED / f"outcome_variants_{args.t0}.parquet"
    out.to_parquet(path, index=False)
    columns = [c for c in out.columns if c.startswith("O")]
    counts = pd.DataFrame({"events": [int(out[c].astype("boolean").sum()) for c in columns], "known": [int(out[c].notna().sum()) for c in columns]}, index=pd.Index(columns, name="variant"))
    counts.to_csv(ROOT / "data" / "probes" / f"outcome_variants_{args.t0}.csv")
    print(counts.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
