#!/usr/bin/env python3
"""Regenerate every table and figure of the paper.

`--reproduce` runs the analysis from the derived data in this repository, offline. The stages rebuild those
data from the sources: they need the raw downloads or the network, a GitHub token and BigQuery access.
Each stage calls the scripts of one `analysis/` subdirectory in order, and reruns from local caches where it can.

Usage:
    python analysis/run_all.py --reproduce      # tables and figures from the derived data
    python analysis/run_all.py [--from STAGE]   # rebuild from the sources, from a stage, e.g. --from 02
    python analysis/run_all.py --list
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBES = "analysis/00_probes"

# (stage id, description, scripts with arguments, relative to the repository root).
STAGES: list[tuple[str, str, list[str]]] = [
    (
        "00",
        "probes: what CrOSSD and the outcome sources can supply",
        [
            f"{PROBES}/probe_crossd_coverage.py",
            f"{PROBES}/probe_crossd_pointintime.py --sample 40",
            f"{PROBES}/fig_crossd_coverage.py",
            f"{PROBES}/collect_claims.py",
            f"{PROBES}/probe_osv.py --freeze-date 2026-11-03",
            f"{PROBES}/probe_github.py meta --t0 2024-08-01",
            f"{PROBES}/probe_github.py gone --t0 2024-08-01",
            f"{PROBES}/probe_github.py issues --t0 2024-08-01",
            f"{PROBES}/probe_depsdev_bq.py --t0 2024-08-01",
            f"{PROBES}/probe_package_map.py --t0 2024-08-01 --accessed 2026-11-03",
            f"{PROBES}/count_events.py --t0 2024-08-01",
            f"{PROBES}/probe_github.py fixtags --t0 2024-08-01",
            f"{PROBES}/count_events.py --t0 2024-08-01",
        ],
    ),
    (
        "01",
        "the frozen cohort",
        ["analysis/01_cohort/build_cohort.py --t0 2024-08-01"],
    ),
    (
        "02",
        "outcome labels under the frozen definitions",
        [
            "analysis/02_outcomes/label_outcomes.py --t0 2024-08-01",
            "analysis/02_outcomes/dependents_at_t0.py --t0 2024-08-01",
            "analysis/02_outcomes/date_gone.py --t0 2024-08-01",
            "analysis/00_probes/probe_github.py demand --t0 2024-08-01",
            "analysis/02_outcomes/dependents_i1b.py --t0 2024-08-01",
            "analysis/02_outcomes/label_outcomes.py --t0 2024-08-01",
            f"{PROBES}/probe_crossd_integrity.py --t0 2024-08-01 --sample 150",
        ],
    ),
    (
        "03",
        "instrument values at the freeze date",
        [
            "analysis/03_instruments/crossd_adapter.py --t0 2024-08-01",
            "analysis/03_instruments/collect_git.py --t0 2024-08-01",
            "analysis/03_instruments/collect_github_t0.py --t0 2024-08-01",
            "analysis/03_instruments/collect_root_files.py --t0 2024-08-01",
            "analysis/03_instruments/collect_stars_gharchive.py --t0 2024-08-01",
            "analysis/03_instruments/collect_criticality_history.py --t0 2024-08-01",
            "analysis/03_instruments/rule_adapters.py --t0 2024-08-01",
            "analysis/03_instruments/criticality_published.py --t0 2024-08-01",
            "analysis/03_instruments/rebuild_bus_factor.py --t0 2024-08-01",
            "analysis/03_instruments/bus_factor_readings.py --t0 2024-08-01",
            "analysis/03_instruments/backdating.py",
            "analysis/03_instruments/collect_policy_paths.py --t0 2024-08-01",
            "analysis/03_instruments/collect_scorecard.py --t0 2024-08-01",
            "analysis/03_instruments/scorecard_adapter.py --t0 2024-08-01",
            "analysis/03_instruments/freeze_features.py --t0 2024-08-01",
            "analysis/03_instruments/collect_scorecard_published.py --t0 2024-08-01 --scan 2024-07-29",
            "analysis/03_instruments/collect_published.py --t0 2024-08-01 --accessed 2026-11-04",
            "analysis/03_instruments/freshness.py --accessed 2026-11-04",
            "analysis/03_instruments/fidelity_recent.py --accessed 2026-11-04 --sample 150",
        ],
    ),
    (
        "04",
        "RQ2 and RQ3: the first join of scores and outcomes",
        [
            "analysis/04_validity/outcome_variants.py --t0 2024-08-01",
            "analysis/04_validity/validity.py --t0 2024-08-01 --resamples 2000",
            "analysis/04_validity/simple.py --t0 2024-08-01 --resamples 2000",
            "analysis/04_validity/bus_documented.py --t0 2024-08-01 --resamples 2000",
            "analysis/04_validity/baseline_strata.py --t0 2024-08-01 --resamples 2000",
    "analysis/04_validity/scorecard_published.py --t0 2024-08-01 --scan 2024-07-29 --resamples 2000",
    "analysis/04_validity/later_dependents_base.py --t0 2024-08-01",
            "analysis/04_validity/scorecard_published.py --t0 2024-08-01 --scan 2024-07-29 --resamples 2000",
            "analysis/04_validity/later_dependents_base.py --t0 2024-08-01",
            "analysis/04_validity/fig_validity.py",
            "analysis/06_paper/export_validity.py",
        ],
    ),
    (
        "04b",
        "robustness: most-starred list at the second freeze date, 12-month window",
        [
            "analysis/00_probes/probe_github.py meta --t0 2025-01-01 --horizon 12",
            "analysis/00_probes/probe_github.py gone --t0 2025-01-01 --horizon 12",
            "analysis/04_validity/prepare_second_date.py --t0 2025-01-01",
            "analysis/01_cohort/build_cohort.py --t0 2025-01-01",
            "analysis/03_instruments/crossd_adapter.py --t0 2025-01-01",
            "analysis/03_instruments/collect_git.py --t0 2025-01-01",
            "analysis/03_instruments/collect_github_t0.py --t0 2025-01-01",
            "analysis/03_instruments/collect_root_files.py --t0 2025-01-01",
            "analysis/03_instruments/rule_adapters.py --t0 2025-01-01",
            "analysis/03_instruments/criticality_published.py --t0 2025-01-01",
            "analysis/03_instruments/freeze_features.py --t0 2025-01-01",
            "analysis/00_probes/probe_github.py demand --t0 2025-01-01 --horizon 12",
            "analysis/02_outcomes/label_outcomes.py --t0 2025-01-01 --months 12",
            "analysis/04_validity/bus_documented.py --t0 2024-08-01 --resamples 2000",
            "analysis/04_validity/baseline_strata.py --t0 2024-08-01 --resamples 2000",
    "analysis/04_validity/scorecard_published.py --t0 2024-08-01 --scan 2024-07-29 --resamples 2000",
    "analysis/04_validity/later_dependents_base.py --t0 2024-08-01",
            "analysis/04_validity/scorecard_published.py --t0 2024-08-01 --scan 2024-07-29 --resamples 2000",
            "analysis/04_validity/later_dependents_base.py --t0 2024-08-01",
    "analysis/04_validity/robustness.py --t0 2025-01-01 --resamples 2000",
        ],
    ),
    (
        "05",
        "illustrative case panel, outside the statistics",
        [
            "analysis/05_cases/screen_incidents.py",
            "analysis/05_cases/case_series.py",
            "analysis/05_cases/case_table.py",
            "analysis/05_cases/case_instruments.py",
            "analysis/05_cases/case_matrix.py",
        ],
    ),
    (
        "06",
        "numbers and tables of the paper",
        [
            "analysis/06_paper/numbers_from_raw.py",
            "analysis/06_paper/export_macros.py",
        ],
    ),
]

# From the derived data, offline. The bootstrap has a fixed seed, so the output matches the paper.
REPRODUCE = [
    "analysis/04_validity/validity.py --t0 2024-08-01 --resamples 2000",
    "analysis/04_validity/simple.py --t0 2024-08-01 --resamples 2000",
    "analysis/04_validity/bus_documented.py --t0 2024-08-01 --resamples 2000",
    "analysis/04_validity/baseline_strata.py --t0 2024-08-01 --resamples 2000",
    "analysis/04_validity/scorecard_published.py --t0 2024-08-01 --scan 2024-07-29 --resamples 2000",
    "analysis/04_validity/later_dependents_base.py --t0 2024-08-01",
    "analysis/04_validity/robustness.py --t0 2025-01-01 --resamples 2000",
    "analysis/04_validity/fig_validity.py",
    "analysis/06_paper/export_validity.py",
    f"{PROBES}/fig_crossd_coverage.py",
    "analysis/05_cases/case_table.py",
    "analysis/05_cases/case_matrix.py",
    "analysis/06_paper/export_macros.py",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="start", default=None, help="run from this stage on")
    ap.add_argument("--list", action="store_true", help="print the stages without running them")
    ap.add_argument("--reproduce", action="store_true", help="tables and figures from the derived data, offline")
    args = ap.parse_args()

    if args.start is not None and not any(s[0] == args.start for s in STAGES):
        print(f"unknown stage {args.start!r}; known: {[s[0] for s in STAGES]}")
        return 2

    if args.list:
        for stage, desc, commands in STAGES:
            print(f"[{stage}] {desc}")
            print("\n".join(f"  {c}" for c in commands))
        return 0

    if args.reproduce:
        for command in REPRODUCE:
            print(f"  {command}", flush=True)
            subprocess.run([sys.executable, *command.split()], cwd=ROOT, check=True)
        return 0

    started = args.start is None
    for stage, desc, commands in STAGES:
        started = started or stage == args.start
        if not started:
            continue
        print(f"[{stage}] {desc}", flush=True)
        for command in commands:
            print(f"  {command}", flush=True)
            subprocess.run([sys.executable, *command.split()], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
