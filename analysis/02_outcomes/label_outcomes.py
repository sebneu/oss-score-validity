#!/usr/bin/env python3
"""Label the frozen cohort with the frozen outcomes.

Freeze commit: 7950cce6dafd. The definitions below are copied from docs/decision_log_full.md.
A change to any of them is a logged deviation, and the original is reported as well.

O1a  archival or deletion: `archivedAt` in the window, or the repository gone without a redirect,
     unless a Software Heritage visit still found it after the window.
O1b  dormancy: no default-branch commit, release or tag in the last 12 months of the window.
O1c  unanswered demand (sensitivity): at least 3 issues opened in the window by non-maintainers,
     with no OWNER, MEMBER or COLLABORATOR comment and not closed within 90 days.
O2a  severe exposure: an advisory published in the window, not withdrawn, not malicious, CVSS v3
     base >= 7.0 or GHSA label HIGH or CRITICAL, naming the repository in `ranges[].repo` or
     `references`, with a package that claims no other repository at deps.dev.
O2b  no fix (primary reading): such an advisory attached through a package, with no fixed version
     listed at the data freeze, at least 90 days after publication, or in CISA KEV.
I1   impact: for a project with an O2a advisory, dependents at t0 of the most depended-on affected
     package, from the deps.dev snapshot before t0.

Amendment 1, commit 3fa3f5df2e66, adds or takes over the primary role:

O1         primary: O1a_v2 or O1b. O1a_v2 is O1a, also excluding a gone repository with a GH Archive
           event after the window.
O1c_share  primary for responsiveness claims: at least 10 external issues in the quarterly sample, and at
           least half unanswered (no OWNER, MEMBER, COLLABORATOR or CONTRIBUTOR comment and not closed within
           90 days).
O1b_demand O1b with at least one external issue unanswered in the last 12 months of the window;
O1b_quiet  O1b with issues enabled and no such issue; O1b_unknown otherwise.
I1b        dependents, at the snapshot of 2026-07-27, of the most depended-on package; I1b_t0 is the
           same at the snapshot of 2024-07-29, the required baseline.

Variants carried along: O1a archived only, O2a verified only, O2b as drafted (`O2b_drafted`), and the frozen
O1a, O1c and I1.

No score may reach this script. It reads the cohort manifest and outcome sources only, and
`count_events.FORBIDDEN_COLUMNS` guards the coverage table. Joining scores to these labels is
the validity step, after the freeze.

Outputs:
  data/processed/outcomes_<t0>.parquet             one row per cohort project
  data/processed/attached_advisories_<t0>.parquet  advisory x package x project

Usage:
    python analysis/02_outcomes/label_outcomes.py --t0 2024-08-01
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--months", type=int, default=24, help="window; 12 for the robustness date")
    ap.add_argument("--freeze", default="2026-11-03", help="OSV and KEV data freeze")
    ap.add_argument("--accessed", default="2026-11-03", help="date of the deps.dev crawl")
    ap.add_argument("--link-snapshot", default="2024-07-29", help="deps.dev snapshot before t0")
    args = ap.parse_args()

    labels = pd.read_csv(
        ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv",
        usecols=["project", "stratum"],
    )
    maintenance = count_events.maintenance_outcomes(args.t0, args.months)
    labels = labels.merge(
        maintenance[["project", "O1", "O1a", "O1a_v2", "O1a_archived", "O1a_gone", "O1b"]],
        on="project",
        how="left",
    )

    attached = count_events.security_outcomes(
        args.t0, args.months, labels[["project"]], args.freeze, args.accessed
    )
    attached = attached[attached.route.isin({"verified", "no_claim", "via_repo"})]
    attached.to_parquet(PROCESSED / f"attached_advisories_{args.t0}.parquet", index=False)
    packaged = attached[attached.route != "via_repo"]
    labels["O2a"] = labels.project.isin(attached.project)
    labels["O2a_verified"] = labels.project.isin(attached[attached.route == "verified"].project)
    labels["O2b"] = labels.project.isin(packaged[packaged.no_fix_listed | packaged.in_kev].project)
    labels["O2b_drafted"] = labels.project.isin(packaged[packaged.response_failure].project)

    plausible = count_events.plausible_links(args.link_snapshot)
    lowered = {p.lower(): p for p in labels.project}
    canonical = pd.read_csv(
        ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv", usecols=["project", "canonical"]
    ).dropna()
    lowered |= {c.lower(): p for p, c in zip(canonical.project, canonical.canonical)}
    publishers = set(plausible.ProjectName.str.lower().map(lowered).dropna())
    labels["in_O2_base"] = labels.project.isin(publishers | set(attached.project))
    labels["in_O2b_base"] = labels.project.isin(publishers | set(packaged.project))

    issues_path = PROCESSED / f"github_issues_{args.t0}.parquet"
    if issues_path.exists():
        issues = pd.read_parquet(issues_path, columns=["project", "unanswered_strict"])
        issues["O1c"] = issues.unanswered_strict.ge(3)
        labels = labels.merge(issues[["project", "O1c"]], on="project", how="left")
    else:
        print("O1c pending: the issue crawl has not finished")

    dependents_path = ROOT / "data" / "raw" / "depsdev" / f"dependents_{args.link_snapshot}.parquet"
    if dependents_path.exists():
        dependents = pd.read_parquet(dependents_path)
        systems = {v: k for k, v in count_events.SYSTEMS.items()}
        pairs = packaged.assign(
            System=packaged.package_ecosystem.map(systems),
            Name=[count_events.query_name(e, p) for e, p in zip(packaged.package_ecosystem, packaged.package)],
        ).merge(dependents, on=["System", "Name"])
        impact = pairs.groupby("project").dependents_all.max().rename("I1")
        labels = labels.merge(impact, on="project", how="left")
    else:
        print("I1 pending: the Dependents scan has not run")

    demand_path = PROCESSED / f"github_demand_{args.t0}.parquet"
    if demand_path.exists():
        demand = pd.read_parquet(demand_path)
        labels = labels.merge(demand, on="project", how="left", suffixes=("", "_demand"))
        in_base = labels.n_external.ge(10)
        labels["O1c_share"] = labels.share_unanswered.ge(0.5).where(in_base)
        has_issues = pd.read_parquet(
            PROCESSED / f"github_meta_{args.t0}.parquet", columns=["project", "hasIssuesEnabled"]
        )
        labels = labels.merge(has_issues, on="project", how="left")
        issues_file = PROCESSED / f"github_issues_{args.t0}.parquet"
        answered = labels.hasIssuesEnabled.fillna(False).astype(bool)
        if issues_file.exists():
            answered &= labels.project.isin(pd.read_parquet(issues_file, columns=["project"]).project)
        labels["O1b_demand"] = labels.O1b & labels.recent_unanswered.fillna(0).gt(0)
        labels["O1b_quiet"] = labels.O1b & ~labels.O1b_demand & answered
        labels["O1b_unknown"] = labels.O1b & ~labels.O1b_demand & ~answered
    else:
        print("O1c_share and the O1b split pending: the demand crawl has not finished")

    i1b_path = ROOT / "data" / "raw" / "depsdev" / f"dependents_i1b_{args.t0}.parquet"
    if i1b_path.exists():
        links = count_events.plausible_links(args.link_snapshot)
        pair_rows = links.assign(project=links.ProjectName.str.lower().map(lowered)).dropna(subset=["project"])
        pair_rows = pair_rows[["project", "System", "Name"]]
        systems = {v: k for k, v in count_events.SYSTEMS.items()}
        extra = packaged[packaged.package_ecosystem.isin(systems)]
        extra = extra.assign(
            System=extra.package_ecosystem.map(systems),
            Name=[count_events.query_name(e, n) for e, n in zip(extra.package_ecosystem, extra.package)],
        )[["project", "System", "Name"]]
        pair_rows = pd.concat([pair_rows, extra]).drop_duplicates()
        counts = pd.read_parquet(i1b_path)
        counts["end"] = counts.SnapshotAt.dt.date.astype(str)
        for end, column in (("2026-07-27", "I1b"), ("2024-07-29", "I1b_t0")):
            part = counts[counts.end == end]
            top = pair_rows.merge(part, on=["System", "Name"]).groupby("project").dependents_all.max()
            labels = labels.merge(top.rename(column), on="project", how="left")
    else:
        print("I1b pending: the Dependents scan has not run")

    out = PROCESSED / f"outcomes_{args.t0}.parquet"
    labels.to_parquet(out, index=False)
    columns = [c for c in labels.columns if c.startswith("O")]
    print(labels[columns].astype("boolean").sum().to_string())
    print(labels.groupby("stratum")[[c for c in ("O1", "O1a_v2", "O1b", "O1c_share", "O1b_demand", "O2b") if c in labels]]
          .agg(lambda s: int(s.astype("boolean").sum())).to_string())
    if "I1b" in labels:
        print(f"I1b known for {int(labels.I1b.notna().sum())}, I1b_t0 for {int(labels.I1b_t0.notna().sum())}")
    print(f"O2a base {int(labels.in_O2_base.sum())}, O2b base {int(labels.in_O2b_base.sum())}")
    if "I1" in labels:
        print(f"I1 known for {int(labels.I1.notna().sum())}; median {labels.I1.median():.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
