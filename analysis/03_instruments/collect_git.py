#!/usr/bin/env python3
"""Commit and tag history up to t0, from commit-only clones.

Git history is an event-time source, so it can answer what was true at t0. A clone with
`--filter=tree:0` holds commits and tags without trees or files, which keeps it small and makes no
API requests. Only rows up to t0 leave this script. Email addresses are stored as salted hashes,
so the derived tables can count people without naming them.

Limits: commits are those reachable from today's default branch, and a
deleted tag is gone.

Outputs:
  data/raw/git/<owner>__<name>.git                   the clones
  data/processed/git/<owner>__<name>.parquet         commits up to t0 in the last 13 months before it
  data/processed/git_summary_<t0>.parquet            per project: last commit, all-time authors, tags

Usage:
    python analysis/03_instruments/collect_git.py --t0 2024-08-01 --workers 6
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from base import PROCESSED, RAW, add_months, cohort, freeze, git_dir

SALT = "oss-score-validity"
CLONES = RAW / "git"
SEP = "\x1f"
END = "\x1e"
CO_AUTHOR = re.compile(r"Co-authored-by:.*?<([^>]+)>", re.IGNORECASE)


def hashed(email: str) -> str:
    return hashlib.sha256((SALT + email.strip().lower()).encode()).hexdigest()[:16]


def git(*args: str, timeout: int = 7200, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, errors="replace", timeout=timeout, cwd=cwd,
                          env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/opt/homebrew/bin:/bin"})


def process(project: str, canonical: str, t0_iso: str) -> dict:
    t0 = freeze(t0_iso)
    slug = project.replace("/", "__")
    clone = CLONES / f"{slug}.git"
    out = git_dir(t0_iso)
    commits_path = out / f"{slug}.parquet"
    summary_path = out / f"{slug}.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text())

    if not (clone / "HEAD").exists():
        done = git("clone", "--bare", "--filter=tree:0", "--single-branch", f"https://github.com/{canonical}.git", str(clone))
        if done.returncode != 0:
            return {"project": project, "error": done.stderr.strip()[-200:]}

    # Everything up to t0, reachable from the default branch.
    until = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    log = git("log", "HEAD", f"--until={until}", f"--format=%H{SEP}%ct{SEP}%at{SEP}%ae{SEP}%ce{SEP}%(trailers:key=Co-authored-by,valueonly,separator=|){END}", cwd=clone)
    if log.returncode != 0:
        return {"project": project, "error": log.stderr.strip()[-200:]}

    start = add_months(t0, -13).timestamp()
    limit = t0.timestamp()
    rows, authors, newest, newest_sha, oldest, total = [], set(), None, None, None, 0
    for record in log.stdout.split(END):
        parts = record.strip().split(SEP)
        if len(parts) < 5:
            continue
        sha, committed, authored, author, committer = parts[0], int(parts[1]), int(parts[2]), parts[3], parts[4]
        if committed > limit:
            continue
        total += 1
        authors.add(hashed(author))
        if newest is None or committed > newest:
            newest, newest_sha = committed, sha
        oldest = committed if oldest is None else min(oldest, committed)
        if committed > start:
            co_authors = CO_AUTHOR.findall("Co-authored-by: " + parts[5].replace("|", "\nCo-authored-by: ")) if len(parts) > 5 and parts[5] else []
            rows.append({"sha": sha, "committed": committed, "authored": authored, "author": hashed(author),
                         "committer": hashed(committer), "co_authors": "|".join(hashed(c) for c in co_authors)})
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["sha", "committed", "authored", "author", "committer", "co_authors"]).to_parquet(commits_path, index=False)

    tags_out = git("for-each-ref", "refs/tags", f"--format=%(refname:short){SEP}%(objecttype){SEP}%(creatordate:unix){SEP}%(contents:signature){END}", cwd=clone)
    tags = []
    for record in tags_out.stdout.split(END):
        parts = record.strip().split(SEP)
        if len(parts) < 3 or not parts[2].isdigit() or int(parts[2]) > limit:
            continue
        tags.append({"created": int(parts[2]), "annotated": parts[1] == "tag", "signed": bool(len(parts) > 3 and parts[3].strip())})

    summary = {"project": project, "error": None, "commits_total": total, "authors_total": len(authors), "last_commit": newest,
               "last_commit_sha": newest_sha, "first_commit": oldest, "tags": tags}
    summary_path.write_text(json.dumps(summary))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    members = cohort(args.t0)
    members = members[~members.gone_now & members.canonical.notna()]
    CLONES.mkdir(parents=True, exist_ok=True)
    git_dir(args.t0).mkdir(parents=True, exist_ok=True)
    print(f"{len(members)} repositories", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process, m.project, m.canonical, args.t0) for m in members.itertuples()]
        for n, future in enumerate(futures, 1):
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - one failed repository must not stop the rest
                results.append({"project": members.iloc[n - 1].project, "error": str(exc)[:200]})
            if n % 100 == 0:
                print(f"  {n}/{len(members)}", flush=True)

    table = pd.DataFrame(results)
    table["tags"] = table.get("tags").map(json.dumps)
    table.to_parquet(PROCESSED / f"git_summary_{args.t0}.parquet", index=False)
    failed = table[table.error.notna()]
    print(f"done: {len(table)} repositories, {len(failed)} failed")
    print(failed.error.str.slice(0, 80).value_counts().head(5).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
