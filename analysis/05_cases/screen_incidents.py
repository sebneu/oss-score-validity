#!/usr/bin/env python3
"""Find candidate incidents among the projects CrOSSD monitors (case panel).

Screens the whole panel since monitoring began (April 2024), so the list comes from data and not from
memory: advisories in the CISA catalogue, advisories for malicious code in a legitimate package, and
archived or vanished repositories. Candidates are then checked against primary sources by hand.

The cases are selected on the outcome. They are illustrations, and they feed no statistic and no
step of the validity analysis. No score is read here.

Output: data/probes/incident_candidates.csv

Usage:
    python analysis/05_cases/screen_incidents.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
START = pd.Timestamp("2024-04-01", tz="UTC")
FREEZE = "2026-11-03"


def main() -> int:
    coverage = pd.read_parquet(ROOT / "data" / "probes" / "crossd_coverage.parquet", columns=["project", "stratum", "snapshot_utc"])
    first = coverage.groupby("project").agg(stratum=("stratum", "first"), first=("snapshot_utc", "min"), last=("snapshot_utc", "max"), n=("snapshot_utc", "size"))
    panel = {p.lower(): p for p in first.index}
    cohort = set(pd.read_csv(ROOT / "analysis" / "01_cohort" / "cohort_2024-08-01.csv").project)

    osv = pd.read_parquet(ROOT / "data" / "processed" / "osv_advisories.parquet")
    osv["published_at"] = pd.to_datetime(osv.published, utc=True, format="ISO8601")
    osv = osv[(osv.published_at >= START) & osv.withdrawn.isna()]
    kev_raw = json.loads((ROOT / "data" / "raw" / "kev" / FREEZE / "known_exploited_vulnerabilities.json").read_text())["vulnerabilities"]
    kev = {v["cveID"]: v for v in kev_raw}

    rows = []
    for rec in osv.itertuples():
        ranges = set(filter(None, rec.range_repos.split("|")))
        named = (ranges | set(filter(None, rec.reference_repos.split("|")))) & panel.keys()
        if not named:
            continue
        ids = {rec.id, *filter(None, rec.aliases.split("|"))}
        hit = ids & kev.keys()
        compromised = rec.malicious and not rec.id.startswith("MAL-")
        if not hit and not compromised:
            continue
        for repo in named:
            rows.append({
                "kind": "kev" if hit else "malicious_code", "project": panel[repo], "advisory": rec.id,
                "cve": next(iter(hit), ""), "package": rec.package, "ecosystem": rec.package_ecosystem,
                "published": rec.published_at.date().isoformat(), "kev_added": kev[next(iter(hit))]["dateAdded"] if hit else "",
                "in_range": repo in ranges,
                "name": kev[next(iter(hit))]["vulnerabilityName"][:70] if hit else "",
            })
    table = pd.DataFrame(rows)
    table = table.drop_duplicates(["kind", "project", "advisory"])

    # Archived or vanished, for the frame we have metadata on.
    meta = pd.read_parquet(ROOT / "data" / "processed" / "github_meta_2024-08-01.parquet", columns=["project", "resolved", "isArchived", "archivedAt"])
    archived = meta[meta.isArchived.fillna(False).astype(bool)]
    archived = archived[pd.to_datetime(archived.archivedAt, utc=True, format="ISO8601") >= START]
    extra = [{"kind": "archived", "project": r.project, "published": r.archivedAt[:10]} for r in archived.itertuples()]
    extra += [{"kind": "gone", "project": r.project} for r in meta[~meta.resolved].itertuples()]
    table = pd.concat([table, pd.DataFrame(extra)], ignore_index=True)

    stars = pd.read_parquet(ROOT / "data" / "raw" / "depsdev" / "projects_2024-07-29.parquet", columns=["Name", "StarsCount"]).dropna()
    star = dict(zip(stars.Name.str.lower(), stars.StarsCount))
    table["stars_t0"] = table.project.str.lower().map(star)
    table["in_cohort"] = table.project.isin(cohort)
    table["list"] = table.project.map(first.stratum)
    table["snapshots"] = table.project.map(first.n)
    table["monitored_from"] = table.project.map(first["first"]).dt.date.astype(str)
    table["monitored_to"] = table.project.map(first["last"]).dt.date.astype(str)
    out = ROOT / "data" / "probes" / "incident_candidates.csv"
    table.sort_values(["kind", "stars_t0"], ascending=[True, False]).to_csv(out, index=False)

    print(table.kind.value_counts().to_string())
    columns = ["project", "advisory", "cve", "published", "stars_t0", "list", "in_cohort", "snapshots", "name"]
    for kind in ("kev", "malicious_code"):
        part = table[table.kind == kind].sort_values("stars_t0", ascending=False)
        print(f"\n== {kind}: {part.project.nunique()} projects")
        print(part[columns].head(40).to_string(index=False, max_colwidth=46))
    for kind in ("archived", "gone"):
        part = table[table.kind == kind].sort_values("stars_t0", ascending=False)
        print(f"\n== {kind}: {len(part)}")
        print(part[["project", "published", "stars_t0", "list", "in_cohort", "snapshots"]].head(25).to_string(index=False))

    watch = ["tukaani-project/xz", "tj-actions/changed-files", "reviewdog/reviewdog", "chalk/chalk", "debug-js/debug", "nrwl/nx",
             "ultralytics/ultralytics", "redis/redis", "valkey-io/valkey", "kubernetes/ingress-nginx", "minio/minio", "facebook/react",
             "vercel/next.js", "apache/logging-log4j2", "openssl/openssl", "prettier/eslint-config-prettier", "polyfillpolyfill/polyfill-service",
             "BerriAI/litellm", "axios/axios", "hashicorp/terraform", "elastic/elasticsearch", "denoland/deno", "langchain-ai/langchain"]
    print("\n== named projects in the panel")
    for name in watch:
        key = name.lower()
        print(f"{name:38} {'panel' if key in panel else '-':6} {first.loc[panel[key], 'stratum'] if key in panel else '':14} {'cohort' if panel.get(key) in cohort else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
