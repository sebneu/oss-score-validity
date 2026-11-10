#!/usr/bin/env python3
"""Inputs of the robustness run that are reused from the first freeze date, to save further BigQuery scans.

GH Archive events after August 2026 also lie after the second window, and the stored Criticality lists hold the dates
before 2025-01-01. Both are copied under the second date; what this leaves out is logged in docs/decision_log_full.md.

Usage:
    python analysis/04_validity/prepare_second_date.py --t0 2025-01-01
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2025-01-01")
    args = ap.parse_args()
    shutil.copy(RAW / "gharchive" / "gone_events_2024-08-01.parquet", RAW / "gharchive" / f"gone_events_{args.t0}.parquet")
    shutil.copy(RAW / "criticality" / "history_cohort_2024-08-01.parquet", RAW / "criticality" / f"history_cohort_{args.t0}.parquet")


if __name__ == "__main__":
    main()
