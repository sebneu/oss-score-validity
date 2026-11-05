#!/usr/bin/env python3
"""What the monitoring recorded around each illustrative incident (case panel).

The cases and the readings are fixed in DECISIONS.md. They are selected on the outcome,
so nothing here enters the validity statistics, and no other script reads this output for them.
Values are dated by `observed_ts`, the time they were read from GitHub.

Outputs:
  data/processed/cases/series.parquet     all readings of the case projects
  data/processed/cases/readings.csv       the four fixed readings per case

Usage:
    python analysis/05_cases/case_series.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import probe_crossd_coverage as cov  # noqa: E402

T0 = pd.Timestamp("2024-08-01", tz="UTC")
CASES = {
    "axios/axios": ("hijacked release channel", "2026-03-31"),
    "Lightning-AI/pytorch-lightning": ("hijacked release channel", "2026-04-30"),
    "ultralytics/ultralytics": ("hijacked release channel", "2024-12-05"),
    "facebook/react": ("exploited flaw", "2025-12-03"),
    "mongodb/mongo": ("exploited flaw", "2025-12-19"),
    "minio/minio": ("end of maintenance", "2025-12-03"),
}
OUT = ROOT / "data" / "processed" / "cases"


def number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def reading(project: str, ts: float, response: dict) -> dict:
    meta = cov.coverage_row(project, ts, response)
    bak, top = response.get("bak") or {}, response.get("metrics") or {}

    def field(name):
        return cov.unwrap(bak.get(name)) if bak.get(name) is not None else top.get(name)

    def sub(name, key):
        block = field(name)
        return number(block.get(key)) if isinstance(block, dict) else None

    return {
        "project": project,
        "snapshot": pd.Timestamp(ts, unit="s", tz="UTC"),
        "observed": pd.to_datetime(meta["observed_ts"], unit="s", utc=True) if meta.get("observed_ts") else pd.NaT,
        "version": top.get("version"),
        "block": meta.get("src_maturity_level"),
        "maturity_level": number(field("maturity_level")),
        "elephant_factor": number(field("elephant_factor")),
        "support_rate": number(field("support_rate")),
        "criticality_score": number(field("criticality_score")),
        "bus_factor": sub("contributions_distributions", "bus_factor_score"),
        "ratio_closed": sub("project_velocity", "ratio_closed_total"),
        "community_health": sub("github_community_health_percentage", "custom_health_score"),
        "first_response_days": sub("issues", "average_first_response_time_days"),
        "dependents_count": number(top.get("dependents_count")),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    keys = []
    for project in CASES:
        stamps = cov.post(session, "snapshots", {"term": project})
        keys += [(project, float(s)) for s in cov_stamps(stamps)]
    cache = cov.read_metric_cache()
    failed = cov.fetch_metrics(sorted(keys), cache, workers=4)
    if failed:
        print(f"{len(failed)} failed")
    series = pd.DataFrame([reading(p, t, cache[(p, t)]) for p, t in keys if cache.get((p, t))])
    series = series.sort_values(["project", "snapshot"])
    series.to_parquet(OUT / "series.parquet", index=False)

    rows = []
    for project, (mechanism, date) in CASES.items():
        event = pd.Timestamp(date, tz="UTC")
        part = series[(series.project == project) & series.observed.notna()].sort_values("observed")
        marks = {
            "t0": part[part.observed <= T0].tail(1),
            "26w_before": part[part.observed <= event - pd.Timedelta(weeks=26)].tail(1),
            "before": part[part.observed < event].tail(1),
            "4w_after": part[part.observed >= event + pd.Timedelta(weeks=4)].head(1),
        }
        for mark, rec in marks.items():
            rows.append({"mechanism": mechanism, "event": date, "mark": mark, **(rec.iloc[0].to_dict() if len(rec) else {"project": project})})
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "readings.csv", index=False)
    show = ["project", "mark", "observed", "block", "maturity_level", "elephant_factor", "support_rate", "criticality_score", "bus_factor", "ratio_closed", "community_health", "first_response_days", "dependents_count"]
    print(table[show].to_string(index=False, max_colwidth=30))
    return 0


def cov_stamps(response) -> list[float]:
    if isinstance(response, dict):
        response = response.get("snapshots") or response.get("timestamps") or next(iter(response.values()))
    out = []
    for item in response:
        out.append(item if isinstance(item, (int, float)) else item.get("timestamp"))
    return [s for s in out if s is not None]


if __name__ == "__main__":
    sys.exit(main())
