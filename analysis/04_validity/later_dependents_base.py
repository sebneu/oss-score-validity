#!/usr/bin/env python3
"""Later dependents with no row read as zero.

deps.dev has no row for a package without dependents, and none for a system it does not count, so a missing count can be
either. The registered test runs on projects with a count at both dates. This reading counts a missing row as zero for
every project with a package, which is an upper bound on what the restriction hides. Added after the results and descriptive.

Output: data/probes/later_dependents_base.csv

Usage:
    python analysis/04_validity/later_dependents_base.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

import simple
import validity as v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    data = v.Data(args.t0)
    labels = data.labels
    with_package = labels.in_O2b_base.to_numpy(dtype=bool)
    later = pd.to_numeric(labels.I1b, errors="coerce").to_numpy(dtype=float)
    at_t0 = pd.to_numeric(labels.I1b_t0, errors="coerce").to_numpy(dtype=float)
    rows = [{
        "score": "counts", "with_package": int(with_package.sum()), "no_row": int((with_package & np.isnan(later) & np.isnan(at_t0)).sum()),
        "first_date_only": int((with_package & np.isnan(later) & ~np.isnan(at_t0)).sum()), "last_date_only": int((with_package & ~np.isnan(later) & np.isnan(at_t0)).sum()),
        "both": int((with_package & ~np.isnan(later) & ~np.isnan(at_t0)).sum()),
    }]
    later0, at_t00 = np.nan_to_num(later), np.nan_to_num(at_t0)
    for name, instrument, component in (("CrOSSD criticality", "crossd", "criticality_score"), ("OpenSSF Criticality", "criticality_published", "openssf_criticality_published")):
        score = data.values(instrument, component)
        known = with_package & ~np.isnan(score)
        group = simple.bins(at_t00[known])
        rows.append({"score": name, "n": int(known.sum()), "rho": v.spearman(score[known], later0[known]), "rho_t0": v.spearman(at_t00[known], later0[known]),
                     "within_rho": simple.within_rho(score[known], later0[known], group)})
    table = pd.DataFrame(rows)
    table.to_csv(v.PROBES / "later_dependents_base.csv", index=False)
    print(table.round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
