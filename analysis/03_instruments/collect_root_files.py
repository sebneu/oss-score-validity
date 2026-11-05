#!/usr/bin/env python3
"""Names of the files in the repository root at the last commit before t0.

Needed for the openCode rule on SECURITY.md. The commit comes from collect_git.py, so the tree is the one at t0.

Output: data/raw/github/root_files_<t0>.jsonl

Usage:
    python analysis/03_instruments/collect_root_files.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_probes"))

import probe_github  # noqa: E402

from base import PROCESSED, RAW, cohort  # noqa: E402

BATCH = 25


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    members = cohort(args.t0).set_index("project")
    summary = pd.read_parquet(PROCESSED / f"git_summary_{args.t0}.parquet")
    summary = summary[summary.last_commit_sha.notna()]
    cache = RAW / "github" / f"root_files_{args.t0}.jsonl"
    done = set()
    if cache.exists():
        with cache.open() as fh:
            done = {json.loads(line)["project"] for line in fh}
    todo = summary[~summary.project.isin(done)]
    print(f"{len(summary)} repositories, {len(todo)} to fetch", flush=True)
    client = probe_github.Client()
    with cache.open("a") as out:
        rows = list(todo.itertuples())
        for start in range(0, len(rows), BATCH):
            batch = rows[start : start + BATCH]
            body = []
            for i, r in enumerate(batch):
                owner, name = str(members.loc[r.project, "canonical"]).split("/", 1)
                body.append(
                    f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
                    f'{{ object(oid: "{r.last_commit_sha}") {{ ... on Commit {{ tree {{ entries {{ name }} }} }} }} }}'
                )
            data = client.query("query { rateLimit { remaining resetAt } " + " ".join(body) + " }").get("data") or {}
            for i, r in enumerate(batch):
                tree = ((data.get(f"r{i}") or {}).get("object") or {}).get("tree")
                entries = [e["name"] for e in tree["entries"]] if tree else None
                out.write(json.dumps({"project": r.project, "entries": entries}) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
