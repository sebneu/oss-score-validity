#!/usr/bin/env python3
"""Rebuild the CrOSSD bus factor from dated commits and compare it with the stored value.

This is the fidelity test for the values stored in the `bak` block. The rebuild follows
`contributions_distributions` in FH-CrOSSD/thesis_metrics: commits counted per email, plus co-authors;
contributors are taken in order of commits until half are reached, and the loop stops first if the running
total reaches 80 percent. So a project in which one person holds at least 80 percent reads 0, although the
documentation gives 1 as the lowest value. The block exists only with a commit in the month before the reading.

The window is an empirical finding. The miner asks for 12 months and the documentation says 6, but the stored
values match a window of one month, which is also what the later library `crossd_metrics` states in its code. We
therefore report the three windows side by side and keep one month as the reconstruction.

Git does not hold GitHub's verification flag. The source uses the author of a verified commit and the
committer otherwise. We use the author where the committer is GitHub's web-flow address, since those commits are the ones
GitHub signs, and report the two plain readings next to it.

No outcomes are read.

Outputs:
  data/processed/features/crossd_rebuilt_<t0>.parquet
  data/probes/bus_factor_fidelity.csv

Usage:
    python analysis/03_instruments/rebuild_bus_factor.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime

import pandas as pd
from scipy.stats import spearmanr

from base import PROCESSED, RECONSTRUCTED, ROOT, add_months, assert_not_after, cohort, freeze, row, write_features
from collect_git import hashed

WEB_FLOW = hashed("noreply@github.com")


def score(commits: pd.DataFrame, reading: str) -> int:
    people: list[str] = []
    for r in commits.itertuples():
        if reading == "committer" or (reading == "web_flow" and r.committer != WEB_FLOW):
            people.append(r.committer)
        else:
            people.append(r.author)
        if r.co_authors:
            people += r.co_authors.split("|")
    counts = sorted(Counter(people).values(), reverse=True)
    half, stop = sum(counts) * 0.5, sum(counts) * 0.8
    running, reached, value = 0, 0, 0
    for n in counts:
        running += n
        if running >= stop:
            break
        if reached <= half:
            reached += n
            value += 1
    return value


def rebuild(project: str, observed: float, reading: str, months: int = 1) -> float | None:
    path = PROCESSED / "git" / f"{project.replace('/', '__')}.parquet"
    if not path.exists():
        return None
    commits = pd.read_parquet(path)
    moment = datetime.fromtimestamp(observed, UTC)
    commits = commits[commits.committed <= observed]
    if not (commits.committed > add_months(moment, -1).timestamp()).any():
        return None
    window = commits[commits.committed > add_months(moment, -months).timestamp()]
    return float(score(window, reading)) if len(window) else None


def agreement(table: pd.DataFrame, column: str) -> dict:
    both = table[table.stored.notna() & table[column].notna()]
    return {
        "both": len(both),
        "exact": (both.stored == both[column]).mean(),
        "within_1": ((both.stored - both[column]).abs() <= 1).mean(),
        "spearman": spearmanr(both.stored, both[column]).statistic,
        "stored_only": int((table.stored.notna() & table[column].isna()).sum()),
        "rebuilt_only": int((table.stored.isna() & table[column].notna()).sum()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = freeze(args.t0)
    stored = pd.read_parquet(PROCESSED / "features" / f"crossd_{args.t0}.parquet")
    stored = stored[stored.component == "bus_factor"].set_index("project")
    members = cohort(args.t0)

    rows, feature_rows = [], []
    for m in members.itertuples():
        observed = float(stored.loc[m.project, "as_of"])
        assert_not_after(observed, t0, m.project)
        values = {reading: rebuild(m.project, observed, reading) for reading in ("web_flow", "committer", "author")}
        values |= {f"months_{n}": rebuild(m.project, observed, "web_flow", n) for n in (6, 12)}
        rows.append({"project": m.project, "stratum": m.stratum, "stored": stored.loc[m.project, "value"], **values})
        feature_rows.append(row(m.project, "bus_factor", values["web_flow"], RECONSTRUCTED, observed))
    table = pd.DataFrame(rows)
    write_features("crossd_rebuilt", args.t0, feature_rows)

    out = []
    for column, label, months in (("web_flow", "web_flow", 1), ("committer", "committer", 1), ("author", "author", 1), ("months_6", "web_flow", 6), ("months_12", "web_flow", 12)):
        out.append({"reading": label, "months": months, "stratum": "all", **agreement(table, column)})
    for stratum, part in table.groupby("stratum"):
        out.append({"reading": "web_flow", "months": 1, "stratum": stratum, **agreement(part, "web_flow")})
    zero = table[table.stored == 0]
    out.append({"reading": "stored", "months": 1, "stratum": "all", "both": int(table.stored.notna().sum()), "zero": len(zero),
                "zero_several_authors": int((zero.author >= 2).sum())})
    result = pd.DataFrame(out)
    result.to_csv(ROOT / "data" / "probes" / "bus_factor_fidelity.csv", index=False)
    print(result.round(3).to_string(index=False))
    both = table[table.stored.notna() & table.web_flow.notna()]
    print(pd.crosstab(both.stored.clip(upper=5), both.web_flow.clip(upper=5)).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
