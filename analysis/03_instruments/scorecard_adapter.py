#!/usr/bin/env python3
"""Scorecard checks and the aggregate at t0.

Backdated checks: the CLI at the last commit before t0 for those that read the commit, and our rule for Maintained.
The classification and its reasons are in backdating.py. Three corrections to the raw CLI values:
  Security-Policy  a policy found only in the owner's `.github` repository counts only if it was committed by t0
  License          stays out, because the check reads GitHub's license API as it is today, whatever the commit
  CI-Tests         stays out, because GitHub has deleted the check data of old commits, so nearly every value reads zero
The aggregate is Scorecard's own weighted mean (risk weights Critical 10, High 7.5, Medium 5, Low 2.5), over the
backdated checks that give a result. Inconclusive checks drop out, as in Scorecard.

Output: data/processed/features/scorecard_<t0>.parquet

Usage:
    python analysis/03_instruments/scorecard_adapter.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from backdating import SCORECARD, WEIGHT
from base import FEATURES, NOT_BACKDATABLE, RAW, RECONSTRUCTED, ROOT, cohort, freeze, row, write_features

POLICY_NAMES = {"security.md", "security.markdown", "security.adoc", "security.rst"}
READ_AT_COMMIT = [name for name, spec in SCORECARD.items() if spec["class"] in ("rebuilt", "partial") and spec["source"] == "cli"]


def own_policy(root: list[str] | None, folders: dict) -> bool | None:
    if root is None:
        return None
    names = {n.lower() for n in root}
    for folder, entries in folders.items():
        names |= {f"{folder}/{n.lower()}" for n in entries}
    allowed = POLICY_NAMES | {f".github/{n}" for n in POLICY_NAMES} | {f"docs/{n}" for n in POLICY_NAMES} | {"doc/security.rst"}
    return bool(names & allowed)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    limit = freeze(args.t0).timestamp()
    members = cohort(args.t0)
    results = {}
    with (RAW / "scorecard" / f"t0_{args.t0}.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            results[rec["project"]] = rec
    root = {}
    with (RAW / "github" / f"root_files_{args.t0}.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            root[rec["project"]] = rec.get("entries")
    paths = {}
    with (RAW / "github" / f"policy_paths_{args.t0}.jsonl").open() as fh:
        for line in fh:
            rec = json.loads(line)
            paths[rec["project"]] = rec
    maintained = pd.read_parquet(FEATURES / f"scorecard_maintained_{args.t0}.parquet").set_index("project")["value"]

    rows, dropped, usable = [], 0, 0
    ci_results, ci_zero = 0, 0
    for m in members.itertuples():
        rec = results.get(m.project)
        checks = (rec or {}).get("checks") or {}
        ok = bool(checks) and not rec.get("error")
        usable += ok
        ci = (checks.get("CI-Tests") or {}).get("score") if ok else None
        if ci is not None and ci >= 0:
            ci_results += 1
            ci_zero += ci == 0
        values: dict[str, float | None] = {}
        for name in READ_AT_COMMIT:
            value = (checks.get(name) or {}).get("score") if ok else None
            values[name] = None if value is None or value < 0 else float(value)
        if values.get("Security-Policy") not in (None, 0.0):
            info = paths.get(m.project)
            own = own_policy(root.get(m.project), info["folders"]) if info else None
            if own is False and not info["org_policy_by_t0"]:
                values["Security-Policy"] = 0.0
                dropped += 1
        value = maintained.get(m.project)
        values["Maintained"] = None if value is None or pd.isna(value) else float(value)
        for name, value in values.items():
            rows.append(row(m.project, f"scorecard_{name}", value, RECONSTRUCTED if value is not None else NOT_BACKDATABLE, limit if value is not None else None))
        # The aggregate needs the CLI run: Maintained alone is no aggregate.
        if ok:
            weights = {name: WEIGHT[SCORECARD[name]["risk"]] for name, value in values.items() if value is not None}
            aggregate = sum(weights[name] * values[name] for name in weights) / sum(weights.values()) if weights else None
        else:
            aggregate = None
        rows.append(row(m.project, "scorecard_aggregate_t0", aggregate, RECONSTRUCTED if aggregate is not None else NOT_BACKDATABLE, limit if aggregate is not None else None))
    print(f"{usable} of {len(members)} projects with a CLI result; {dropped} policies dropped as later than t0", flush=True)
    write_features("scorecard", args.t0, rows)
    stats = {"runs": len(results), "usable": usable, "policy_dropped": dropped, "ci_results": ci_results, "ci_zero": ci_zero}
    pd.DataFrame([stats]).to_csv(ROOT / "data" / "probes" / "scorecard_t0_stats.csv", index=False)
    print(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
