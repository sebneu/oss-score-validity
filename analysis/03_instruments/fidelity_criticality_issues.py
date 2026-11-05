#!/usr/bin/env python3
"""The issue signals in the published Criticality Score list (RQ1c).

The last published list reports zero for the issue signals of nearly all repositories, including very active ones. So our
rebuilt issue signals cannot agree with it, and the fidelity test of the score has to say which part it can test. We
compute the rebuilt score with the issue signals set to the published values, and report the zeros. No outcomes are read.

Output: data/probes/fidelity_criticality_issues.csv (one row per statistic)

Usage:
    python analysis/03_instruments/fidelity_criticality_issues.py --accessed 2026-11-04
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd
from scipy.stats import spearmanr

from base import RAW, ROOT
from rule_adapters import criticality_score

ISSUES = {"closed_issues_count": "legacy.closed_issues_count", "updated_issues_count": "legacy.updated_issues_count", "comment_frequency": "legacy.issue_comment_frequency"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--accessed", default="2026-11-04")
    args = ap.parse_args()
    listing = pd.read_csv(RAW / "criticality" / "20250725_all.csv.gz", usecols=["repo.url", *ISSUES.values()])
    stats = {"list_rows": len(listing)}
    for name, column in ISSUES.items():
        stats[f"list_zero_{name}"] = float((listing[column] == 0).mean())
    stats["list_all_three_zero"] = float((listing[list(ISSUES.values())] == 0).all(axis=1).mean())

    with (RAW / "fidelity" / f"criticality_{args.accessed}.jsonl").open() as fh:
        rows = [json.loads(line) for line in fh]
    ours, plain = [], []
    for r in rows:
        signals, published = dict(r["signals"]), r["published_signals"]
        signals["dependents_count"] = float(published["legacy.github_mention_count"] or 0)
        plain.append(criticality_score(signals))
        for name, column in ISSUES.items():
            signals[name] = float(published[column] or 0)
        ours.append(criticality_score(signals))
    published = pd.Series([r["published"] for r in rows], dtype=float)
    ours, plain = pd.Series(ours), pd.Series(plain)
    stats.update({"sample": len(rows), "sample_zero_closed": float((pd.Series([r["published_signals"]["legacy.closed_issues_count"] for r in rows]) == 0).mean()),
                  "rho_rebuilt": spearmanr(plain, published).statistic, "mad_rebuilt": float((plain - published).abs().median()),
                  "rho_issue_as_published": spearmanr(ours, published).statistic, "mad_issue_as_published": float((ours - published).abs().median())})
    pd.Series(stats).rename("value").rename_axis("statistic").reset_index().to_csv(ROOT / "data" / "probes" / "fidelity_criticality_issues.csv", index=False)
    print(json.dumps(stats, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
