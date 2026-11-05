#!/usr/bin/env python3
"""Published values for the fidelity and freshness tests (RQ1c and RQ1d).

  - the current Scorecard result of each cohort repository from api.scorecard.dev: date, commit, checks;
  - the last published Criticality Score list from ossf/criticality_score, kept with its checksum.

These are present-day values. They are used only to test reconstructions and to measure how old published
results are, and they never enter a feature at t0. Resumable.

Outputs:
  data/raw/scorecard/published_<accessed>.jsonl
  data/raw/criticality/20250725_all.csv.gz

Usage:
    python analysis/03_instruments/collect_published.py --t0 2024-08-01 --accessed 2026-11-04
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

from base import RAW, cohort

LOCK = threading.Lock()
CRITICALITY = "https://raw.githubusercontent.com/ossf/criticality_score/main/data/20250725_all.csv.gz"


def fetch(session: requests.Session, canonical: str) -> dict:
    for attempt in range(4):
        try:
            resp = session.get(f"https://api.scorecard.dev/projects/github.com/{canonical}", timeout=60)
        except requests.RequestException as exc:
            error = str(exc)[:120]
            continue
        if resp.status_code == 404:
            return {"status": 404}
        if resp.status_code == 200:
            data = resp.json()
            return {"status": 200, "date": data.get("date"), "commit": (data.get("repo") or {}).get("commit"), "score": data.get("score"),
                    "version": (data.get("scorecard") or {}).get("version"),
                    "checks": {c["name"]: c["score"] for c in data.get("checks", [])}}
        error = f"http {resp.status_code}"
    return {"status": None, "error": error}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--accessed", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    target = RAW / "criticality" / "20250725_all.csv.gz"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(requests.get(CRITICALITY, timeout=600).content)
    print(target.name, target.stat().st_size, hashlib.sha256(target.read_bytes()).hexdigest(), flush=True)

    members = cohort(args.t0)
    members = members[~members.gone_now & members.canonical.notna()]
    out = RAW / "scorecard" / f"published_{args.accessed}.jsonl"
    done = {json.loads(line)["project"] for line in out.open()} if out.exists() else set()
    todo = members[~members.project.isin(done)]
    session = requests.Session()

    def task(m):
        result = fetch(session, m.canonical)
        with LOCK, out.open("a") as fh:
            fh.write(json.dumps({"project": m.project, "canonical": m.canonical, **result}) + "\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(task, todo.itertuples()))
    print(f"{len(todo)} fetched", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
