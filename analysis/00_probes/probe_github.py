#!/usr/bin/env python3
"""What GitHub can say about the panel for eligibility at t0 and outcomes after t0.

The GitHub API returns the present. Nothing read here may become a feature: `archivedAt`,
commit dates and release dates are event times and are used only to decide eligibility at
t0 and the outcomes in the window. `nameWithOwner` resolves renames and transfers.

Subcommands:
  meta    per repository: rename, archived date, commit counts per period, releases, tags.
  gone    repositories GitHub no longer serves, checked against Software Heritage.
  issues  for O1c: issues opened in the window and whether a maintainer answered in time.
  fixtags fixed versions missing from the registry, looked up among the repository's tags.
  demand  for O1c_share and the split of O1b (Amendment 1): a sample of external issues per quarter.

Known limits: commit counts walk today's default branch,
so history rewrites and branch renames are invisible, and `committedDate` is set by the
committer. `authorAssociation` is the relation today, not at the time of the comment.

Token: $GITHUB_TOKEN. It is never printed or stored.

Outputs:
  data/raw/github/meta_<t0>.jsonl, issues_<t0>.jsonl, gone_<t0>.jsonl (resumable caches)
  data/processed/github_meta_<t0>.parquet, github_issues_<t0>.parquet

Usage:
    python analysis/00_probes/probe_github.py meta --t0 2024-08-01
    python analysis/00_probes/probe_github.py gone --t0 2024-08-01
    python analysis/00_probes/probe_github.py issues --t0 2024-08-01
    python analysis/00_probes/probe_github.py fixtags --t0 2024-08-01
    python analysis/00_probes/probe_github.py demand --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "github"
PROCESSED = ROOT / "data" / "processed"
COVERAGE = ROOT / "data" / "probes" / "crossd_coverage.parquet"

GRAPHQL = "https://api.github.com/graphql"

BATCH = 20  # commit-history counts are expensive; larger batches time out on big repositories
STOP_AFTER = 3  # O1c needs at least 3 unanswered issues
ISSUE_CAP = 1000  # the search API serves no more per query
RESPONSE_DAYS = 90


def read_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("no GitHub token: set GITHUB_TOKEN")
    return token


def add_months(date: datetime, months: int) -> datetime:
    index = date.month - 1 + months
    return date.replace(year=date.year + index // 12, month=index % 12 + 1)


def iso(date: datetime) -> str:
    return date.strftime("%Y-%m-%dT%H:%M:%SZ")


def frame() -> list[str]:
    """Every project with a snapshot by 2024-08-10, so t0 can still move inside that range."""
    coverage = pd.read_parquet(COVERAGE, columns=["project", "snapshot_ts"])
    limit = datetime(2024, 8, 11, tzinfo=UTC).timestamp()
    return sorted(coverage[coverage.snapshot_ts < limit].project.unique())


class Client:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"bearer {read_token()}"

    def query(self, text: str, tries: int = 6) -> dict:
        """Returns the raw response, partial data and errors included."""
        for attempt in range(tries):
            try:
                resp = self.session.post(GRAPHQL, json={"query": text}, timeout=120)
            except requests.RequestException:
                time.sleep(2**attempt)
                continue
            if resp.status_code in (403, 429):  # secondary rate limit
                wait = int(resp.headers.get("Retry-After", 60))
                print(f"  rate limited, sleeping {wait}s", file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            if resp.status_code >= 500 or resp.status_code == 401:
                # GitHub answers 401 now and then for a valid token, so it gets retried too.
                time.sleep(max(2**attempt, 20 if resp.status_code == 401 else 0))
                continue
            resp.raise_for_status()
            try:
                payload = resp.json()
            except ValueError:  # GitHub answers some gateway errors with an HTML body and 200
                time.sleep(2**attempt)
                continue
            limit = (payload.get("data") or {}).get("rateLimit")
            if limit and limit["remaining"] < 100:
                reset = datetime.fromisoformat(limit["resetAt"].replace("Z", "+00:00"))
                wait = max((reset - datetime.now(UTC)).total_seconds(), 0) + 5
                print(f"  quota low, sleeping {wait:.0f}s", file=sys.stderr, flush=True)
                time.sleep(wait)
            return payload
        return {"errors": [{"type": "CLIENT_GAVE_UP"}]}


def done_keys(path: Path) -> set[str]:
    """Projects with a final answer. A client failure is no answer: it is fetched again."""
    if not path.exists():
        return set()
    done = set()
    with path.open() as fh:
        for line in fh:
            rec = json.loads(line)
            if "CLIENT_GAVE_UP" not in (rec.get("errors") or []):
                done.add(rec["project"])
    return done


# --- meta ---------------------------------------------------------------------------------


def periods(t0: datetime, horizon: int) -> dict[str, tuple[datetime, datetime]]:
    """The counting periods behind eligibility, O1b and its sensitivity variants."""
    t1 = add_months(t0, horizon)
    t1_short = add_months(t0, 12)
    return {
        "before_180d": (t0 - timedelta(days=180), t0),
        "last_12m": (add_months(t1, -12), t1),
        "last_6m": (add_months(t1, -6), t1),
        "short_last_12m": (add_months(t1_short, -12), t1_short),
        "short_last_6m": (add_months(t1_short, -6), t1_short),
    }


def meta_fragment(alias: str, project: str, spans: dict) -> str:
    owner, name = project.split("/", 1)
    counts = " ".join(
        f'{key}: history(since: "{iso(lo)}", until: "{iso(hi)}") {{ totalCount }}'
        for key, (lo, hi) in spans.items()
    )
    return f"""{alias}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
      nameWithOwner databaseId createdAt pushedAt isArchived archivedAt isFork isMirror isEmpty
      hasIssuesEnabled isDisabled isLocked
      defaultBranchRef {{ name target {{ ... on Commit {{ {counts} }} }} }}
      releases(first: 100, orderBy: {{field: CREATED_AT, direction: DESC}}) {{
        totalCount nodes {{ publishedAt createdAt isDraft }} }}
    }}"""


def fetch_tag_dates(client: Client, project: str) -> list[str]:
    """Tag dates of one repository. Sorting tags by date times out in a batch, so this runs
    only for the projects where it can change O1b: no commit and no release in the period."""
    owner, name = project.split("/", 1)
    payload = client.query(
        f"""query {{ rateLimit {{ remaining resetAt }}
        repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
          refs(refPrefix: "refs/tags/", first: 30,
               orderBy: {{field: TAG_COMMIT_DATE, direction: DESC}}) {{
            nodes {{ target {{ ... on Commit {{ committedDate }}
                               ... on Tag {{ tagger {{ date }} }} }} }} }} }} }}""",
        tries=3,
    )
    repo = (payload.get("data") or {}).get("repository") or {}
    dates = []
    for node in (repo.get("refs") or {}).get("nodes") or []:
        target = node.get("target") or {}
        date = target.get("committedDate") or (target.get("tagger") or {}).get("date")
        if date:
            dates.append(date)
    return dates


def fetch_meta(client: Client, batch: list[str], spans: dict) -> list[dict]:
    aliases = {f"r{i}": p for i, p in enumerate(batch)}
    body = "\n".join(meta_fragment(a, p, spans) for a, p in aliases.items())
    text = f"query {{ rateLimit {{ remaining resetAt }} {body} }}"
    payload = client.query(text)
    data = payload.get("data") or {}
    errors = payload.get("errors") or []

    # A timeout hides which repository caused it, so split until the culprit stands alone.
    if not data or (errors and not any(aliases.keys() & data.keys())):
        if len(batch) > 1:
            middle = len(batch) // 2
            return fetch_meta(client, batch[:middle], spans) + fetch_meta(
                client, batch[middle:], spans
            )
    records = []
    for alias, project in aliases.items():
        own = [e for e in errors if (e.get("path") or [None])[0] == alias]
        if not data and not own:
            own = errors
        records.append(
            {
                "project": project,
                "repo": data.get(alias),
                "errors": [e.get("type") or e.get("message") for e in own],
            }
        )
    return records


def latest_in(dates: list[str], lo: datetime, hi: datetime) -> bool:
    for value in dates:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if lo < when <= hi:
            return True
    return False


def flatten_meta(rec: dict, spans: dict) -> dict:
    repo = rec["repo"] or {}
    row = {
        "project": rec["project"],
        "errors": "|".join(str(e) for e in rec["errors"]),
        "resolved": bool(repo),
        "canonical": repo.get("nameWithOwner"),
        "renamed": bool(repo) and repo["nameWithOwner"].lower() != rec["project"].lower(),
    }
    for key in ("databaseId", "createdAt", "pushedAt", "isArchived", "archivedAt", "isFork",
                "isMirror", "isEmpty", "hasIssuesEnabled", "isDisabled", "isLocked"):
        row[key] = repo.get(key)

    target = ((repo.get("defaultBranchRef") or {}).get("target")) or {}
    releases = [
        n.get("publishedAt") or n.get("createdAt")
        for n in (repo.get("releases") or {}).get("nodes") or []
        if not n.get("isDraft")
    ]
    tags = rec.get("tag_dates") or []
    row["releases_total"] = (repo.get("releases") or {}).get("totalCount")
    for key, (lo, hi) in spans.items():
        row[f"commits_{key}"] = (target.get(key) or {}).get("totalCount")
        row[f"release_{key}"] = latest_in([d for d in releases if d], lo, hi)
        row[f"tag_{key}"] = latest_in(tags, lo, hi)
    return row


def cmd_meta(args) -> int:
    t0 = datetime.fromisoformat(args.t0).replace(tzinfo=UTC)
    spans = periods(t0, args.horizon)
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / f"meta_{args.t0}.jsonl"
    projects = frame()
    todo = [p for p in projects if p not in done_keys(cache)]
    print(f"meta: {len(projects)} in frame, {len(todo)} to fetch", flush=True)

    client = Client()
    with cache.open("a") as out:
        for start in range(0, len(todo), BATCH):
            for rec in fetch_meta(client, todo[start : start + BATCH], spans):
                out.write(json.dumps(rec) + "\n")
            out.flush()
            if start % (BATCH * 20) == 0:
                print(f"  {start}/{len(todo)}", flush=True)

    records = {}
    with cache.open() as fh:
        for line in fh:
            rec = json.loads(line)
            records[rec["project"]] = rec

    # Second pass: tags, only where they can decide O1b.
    tag_cache = RAW / f"tags_{args.t0}.jsonl"
    known_tags: dict[str, list] = {}
    if tag_cache.exists():
        with tag_cache.open() as fh:
            for line in fh:
                item = json.loads(line)
                known_tags[item["project"]] = item["tag_dates"]
    with tag_cache.open("a") as out:
        for project, rec in records.items():
            row = flatten_meta(rec, spans)
            quiet = row["resolved"] and not (row["commits_last_12m"] or row["release_last_12m"])
            short_quiet = row["resolved"] and not (
                row["commits_short_last_12m"] or row["release_short_last_12m"]
            )
            if (quiet or short_quiet) and project not in known_tags:
                known_tags[project] = fetch_tag_dates(client, project)
                out.write(json.dumps({"project": project, "tag_dates": known_tags[project]}) + "\n")
                out.flush()
    print(f"tags looked up for {len(known_tags)} quiet repositories", flush=True)

    rows = [
        flatten_meta({**rec, "tag_dates": known_tags.get(project)}, spans)
        for project, rec in records.items()
    ]
    table = pd.DataFrame(rows)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    table.to_parquet(PROCESSED / f"github_meta_{args.t0}.parquet", index=False)
    print(
        f"resolved {int(table.resolved.sum())}, gone or inaccessible {int((~table.resolved).sum())}, "
        f"renamed {int(table.renamed.sum())}, archived {int(table.isArchived.fillna(False).sum())}, "
        f"archived without date {int((table.isArchived.fillna(False) & table.archivedAt.isna()).sum())}"
    )
    print("error types:", table[~table.resolved].errors.value_counts().to_dict())
    return 0


# --- gone ---------------------------------------------------------------------------------


def cmd_gone(args) -> int:
    """Software Heritage knows when it last reached an origin, which dates a disappearance."""
    table = pd.read_parquet(PROCESSED / f"github_meta_{args.t0}.parquet")
    gone = table[~table.resolved].project.tolist()
    cache = RAW / f"gone_{args.t0}.jsonl"
    todo = [p for p in gone if p not in done_keys(cache)]
    print(f"gone: {len(gone)} candidates, {len(todo)} to check", flush=True)
    swh = "https://archive.softwareheritage.org/api/1/origin"
    with cache.open("a") as out:
        for project in todo:
            url = f"https://github.com/{project}"
            resp = requests.get(f"{swh}/{url}/visits/", params={"per_page": 50}, timeout=60)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", 300)))
                resp = requests.get(f"{swh}/{url}/visits/", params={"per_page": 50}, timeout=60)
            visits = resp.json() if resp.ok else []
            full = [v["date"] for v in visits if v.get("status") == "full"]
            missing = [v["date"] for v in visits if v.get("status") == "not_found"]
            out.write(
                json.dumps(
                    {
                        "project": project,
                        "swh_status": resp.status_code,
                        "visits": len(visits),
                        "last_full_visit": max(full) if full else None,
                        "first_not_found_after_last_full": min(
                            (d for d in missing if not full or d > max(full)), default=None
                        ),
                    }
                )
                + "\n"
            )
            out.flush()
            time.sleep(1)
    print(pd.read_json(cache, lines=True).describe(include="all").T.iloc[:, :4].to_string())
    return 0


# --- issues -------------------------------------------------------------------------------


MAINTAINER = {"OWNER", "MEMBER", "COLLABORATOR"}

ISSUE_FIELDS = """
  ... on Issue {
    number createdAt closedAt authorAssociation
    comments(first: 30) { nodes { createdAt authorAssociation } }
  }
"""


def classify(node: dict) -> dict:
    created = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
    limit = created + timedelta(days=RESPONSE_DAYS)
    answered = False
    for comment in (node.get("comments") or {}).get("nodes") or []:
        when = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00"))
        if comment.get("authorAssociation") in MAINTAINER and when <= limit:
            answered = True
            break
    closed = node.get("closedAt")
    closed_in_time = bool(
        closed and datetime.fromisoformat(closed.replace("Z", "+00:00")) <= limit
    )
    return {
        "number": node["number"],
        "createdAt": node["createdAt"],
        "by_maintainer": node.get("authorAssociation") in MAINTAINER,
        "maintainer_answer_90d": answered,
        "closed_90d": closed_in_time,
    }


def issues_for(client: Client, canonical: str, lo: datetime, hi: datetime) -> dict:
    """Stops once the strictest reading of O1c has 3 issues, so every reading can be counted."""
    search = f"repo:{canonical} is:issue created:{iso(lo)}..{iso(hi)} sort:created-asc"
    seen: list[dict] = []
    strict = 0
    cursor = None
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        text = f"""query {{ rateLimit {{ remaining resetAt }}
          search(query: {json.dumps(search)}, type: ISSUE, first: 50{after}) {{
            issueCount pageInfo {{ hasNextPage endCursor }} nodes {{ {ISSUE_FIELDS} }} }} }}"""
        payload = client.query(text)
        result = (payload.get("data") or {}).get("search")
        if result is None:
            return {"issue_count": None, "issues": seen, "complete": False,
                    "errors": [e.get("type") or e.get("message") for e in payload.get("errors", [])]}
        for node in result["nodes"]:
            if not node:
                continue
            row = classify(node)
            seen.append(row)
            if not (row["by_maintainer"] or row["maintainer_answer_90d"] or row["closed_90d"]):
                strict += 1
        if strict >= STOP_AFTER or not result["pageInfo"]["hasNextPage"]:
            complete = not result["pageInfo"]["hasNextPage"]
            return {"issue_count": result["issueCount"], "issues": seen, "complete": complete,
                    "stopped_early": strict >= STOP_AFTER, "errors": []}
        if len(seen) >= ISSUE_CAP:
            return {"issue_count": result["issueCount"], "issues": seen, "complete": False,
                    "stopped_early": False, "errors": []}
        cursor = result["pageInfo"]["endCursor"]


def cmd_issues(args) -> int:
    t0 = datetime.fromisoformat(args.t0).replace(tzinfo=UTC)
    t1 = add_months(t0, args.horizon)
    table = pd.read_parquet(PROCESSED / f"github_meta_{args.t0}.parquet")
    table = table[table.resolved & table.hasIssuesEnabled.fillna(False)]
    cache = RAW / f"issues_{args.t0}.jsonl"
    done = done_keys(cache)
    todo = table[~table.project.isin(done)]
    print(f"issues: {len(table)} with issues enabled, {len(todo)} to fetch", flush=True)
    client = Client()
    with cache.open("a") as out:
        for n, row in enumerate(todo.itertuples(), 1):
            result = issues_for(client, row.canonical, t0, t1)
            out.write(json.dumps({"project": row.project, **result}) + "\n")
            out.flush()
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
            time.sleep(0.5)  # search has a lower secondary limit than the rest of GraphQL

    rows = []
    with cache.open() as fh:
        for line in fh:
            rec = json.loads(line)
            issues = rec["issues"]
            rows.append(
                {
                    "project": rec["project"],
                    "issue_count": rec.get("issue_count"),
                    "complete": rec.get("complete"),
                    "stopped_early": rec.get("stopped_early"),
                    "seen": len(issues),
                    # as drafted: any issue without a maintainer comment in 90 days
                    "unanswered_draft": sum(not i["maintainer_answer_90d"] for i in issues),
                    # issues filed by maintainers are not demand on them
                    "unanswered_external": sum(
                        not (i["maintainer_answer_90d"] or i["by_maintainer"]) for i in issues
                    ),
                    # and a closed issue was dealt with, comment or not
                    "unanswered_strict": sum(
                        not (i["maintainer_answer_90d"] or i["by_maintainer"] or i["closed_90d"])
                        for i in issues
                    ),
                    "errors": "|".join(str(e) for e in rec.get("errors") or []),
                }
            )
    result = pd.DataFrame(rows).drop_duplicates("project")
    result.to_parquet(PROCESSED / f"github_issues_{args.t0}.parquet", index=False)
    print(result[["unanswered_draft", "unanswered_external", "unanswered_strict"]].ge(3).sum())
    return 0


# --- demand -------------------------------------------------------------------------------

DEMAND_PER_QUARTER = 25
DEMAND_MIN_ISSUES = 10
RESPONDERS_NARROW = MAINTAINER
RESPONDERS_BROAD = MAINTAINER | {"CONTRIBUTOR"}


def classify_demand(node: dict) -> dict:
    created = datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00"))
    limit = created + timedelta(days=RESPONSE_DAYS)
    in_time = [
        c.get("authorAssociation")
        for c in (node.get("comments") or {}).get("nodes") or []
        if datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00")) <= limit
    ]
    closed = node.get("closedAt")
    return {
        "number": node["number"],
        "createdAt": node["createdAt"],
        "external": node.get("authorAssociation") not in MAINTAINER,
        "narrow_answer": any(a in RESPONDERS_NARROW for a in in_time),
        "broad_answer": any(a in RESPONDERS_BROAD for a in in_time),
        "closed_90d": bool(closed and datetime.fromisoformat(closed.replace("Z", "+00:00")) <= limit),
    }


def demand_for(client: Client, canonical: str, t0: datetime, quarters: int = 8) -> dict:
    """The earliest issues of each quarter, so a long window is not read from its start only."""
    issues: list[dict] = []
    failed = False
    for quarter in range(quarters):
        lo, hi = add_months(t0, 3 * quarter), add_months(t0, 3 * (quarter + 1))
        search = f"repo:{canonical} is:issue created:{iso(lo)}..{iso(hi)} sort:created-asc"
        text = f"""query {{ rateLimit {{ remaining resetAt }}
          search(query: {json.dumps(search)}, type: ISSUE, first: {DEMAND_PER_QUARTER}) {{
            nodes {{ {ISSUE_FIELDS} }} }} }}"""
        result = (client.query(text).get("data") or {}).get("search")
        if result is None:
            failed = True
            continue
        issues += [classify_demand(node) for node in result["nodes"] if node]
    return {"issues": issues, "errors": ["CLIENT_GAVE_UP"] if failed else []}


def cmd_demand(args) -> int:
    t0 = datetime.fromisoformat(args.t0).replace(tzinfo=UTC)
    t1 = add_months(t0, args.horizon)
    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{args.t0}.csv")
    if args.horizon == 24:
        issues = pd.read_parquet(PROCESSED / f"github_issues_{args.t0}.parquet", columns=["project", "issue_count"])
        outcomes = pd.read_parquet(PROCESSED / f"outcomes_{args.t0}.parquet", columns=["project", "O1b"])
        table = cohort.merge(issues, on="project").merge(outcomes, on="project")
        # The issue count of the first crawl spares projects that cannot reach the minimum.
        wanted = table[table.issue_count.ge(DEMAND_MIN_ISSUES) | (table.O1b & table.issue_count.gt(0))]
    else:  # the robustness date has no first crawl
        wanted = cohort[cohort.canonical.notna() & ~cohort.gone_now.fillna(False).astype(bool)]
    cache = RAW / f"demand_{args.t0}.jsonl"
    todo = wanted[~wanted.project.isin(done_keys(cache))]
    print(f"demand: {len(wanted)} wanted, {len(todo)} to fetch", flush=True)
    client = Client()
    with cache.open("a") as out:
        for n, row in enumerate(todo.itertuples(), 1):
            out.write(json.dumps({"project": row.project, **demand_for(client, row.canonical, t0, args.horizon // 3)}) + "\n")
            out.flush()
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}", flush=True)

    last_year = add_months(t1, -12)
    records: dict[str, dict] = {}
    with cache.open() as fh:
        for line in fh:
            rec = json.loads(line)
            records[rec["project"]] = rec
    rows = []
    for project, rec in records.items():
        external = [i for i in rec["issues"] if i["external"]]
        broad = [not (i["broad_answer"] or i["closed_90d"]) for i in external]
        narrow = [not (i["narrow_answer"] or i["closed_90d"]) for i in external]
        recent = [
            i
            for i in external
            if datetime.fromisoformat(i["createdAt"].replace("Z", "+00:00")) > last_year
            and not (i["broad_answer"] or i["closed_90d"])
        ]
        rows.append(
            {
                "project": project,
                "n_external": len(external),
                "share_unanswered": sum(broad) / len(broad) if broad else None,
                "share_unanswered_narrow": sum(narrow) / len(narrow) if narrow else None,
                "recent_unanswered": len(recent),
                "errors": "|".join(rec.get("errors") or []),
            }
        )
    result = pd.DataFrame(rows)
    result.to_parquet(PROCESSED / f"github_demand_{args.t0}.parquet", index=False)
    print(f"{len(result)} projects, {int(result.n_external.ge(DEMAND_MIN_ISSUES).sum())} at the minimum")
    return 0


# --- fixtags ------------------------------------------------------------------------------


def tag_candidates(version: str, package: str) -> list[str]:
    short = re.split(r"[/:]", package)[-1]
    return [f"v{version}", version, f"{package}@{version}", f"{short}-{version}", f"{short}-v{version}",
            f"{short}@{version}", f"release-{version}", f"{short}/v{version}"]


def cmd_fixtags(args) -> int:
    """The date of a tag naming the fixed version, for versions the registry does not list."""
    lookup = pd.read_parquet(PROCESSED / f"fix_lookup_{args.t0}.parquet")
    cache = RAW / f"fix_tags_{args.t0}.jsonl"
    done: set[tuple[str, str]] = set()
    if cache.exists():
        with cache.open() as fh:
            for line in fh:
                rec = json.loads(line)
                done.add((rec["repo"], rec["version"]))
    wanted = sorted(
        {
            (row.repo, row.package, version)
            for row in lookup.itertuples()
            for version in row.fixed_versions.split("|")
            if version and (row.repo, version) not in done
        }
    )
    print(f"fixtags: {len(wanted)} versions to look up", flush=True)
    client = Client()
    with cache.open("a") as out:
        for repo, package, version in wanted:
            owner, name = repo.split("/", 1)
            names = tag_candidates(version, package)
            aliases = " ".join(
                f"""t{i}: ref(qualifiedName: {json.dumps("refs/tags/" + tag)}) {{
                      target {{ ... on Commit {{ committedDate }}
                                ... on Tag {{ tagger {{ date }}
                                              target {{ ... on Commit {{ committedDate }} }} }} }} }}"""
                for i, tag in enumerate(names)
            )
            payload = client.query(
                f"""query {{ rateLimit {{ remaining resetAt }}
                repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {aliases} }} }}""",
                tries=3,
            )
            found = (payload.get("data") or {}).get("repository") or {}
            date, matched = None, None
            for i, tag in enumerate(names):
                target = (found.get(f"t{i}") or {}).get("target") or {}
                date = (
                    (target.get("tagger") or {}).get("date")
                    or target.get("committedDate")
                    or (target.get("target") or {}).get("committedDate")
                )
                if date:
                    matched = tag
                    break
            out.write(json.dumps({"repo": repo, "version": version, "tag": matched, "date": date}) + "\n")
            out.flush()
    with cache.open() as fh:
        rows = [json.loads(line) for line in fh]
    print(f"found a tag for {sum(bool(r['date']) for r in rows)} of {len(rows)} versions")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["meta", "gone", "issues", "fixtags", "demand"])
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--horizon", type=int, default=24, help="months")
    args = ap.parse_args()
    commands = {"meta": cmd_meta, "gone": cmd_gone, "issues": cmd_issues, "fixtags": cmd_fixtags,
                "demand": cmd_demand}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
