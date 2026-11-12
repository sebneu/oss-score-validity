#!/usr/bin/env python3
"""Commit dates of the commits a published Scorecard scan read.

A weekly scan carries the date it started and runs for several days, so a scan dated before t0 can read a commit made
after it. The commit date is a lower bound on when the project was scanned. Dates come from the commit-only clones and
never trigger a fetch (GIT_NO_LAZY_FETCH); a commit missing from today's default branch stays undated.

Output: data/processed/scorecard_published_<scan>_commits.parquet (project, commit, committed as Unix seconds)

Usage:
    python analysis/03_instruments/date_scanned_commits.py --scan 2024-07-29
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
CLONES = ROOT / "data" / "raw" / "git"


def committed(project: str, commit: str, env: dict) -> int | None:
    clone = CLONES / (project.replace("/", "__") + ".git")
    if not clone.exists() or not isinstance(commit, str):
        return None
    try:
        out = subprocess.run(["git", "--git-dir", str(clone), "log", "-1", "--format=%ct", commit],
                             capture_output=True, text=True, env=env, timeout=20)
    except subprocess.TimeoutExpired:
        return None
    value = out.stdout.strip()
    return int(value) if out.returncode == 0 and value.isdigit() else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", default="2024-07-29")
    args = ap.parse_args()
    scan = pd.read_parquet(PROCESSED / f"scorecard_published_{args.scan}.parquet")
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    out = scan[["project", "commit"]].assign(committed=[committed(p, c, env) for p, c in zip(scan.project, scan.commit)])
    out["committed"] = out.committed.astype("Int64")
    path = PROCESSED / f"scorecard_published_{args.scan}_commits.parquet"
    out.to_parquet(path, index=False)
    print(f"{path.relative_to(ROOT)}: {out.committed.notna().sum()} of {len(out)} commits dated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
