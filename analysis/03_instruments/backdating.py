#!/usr/bin/env python3
"""Which component can be computed for a past date, and from what (RQ1b).

The classes are decided from the CLI probe (scorecard_cli.csv), the Scorecard source at v5.6.0, the published rules and
what the collected values show. Reasons are in `why`.

  recorded  read at the time and stored
  rebuilt   computed from data dated before t0
  partial   computed from dated data, with a named part read today or capped
  none      not backdatable, or read today; excluded

Output: data/probes/backdating.csv

Usage:
    python analysis/03_instruments/backdating.py
"""

from __future__ import annotations

import csv
import sys

from base import ROOT

WEIGHT = {"Critical": 10.0, "High": 7.5, "Medium": 5.0, "Low": 2.5}  # pkg/scorecard/scorecard_result.go at v5.6.0

COMMIT_ONLY = "the CLI refuses this check at a commit"
SCORECARD = {  # risk levels from docs/checks/internal/checks.yaml at v5.6.0
    "Maintained": {"risk": "High", "class": "partial", "source": "rule", "why": "rebuilt from dated commits and issues; association read today"},
    "Binary-Artifacts": {"risk": "High", "class": "rebuilt", "source": "cli", "why": "files at the commit"},
    "Dangerous-Workflow": {"risk": "Critical", "class": "rebuilt", "source": "cli", "why": "files at the commit"},
    "Token-Permissions": {"risk": "High", "class": "rebuilt", "source": "cli", "why": "files at the commit"},
    "Pinned-Dependencies": {"risk": "Medium", "class": "rebuilt", "source": "cli", "why": "files at the commit"},
    "Code-Review": {"risk": "High", "class": "rebuilt", "source": "cli", "why": "commit history with dated reviews"},
    "Security-Policy": {"risk": "Medium", "class": "partial", "source": "cli", "why": "files at the commit; the owner's .github repository is read today, so we keep it only if committed by t0"},
    "License": {"risk": "Low", "class": "none", "source": "", "why": "the check asks GitHub's license API, which answers for today whatever the commit"},
    "CI-Tests": {"risk": "Low", "class": "none", "source": "", "why": "runs at a commit, but GitHub has deleted the check data of old commits, so nearly every value reads zero"},
    "Vulnerabilities": {"risk": "High", "class": "none", "source": "", "why": "runs at a commit, but asks OSV today, so later advisories enter"},
    "Dependency-Update-Tool": {"risk": "High", "class": "none", "source": "", "why": COMMIT_ONLY},
    "Branch-Protection": {"risk": "High", "class": "none", "source": "", "why": "current settings; " + COMMIT_ONLY},
    "Signed-Releases": {"risk": "High", "class": "none", "source": "", "why": COMMIT_ONLY},
    "Webhooks": {"risk": "Critical", "class": "none", "source": "", "why": "current settings; " + COMMIT_ONLY},
    "Fuzzing": {"risk": "Medium", "class": "none", "source": "", "why": COMMIT_ONLY},
    "Packaging": {"risk": "Medium", "class": "none", "source": "", "why": COMMIT_ONLY},
    "SAST": {"risk": "Medium", "class": "none", "source": "", "why": COMMIT_ONLY},
    "SBOM": {"risk": "Medium", "class": "none", "source": "", "why": COMMIT_ONLY},
    "CII-Best-Practices": {"risk": "Low", "class": "none", "source": "", "why": "current badge state; " + COMMIT_ONLY},
    "Contributors": {"risk": "Low", "class": "none", "source": "", "why": "current organisations; " + COMMIT_ONLY},
}

OTHER = [
    *[("CrOSSD", c, "recorded", "stored value, dated by its reading") for c in
      ("maturity_level", "support_rate", "project_velocity", "bus_factor", "elephant_factor", "community_health", "criticality_score")],
    ("Criticality Score", "published score", "recorded", "last list before t0, from the project's BigQuery table"),
    ("Criticality Score", "created_since", "rebuilt", "createdAt, or the first commit if recreated"),
    ("Criticality Score", "updated_since", "rebuilt", "git"),
    ("Criticality Score", "contributor_count", "rebuilt", "git authors, today's default branch"),
    ("Criticality Score", "commit_frequency", "rebuilt", "git"),
    ("Criticality Score", "recent_releases_count", "rebuilt", "dated releases"),
    ("Criticality Score", "closed_issues_count", "rebuilt", "search by closing date"),
    ("Criticality Score", "updated_issues_count", "partial", "created or commented in the window, capped at 100 issues"),
    ("Criticality Score", "comment_frequency", "partial", "capped at 100 issues"),
    ("Criticality Score", "dependents_count", "partial", "CrOSSD value at t0 in the place of mentions in commit messages"),
    ("Criticality Score", "org_count", "none", "current organisations"),
    ("openCode maintenance", "commits in 6 months", "rebuilt", "git"),
    ("openCode maintenance", "mean issue response", "rebuilt", "dated issues and comments"),
    ("openCode maintenance", "release or tag in 6 months", "rebuilt", "dated releases and tags"),
    ("openCode maintenance", "contributor absence factor", "rebuilt", "git"),
    ("openCode security", "mean issue response", "rebuilt", "dated issues and comments"),
    ("openCode security", "SECURITY.md", "rebuilt", "tree at the commit"),
    ("openCode security", "reviewed merges", "partial", "dated reviews; association read today"),
    ("openCode security", "signed tags", "rebuilt", "tag objects"),
    ("openCode security", "branch protection", "none", "current settings"),
    ("openCode security", "force pushes", "none", "current settings"),
    ("openCode security", "vulnerability criteria", "none", "advisory data is backfilled; level 3 stays out"),
]


def main() -> int:
    rows = [{"instrument": "Scorecard", "component": name, "class": spec["class"], "risk": spec["risk"], "weight": WEIGHT[spec["risk"]], "why": spec["why"]}
            for name, spec in SCORECARD.items()]
    rows += [{"instrument": i, "component": c, "class": k, "risk": "", "weight": "", "why": w} for i, c, k, w in OTHER]
    out = ROOT / "data" / "probes" / "backdating.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    total = sum(WEIGHT[s["risk"]] for s in SCORECARD.values())
    kept = sum(WEIGHT[s["risk"]] for s in SCORECARD.values() if s["class"] != "none")
    print(f"{len(rows)} components; Scorecard weight kept {kept} of {total} ({kept / total:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
