#!/usr/bin/env python3
"""Scorecard checks at each project's last commit before t0.

Runs the pinned CLI with `--commit` on the checks that run at a commit and read the content of that commit
(see probe_scorecard_cli.py). `Vulnerabilities` also runs, but asks OSV today, so it would carry later advisories
into t0 and stays out. `Code-Review` and `CI-Tests` run here too, and the fidelity step decides how they are reported,
because they read pull request data through the API. Resumable, one JSON line per project.

License and CI-Tests turned out to read today or to find nothing on old commits (docs/decision_log_full.md, 2026-11-04). They ran on the
first 490 projects, which is the evidence for that, and later runs skip them, since CI-Tests uses most of the API budget.

Output: data/raw/scorecard/t0_<t0>.jsonl

Usage:
    python analysis/03_instruments/collect_scorecard.py --t0 2024-08-01 --workers 4
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from base import PROCESSED, RAW, ROOT, cohort
from probe_scorecard_cli import BINARY, token

CHECKS = ["Binary-Artifacts", "Security-Policy", "License", "Dangerous-Workflow", "Token-Permissions",
          "Pinned-Dependencies", "Code-Review", "CI-Tests"]
T0_CHECKS = [c for c in CHECKS if c not in ("License", "CI-Tests")]
LOCK = threading.Lock()


def run(canonical: str, sha: str, timeout: int, checks: list[str] = CHECKS) -> dict:
    # A few repositories hold paths that differ only by case, so a retry can point TMPDIR at a case-sensitive volume.
    tmpdir = {"TMPDIR": os.environ["TMPDIR"]} if os.environ.get("SCORECARD_USE_TMPDIR") else {}
    command = [str(BINARY), f"--repo=github.com/{canonical}", f"--checks={','.join(checks)}", "--format=json", f"--commit={sha}"]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout,
                              env={"GITHUB_AUTH_TOKEN": token(), "PATH": "/usr/bin:/bin:/opt/homebrew/bin", "HOME": str(ROOT / "data" / "tools"), **tmpdir})
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {"error": (proc.stderr or proc.stdout).strip()[-300:]}
    return {"error": None, "commit_seen": (data.get("repo") or {}).get("commit"),
            "checks": {c["name"]: {"score": c["score"], "reason": c["reason"][:160]} for c in data.get("checks", [])}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--retry-errors", action="store_true", help="run projects again whose last result is an error; the adapter keeps the last line")
    args = ap.parse_args()
    members = cohort(args.t0).set_index("project")
    summary = pd.read_parquet(PROCESSED / f"git_summary_{args.t0}.parquet")
    summary = summary[summary.last_commit_sha.notna()]
    out = RAW / "scorecard" / f"t0_{args.t0}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if out.exists():
        with out.open() as fh:
            for line in fh:
                rec = json.loads(line)
                done[rec["project"]] = rec.get("error")
    if args.retry_errors:
        done = {project: error for project, error in done.items() if not error}
    todo = summary[~summary.project.isin(list(done))]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"{len(summary)} repositories, {len(todo)} to run", flush=True)

    def task(r):
        result = run(str(members.loc[r.project, "canonical"]), r.last_commit_sha, args.timeout, T0_CHECKS)
        with LOCK, out.open("a") as fh:
            fh.write(json.dumps({"project": r.project, "sha": r.last_commit_sha, **result}) + "\n")
        return result.get("error")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, error in enumerate(pool.map(task, todo.itertuples()), 1):
            if n % 100 == 0 or (args.limit and n <= args.limit):
                print(f"  {n}/{len(todo)}{' error: ' + str(error)[:90] if error else ''}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
