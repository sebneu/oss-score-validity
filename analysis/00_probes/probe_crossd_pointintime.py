#!/usr/bin/env python3
"""Check that a CrOSSD record holds nothing younger than its own observation time.

The paper treats the CrOSSD snapshots as values recorded at the time. Two tests:

  P1  `current_state_workflows[*].created_at` in the cached `/api/metrics` responses must
      not be later than the block's `timestamp`. Runs on the whole cache, without network.
  P2  In `/api/repo` at the snapshot, every date-valued field must be no later than the
      latest time the crawl can have run. A small seeded sample, because the responses are
      large. The bound is the metrics `timestamp`, which is written after the crawl.

A later date would mean a record was updated or recomputed after the fact, and the values
at t0 could then hold hindsight. A clean result does not rule out recomputation from data
that was all old enough, which has to come from the people who ran the platform.

Output: data/probes/crossd_pointintime.json

Usage:
    python analysis/00_probes/probe_crossd_pointintime.py --sample 40
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "raw" / "crossd" / "metrics.jsonl.gz"
OUT = ROOT / "data" / "probes" / "crossd_pointintime.json"
API = "https://health.crossd.tech/api"

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
# Tolerates clock differences between GitHub and the crawler, nothing more.
TOLERANCE_S = 300


def parse(value: str) -> float:
    parsed = datetime.fromisoformat(value[:19]).replace(tzinfo=UTC)
    return parsed.timestamp()


def dates_in(obj, path: str = ""):
    """Every date-valued field, as (normalised path, timestamp)."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from dates_in(value, f"{path}/{re.sub(r'^issue[0-9]+$', 'issueN', key)}")
    elif isinstance(obj, list):
        for value in obj:
            yield from dates_in(value, f"{path}[]")
    elif isinstance(obj, str) and ISO_DATE.match(obj):
        try:
            yield path, parse(obj)
        except ValueError:
            pass


def check_workflows() -> tuple[dict, list[tuple[str, float, float]]]:
    """P1, and the cached snapshots usable for P2."""
    checked = violations = 0
    worst = 0.0
    usable: list[tuple[str, float, float]] = []
    with gzip.open(CACHE, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            block = (rec["response"] or {}).get("metrics") or {}
            stamp = block.get("timestamp")
            if not stamp:
                continue
            usable.append((rec["project"], rec["snapshot_ts"], stamp))
            for run in (block.get("current_state_workflows") or {}).values():
                if not isinstance(run, dict) or not run.get("created_at"):
                    continue
                checked += 1
                excess = parse(run["created_at"]) - stamp
                if excess > TOLERANCE_S:
                    violations += 1
                    worst = max(worst, excess)
    result = {
        "workflow_runs_checked": checked,
        "later_than_block_timestamp": violations,
        "worst_excess_days": round(worst / 86400, 3),
    }
    return result, usable


def check_repo_payloads(usable: list, sample: int, seed: int) -> dict:
    """P2 on snapshots around the candidate freeze date."""
    lo = datetime(2024, 7, 1, tzinfo=UTC).timestamp()
    hi = datetime(2024, 8, 10, tzinfo=UTC).timestamp()
    pool = [u for u in usable if lo <= u[1] <= hi]
    chosen = random.Random(seed).sample(pool, min(sample, len(pool)))

    fields = violations = failures = 0
    by_path: Counter[str] = Counter()
    worst = 0.0
    for project, ts, stamp in chosen:
        try:
            resp = requests.post(
                f"{API}/repo", json={"term": project, "timestamp": ts}, timeout=180
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"  ! {project}: {exc}", file=sys.stderr)
            failures += 1
            continue
        for path, value in dates_in(payload):
            fields += 1
            excess = value - stamp
            if excess > TOLERANCE_S:
                violations += 1
                worst = max(worst, excess)
                by_path[path] += 1
    return {
        "snapshots_sampled": len(chosen),
        "fetch_failures": failures,
        "date_fields_checked": fields,
        "later_than_metrics_timestamp": violations,
        "worst_excess_days": round(worst / 86400, 3),
        "paths_with_later_dates": dict(by_path.most_common(15)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    workflows, usable = check_workflows()
    repo = check_repo_payloads(usable, args.sample, args.seed)
    result = {
        "generated": datetime.now(UTC).isoformat(),
        "P1_workflow_runs": workflows,
        "P2_repo_payload": repo,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
