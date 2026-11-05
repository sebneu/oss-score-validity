#!/usr/bin/env python3
"""Probe which CrOSSD snapshots and metrics exist per project and date.

The question: at which freeze date t0 does the panel have values, and which metrics do those
values contain?

Fetches, with a local cache so a rerun needs no network:
  - the project list and every project's snapshot timestamps;
  - `/api/metrics` for all projects in the `--window` date ranges;
  - `/api/metrics` for the full series of a seeded project sample (`--series-sample`),
    to see how metric availability changes over time.

A metric can sit in one of two blocks of the `/api/metrics` response. `metrics` is the
top level; `bak` is a second block holding the core metrics for snapshots before mid-2025,
with values keyed by repository id and its own `timestamp`. The `bak` block comes from a
separate worker (`bak-rest-drone` in FH-CrOSSD/crossd) that crawls GitHub when its task
runs and only then writes `timestamp`, so a value can be days or weeks younger than its
snapshot. The snapshot date therefore does not date the value; `observed_ts` does, and it
is what the point-in-time rule has to compare with t0.

The stratum of each project comes from the two lists the weekly crawl jobs were defined
over (`most-starred-09-04-2024`, `random-sample-09-04-2024`) in FH-CrOSSD/crossd.

Outputs:
  data/raw/crossd/index_<YYYYMMDD>.json      project list and snapshot timestamps
  data/raw/crossd/metrics.jsonl.gz           raw metric responses (append-only cache)
  data/raw/crossd/strata/*.yaml              the crawl lists, pinned to a commit
  data/probes/crossd_coverage.parquet        one row per project x snapshot
  data/probes/crossd_t0_candidates.csv       counts per candidate t0 and stratum
  data/probes/crossd_t0_daily.csv            eligible projects per day, for choosing t0

Usage:
    python analysis/00_probes/probe_crossd_coverage.py
    python analysis/00_probes/probe_crossd_coverage.py --refresh-index
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "crossd"
PROBES = ROOT / "data" / "probes"
METRICS_CACHE = RAW / "metrics.jsonl.gz"

API = os.environ.get("CROSSD_API", "https://health.crossd.tech/api")

# Metrics the instruments use or the baselines need.
METRICS = (
    "criticality_score",
    "maturity_level",
    "elephant_factor",
    "support_rate",
    "size_of_community",
    "project_velocity",
    "pull_requests",
    "issues",
    "technical_fork",
    "contributions_distributions",
    "churn",
    "github_community_health_percentage",
    "has_contributing_policy",
    "has_security_policy",
    "code_dependency",
    "dependents_count",
    "osi_approved_license",
)

# All windows are closed intervals of UTC dates.
DEFAULT_WINDOWS = ("2024-07-01:2024-08-10", "2024-12-15:2025-01-01")
DEFAULT_T0 = (
    "2024-05-01",
    "2024-06-01",
    "2024-07-01",
    "2024-08-01",
    "2024-08-05",
    "2024-08-09",
    "2024-08-10",
    "2025-01-01",
)
ELIGIBILITY_DAYS = 14  # a snapshot within 14 days before t0

CROSSD_COMMIT = "604a0c664f9998d4945aa9f4fe221888d8768675"
STRATA = {
    "most_starred": "cronjobs/most-starred-repos.yaml",
    "random_sample": "cronjobs/random-sample-repos.yaml",
    "netidee": "cronjobs/netidee_configmap.yaml",
}


def utc_ts(date: str) -> float:
    return datetime.fromisoformat(date).replace(tzinfo=UTC).timestamp()


def post(session: requests.Session, endpoint: str, payload: dict, tries: int = 5):
    for attempt in range(tries):
        try:
            resp = session.post(f"{API}/{endpoint}", json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def load_index(refresh: bool, workers: int) -> tuple[Path, dict[str, list[float]]]:
    """Project list and snapshot timestamps, from the newest cached index if there is one."""
    RAW.mkdir(parents=True, exist_ok=True)
    cached = sorted(RAW.glob("index_*.json"))
    if cached and not refresh:
        return cached[-1], json.loads(cached[-1].read_text())["snapshots"]

    session = requests.Session()
    projects = post(session, "projects", {})

    def fetch(project: str):
        return project, post(session, "snapshots", {"term": project})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        snapshots = dict(pool.map(fetch, projects))

    path = RAW / f"index_{datetime.now(UTC):%Y%m%d}.json"
    path.write_text(
        json.dumps({"fetched": datetime.now(UTC).isoformat(), "api": API, "snapshots": snapshots})
    )
    return path, snapshots


def load_strata() -> dict[str, str]:
    """Project -> stratum, case-insensitive, from the crawl lists at the pinned commit."""
    folder = RAW / "strata"
    folder.mkdir(parents=True, exist_ok=True)
    strata: dict[str, str] = {}
    for stratum, repo_path in STRATA.items():
        path = folder / Path(repo_path).name
        if not path.exists():
            url = f"https://raw.githubusercontent.com/FH-CrOSSD/crossd/{CROSSD_COMMIT}/{repo_path}"
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if re.fullmatch(r"[\w.-]+/[\w.-]+", entry) and not entry.startswith("apps/"):
                strata.setdefault(entry.lower(), stratum)
    return strata


def read_metric_cache() -> dict[tuple[str, float], dict]:
    cache: dict[tuple[str, float], dict] = {}
    if METRICS_CACHE.exists():
        with gzip.open(METRICS_CACHE, "rt") as fh:
            for line in fh:
                rec = json.loads(line)
                cache[(rec["project"], rec["snapshot_ts"])] = rec["response"]
    return cache


def fetch_metrics(keys: list[tuple[str, float]], cache: dict, workers: int) -> list[tuple]:
    """Fetch what the cache lacks. Returns the keys that failed; those stay out of the cache."""
    missing = [k for k in keys if k not in cache]
    print(f"metrics: {len(keys)} wanted, {len(missing)} to fetch")
    session = requests.Session()
    failed: list[tuple] = []

    def fetch(key: tuple[str, float]):
        project, ts = key
        return key, post(session, "metrics", {"term": project, "timestamp": ts})

    started = time.time()
    batch: list[str] = []

    def flush() -> None:
        # Each flush is one gzip member; concatenated members read back as one stream.
        with gzip.open(METRICS_CACHE, "at") as out:
            out.writelines(batch)
        batch.clear()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, k): k for k in missing}
        for n, future in enumerate(as_completed(futures), 1):
            key = futures[future]
            try:
                _, response = future.result()
            except Exception as exc:  # noqa: BLE001 - a failed fetch is recorded, not fatal
                print(f"  ! {key}: {exc}", file=sys.stderr)
                failed.append(key)
                continue
            cache[key] = response
            batch.append(
                json.dumps({"project": key[0], "snapshot_ts": key[1], "response": response}) + "\n"
            )
            if len(batch) >= 500:
                flush()
            if n % 2000 == 0:
                print(f"  {n}/{len(missing)} in {time.time() - started:.0f}s", flush=True)
    if batch:
        flush()
    return failed


def unwrap(value):
    """`bak` values are wrapped as {repo_id: value}."""
    if isinstance(value, dict) and len(value) == 1:
        key, inner = next(iter(value.items()))
        if key.isdigit():
            return inner
    return value


def present(value) -> bool:
    return value is not None and value != {} and value != []


def coverage_row(project: str, ts: float, response: dict | None) -> dict:
    row: dict = {"project": project, "snapshot_ts": ts, "fetched": response is not None}
    if response is None:
        return row
    top = response.get("metrics") or {}
    bak = response.get("bak") or {}
    row["metrics_ts"] = top.get("timestamp")
    row["bak_ts"] = bak.get("timestamp")
    row["metrics_scan_id"] = top.get("scan_id")
    row["bak_scan_id"] = bak.get("scan_id")
    row["metrics_version"] = top.get("version")
    for name in METRICS:
        in_top = present(top.get(name))
        in_bak = present(unwrap(bak.get(name)))
        row[f"src_{name}"] = "metrics" if in_top else "bak" if in_bak else None
    # When the core metrics were actually read from GitHub. `maturity_level` stands for the
    # block they live in: it is almost always present, while `criticality_score` is missing
    # for about a seventh of the panel and must not decide eligibility.
    source = row["src_maturity_level"]
    row["observed_ts"] = row["bak_ts"] if source == "bak" else row["metrics_ts"] if source else None
    return row


def eligible_at(coverage: pd.DataFrame, t0: str, by_observation: bool) -> pd.DataFrame:
    """Each project's latest usable snapshot in the eligibility window before t0.

    With `by_observation` the window applies to `observed_ts`, otherwise to the snapshot
    date, which is the rule as first drafted and admits values read after t0.
    """
    end = utc_ts(t0)
    start = end - ELIGIBILITY_DAYS * 86400
    col = "observed_ts" if by_observation else "snapshot_ts"
    window = coverage[(coverage[col] <= end) & (coverage[col] > start)]
    return window.sort_values(col).groupby("project").tail(1)


def t0_table(coverage: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    """Counts per t0 and stratum under both eligibility rules."""
    rows = []
    for t0 in candidates:
        by_snapshot = eligible_at(coverage, t0, by_observation=False)
        by_observed = eligible_at(coverage, t0, by_observation=True)
        for stratum in ["all", *sorted(coverage.stratum.unique())]:
            snap = by_snapshot if stratum == "all" else by_snapshot[by_snapshot.stratum == stratum]
            obs = by_observed if stratum == "all" else by_observed[by_observed.stratum == stratum]
            leaked = snap[snap.observed_ts > utc_ts(t0)]
            age = (utc_ts(t0) - obs.observed_ts) / 86400
            row = {
                "t0": t0,
                "stratum": stratum,
                "snapshot_in_window": len(snap),
                "of_which_observed_after_t0": len(leaked),
                "observed_in_window": len(obs),
                "median_age_days": round(float(age.median()), 2) if len(obs) else None,
                "max_age_days": round(float(age.max()), 2) if len(obs) else None,
            }
            for name in METRICS:
                row[f"n_{name}"] = int(obs[f"src_{name}"].notna().sum())
            rows.append(row)
    return pd.DataFrame(rows)


def daily_table(coverage: pd.DataFrame, first: str, last: str) -> pd.DataFrame:
    """Observed-in-window counts per day. Only meaningful for fetched windows."""
    rows = []
    for day in pd.date_range(first, last, freq="D"):
        obs = eligible_at(coverage, day.strftime("%Y-%m-%d"), by_observation=True)
        counts = obs.stratum.value_counts()
        rows.append(
            {"t0": day.date(), "all": len(obs), **{s: int(counts.get(s, 0)) for s in STRATA}}
        )
    return pd.DataFrame(rows)


def provenance_row(path: Path, what: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rel = path.relative_to(ROOT / "data")
    return (
        f"| `{rel}` | {what} | CrOSSD API `{API}` | {datetime.now(UTC):%Y-%m-%d} "
        f"| `{digest}` | see CrOSSD terms |"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", action="append", help="START:END, repeatable")
    ap.add_argument("--t0", action="append", help="candidate freeze date, repeatable")
    ap.add_argument("--series-sample", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh-index", action="store_true")
    args = ap.parse_args()

    index_path, snapshots = load_index(args.refresh_index, args.workers)
    empty = sorted(p for p, s in snapshots.items() if not s)
    print(f"{index_path.name}: {len(snapshots)} projects, {len(empty)} without any snapshot")

    keys: set[tuple[str, float]] = set()
    for window in args.window or DEFAULT_WINDOWS:
        start, end = window.split(":")
        lo, hi = utc_ts(start), utc_ts(end) + 86400
        keys |= {(p, t) for p, s in snapshots.items() for t in s if lo <= t < hi}

    with_snaps = sorted(p for p, s in snapshots.items() if s)
    sample = random.Random(args.seed).sample(with_snaps, args.series_sample)
    keys |= {(p, t) for p in sample for t in snapshots[p]}

    cache = read_metric_cache()
    failed = fetch_metrics(sorted(keys), cache, args.workers)
    if failed:
        print(f"{len(failed)} metric fetches failed; rerun to retry them", file=sys.stderr)

    rows = [
        coverage_row(p, t, cache.get((p, t))) for p, s in snapshots.items() for t in s
    ]
    coverage = pd.DataFrame(rows)
    coverage["snapshot_utc"] = pd.to_datetime(coverage.snapshot_ts, unit="s", utc=True)
    coverage["in_series_sample"] = coverage.project.isin(sample)
    strata = load_strata()
    coverage["stratum"] = coverage.project.str.lower().map(strata).fillna("added_later")

    PROBES.mkdir(parents=True, exist_ok=True)
    out = PROBES / "crossd_coverage.parquet"
    coverage.to_parquet(out, index=False)

    table = t0_table(coverage, args.t0 or list(DEFAULT_T0))
    table.to_csv(PROBES / "crossd_t0_candidates.csv", index=False)
    daily = daily_table(coverage, "2024-07-08", "2024-09-10")
    daily.to_csv(PROBES / "crossd_t0_daily.csv", index=False)
    print(table[table.stratum == "all"].iloc[:, :7].to_string(index=False))
    print(f"\nstrata (projects): {coverage.groupby('stratum').project.nunique().to_dict()}")
    print(f"listed but not in the panel: {len(set(strata) - set(coverage.project.str.lower()))}")
    best = daily.sort_values(["all", "t0"], ascending=False).iloc[0]
    print(f"highest observed-in-window count: {best['all']} at {best['t0']}")

    print("\nprovenance rows for data/README.md:")
    print(provenance_row(index_path, "project list and snapshot timestamps"))
    print(provenance_row(METRICS_CACHE, "raw `/api/metrics` responses (append-only cache)"))
    print(provenance_row(out, "snapshots and metric availability per project"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
