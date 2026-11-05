#!/usr/bin/env python3
"""All instruments at the last commit before each incident (case panel).

The cases, components and readings are fixed in DECISIONS.md ("Case panel, extended"). The cases are
selected on the outcome, so nothing here enters the validity statistics, and no other script reads this output for them.

XZ Utils and tj-actions are not in the CrOSSD panel. Their values are rebuilt by the same rules and carry no recorded
CrOSSD value. Their Criticality Score is the last list before the event.

Reading date: the day before the event. Scorecard runs at the last commit before that date.

Outputs:
  data/raw/cases/instruments.jsonl          one line per case, resumable
  data/raw/cases/criticality_lists.parquet  published lists of the two projects outside the cohort

Usage:
    python analysis/05_cases/case_instruments.py
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))
sys.path.insert(0, str(ROOT / "analysis" / "03_instruments"))

import collect_github_t0 as events  # noqa: E402
import probe_depsdev_bq  # noqa: E402
import probe_github  # noqa: E402
import rule_adapters as rules  # noqa: E402
from base import RAW, add_months, assert_not_after, cohort, days_before, freeze, parse  # noqa: E402
from collect_git import CLONES, CO_AUTHOR, END, SEP, git, hashed  # noqa: E402
from collect_scorecard import T0_CHECKS, run  # noqa: E402
from rebuild_bus_factor import score as bus_score  # noqa: E402

CASES = {  # project: event date, fixed in DECISIONS.md
    "axios/axios": "2026-03-31",
    "Lightning-AI/pytorch-lightning": "2026-04-30",
    "ultralytics/ultralytics": "2024-12-05",
    "facebook/react": "2025-12-03",
    "mongodb/mongo": "2025-12-19",
    "minio/minio": "2025-12-03",
    "tukaani-project/xz": "2024-02-23",
    "tj-actions/changed-files": "2025-03-14",
}
OUTSIDE = ["tukaani-project/xz", "tj-actions/changed-files"]
OUT = RAW / "cases"


def commits_until(clone: Path, when) -> tuple[pd.DataFrame, str | None]:
    """Commits in the 13 months before a date, in the columns of collect_git.py, and the newest commit."""
    until = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    log = git("log", "HEAD", f"--until={until}", f"--format=%H{SEP}%ct{SEP}%at{SEP}%ae{SEP}%ce{SEP}%(trailers:key=Co-authored-by,valueonly,separator=|){END}", cwd=clone)
    start, limit = add_months(when, -13).timestamp(), when.timestamp()
    rows, newest, sha = [], None, None
    for record in log.stdout.split(END):
        parts = record.strip().split(SEP)
        if len(parts) < 5:
            continue
        committed = int(parts[1])
        if committed > limit:
            continue
        if newest is None or committed > newest:
            newest, sha = committed, parts[0]
        if committed > start:
            co = CO_AUTHOR.findall("Co-authored-by: " + parts[5].replace("|", "\nCo-authored-by: ")) if len(parts) > 5 and parts[5] else []
            rows.append({"sha": parts[0], "committed": committed, "author": hashed(parts[3]), "committer": hashed(parts[4]), "co_authors": "|".join(hashed(c) for c in co)})
    return pd.DataFrame(rows, columns=["sha", "committed", "author", "committer", "co_authors"]), sha


def tags_until(clone: Path, limit: float) -> list[dict]:
    out = git("for-each-ref", "refs/tags", f"--format=%(refname:short){SEP}%(objecttype){SEP}%(creatordate:unix){SEP}%(contents:signature){END}", cwd=clone)
    tags = []
    for record in out.stdout.split(END):
        parts = record.strip().split(SEP)
        if len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) <= limit:
            tags.append({"created": int(parts[2]), "signed": bool(len(parts) > 3 and parts[3].strip())})
    return tags


def root_entries(client, repo: str, sha: str) -> list[str] | None:
    owner, name = repo.split("/", 1)
    text = f'query {{ rateLimit {{ remaining resetAt }} repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ object(oid: "{sha}") {{ ... on Commit {{ tree {{ entries {{ name }} }} }} }} }} }}'
    tree = (((client.query(text).get("data") or {}).get("repository") or {}).get("object") or {}).get("tree")
    return [e["name"] for e in tree["entries"]] if tree else None


def created_at(client, repo: str):
    owner, name = repo.split("/", 1)
    text = f"query {{ rateLimit {{ remaining resetAt }} repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ createdAt }} }}"
    return parse(client.query(text)["data"]["repository"]["createdAt"])


def case_values(client, project: str, repo: str, event: str) -> dict:
    when = freeze(event) - timedelta(days=1)
    slug = project.replace("/", "__")
    clone = CLONES / f"{slug}.git"
    if not (clone / "HEAD").exists():
        done = git("clone", "--bare", "--filter=tree:0", "--single-branch", f"https://github.com/{repo}.git", str(clone))
        if done.returncode != 0:
            return {"project": project, "error": done.stderr.strip()[-200:]}
    commits, sha = commits_until(clone, when)
    assert_not_after(float(commits.committed.max()), when, project)
    limit = when.timestamp()
    lo90, lo180, lo12 = days_before(when, 90), add_months(when, -6), add_months(when, -12)
    end = events.iso(when)
    issues, _, _ = events.search(client, f"repo:{repo} is:issue created:{events.iso(lo90)}..{end} sort:created-asc", events.ISSUE, events.MAX_ISSUES)
    activity, _, _ = events.search(client, f"repo:{repo} is:issue updated:>={events.iso(lo90)} created:<={end} sort:updated-asc", events.ACTIVITY, events.MAX_ACTIVITY)
    prs, _, _ = events.search(client, f"repo:{repo} is:pr is:merged merged:{events.iso(lo180)}..{end} sort:created-desc", events.PR, events.MAX_PRS)
    owner, name = repo.split("/", 1)
    released, _ = events.releases(client, owner, name, lo12)
    release_dates = [parse(d) for d in released if parse(d) <= when]
    tags = tags_until(clone, limit)
    tags_6m = [t for t in tags if t["created"] > lo180.timestamp()]
    commits_6m = commits[commits.committed > lo180.timestamp()]
    commits_90 = int((commits.committed > lo90.timestamp()).sum())
    release_6m = any(d > lo180 for d in release_dates) or bool(tags_6m)
    created = min(created_at(client, repo), parse(pd.Timestamp(commits.committed.min(), unit="s", tz="UTC").isoformat())) if len(commits) else created_at(client, repo)
    opencode = rules.opencode_values(commits_6m, [i for i in issues if parse(i["createdAt"]) <= when], release_6m, tags_6m,
                                     [p for p in prs if parse(p["mergedAt"]) <= when], root_entries(client, repo, sha), when)
    month = commits[commits.committed > add_months(when, -1).timestamp()]
    result = run(repo, sha, 1200, T0_CHECKS)
    checks = {k: v["score"] for k, v in (result.get("checks") or {}).items()}
    return {"project": project, "error": result.get("error"), "event": event, "reading": when.date().isoformat(), "commit": sha,
            "checks": {**checks, "Maintained": rules.maintained_value(commits_90, activity, created, when)},
            "reasons": {k: v["reason"] for k, v in (result.get("checks") or {}).items()},
            "bus_factor_rebuilt": bus_score(month, "web_flow") if len(month) else None, "opencode": opencode}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    members = cohort("2024-08-01").set_index("project")
    path = OUT / "instruments.jsonl"
    done = {}
    if path.exists():
        with path.open() as fh:
            for line in fh:
                rec = json.loads(line)
                done[rec["project"]] = rec
    client = probe_github.Client()
    with path.open("a") as out:
        for project, event in CASES.items():
            if project in done and not done[project].get("error"):
                continue
            repo = str(members.loc[project, "canonical"]) if project in members.index else project
            print(project, event, flush=True)
            out.write(json.dumps(case_values(client, project, repo, event)) + "\n")
            out.flush()

    lists = OUT / "criticality_lists.parquet"
    if not lists.exists():
        bq = bigquery.Client(project=probe_depsdev_bq.calling_project())
        urls = [f"https://github.com/{p}".lower() for p in OUTSIDE]
        sql = """SELECT collection_date, default_score, LOWER(repo.url) AS url FROM `openssf.criticality_score_cron.criticality-score-v0`
                 WHERE LOWER(repo.url) IN UNNEST(@urls)"""
        config = bigquery.QueryJobConfig(maximum_bytes_billed=2 * 10**9, query_parameters=[bigquery.ArrayQueryParameter("urls", "STRING", urls)])
        bq.query(sql, job_config=config).to_dataframe().to_parquet(lists, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
