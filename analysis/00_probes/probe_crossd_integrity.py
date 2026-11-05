#!/usr/bin/env python3
"""Evidence on how CrOSSD values came about, where the operators cannot be asked (2026-11-04).

Tests whether stored values were read at the time and whether gaps are selective. It reads
availability and timestamps, plus one raw count, and it joins nothing to any outcome.

  R1  Delay bound. A recomputation writes a new `bak.timestamp` (`bak-rest-drone`, worker.py), so
      values recomputed later would show long delays.
  R2  Time variation. A batch recomputation from one state would leave a project's values constant
      across snapshots. Counts how often a cumulative-looking value changes between neighbours.
  R3  External check of a dated count. `/api/repo` stores the number of merged pull requests at the
      snapshot. GitHub search counts today how many were merged by that time and by the end of the
      window. A value read at the time matches the first; a later read drifts to the second.
  S1  Random list: stars, age and forks of the list, to infer its filter. Current state, used only
      to describe the frame, never as a feature.
  S2  Gaps by size: missing `bus_factor_score` and `criticality_score` per stars quartile at t0 and
      per issue volume.
  S3  Stall: how the last snapshots of the random stratum are spread in time.

Output: data/probes/crossd_integrity.json

Usage:
    python analysis/00_probes/probe_crossd_integrity.py --t0 2024-08-01 --sample 150
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import probe_github  # noqa: E402

API = "https://health.crossd.tech/api"
PROBES = ROOT / "data" / "probes"
PROCESSED = ROOT / "data" / "processed"


def iter_cache():
    with gzip.open(ROOT / "data" / "raw" / "crossd" / "metrics.jsonl.gz", "rt") as fh:
        for line in fh:
            yield json.loads(line)


def unwrap(value):
    if isinstance(value, dict) and len(value) == 1 and next(iter(value)).isdigit():
        return next(iter(value.values()))
    return value


def delay_bound() -> dict:
    delays = []
    series: dict[str, list[tuple[float, int]]] = {}
    for rec in iter_cache():
        bak = (rec["response"] or {}).get("bak") or {}
        if not bak.get("timestamp"):
            continue
        delays.append((bak["timestamp"] - rec["snapshot_ts"]) / 86400)
        forks = unwrap(bak.get("technical_fork")) or {}
        if forks.get("total_forks") is not None:
            series.setdefault(rec["project"], []).append((rec["snapshot_ts"], forks["total_forks"]))
    s = pd.Series(delays)
    changed = same = increased = 0
    for values in series.values():
        ordered = [v for _, v in sorted(values)]
        for a, b in zip(ordered, ordered[1:]):
            if a == b:
                same += 1
            else:
                changed += 1
                increased += b > a
    return {
        "R1": {
            "bak_records": len(s),
            "median_days": round(float(s.median()), 2),
            "p99_days": round(float(s.quantile(0.99)), 2),
            "max_days": round(float(s.max()), 2),
            "over_60_days": int((s > 60).sum()),
            "negative": int((s < 0).sum()),
        },
        "R2": {
            "projects": sum(len(v) > 1 for v in series.values()),
            "neighbour_pairs_changed": changed,
            "neighbour_pairs_same": same,
            "share_changed": round(changed / max(changed + same, 1), 3),
            "share_of_changes_upward": round(increased / max(changed, 1), 3),
        },
    }


def external_count(t0: str, sample: int, seed: int) -> dict:
    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{t0}.csv")
    cohort = cohort[~cohort.gone_now & cohort.canonical.notna()]
    chosen = cohort.sample(min(sample, len(cohort)), random_state=seed)
    client = probe_github.Client()
    t1 = probe_github.add_months(datetime.fromisoformat(t0).replace(tzinfo=UTC), 24)
    rows = []
    for row in chosen.itertuples():
        try:
            resp = requests.post(
                f"{API}/repo", json={"term": row.project, "timestamp": row.snapshot_ts}, timeout=180
            )
            resp.raise_for_status()
            record = resp.json()["repository"]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            continue
        recorded = ((record.get("repository") or {}).get("pullRequests") or {}).get("totalCount")
        read_at = record.get("timestamp")
        if recorded is None or not read_at:
            continue
        at = datetime.fromtimestamp(read_at, UTC)
        query = f"repo:{row.canonical} is:pr is:merged merged:<="
        text = f"""query {{ rateLimit {{ remaining resetAt }}
          then: search(query: {json.dumps(query + probe_github.iso(at))}, type: ISSUE, first: 1) {{ issueCount }}
          late: search(query: {json.dumps(query + probe_github.iso(t1))}, type: ISSUE, first: 1) {{ issueCount }} }}"""
        data = client.query(text).get("data") or {}
        if not data.get("then") or not data.get("late"):
            continue
        rows.append(
            {"project": row.project, "recorded": recorded, "then": data["then"]["issueCount"],
             "late": data["late"]["issueCount"]}
        )
    table = pd.DataFrame(rows)
    table["then_vs_recorded"] = table.recorded - table.then
    grew = table[table.late > table.then * 1.02].copy()
    grew["to_then"] = (grew.recorded - grew.then).abs() / grew.then.clip(lower=1)
    grew["to_late"] = (grew.recorded - grew.late).abs() / grew.late.clip(lower=1)
    table.to_csv(PROBES / "crossd_integrity_prs.csv", index=False)
    return {
        "projects": len(table),
        "exact_match": int((table.recorded == table.then).sum()),
        "within_1pct_of_then": int(((table.recorded - table.then).abs() <= table.then.clip(lower=1) * 0.01).sum()),
        "recorded_above_then": int((table.recorded > table.then * 1.01).sum()),
        "projects_that_grew_by_over_2pct": len(grew),
        "of_those_closer_to_then": int((grew.to_then < grew.to_late).sum()),
        "median_error_to_then": round(float(grew.to_then.median()), 4) if len(grew) else None,
        "median_error_to_late": round(float(grew.to_late.median()), 4) if len(grew) else None,
    }


def random_list_profile(t0: str) -> dict:
    coverage = pd.read_parquet(PROBES / "crossd_coverage.parquet", columns=["project", "stratum"])
    frame = coverage.drop_duplicates("project")
    names = sorted(frame[frame.stratum.isin(["random_sample", "most_starred"])].project)
    client = probe_github.Client()
    rows = []
    for start in range(0, len(names), 50):
        batch = names[start : start + 50]
        body = " ".join(
            f"r{i}: repository(owner: {json.dumps(p.split('/', 1)[0])}, name: {json.dumps(p.split('/', 1)[1])}) "
            "{ stargazerCount forkCount createdAt isFork isTemplate primaryLanguage { name } }"
            for i, p in enumerate(batch)
        )
        data = client.query(f"query {{ rateLimit {{ remaining resetAt }} {body} }}").get("data") or {}
        for i, project in enumerate(batch):
            if data.get(f"r{i}"):
                rows.append({"project": project, **data[f"r{i}"]})
    table = pd.DataFrame(rows).merge(frame, on="project")
    table["created"] = pd.to_datetime(table.createdAt, utc=True)
    table.drop(columns=["primaryLanguage"]).to_parquet(PROBES / "crossd_list_profile.parquet", index=False)
    out = {}
    for stratum, part in table.groupby("stratum"):
        q = part.stargazerCount.quantile([0, 0.05, 0.25, 0.5, 0.75, 0.95])
        out[stratum] = {
            "projects": len(part),
            "stars_today_quantiles": {str(k): int(v) for k, v in q.items()},
            "under_10_stars": int((part.stargazerCount < 10).sum()),
            "forks": int(part.isFork.sum()),
            "created_first": part.created.min().date().isoformat(),
            "created_last": part.created.max().date().isoformat(),
            "created_after_list_date": int((part.created > "2024-04-09").sum()),
            "created_by_year": part.created.dt.year.value_counts().sort_index().to_dict(),
        }
    return out


def gaps_by_size(t0: str) -> dict:
    coverage = pd.read_parquet(PROBES / "crossd_coverage.parquet")
    end = pd.Timestamp(t0, tz="UTC").timestamp()
    seen = coverage[(coverage.observed_ts <= end) & (coverage.observed_ts > end - 14 * 86400)]
    latest = seen.sort_values("observed_ts").groupby("project").tail(1)
    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{t0}.csv", usecols=["project"])
    latest = latest.merge(cohort, on="project")
    stars = pd.read_parquet(ROOT / "data" / "raw" / "depsdev" / "projects_2024-07-29.parquet")
    stars["key"] = stars.Name.str.lower()
    latest["key"] = latest.project.str.lower()
    latest = latest.merge(stars[["key", "StarsCount"]], on="key", how="left")
    meta = pd.read_parquet(
        PROCESSED / f"github_meta_{t0}.parquet", columns=["project", "commits_before_180d", "hasIssuesEnabled"]
    )
    latest = latest.merge(meta, on="project", how="left")
    issues = pd.read_parquet(PROCESSED / f"github_issues_{t0}.parquet", columns=["project", "issue_count"])
    latest = latest.merge(issues, on="project", how="left")
    latest["no_bus"] = latest.src_contributions_distributions.isna()
    latest["no_crit"] = latest.src_criticality_score.isna()

    def share(by) -> dict:
        grouped = latest.groupby(by, observed=True)[["no_bus", "no_crit"]].mean().round(3)
        grouped["n"] = latest.groupby(by, observed=True).size()
        return {str(k): v for k, v in grouped.to_dict("index").items()}

    latest["stars_q"] = pd.qcut(latest.StarsCount, 4, labels=["q1", "q2", "q3", "q4"])
    latest["commits_q"] = pd.qcut(latest.commits_before_180d.fillna(0), 4, labels=["q1", "q2", "q3", "q4"], duplicates="drop")
    latest["issues_bin"] = pd.cut(latest.issue_count.fillna(-1), [-2, -1, 0, 9, 99, 1e9], labels=["no data", "0", "1-9", "10-99", "100+"])
    return {
        "by_stars_quartile_at_t0": share("stars_q"),
        "by_commits_quartile_before_t0": share("commits_q"),
        "by_issues_in_window": share("issues_bin"),
        "by_stratum": share("stratum"),
        "by_issues_enabled": share(latest.hasIssuesEnabled.astype(str)),
    }


def stall(t0: str) -> dict:
    coverage = pd.read_parquet(PROBES / "crossd_coverage.parquet", columns=["project", "stratum", "snapshot_utc"])
    last = coverage[coverage.stratum == "random_sample"].groupby("project").snapshot_utc.max().dt.date.astype(str)
    counts = last.value_counts()
    return {"random_projects": len(last), "last_snapshot_top": counts.head(6).to_dict(),
            "continued_after_2024_08_09": int((last > "2024-08-09").sum())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--sample", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    random.seed(args.seed)
    result = {"generated": datetime.now(UTC).isoformat()}
    result |= delay_bound()
    result["R3"] = external_count(args.t0, args.sample, args.seed)
    result["S1"] = random_list_profile(args.t0)
    result["S2"] = gaps_by_size(args.t0)
    result["S3"] = stall(args.t0)
    out = PROBES / "crossd_integrity.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
