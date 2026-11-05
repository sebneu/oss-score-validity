#!/usr/bin/env python3
"""The few numbers of the paper that need the raw downloads, as one small table.

Everything else in `export_macros.py` and `case_matrix.py` reads derived files. These numbers come from the
CrOSSD project index, the deps.dev package details, the fix tags and the XZ Utils clone, none of which is
redistributed, so they are computed here once and the table ships with the package.

Output: data/probes/numbers_from_raw.csv

Usage:
    python analysis/06_paper/numbers_from_raw.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "00_probes"))

import count_events  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
T0 = "2024-08-01"


def thousands(value: int) -> str:
    return f"{int(value):,}".replace(",", "{,}")


def main() -> int:
    t0 = T0
    m: dict[str, str] = {}
    index = sorted((ROOT / "data" / "raw" / "crossd").glob("index_*.json"))[-1]
    m["PanelProjects"] = thousands(len(json.loads(index.read_text())["snapshots"]))

    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{t0}.csv")
    members = cohort[["project"]]
    pairs = count_events.security_outcomes(t0, 24, members, "2026-11-03", "2026-11-03")
    routes = pairs.route.value_counts()
    m["PairsCandidate"] = thousands(len(pairs))
    m["PairsVerified"] = thousands(routes["verified"])
    m["PairsNoClaim"] = thousands(routes["no_claim"])
    m["PairsViaRepo"] = thousands(routes["via_repo"])
    m["PairsOtherClaim"] = thousands(routes["dropped_other_claim"])
    m["PairsReferenceOnly"] = thousands(routes["dropped_no_package"])
    packaged = pairs[pairs.route.isin({"verified", "no_claim"})]
    m["PairsPackaged"] = thousands(len(packaged))
    m["PairsFailDrafted"] = thousands(packaged.response_failure.sum())
    m["PairsNoFix"] = thousands(packaged.no_fix_listed.sum())
    m["PairsKev"] = thousands(packaged.in_kev.sum())
    m["PairsNotFound"] = thousands(packaged.fix_not_found.sum())
    details = {}
    with (ROOT / "data" / "raw" / "depsdev" / "package_details_2026-11-03.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            details[(rec["system"], rec["package"])] = rec.get("versions") or {}
    systems = {v: k for k, v in count_events.SYSTEMS.items()}
    tags = count_events.load_fix_tags(t0)
    lags, late = [], 0
    for row_ in packaged[~packaged.no_fix_listed & ~packaged.fix_not_found].itertuples():
        versions = details.get((systems[row_.package_ecosystem], count_events.query_name(row_.package_ecosystem, row_.package))) or {}
        dates = []
        for name in row_.fixed_versions.split("|"):
            when = versions.get(name) or versions.get(f"v{name}") or tags.get((row_.repo, name))
            if when:
                dates.append(pd.Timestamp(when))
        if dates:
            lags.append((min(dates) - row_.published_at).total_seconds() / 86400)
    lag = pd.Series(lags)
    m["FixDated"] = thousands(len(lag))
    m["FixBeforeAdvisory"] = f"{100 * (lag <= 0).mean():.1f}\\%"
    m["FixMedianLead"] = f"{-lag.median():.1f}"
    m["FixOverNinety"] = str(int((lag > 90).sum()))

    mapping = pd.read_parquet(PROCESSED / "package_map.parquet")
    m["LodashClaims"] = thousands(((mapping.project == "lodash/lodash") & (mapping.system == "NPM")).sum())

    # Share of the commits in the six months before the XZ reading by the person who added the payload. Names are counted, not stored.
    with (ROOT / "data" / "raw" / "cases" / "instruments.jsonl").open() as fh:
        xz = next(rec for rec in map(json.loads, fh) if rec["project"] == "tukaani-project/xz")
    log = subprocess.run(["git", "log", "HEAD", f"--until={xz['reading']}T00:00:00Z", "--since=2023-08-22T00:00:00Z", "--format=%an"],
                         cwd=ROOT / "data" / "raw" / "git" / "tukaani-project__xz.git", capture_output=True, text=True, check=True).stdout.splitlines()
    m["CaseXzTan"] = f"{100 * sum(name == 'Jia Tan' for name in log) / len(log):.0f}\\%"
    m["CaseXzCommits"] = str(len(log))

    pd.Series(m, name="value").rename_axis("macro").to_csv(ROOT / "data" / "probes" / "numbers_from_raw.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
