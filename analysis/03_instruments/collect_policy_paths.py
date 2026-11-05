#!/usr/bin/env python3
"""Where a security policy existed at t0.

The Scorecard check reads the repository at the pinned commit, and when it finds no policy there it reads the
`.github` repository of the owner as it is today. That second path carries current state into t0. This script records
the files in `.github`, `docs` and `doc` at the pinned commit, and whether the owner's `.github` repository had a policy
committed by t0, so that the adapter can drop a policy that appeared later. A file deleted again before t0 still counts,
and the owner's file is looked up under the usual spellings only.

Output: data/raw/github/policy_paths_<t0>.jsonl

Usage:
    python analysis/03_instruments/collect_policy_paths.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_probes"))

import probe_github  # noqa: E402

from base import PROCESSED, RAW, cohort, freeze  # noqa: E402

BATCH = 25
FOLDERS = {"github": ".github", "docs": "docs", "doc": "doc"}
ORG_PATHS = ["SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md", "security.md", "SECURITY.rst", "SECURITY.adoc", "SECURITY.markdown"]


def owner_policies(client, owners: list[str], limit: str) -> dict[str, bool]:
    found = {}
    for start in range(0, len(owners), BATCH):
        batch = owners[start : start + BATCH]
        body = []
        for i, owner in enumerate(batch):
            paths = " ".join(f'p{j}: history(first: 1, path: {json.dumps(path)}, until: "{limit}") {{ totalCount }}' for j, path in enumerate(ORG_PATHS))
            body.append(f'o{i}: repository(owner: {json.dumps(owner)}, name: ".github") {{ defaultBranchRef {{ target {{ ... on Commit {{ {paths} }} }} }} }}')
        data = client.query("query { rateLimit { remaining resetAt } " + " ".join(body) + " }").get("data") or {}
        for i, owner in enumerate(batch):
            target = (((data.get(f"o{i}") or {}).get("defaultBranchRef") or {}).get("target")) or {}
            found[owner] = any((target.get(f"p{j}") or {}).get("totalCount", 0) > 0 for j in range(len(ORG_PATHS)))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    limit = freeze(args.t0).strftime("%Y-%m-%dT%H:%M:%SZ")
    members = cohort(args.t0).set_index("project")
    summary = pd.read_parquet(PROCESSED / f"git_summary_{args.t0}.parquet")
    summary = summary[summary.last_commit_sha.notna()]
    cache = RAW / "github" / f"policy_paths_{args.t0}.jsonl"
    done = set()
    if cache.exists():
        with cache.open() as fh:
            done = {json.loads(line)["project"] for line in fh}
    rows = [r for r in summary.itertuples() if r.project not in done]
    print(f"{len(summary)} repositories, {len(rows)} to fetch", flush=True)
    client = probe_github.Client()
    owners = sorted({str(members.loc[r.project, "canonical"]).split("/", 1)[0] for r in rows})
    org = owner_policies(client, owners, limit)
    print(f"{len(owners)} owners, {sum(org.values())} with a policy in .github by t0", flush=True)
    with cache.open("a") as out:
        for start in range(0, len(rows), BATCH):
            batch = rows[start : start + BATCH]
            body = []
            for i, r in enumerate(batch):
                owner, name = str(members.loc[r.project, "canonical"]).split("/", 1)
                trees = " ".join(f'{alias}: object(expression: {json.dumps(r.last_commit_sha + ":" + folder)}) {{ ... on Tree {{ entries {{ name }} }} }}' for alias, folder in FOLDERS.items())
                body.append(f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {trees} }}")
            data = client.query("query { rateLimit { remaining resetAt } " + " ".join(body) + " }").get("data") or {}
            for i, r in enumerate(batch):
                repo = data.get(f"r{i}") or {}
                folders = {folder: [e["name"] for e in (repo.get(alias) or {}).get("entries", [])] for alias, folder in FOLDERS.items()}
                owner = str(members.loc[r.project, "canonical"]).split("/", 1)[0]
                out.write(json.dumps({"project": r.project, "answered": bool(repo), "folders": folders, "org_policy_by_t0": org[owner]}) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
