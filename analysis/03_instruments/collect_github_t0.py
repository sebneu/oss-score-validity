#!/usr/bin/env python3
"""Dated GitHub events before t0, for the openCode rules and the Scorecard Maintained check.

Only dated events are used, and every date is checked against t0 again in the adapters:
  - issues created in the 90 days before t0, with their comments (issue response time);
  - issues touched since 90 days before t0, for activity by project members;
  - pull requests merged in the 6 months before t0, with their reviews;
  - releases published in the 12 months before t0;
  - the number of issues closed in the 90 days before t0;

Stars are not read here: GitHub closed dated stargazers, see collect_stars_gharchive.py.

`authorAssociation` is today's relation, a limit stated in the paper. Resumable.

Output: data/raw/github/t0_events_<t0>.jsonl

Usage:
    python analysis/03_instruments/collect_github_t0.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_probes"))

import probe_github  # noqa: E402

from base import RAW, add_months, cohort, days_before, freeze  # noqa: E402

MAX_ISSUES = 100
MAX_ACTIVITY = 100
MAX_PRS = 100
MAX_RELEASE_PAGES = 5


def iso(date) -> str:
    return date.strftime("%Y-%m-%dT%H:%M:%SZ")


def search(client, query: str, fields: str, limit: int) -> tuple[list[dict], int | None, bool]:
    nodes, total, cursor, failed = [], None, None, False
    while len(nodes) < limit:
        after = f', after: "{cursor}"' if cursor else ""
        text = f"""query {{ rateLimit {{ remaining resetAt }}
          search(query: {json.dumps(query)}, type: ISSUE, first: {min(100, limit - len(nodes))}{after}) {{
            issueCount pageInfo {{ hasNextPage endCursor }} nodes {{ {fields} }} }} }}"""
        result = (client.query(text).get("data") or {}).get("search")
        if result is None:
            failed = True
            break
        total = result["issueCount"]
        nodes += [n for n in result["nodes"] if n]
        if not result["pageInfo"]["hasNextPage"]:
            break
        cursor = result["pageInfo"]["endCursor"]
    return nodes, total, failed


ISSUE = """... on Issue { number createdAt closedAt author { login } authorAssociation
  comments(first: 30) { nodes { createdAt authorAssociation author { login } } } }"""
ACTIVITY = """... on Issue { number createdAt authorAssociation
  comments(last: 30) { nodes { createdAt authorAssociation } } }"""
PR = """... on PullRequest { number mergedAt author { login } mergedBy { login }
  reviews(first: 30) { nodes { state submittedAt authorAssociation author { login } } } }"""


def releases(client, owner: str, name: str, lo) -> tuple[list[str], bool]:
    dates, cursor, failed = [], None, False
    for _ in range(MAX_RELEASE_PAGES):
        after = f', after: "{cursor}"' if cursor else ""
        text = f"""query {{ rateLimit {{ remaining resetAt }}
          repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
            releases(first: 100, orderBy: {{field: CREATED_AT, direction: DESC}}{after}) {{
              pageInfo {{ hasNextPage endCursor }} nodes {{ publishedAt createdAt isDraft }} }} }} }}"""
        repo = (client.query(text).get("data") or {}).get("repository")
        if repo is None:
            return dates, True
        page = repo["releases"]
        stamps = [n.get("publishedAt") or n["createdAt"] for n in page["nodes"] if not n["isDraft"]]
        dates += stamps
        if not page["pageInfo"]["hasNextPage"] or (stamps and min(stamps) < iso(lo)):
            break
        cursor = page["pageInfo"]["endCursor"]
    return dates, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = freeze(args.t0)
    members = cohort(args.t0)
    members = members[~members.gone_now & members.canonical.notna()]


    cache = RAW / "github" / f"t0_events_{args.t0}.jsonl"
    done = set()
    if cache.exists():
        with cache.open() as fh:
            for line in fh:
                rec = json.loads(line)
                if not rec.get("failed"):
                    done.add(rec["project"])
    todo = members[~members.project.isin(done)]
    print(f"{len(members)} repositories, {len(todo)} to fetch", flush=True)

    client = probe_github.Client()
    lo90, lo180, lo12 = days_before(t0, 90), add_months(t0, -6), add_months(t0, -12)
    end = iso(t0)
    with cache.open("a") as out:
        for n, m in enumerate(todo.itertuples(), 1):
            repo = m.canonical
            owner, name = repo.split("/", 1)
            issues, _, f1 = search(client, f"repo:{repo} is:issue created:{iso(lo90)}..{end} sort:created-asc", ISSUE, MAX_ISSUES)
            activity, _, f2 = search(client, f"repo:{repo} is:issue updated:>={iso(lo90)} created:<={end} sort:updated-asc", ACTIVITY, MAX_ACTIVITY)
            prs, prs_total, f3 = search(client, f"repo:{repo} is:pr is:merged merged:{iso(lo180)}..{end} sort:created-desc", PR, MAX_PRS)
            _, closed_total, f4 = search(client, f"repo:{repo} is:issue closed:{iso(lo90)}..{end}", "... on Issue { number }", 1)
            rel, f5 = releases(client, owner, name, lo12)
            out.write(json.dumps({
                "project": m.project, "issues": issues, "activity": activity, "prs": prs, "prs_total": prs_total,
                "closed_90d": closed_total, "releases": rel,
                "failed": any((f1, f2, f3, f4, f5)),
            }) + "\n")
            out.flush()
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
            time.sleep(0.2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
