#!/usr/bin/env python3
"""Which Scorecard checks run against a pinned commit, and do they stay at that commit?

Runs each documented check with `--commit` on a few repositories at their last commit before t0,
and once at HEAD as a contrast. A check that errors at a commit cannot be backdated with the CLI.
A check that runs can still read current state (see the source notes in `BACKDATABLE`), which is why
the table in the paper is decided from both the run and the source, at the version we pinned.

Output: data/probes/scorecard_cli.csv

Usage:
    python analysis/03_instruments/probe_scorecard_cli.py --repos expressjs/express,pallets/flask,gin-gonic/gin
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "data" / "tools" / "scorecard"
OUT = ROOT / "data" / "probes" / "scorecard_cli.csv"

CHECKS = [
    "Binary-Artifacts", "Security-Policy", "License", "Dangerous-Workflow", "Token-Permissions",
    "Pinned-Dependencies", "Dependency-Update-Tool", "Packaging", "Code-Review", "Signed-Releases",
    "Vulnerabilities", "Fuzzing", "SBOM", "SAST", "CI-Tests", "Contributors", "Maintained",
    "Branch-Protection", "Webhooks", "CII-Best-Practices",
]


def token() -> str:
    value = os.environ.get("GITHUB_TOKEN", "").strip()
    if not value:
        raise SystemExit("no GitHub token: set GITHUB_TOKEN")
    return value


def commit_before(repo: str, t0: str) -> str:
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/commits",
        params={"until": f"{t0}T00:00:00Z", "per_page": 1},
        headers={"Authorization": f"bearer {token()}"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()[0]["sha"]


def run_check(repo: str, check: str, sha: str | None, timeout: int) -> dict:
    command = [str(BINARY), f"--repo=github.com/{repo}", f"--checks={check}", "--format=json"]
    if sha:
        command.append(f"--commit={sha}")
    env = {**os.environ, "GITHUB_AUTH_TOKEN": token()}
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"score": None, "reason": "timeout"}
    try:
        result = json.loads(proc.stdout)["checks"][0]
        return {"score": result["score"], "reason": result["reason"][:160]}
    except (ValueError, KeyError, IndexError):
        return {"score": None, "reason": (proc.stderr or proc.stdout).strip()[:160]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repos", required=True)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    rows = []
    for repo in args.repos.split(","):
        sha = commit_before(repo, args.t0)
        print(repo, sha[:12], flush=True)
        for check in CHECKS:
            pinned = run_check(repo, check, sha, args.timeout)
            head = run_check(repo, check, None, args.timeout)
            rows.append(
                {"repo": repo, "commit": sha, "check": check,
                 "score_at_commit": pinned["score"], "reason_at_commit": pinned["reason"],
                 "score_at_head": head["score"], "reason_at_head": head["reason"]}
            )
            print(f"  {check:24} commit {pinned['score']!s:>5}  head {head['score']!s:>5}  {pinned['reason'][:70]}", flush=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
