#!/usr/bin/env python3
"""Count events per draft outcome before anything is frozen.

The counts decide which outcomes can enter the statistics at all: at least 40 events in the
eligible cohort.

No score may reach this script. From the CrOSSD coverage table it reads only project,
stratum and observation time, and `FORBIDDEN_COLUMNS` makes that a failure instead of a
habit: looking at metric values next to outcomes before the freeze would void the design.

Outcomes are counted as first drafted, with these reading choices, all open
for the freeze:
  - An advisory belongs to a project if its `ranges[].repo` or `references` name the repository
    and the package does not claim a different one (deps.dev, default version). `verified` means
    the package claims this repository, `no_claim` that it claims none. A package claiming
    another repository is dropped: the advisory only mentions this one.
  - Records without a package (`GIT`, `OSS-Fuzz`) are attached through `ranges[].repo` only and
    count for O2a; their fix is a commit, so O2b is not defined for them (`via_repo`).
  - The denominator is the projects with a `plausible` package at t0 (the latest deps.dev
    snapshot before t0, `probe_depsdev_bq.py`), an estimate, plus those attached through `via_repo`.
  - A severity qualifies with CVSS v3 base >= 7.0 or a GHSA label HIGH or CRITICAL.
  - O2b as drafted: no listed fixed version was released within 90 days of publication, or the
    advisory or an alias is in CISA KEV. A fix released before publication counts as fixed.
    The release date comes from the registry or else from a matching GitHub tag
    (`probe_github.py fixtags`). A listed version found in neither is counted apart
    (`fix_not_found`).
    `O2b_strict` is the part this cannot blur: no fixed version listed at the data freeze,
    at least 90 days after publication, or in KEV.
  - O1a and O1b need `probe_github.py meta`, O1c needs `issues`; without them they are
    reported as pending, and eligibility falls back to the CrOSSD observation alone.
  - A repository gone today has no commit history to check, so it counts as active at t0 if
    CrOSSD read it in the window. Dropping these would hide the very outcome O1a looks for.

Outputs:
  data/raw/depsdev/package_details_<date>.jsonl  release dates and claimed repository per package
  data/processed/outcome_draft_<t0>.parquet    per project, one column per draft outcome
  data/probes/event_counts_<t0>.csv            the event table

Usage:
    python analysis/00_probes/count_events.py --t0 2024-08-01 --accessed 2026-11-03
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
PROBES = ROOT / "data" / "probes"
API = "https://api.deps.dev/v3"

COVERAGE_COLUMNS = ["project", "stratum", "observed_ts"]
FORBIDDEN_COLUMNS = {"criticality_score", "maturity_level", "support_rate", "elephant_factor"}

MIN_EVENTS = 40
FIX_DAYS = 90
ELIGIBILITY_DAYS = 14
SEVERE_LABELS = {"HIGH", "CRITICAL"}
# deps.dev system name -> OSV ecosystem name
SYSTEMS = {"NPM": "npm", "PYPI": "PyPI", "MAVEN": "Maven", "GO": "Go", "CARGO": "crates.io",
           "NUGET": "NuGet", "RUBYGEMS": "RubyGems"}


def window(t0: str, months: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(t0, tz="UTC")
    return start, start + pd.DateOffset(months=months)


def cohort(t0: str) -> pd.DataFrame:
    table = pd.read_parquet(PROBES / "crossd_coverage.parquet", columns=COVERAGE_COLUMNS)
    if FORBIDDEN_COLUMNS & set(table.columns):
        raise SystemExit("a score column reached count_events.py")
    end = pd.Timestamp(t0, tz="UTC").timestamp()
    start = end - ELIGIBILITY_DAYS * 86400
    seen = table[(table.observed_ts <= end) & (table.observed_ts > start)]
    return seen.sort_values("observed_ts").groupby("project").tail(1)[["project", "stratum"]]


def eligible_members(t0: str, months: int = 24) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """The eligible cohort at t0, and the maintenance outcomes if GitHub data exists."""
    members = cohort(t0)
    print(f"observed in the window before {t0}: {len(members)}", flush=True)
    maintenance = maintenance_outcomes(t0, months)
    if maintenance is None:
        print("GitHub metadata missing: O1 pending, eligibility is the CrOSSD observation only")
        return members, None
    members = members.merge(maintenance, on="project", how="left")
    members = members[
        (members.active_at_t0.fillna(False) | members.gone_now.fillna(False))
        & ~members.archived_before_t0.fillna(False)
    ]
    print(f"also active and not archived at t0: {len(members)}", flush=True)
    print(members.stratum.value_counts().to_string())
    return members, maintenance


def severe_advisories(lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    osv = pd.read_parquet(PROCESSED / "osv_advisories.parquet")
    osv["published_at"] = pd.to_datetime(osv.published, utc=True, format="ISO8601")
    keep = (
        osv.published_at.gt(lo)
        & osv.published_at.le(hi)
        & osv.withdrawn.isna()
        & ~osv.malicious
        & (osv.cvss3_base.ge(7.0) | osv.ghsa_severity.isin(SEVERE_LABELS))
    )
    return osv[keep]


def kev_ids(freeze: str) -> set[str]:
    path = ROOT / "data" / "raw" / "kev" / freeze / "known_exploited_vulnerabilities.json"
    return {v["cveID"] for v in json.loads(path.read_text())["vulnerabilities"]}


def package_details(packages: list[tuple[str, str]], accessed: str) -> dict[tuple, dict]:
    """Release dates and the repositories a package claims, from deps.dev. Cached, resumable."""
    cache = ROOT / "data" / "raw" / "depsdev" / f"package_details_{accessed}.jsonl"
    cache.parent.mkdir(parents=True, exist_ok=True)
    known: dict[tuple, dict] = {}
    if cache.exists():
        with cache.open() as fh:
            for line in fh:
                rec = json.loads(line)
                known[(rec["system"], rec["package"])] = rec
    todo = [p for p in packages if p not in known]
    print(f"package details: {len(packages)} packages, {len(todo)} to fetch", flush=True)
    session = requests.Session()

    def get(url: str) -> dict | None:
        for attempt in range(5):
            try:
                resp = session.get(url, timeout=60)
                if resp.status_code == 404:
                    return {}
                if resp.ok:
                    return resp.json()
            except requests.RequestException:
                pass
            time.sleep(2**attempt)
        return None

    def fetch(item: tuple[str, str]) -> dict | None:
        system, package = item
        base = f"{API}/systems/{system}/packages/{quote(package, safe='')}"
        body = get(base)
        if body is None:
            return None
        versions = body.get("versions") or []
        default = next((v for v in versions if v.get("isDefault")), versions[-1] if versions else None)
        related = []
        if default:
            detail = get(f"{base}/versions/{quote(default['versionKey']['version'], safe='')}")
            related = [
                (r.get("projectKey") or {}).get("id", "").lower()
                for r in (detail or {}).get("relatedProjects") or []
                if r.get("relationType") == "SOURCE_REPO"
            ]
        return {
            "system": system,
            "package": package,
            "versions": {v["versionKey"]["version"]: v.get("publishedAt") for v in versions},
            "source_repos": sorted(set(related)),
        }

    with cache.open("a") as out, ThreadPoolExecutor(max_workers=8) as pool:
        for rec in pool.map(fetch, todo):
            if rec is not None:
                known[(rec["system"], rec["package"])] = rec
                out.write(json.dumps(rec) + "\n")
    return known


def plausible_links(snapshot: str) -> pd.DataFrame:
    """Repository to package links at t0 that are more than a package's own unverified claim."""
    links = pd.read_parquet(ROOT / "data" / "raw" / "depsdev" / f"package_links_{snapshot}.parquet")
    keep = []
    for row in links.itertuples():
        repo = row.ProjectName.lower()
        if "ATTESTATION" in row.RelationProvenance:
            keep.append(True)
        elif row.System == "GO":
            keep.append(row.Name.lower() == f"github.com/{repo}" and bool(row.tagged))
        else:
            token = re.split(r"[/:]", row.Name)[-1]
            keep.append(normal(token) == normal(repo.split("/", 1)[1]))
    return links[keep]


def normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def query_name(ecosystem: str, package: str) -> str:
    return re.sub(r"[-_.]+", "-", package).lower() if ecosystem == "PyPI" else package


def fix_in_time(versions: dict, fixed: str, limit: pd.Timestamp, ecosystem: str,
                tags: dict | None = None) -> bool:
    for name in filter(None, fixed.split("|")):
        # OSV writes Go versions without the `v` that deps.dev keeps.
        released = versions.get(name) or (versions.get(f"v{name}") if ecosystem == "Go" else None)
        released = released or (tags or {}).get(name)
        if released and pd.Timestamp(released) <= limit:
            return True
    return False


def load_fix_tags(t0: str) -> dict[tuple[str, str], str]:
    """(repo, version) -> date of the matching tag, from `probe_github.py fixtags`."""
    path = ROOT / "data" / "raw" / "github" / f"fix_tags_{t0}.jsonl"
    found: dict[tuple[str, str], str] = {}
    if path.exists():
        with path.open() as fh:
            for line in fh:
                rec = json.loads(line)
                if rec.get("date"):
                    found[(rec["repo"], rec["version"])] = rec["date"]
    return found


def security_outcomes(t0: str, months: int, members: pd.DataFrame, freeze: str, accessed: str,
                      cvss_cut: float = 7.0, fix_days: int = FIX_DAYS) -> pd.DataFrame:
    """One row per advisory x package x project that the advisory can be attached to."""
    lo, hi = window(t0, months)
    osv = severe_advisories(lo, hi)
    if cvss_cut > 7.0:
        osv = osv[osv.cvss3_base.ge(cvss_cut) | osv.ghsa_severity.eq("CRITICAL")]
    panel = {p.lower(): p for p in members.project}
    meta_path = PROCESSED / f"github_meta_{t0}.parquet"
    if meta_path.exists():
        meta = pd.read_parquet(meta_path, columns=["project", "canonical"]).dropna()
        panel |= {c.lower(): p for p, c in zip(meta.project, meta.canonical) if p in members.project.values}

    rows = []
    for rec in osv.itertuples():
        ranges = set(filter(None, rec.range_repos.split("|")))
        named = ranges | set(filter(None, rec.reference_repos.split("|")))
        for repo in named & panel.keys():
            rows.append(
                {"id": rec.id, "package_ecosystem": rec.package_ecosystem, "package": rec.package,
                 "published_at": rec.published_at, "fixed_versions": rec.fixed_versions,
                 "aliases": rec.aliases, "project": panel[repo], "repo": repo,
                 "in_ranges": repo in ranges}
            )
    pairs = pd.DataFrame(rows)
    if pairs.empty:
        return pairs
    print(f"advisory x project candidates: {len(pairs)}", flush=True)

    systems = {v: k for k, v in SYSTEMS.items()}
    with_package = pairs[pairs.package.notna() & pairs.package_ecosystem.isin(systems)]
    wanted = sorted(
        {(systems[e], query_name(e, p))
         for e, p in zip(with_package.package_ecosystem, with_package.package)}
    )
    details = package_details(wanted, accessed)
    kev = kev_ids(freeze)
    fix_tags = load_fix_tags(t0)

    routes, failures, no_fix, not_found, kev_hit = [], [], [], [], []
    for row in pairs.itertuples():
        limit = row.published_at + pd.Timedelta(days=fix_days)
        in_kev = bool({row.id, *row.aliases.split("|")} & kev)
        if pd.isna(row.package) or row.package_ecosystem not in systems:
            # No package deps.dev can speak for: only the record's own range names the repository.
            routes.append("via_repo" if row.in_ranges else "dropped_no_package")
            failures.append(in_kev)
            no_fix.append(False)
            not_found.append(False)
            kev_hit.append(in_kev)
            continue
        detail = details.get(
            (systems[row.package_ecosystem], query_name(row.package_ecosystem, row.package))
        ) or {}
        claims = detail.get("source_repos") or []
        repo_key = f"github.com/{row.repo}"
        if repo_key in claims:
            routes.append("verified")
        elif not claims:
            routes.append("no_claim")
        else:
            routes.append("dropped_other_claim")
        versions = detail.get("versions") or {}
        names = list(filter(None, row.fixed_versions.split("|")))
        no_fix.append(not names)
        kev_hit.append(in_kev)
        tags = {n: fix_tags[(row.repo, n)] for n in names if (row.repo, n) in fix_tags}
        not_found.append(
            bool(names)
            and not any(n in versions or f"v{n}" in versions or n in tags for n in names)
        )
        failures.append(
            in_kev
            or not fix_in_time(versions, row.fixed_versions, limit, row.package_ecosystem, tags)
        )
    pairs["route"] = routes
    pairs["response_failure"] = failures
    pairs["no_fix_listed"] = no_fix
    pairs["fix_not_found"] = not_found
    pairs["in_kev"] = kev_hit
    return pairs


def maintenance_outcomes(t0: str, months: int) -> pd.DataFrame | None:
    path = PROCESSED / f"github_meta_{t0}.parquet"
    if not path.exists():
        return None
    meta = pd.read_parquet(path)
    lo, hi = window(t0, months)
    archived = pd.to_datetime(meta.archivedAt, utc=True, format="ISO8601")
    label = "last_12m" if months == 24 else "short_last_12m"
    label_6m = "last_6m" if months == 24 else "short_last_6m"
    out = pd.DataFrame({"project": meta.project})
    out["gone_now"] = ~meta.resolved
    out["active_at_t0"] = meta.commits_before_180d.fillna(0).gt(0)
    out["archived_before_t0"] = archived.le(lo)
    out["O1a_archived"] = archived.gt(lo) & archived.le(hi)

    # GitHub cannot say when a repository went away; Software Heritage's visits sometimes can.
    # A visit that still found it after the window excludes it. Without a date it stays an event,
    # and `O1a_gone_dated` shows how many of the events have one.
    gone_path = ROOT / "data" / "raw" / "github" / f"gone_{t0}.jsonl"
    last_seen = pd.Series(dtype="datetime64[ns, UTC]")
    first_missing = pd.Series(dtype="datetime64[ns, UTC]")
    if gone_path.exists():
        gone = pd.read_json(gone_path, lines=True).set_index("project")
        last_seen = pd.to_datetime(gone.last_full_visit, utc=True, errors="coerce")
        first_missing = pd.to_datetime(gone.first_not_found_after_last_full, utc=True, errors="coerce")
    seen = out.project.map(last_seen)
    missing = out.project.map(first_missing)
    after_window = seen.gt(hi) | missing.gt(hi)
    out["O1a_gone"] = out.gone_now & ~after_window
    out["O1a_gone_dated"] = out.gone_now & missing.gt(lo) & missing.le(hi)
    out["O1a"] = out.O1a_archived | out.O1a_gone
    # Amendment 1, A4: an event in GH Archive after the window also excludes a gone repository.
    events_path = ROOT / "data" / "raw" / "gharchive" / f"gone_events_{t0}.parquet"
    later_event = out.project.str.lower().isin(
        pd.read_parquet(events_path, columns=["repo"]).repo if events_path.exists() else []
    )
    out["O1a_gone_v2"] = out.O1a_gone & ~later_event
    out["O1a_v2"] = out.O1a_archived | out.O1a_gone_v2

    def quiet(period: str) -> pd.Series:
        return (
            meta.resolved
            & meta[f"commits_{period}"].fillna(0).eq(0)
            & ~meta[f"release_{period}"].fillna(False).astype(bool)
            & ~meta[f"tag_{period}"].fillna(False).astype(bool)
        )

    out["O1b"] = quiet(label)
    # Tags were looked up only for the 12-month reading, so this one can only err upward.
    out["O1b_6m"] = quiet(label_6m)
    out["O1"] = out.O1a_v2 | out.O1b
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--freeze", default="2026-11-03", help="OSV and KEV data freeze")
    ap.add_argument("--accessed", default="2026-11-03", help="date of the deps.dev crawl")
    ap.add_argument("--link-snapshot", default="2024-07-29", help="deps.dev snapshot before t0")
    args = ap.parse_args()

    members, maintenance = eligible_members(args.t0, args.months)

    rows = []

    def add(outcome, stratum, ecosystem, events, base) -> None:
        rows.append(
            {"outcome": outcome, "stratum": stratum, "ecosystem": ecosystem, "events": events,
             "base": base, "rate": round(events / base, 4) if base else None,
             "meets_min": events >= MIN_EVENTS}
        )

    security = security_outcomes(args.t0, args.months, members, args.freeze, args.accessed)
    print(security.route.value_counts().to_string())
    kept = security[security.route.isin({"verified", "no_claim", "via_repo"})]
    packaged = kept[kept.route != "via_repo"]
    # Versions to look for among GitHub tags; `probe_github.py fixtags` reads this.
    packaged[packaged.fix_not_found][["repo", "package", "fixed_versions"]].drop_duplicates().to_parquet(
        PROCESSED / f"fix_lookup_{args.t0}.parquet", index=False
    )
    links = plausible_links(args.link_snapshot)
    by_lower = {p.lower(): p for p in members.project}
    meta_path = PROCESSED / f"github_meta_{args.t0}.parquet"
    if meta_path.exists():
        meta = pd.read_parquet(meta_path, columns=["project", "canonical"]).dropna()
        by_lower |= {c.lower(): p for p, c in zip(meta.project, meta.canonical) if p in set(members.project)}
    mapping = links.assign(project=links.ProjectName.str.lower().map(by_lower)).dropna(subset=["project"])
    mapping["ecosystem"] = mapping.System.map(SYSTEMS)

    for stratum in ["all", *sorted(members.stratum.unique())]:
        part = members if stratum == "all" else members[members.stratum == stratum]
        members_set = set(part.project)
        in_part = kept[kept.project.isin(members_set)]
        with_pkg = packaged[packaged.project.isin(members_set)]
        base_set = set(mapping[mapping.project.isin(members_set)].project)
        base_o2a = len(base_set | set(in_part.project))
        base_o2b = len(base_set | set(with_pkg.project))
        add("O2a", stratum, "all", in_part.project.nunique(), base_o2a)
        add("O2a_verified_only", stratum, "all",
            in_part[in_part.route == "verified"].project.nunique(), base_o2a)
        add("O2a_via_repo_only", stratum, "all",
            in_part[in_part.route == "via_repo"].project.nunique(), base_o2a)
        add("O2b", stratum, "all", with_pkg[with_pkg.response_failure].project.nunique(), base_o2b)
        add("O2b_strict", stratum, "all",
            with_pkg[with_pkg.no_fix_listed | with_pkg.in_kev].project.nunique(), base_o2b)
        add("O2b_fix_not_found", stratum, "all",
            with_pkg[with_pkg.fix_not_found].project.nunique(), base_o2b)
        if stratum == "all":
            for ecosystem, group in mapping.groupby("ecosystem"):
                eco = with_pkg[with_pkg.package_ecosystem == ecosystem]
                add("O2a", "all", ecosystem, eco.project.nunique(), group.project.nunique())
                add("O2b", "all", ecosystem, eco[eco.response_failure].project.nunique(),
                    group.project.nunique())
                add("O2b_strict", "all", ecosystem,
                    eco[eco.no_fix_listed | eco.in_kev].project.nunique(), group.project.nunique())
        if maintenance is not None:
            for name in ("O1", "O1a", "O1a_v2", "O1a_archived", "O1a_gone", "O1a_gone_v2",
                         "O1a_gone_dated", "O1b", "O1b_6m"):
                add(name, stratum, "all", int(part[name].sum()), len(part))
        else:
            for name in ("O1a_archived", "O1a_gone", "O1b"):
                add(f"{name} (pending)", stratum, "all", 0, 0)

    issues_path = PROCESSED / f"github_issues_{args.t0}.parquet"
    if issues_path.exists():
        issues = pd.read_parquet(issues_path).merge(members[["project", "stratum"]], on="project")
        for stratum in ["all", *sorted(members.stratum.unique())]:
            part = issues if stratum == "all" else issues[issues.stratum == stratum]
            for reading in ("draft", "external", "strict"):
                add(f"O1c_{reading}", stratum, "all", int(part[f"unanswered_{reading}"].ge(3).sum()),
                    len(part))

    demand_path = PROCESSED / f"github_demand_{args.t0}.parquet"
    if demand_path.exists():
        demand = pd.read_parquet(demand_path).merge(members[["project", "stratum", "O1b"]], on="project")
        base = demand[demand.n_external.ge(10)]
        for stratum in ["all", *sorted(members.stratum.unique())]:
            part = base if stratum == "all" else base[base.stratum == stratum]
            for name, column, cut in (("O1c_share", "share_unanswered", 0.5),
                                      ("O1c_share_25", "share_unanswered", 0.25),
                                      ("O1c_share_75", "share_unanswered", 0.75),
                                      ("O1c_share_narrow", "share_unanswered_narrow", 0.5)):
                add(name, stratum, "all", int(part[column].ge(cut).sum()), len(part))
            members_part = members if stratum == "all" else members[members.stratum == stratum]
            dormant = set(members_part[members_part.O1b.fillna(False)].project)
            with_demand = set(demand[demand.recent_unanswered.gt(0)].project)
            add("O1b_demand", stratum, "all", len(dormant & with_demand), len(members_part))
            add("O1b_quiet_or_unknown", stratum, "all", len(dormant - with_demand), len(members_part))

    table = pd.DataFrame(rows)
    table.to_csv(PROBES / f"event_counts_{args.t0}.csv", index=False)
    print(table.to_string(index=False))

    draft = members[["project", "stratum"]].copy()
    draft["O2a"] = draft.project.isin(kept.project)
    draft["O2b"] = draft.project.isin(packaged[packaged.response_failure].project)
    draft["O2b_strict"] = draft.project.isin(packaged[packaged.no_fix_listed | packaged.in_kev].project)
    if maintenance is not None:
        draft = draft.merge(
            maintenance[["project", "O1a", "O1a_archived", "O1a_gone", "O1b"]], on="project", how="left"
        )
    draft.to_parquet(PROCESSED / f"outcome_draft_{args.t0}.parquet", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
