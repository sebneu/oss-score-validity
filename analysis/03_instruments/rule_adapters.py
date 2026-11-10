#!/usr/bin/env python3
"""Rebuild the rule-based instruments and baselines at t0 from dated events.

Reads the git history, the dated GitHub events and the deps.dev snapshot before t0, and nothing else.
Readings that the published rules leave open are fixed in docs/decision_log_full.md ("Readings of the
instruments", 2026-11-04). Nothing here reads an outcome.

Scorecard Maintained: (commits + issues with member activity in the last 90 days) / 12, times 10, capped at 10.
  Zero for a project created in the last 90 days. As in the source: checks/evaluation/maintained.go.
OpenSSF Criticality Score: the published formula with the default weights. `org_count` cannot be backdated and
  its weight is removed; `dependents_count` comes from the CrOSSD value at t0; `updated_issues_count` counts issues
  created or commented on in the window, since `updatedAt` is current state.
openCode maintenance: L1 at least 5 commits in 6 months and mean issue response under 7 days over issues of the
  last 3 months; L2 adds a release or tag in 6 months; L3 adds a contributor absence factor of at least 2.
openCode security: L1 issue response and SECURITY.md in the root; L2 adds 75% of merged PRs reviewed by a maintainer
  and 80% of tags signed. Branch protection (L1) and the vulnerability criteria (L3) cannot be backdated.

Outputs: data/processed/features/{scorecard_maintained,criticality,opencode,baselines}_<t0>.parquet

Usage:
    python analysis/03_instruments/rule_adapters.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone

import pandas as pd

from base import (git_dir, FEATURES, NOT_BACKDATABLE, PROCESSED, RAW, RECONSTRUCTED, add_months, assert_not_after, cohort,
                  days_before, freeze, parse, row, write_features)

MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}
MAX_RESPONSE_DAYS = 7.0
CRITICALITY = {  # weight, threshold
    "created_since": (1.0, 120), "updated_since": (-1.0, 120), "contributor_count": (2.0, 5000),
    "commit_frequency": (1.0, 1000), "recent_releases_count": (0.5, 26), "closed_issues_count": (0.5, 5000),
    "updated_issues_count": (0.5, 5000), "comment_frequency": (1.0, 15), "dependents_count": (2.0, 500000),
}


def contributor_absence_factor(authors: pd.Series) -> int:
    """Smallest number of contributors who together made at least half of the commits."""
    counts = authors.value_counts().tolist()
    total, running = sum(counts), 0
    for n, value in enumerate(counts, 1):
        running += value
        if running >= total / 2:
            return n
    return 0


def response_days(issues: list[dict], t0) -> list[float]:
    """Days to the first comment by someone else or to closure; open issues are censored at t0."""
    out = []
    for issue in issues:
        created = parse(issue["createdAt"])
        assert_not_after(created, t0, "issue")
        author = (issue.get("author") or {}).get("login")
        times = [parse(c["createdAt"]) for c in (issue.get("comments") or {}).get("nodes") or []
                 if (c.get("author") or {}).get("login") != author]
        if issue.get("closedAt"):
            times.append(parse(issue["closedAt"]))
        times = [w for w in times if w <= t0]
        first = min(times) if times else t0
        out.append((first - created).total_seconds() / 86400)
    return out


def member_activity(activity: list[dict], t0) -> int:
    """Issues created or commented on by a member in the 90 days before t0, as in the Scorecard probe."""
    start = days_before(t0, 90)
    count = 0
    for issue in activity:
        created = parse(issue["createdAt"])
        if created > t0:
            continue
        by_member = issue.get("authorAssociation") in MAINTAINER and created > start
        commented = any(
            c.get("authorAssociation") in MAINTAINER and start < parse(c["createdAt"]) <= t0
            for c in (issue.get("comments") or {}).get("nodes") or []
        )
        count += by_member or commented
    return count


def reviewed_share(prs: list[dict]) -> float | None:
    reviewed = 0
    for pr in prs:
        merged = parse(pr["mergedAt"])
        author = (pr.get("author") or {}).get("login")
        for review in (pr.get("reviews") or {}).get("nodes") or []:
            when = review.get("submittedAt")
            if (review.get("authorAssociation") in MAINTAINER and (review.get("author") or {}).get("login") != author
                    and when and parse(when) <= merged):
                reviewed += 1
                break
    return reviewed / len(prs) if prs else None


def criticality_score(signals: dict[str, float]) -> float:
    total_weight = sum(w for w, _ in CRITICALITY.values())
    score = 0.0
    for name, (weight, threshold) in CRITICALITY.items():
        value = max(signals[name], 0.0)
        score += weight * math.log(1 + value) / math.log(1 + max(value, threshold))
    return score / total_weight


def maintained_value(commits_90: int, activity: list[dict], created, t0) -> float:
    """Scorecard Maintained at t0, from dated commits and issue activity."""
    if created > days_before(t0, 90):
        return 0.0
    return min(10.0, math.floor(10 * (commits_90 + member_activity(activity, t0)) / 12))


def criticality_signals(created, last_commit: float, authors_total: float, commits_12m: int, releases_12m: int, ev: dict, t0, dependents: float) -> dict[str, float]:
    """The signals of the Criticality Score at t0, without org_count."""
    limit = t0.timestamp()
    answered = [i for i in ev["issues"] if parse(i["createdAt"]) <= t0]
    comments = [len([c for c in (i.get("comments") or {}).get("nodes") or [] if parse(c["createdAt"]) <= t0]) for i in answered]
    updated = {i["number"] for i in answered} | {i["number"] for i in ev["activity"] if parse(i["createdAt"]) <= t0 and any(
        days_before(t0, 90) < parse(c["createdAt"]) <= t0 for c in (i.get("comments") or {}).get("nodes") or [])}
    return {
        "created_since": (limit - created.timestamp()) / (30.44 * 86400),
        "updated_since": (limit - last_commit) / (30.44 * 86400),
        "contributor_count": authors_total,
        "commit_frequency": commits_12m / 52.0,
        "recent_releases_count": float(releases_12m),
        "closed_issues_count": float(ev["closed_90d"] or 0),
        "updated_issues_count": float(len(updated)),
        "comment_frequency": float(sum(comments) / len(comments)) if comments else 0.0,
        "dependents_count": dependents,
    }


def opencode_values(commits_6m: pd.DataFrame, issues: list[dict], release_6m: bool, tags_6m: list[dict], prs: list[dict], entries: list[str] | None, t0) -> dict:
    """The openCode maintenance and security levels at a date, from dated events."""
    days = response_days(issues, t0)
    mean_response = sum(days) / len(days) if days else None
    response_ok = mean_response is None or mean_response < MAX_RESPONSE_DAYS
    caf = contributor_absence_factor(commits_6m.author) if len(commits_6m) else 0
    l1 = len(commits_6m) >= 5 and response_ok
    l2 = l1 and release_6m
    l3 = l2 and caf >= 2
    has_policy = None if entries is None else any(e.lower() == "security.md" for e in entries)
    share = reviewed_share(prs)
    signed = [t["signed"] for t in tags_6m]
    reviewed_ok = share is None or share >= 0.75
    signed_ok = not signed or sum(signed) / len(signed) >= 0.8
    if has_policy is None:
        level = None
    else:
        s1 = response_ok and has_policy
        level = 2 if s1 and reviewed_ok and signed_ok else 1 if s1 else 0
    return {"opencode_maintenance": 3 if l3 else 2 if l2 else 1 if l1 else 0, "opencode_response_days": mean_response, "opencode_response_ok": float(response_ok),
            "opencode_security": level, "opencode_security_policy": None if has_policy is None else float(has_policy), "opencode_reviewed_share": share}


def add_baselines(out: list, m, project: str, stars_t0: dict, walked: dict, created, info, commits_90: int, commits_12m, dependents, limit: float) -> None:
    name = (m.canonical if isinstance(m.canonical, str) else project).lower()
    stars = stars_t0.get(name, stars_t0.get(project.lower(), walked.get(project)))
    out.append(row(project, "stars", stars, RECONSTRUCTED, limit))
    out.append(row(project, "age_days", (limit - created.timestamp()) / 86400, RECONSTRUCTED, limit))
    out.append(row(project, "days_since_last_commit", None if pd.isna(info.last_commit) else (limit - info.last_commit) / 86400, RECONSTRUCTED, limit))
    out.append(row(project, "commits_90d", commits_90, RECONSTRUCTED, limit))
    out.append(row(project, "contributors_12m", commits_12m.author.nunique(), RECONSTRUCTED, limit))
    out.append(row(project, "dependents", dependents.get(project), RECONSTRUCTED, limit))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = freeze(args.t0)
    limit = t0.timestamp()
    members = cohort(args.t0)

    meta = pd.read_parquet(PROCESSED / f"github_meta_{args.t0}.parquet", columns=["project", "createdAt", "hasIssuesEnabled"]).set_index("project")
    summary = pd.read_parquet(PROCESSED / f"git_summary_{args.t0}.parquet").set_index("project")
    root_files = {}
    path = RAW / "github" / f"root_files_{args.t0}.jsonl"
    if path.exists():
        with path.open() as fh:
            for line in fh:
                rec = json.loads(line)
                root_files[rec["project"]] = rec.get("entries")
    events = {}
    with (RAW / "github" / f"t0_events_{args.t0}.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            events[rec["project"]] = rec
    crossd = pd.read_parquet(FEATURES / f"crossd_{args.t0}.parquet")
    dependents = crossd[crossd.component == "dependents_count"].set_index("project")["value"]
    stars_t0 = pd.read_parquet(RAW / "depsdev" / "projects_2024-07-29.parquet", columns=["Name", "StarsCount"]).dropna()
    stars_t0 = dict(zip(stars_t0.Name.str.lower(), stars_t0.StarsCount))
    # Stars: the deps.dev snapshot, else the last Criticality list before t0, else star events in GH Archive.
    walked = {}
    path = RAW / "gharchive" / f"stars_{args.t0}.parquet"
    if path.exists():
        walked = pd.read_parquet(path).set_index("project").star_events.to_dict()
    path = RAW / "criticality" / f"history_cohort_{args.t0}.parquet"
    if path.exists():
        listed = pd.read_parquet(path, columns=["project", "collection_date", "star_count"])
        listed = listed[pd.to_datetime(listed.collection_date, utc=True) <= pd.Timestamp(t0)].sort_values(["collection_date", "star_count"]).groupby("project").tail(1)
        walked.update(listed.set_index("project").star_count.dropna().to_dict())

    maintained, criticality, opencode, baselines = [], [], [], []
    missing = 0
    recreated: list[str] = []
    for m in members.itertuples():
        project = m.project
        if project not in summary.index or project not in events or pd.notna(summary.loc[project, "error"]):
            missing += 1
            continue
        info = summary.loc[project]
        commit_path = git_dir(args.t0) / f"{project.replace('/', '__')}.parquet"
        commits = pd.read_parquet(commit_path)
        if len(commits) and commits.committed.max() > limit:
            raise SystemExit(f"{project}: commit after the freeze date in the derived table")
        ev = events[project]
        created = parse(meta.loc[project, "createdAt"])
        # createdAt is current state. A repository object made after t0 was recreated under the same name: git keeps the
        # history, the issues, pull requests and releases before t0 are gone. Its age comes from the first commit.
        lost = created > t0
        if lost:
            recreated.append(project)
            created = datetime.fromtimestamp(info.first_commit, tz=timezone.utc)
        assert_not_after(created, t0, f"{project} createdAt")

        lo90, lo180, lo12 = days_before(t0, 90).timestamp(), add_months(t0, -6).timestamp(), add_months(t0, -12).timestamp()
        commits_90 = int((commits.committed > lo90).sum())
        commits_6m = commits[commits.committed > lo180]
        commits_12m = commits[commits.committed > lo12]
        tags = json.loads(info.tags) if isinstance(info.tags, str) else []
        tags = [t for t in tags if t["created"] <= limit]
        tags_6m = [t for t in tags if t["created"] > lo180]
        releases = [parse(d) for d in ev["releases"] if parse(d) <= t0]
        releases_12m = [d for d in releases if d.timestamp() > lo12]
        releases_6m = [d for d in releases if d.timestamp() > lo180]

        if lost:
            maintained.append(row(project, "scorecard_maintained", None, NOT_BACKDATABLE))
            criticality.append(row(project, "openssf_criticality", None, NOT_BACKDATABLE))
            opencode.append(row(project, "opencode_maintenance", None, NOT_BACKDATABLE))
            opencode.append(row(project, "opencode_security", None, NOT_BACKDATABLE))
            add_baselines(baselines, m, project, stars_t0, walked, created, info, commits_90, commits_12m, dependents, limit)
            continue

        # --- Scorecard Maintained -------------------------------------------------------
        score = maintained_value(commits_90, ev["activity"], created, t0)
        maintained.append(row(project, "scorecard_maintained", score, RECONSTRUCTED, limit))

        # --- OpenSSF Criticality Score --------------------------------------------------
        last_commit = info.last_commit if pd.notna(info.last_commit) else created.timestamp()
        signals = criticality_signals(created, last_commit, float(info.authors_total or 0), len(commits_12m), len(releases_12m), ev, t0,
                                      float(dependents.get(project, 0) or 0))
        criticality.append(row(project, "openssf_criticality", criticality_score(signals), RECONSTRUCTED, limit))
        for name, value in signals.items():
            criticality.append(row(project, f"signal_{name}", value, RECONSTRUCTED, limit))
        criticality.append(row(project, "signal_org_count", None, NOT_BACKDATABLE))

        # --- openCode ------------------------------------------------------------------
        issues_3m = [i for i in ev["issues"] if parse(i["createdAt"]) <= t0]
        prs = [p for p in ev["prs"] if parse(p["mergedAt"]) <= t0]
        values = opencode_values(commits_6m, issues_3m, bool(releases_6m or tags_6m), tags_6m, prs, root_files.get(project), t0)
        for name, value in values.items():
            opencode.append(row(project, name, value, RECONSTRUCTED, limit))
        opencode.append(row(project, "opencode_branch_protection", None, NOT_BACKDATABLE))

        add_baselines(baselines, m, project, stars_t0, walked, created, info, commits_90, commits_12m, dependents, limit)

    print(f"{len(members) - missing} of {len(members)} projects have the inputs; gone repositories have none", flush=True)
    print(f"recreated after t0, events lost: {recreated}", flush=True)
    write_features("scorecard_maintained", args.t0, maintained)
    write_features("criticality", args.t0, criticality)
    write_features("opencode", args.t0, opencode)
    write_features("baselines", args.t0, baselines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
