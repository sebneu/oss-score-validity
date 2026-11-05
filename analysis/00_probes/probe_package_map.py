#!/usr/bin/env python3
"""Map panel repositories to packages through deps.dev.

The API serves the current mapping, so this is today's view of which packages a repository
publishes. It is a join key for the outcomes, not a feature, and it is marked as current
state. `probe_depsdev_bq.py` checks it against `SnapshotAt` once BigQuery is available.

Repositories are looked up under their panel name and, once `probe_github.py meta` has run,
also under the name GitHub serves now. A rerun only does the lookups still missing. The API
caps the versions it lists per project, so a project at the cap can have missing packages.

This reverse lookup is noisy and is used only to estimate who publishes a package at all, the
denominator of O2. Most links are `UNVERIFIED_METADATA`: the package's own claim, which clones
copy (1,472 npm packages claim lodash/lodash). Every GitHub repository also resolves to a Go
module, Go code or not. `plausible` therefore requires an attestation, a package name that
matches the repository, or for Go a tagged, non-pseudo version. Which advisory belongs to which
project is decided in the other direction, in `count_events.py`.

Outputs:
  data/raw/depsdev/projects_<date>.jsonl          raw responses (resumable)
  data/processed/package_map.parquet              one row per project x package
  data/probes/package_map_summary.csv             share mapped per stratum

Usage:
    python analysis/00_probes/probe_package_map.py --t0 2024-08-01 --accessed 2026-11-03
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.deps.dev/v3"
COVERAGE = ROOT / "data" / "probes" / "crossd_coverage.parquet"
WORKERS = 8
VERSION_CAP = 1500
GO_RELEASE = re.compile(r"^v\d+\.\d+\.\d+$")


def normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def plausible(project: str, entry: dict) -> bool:
    if any("ATTESTATION" in p for p in entry["provenances"]):
        return True
    if entry["system"] == "GO":
        return entry["package"].lower() == f"github.com/{project.lower()}" and entry["tagged"]
    token = re.split(r"[/:]", entry["package"])[-1]
    return normal(token) == normal(project.split("/", 1)[1])


def get(session: requests.Session, url: str, tries: int = 5) -> tuple[int, dict | None]:
    for attempt in range(tries):
        try:
            resp = session.get(url, timeout=60)
        except requests.RequestException:
            time.sleep(2**attempt)
            continue
        if resp.status_code == 404:
            return 404, None
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2**attempt)
            continue
        resp.raise_for_status()
        return resp.status_code, resp.json()
    return 0, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--accessed", required=True, help="date of this crawl, YYYY-MM-DD")
    args = ap.parse_args()

    coverage = pd.read_parquet(COVERAGE, columns=["project", "snapshot_ts"])
    limit = pd.Timestamp("2024-08-11", tz="UTC").timestamp()
    names: dict[str, set[str]] = {
        p: {p.lower()} for p in coverage[coverage.snapshot_ts < limit].project.unique()
    }
    meta_path = ROOT / "data" / "processed" / f"github_meta_{args.t0}.parquet"
    if meta_path.exists():
        for row in pd.read_parquet(meta_path, columns=["project", "canonical"]).itertuples():
            if row.canonical and row.project in names:
                names[row.project].add(row.canonical.lower())
    else:
        print("no GitHub metadata yet: panel names only, rerun later for renamed repositories")

    cache = ROOT / "data" / "raw" / "depsdev" / f"projects_{args.accessed}.jsonl"
    cache.parent.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, str]] = set()
    if cache.exists():
        with cache.open() as fh:
            for line in fh:
                rec = json.loads(line)
                done.add((rec["project"], rec["queried"]))
    todo = [(p, n) for p, ns in names.items() for n in ns if (p, n) not in done]
    print(f"{len(names)} projects, {len(todo)} lookups to do", flush=True)

    session = requests.Session()

    def fetch(item: tuple[str, str]) -> dict:
        project, name = item
        key = quote(f"github.com/{name}", safe="")
        status, body = get(session, f"{API}/projects/{key}:packageversions")
        return {"project": project, "queried": name, "status": status,
                "versions": (body or {}).get("versions") or []}

    with cache.open("a") as out, ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, rec in enumerate(pool.map(fetch, todo), 1):
            out.write(json.dumps(rec) + "\n")
            if n % 500 == 0:
                out.flush()
                print(f"  {n}/{len(todo)}", flush=True)

    rows = []
    version_counts: dict[str, int] = {}
    with cache.open() as fh:
        for line in fh:
            rec = json.loads(line)
            version_counts[rec["project"]] = version_counts.get(rec["project"], 0) + len(
                rec["versions"]
            )
            seen: dict[tuple[str, str], dict] = {}
            for version in rec["versions"]:
                key = version["versionKey"]
                entry = seen.setdefault(
                    (key["system"], key["name"]),
                    {"project": rec["project"], "queried": rec["queried"], "system": key["system"],
                     "package": key["name"], "n_versions": 0, "relation_types": set(),
                     "provenances": set(), "tagged": False},
                )
                entry["n_versions"] += 1
                entry["tagged"] |= bool(GO_RELEASE.match(key["version"]))
                entry["relation_types"].add(version.get("relationType"))
                entry["provenances"].add(version.get("relationProvenance"))
            at_cap = len(rec["versions"]) >= VERSION_CAP
            for entry in seen.values():
                entry["at_cap"] = at_cap
                entry["plausible"] = plausible(rec["project"], entry)
                entry["relation_types"] = "|".join(sorted(x for x in entry["relation_types"] if x))
                entry["provenances"] = "|".join(sorted(x for x in entry["provenances"] if x))
                rows.append(entry)

    mapping = pd.DataFrame(rows).drop_duplicates(["project", "system", "package"])
    out_path = ROOT / "data" / "processed" / "package_map.parquet"
    mapping.to_parquet(out_path, index=False)

    strata = (
        pd.read_parquet(COVERAGE, columns=["project", "stratum"]).drop_duplicates("project")
    )
    panel = strata[strata.project.isin(names)].copy()
    panel["any_link"] = panel.project.isin(set(mapping.project))
    panel["publishes"] = panel.project.isin(set(mapping[mapping.plausible].project))
    panel["at_cap"] = panel.project.isin(set(mapping[mapping.at_cap].project))
    summary = panel.groupby("stratum")[["any_link", "publishes", "at_cap"]].sum()
    summary.loc["all"] = summary.sum()
    summary.insert(0, "projects", panel.groupby("stratum").size())
    summary.loc["all", "projects"] = len(panel)
    summary["share_publishes"] = (summary.publishes / summary.projects).round(3)
    summary.to_csv(ROOT / "data" / "probes" / "package_map_summary.csv")
    print(summary.to_string())
    print(mapping.system.value_counts().to_string())
    print(f"largest version count per project: {max(version_counts.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
