#!/usr/bin/env python3
"""Write every number and generated table of the manuscript into paper/generated/.

No number enters the paper by hand. A quantity the text needs gets a macro here.

Reads outcome labels and availability counts only, and no score value: no association
between a score and an outcome is computed before the instruments exist and only
under the frozen analysis plan.

Outputs:
  paper/generated/numbers.tex       \\newcommand macros
  paper/generated/t_*.tex           mini tables
  paper/figures/crossd_coverage.pdf

Usage:
    python analysis/06_paper/export_macros.py --t0 2024-08-01
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / "data" / "probes"
PROCESSED = ROOT / "data" / "processed"
GENERATED = ROOT / "paper" / "generated"
LISTS = {"most_starred": "Most-starred", "random_sample": "Filtered sample"}


def thousands(value: int) -> str:
    return f"{int(value):,}".replace(",", "{,}")


def percent(numerator: float, denominator: float, digits: int = 0) -> str:
    return f"{100 * numerator / denominator:.{digits}f}\\%"


def table(path: Path, spec: str, header: list[str], rows: list[list[str]], total: list[str] | None = None) -> None:
    lines = [f"\\begin{{tabular}}{{{spec}}}", "\\toprule", " & ".join(header) + " \\\\", "\\midrule"]
    lines += [" & ".join(r) + " \\\\" for r in rows]
    if total:
        lines += ["\\midrule", " & ".join(f"\\textbf{{{c}}}" for c in total) + " \\\\"]
    lines += ["\\bottomrule", "\\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    args = ap.parse_args()
    t0 = args.t0
    GENERATED.mkdir(parents=True, exist_ok=True)
    (ROOT / "paper" / "figures").mkdir(parents=True, exist_ok=True)
    shutil.copy(PROBES / "crossd_coverage.pdf", ROOT / "paper" / "figures" / "crossd_coverage.pdf")

    m: dict[str, str] = {}

    # --- panel and cohort -------------------------------------------------------------
    coverage = pd.read_parquet(PROBES / "crossd_coverage.parquet")
    per_project = coverage.drop_duplicates("project")
    m["PanelWithSnapshots"] = thousands(len(per_project))
    m["PanelSnapshotCount"] = thousands(len(coverage))
    m["PanelScansMean"] = f"{len(coverage) / len(per_project):.0f}"
    counts = per_project.stratum.value_counts()
    m["ListStarred"] = thousands(counts["most_starred"])
    m["ListSample"] = thousands(counts["random_sample"])

    last = coverage[coverage.stratum == "random_sample"].groupby("project").snapshot_utc.max()
    m["StallCount"] = thousands((last.dt.date.astype(str) == "2024-08-09").sum())

    candidates = pd.read_csv(PROBES / "crossd_t0_candidates.csv")
    row = candidates[(candidates.t0 == t0)].set_index("stratum")
    m["SnapshotInWindow"] = thousands(row.loc["all", "snapshot_in_window"])
    m["ReadAfterFreeze"] = thousands(row.loc["all", "of_which_observed_after_t0"])
    m["ObservedInWindow"] = thousands(row.loc["all", "observed_in_window"])
    m["MedianAgeDays"] = f"{row.loc['all', 'median_age_days']:.1f}"

    near = coverage[coverage.observed_ts.notna() & (coverage.snapshot_utc >= "2024-07-01") & (coverage.snapshot_utc < "2024-08-11")]
    delay = (near.observed_ts - near.snapshot_ts) / 86400
    m["DelayMedian"] = f"{delay.median():.1f}"
    m["DelayPNinety"] = f"{delay.quantile(0.9):.1f}"
    m["DelayMax"] = f"{delay.max():.0f}"

    cohort = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{t0}.csv")
    cohort_counts = cohort.stratum.value_counts()
    m["Cohort"] = thousands(len(cohort))
    m["CohortStarred"] = thousands(cohort_counts["most_starred"])
    m["CohortSample"] = thousands(cohort_counts["random_sample"])

    # --- integrity of the record ------------------------------------------------------
    integrity = json.loads((PROBES / "crossd_integrity.json").read_text())
    r1, r3 = integrity["R1"], integrity["R3"]
    m["BakRecords"] = thousands(r1["bak_records"])
    m["BakMaxDelay"] = f"{r1['max_days']:.0f}"
    m["BakOverSixty"] = str(r1["over_60_days"])
    m["CheckProjects"] = str(r3["projects"])
    m["CheckWithinOne"] = str(r3["within_1pct_of_then"])
    m["CheckGrew"] = str(r3["projects_that_grew_by_over_2pct"])
    m["CheckCloser"] = str(r3["of_those_closer_to_then"])
    m["CheckErrorThen"] = f"{100 * r3['median_error_to_then']:.2f}\\%"
    m["CheckErrorLate"] = f"{100 * r3['median_error_to_late']:.1f}\\%"
    point = json.loads((PROBES / "crossd_pointintime.json").read_text())
    m["PointWorkflowRuns"] = thousands(point["P1_workflow_runs"]["workflow_runs_checked"])
    m["PointDateFields"] = thousands(point["P2_repo_payload"]["date_fields_checked"])
    m["PointSnapshots"] = str(point["P2_repo_payload"]["snapshots_sampled"])

    s1 = integrity["S1"]["random_sample"]
    m["SampleMedianStars"] = thousands(s1["stars_today_quantiles"]["0.5"])
    m["SampleLowStars"] = thousands(s1["stars_today_quantiles"]["0.05"])
    m["SampleForks"] = str(s1["forks"])
    m["StarredLowStars"] = thousands(integrity["S1"]["most_starred"]["stars_today_quantiles"]["0.05"])

    s2 = integrity["S2"]
    commits = s2["by_commits_quartile_before_t0"]
    m["BusMissingLowest"] = f"{100 * commits['q1']['no_bus']:.0f}\\%"
    m["BusMissingHighest"] = f"{100 * commits['q4']['no_bus']:.0f}\\%"
    issues_bins = s2["by_issues_in_window"]
    m["CritMissingNoIssues"] = f"{100 * issues_bins['0']['no_crit']:.0f}\\%"
    m["CritMissingManyIssues"] = f"{100 * issues_bins['100+']['no_crit']:.0f}\\%"

    # --- metric coverage in the cohort ------------------------------------------------
    end = pd.Timestamp(t0, tz="UTC").timestamp()
    seen = coverage[(coverage.observed_ts <= end) & (coverage.observed_ts > end - 14 * 86400)]
    latest = seen.sort_values("observed_ts").groupby("project").tail(1)
    latest = latest[latest.project.isin(cohort.project)]
    rows = []
    for label, column in (("Maturity level", "src_maturity_level"), ("Elephant factor", "src_elephant_factor"),
                          ("Support rate", "src_support_rate"), ("Criticality score", "src_criticality_score"),
                          ("Bus factor", "src_contributions_distributions")):
        rows.append([label] + [thousands(latest[latest.stratum == s][column].notna().sum()) for s in LISTS])
    table(GENERATED / "t_coverage.tex", "lrr", ["Metric", "Most-starred", "Filtered"], rows,
          ["Projects"] + [thousands(cohort_counts[s]) for s in LISTS])

    # --- bus factor fidelity -----------------------------------------------------------
    fidelity_path = PROBES / "bus_factor_fidelity.csv"
    if fidelity_path.exists():
        fid = pd.read_csv(fidelity_path)
        web = fid[(fid.reading == "web_flow") & (fid.stratum == "all")].set_index("months")
        stored_row = fid[fid.reading == "stored"].iloc[0]
        m["BusRebuiltBoth"] = thousands(web.loc[1, "both"])
        m["BusRebuiltExact"] = f"{100 * web.loc[1, 'exact']:.0f}\\%"
        m["BusRebuiltWithin"] = f"{100 * web.loc[1, 'within_1']:.0f}\\%"
        m["BusRebuiltRho"] = f"{web.loc[1, 'spearman']:.2f}"
        m["BusRebuiltExactSix"] = f"{100 * web.loc[6, 'exact']:.0f}\\%"
        m["BusRebuiltExactTwelve"] = f"{100 * web.loc[12, 'exact']:.0f}\\%"
        m["BusStored"] = thousands(stored_row.both)
        m["BusZero"] = thousands(stored_row.zero)
        m["BusZeroAuthors"] = thousands(stored_row.zero_several_authors)

    # --- freshness of published values --------------------------------------------------
    fresh_path = PROBES / "freshness.csv"
    if fresh_path.exists():
        fresh = pd.read_csv(fresh_path).set_index("stratum")
        for suffix, stratum in (("", "all"), ("Starred", "most_starred"), ("Sample", "random_sample")):
            m[f"FreshRepos{suffix}"] = thousands(fresh.loc[stratum, "repositories"])
            m[f"FreshScorecard{suffix}"] = thousands(fresh.loc[stratum, "scorecard_published"])
        m["FreshAgeMedian"] = f"{fresh.loc['all', 'age_median']:.0f}"
        m["FreshAgeMax"] = thousands(fresh.loc["all", "age_max"])
        m["FreshOverYear"] = str(int(fresh.loc["all", "over_365d"]))
        m["FreshCriticality"] = thousands(fresh.loc["all", "criticality_listed"])

    back_path = PROBES / "backdating.csv"
    if back_path.exists():
        back = pd.read_csv(back_path)
        groups = {"CrOSSD": ["CrOSSD"], "OpenSSF Scorecard": ["Scorecard"], "Criticality Score": ["Criticality Score"], "openCode badges": ["openCode maintenance", "openCode security"]}
        rows = []
        for label, members in groups.items():
            part = back[back.instrument.isin(members)]["class"].value_counts()
            rows.append([label] + [str(part.get(k, 0)) if part.get(k, 0) else "--" for k in ("recorded", "rebuilt", "partial", "none")])
        table(GENERATED / "t_backdating.tex", "lrrrr", ["Instrument", "Recorded", "Rebuilt", "Partly", "Not"], rows)
        checks = back[back.instrument == "Scorecard"]
        kept = checks[checks["class"] != "none"]
        m["BackChecksAll"] = str(len(checks))
        m["BackChecksKept"] = str(len(kept))
        m["BackWeightShare"] = percent(kept.weight.sum(), checks.weight.sum())
    issues_path = PROBES / "fidelity_criticality_issues.csv"
    if issues_path.exists():
        issues = pd.read_csv(issues_path).set_index("statistic")["value"]
        m["CritListRows"] = thousands(issues["list_rows"])
        m["CritZeroAll"] = percent(issues["list_all_three_zero"], 1)
        m["CritZeroSample"] = percent(issues["sample_zero_closed"], 1)
    lists_path = PROBES / "criticality_lists.csv"
    if lists_path.exists():
        lists = pd.read_csv(lists_path).set_index("list_date")
        m["CritZeroBefore"] = percent(lists.loc["2024-05-02", "zero_all"], 1)
        m["CritZeroAfter"] = percent(lists.loc["2024-05-18", "zero_all"], 1)
        m["CritZeroLater"] = percent(lists.loc["2025-04-17", "zero_all"], 1)
    crit_path = PROBES / "fidelity_criticality_t0.csv"
    if crit_path.exists():
        crit = pd.read_csv(crit_path).set_index("signal")
        m["CritTzeroN"] = thousands(crit.loc["score", "n"])
        for macro, signal in (("Score", "score"), ("Mentions", "score_with_mentions"), ("Contributors", "contributor_count"), ("Commits", "commit_frequency"),
                              ("Closed", "closed_issues_count"), ("Updated", "updated_issues_count"), ("Comments", "comment_frequency")):
            m[f"CritTzeroRho{macro}"] = f"{crit.loc[signal, 'spearman']:.2f}"
        m["CritTzeroRhoContributors"] = f"{crit.loc['contributor_count', 'spearman']:.3f}"
        m["CritMedianClosedOurs"] = f"{crit.loc['closed_issues_count', 'median_ours']:.0f}"
        m["CritMedianClosedPub"] = f"{crit.loc['closed_issues_count', 'median_published']:.0f}"
        m["CritCoverStarred"] = thousands(crit.loc["coverage_most_starred", "n"])
        m["CritCoverSample"] = thousands(crit.loc["coverage_random_sample", "n"])
    fid_path = PROBES / "fidelity_scorecard.csv"
    if fid_path.exists():
        fid = pd.read_csv(fid_path).set_index("check")
        keep = ["Maintained", "Binary-Artifacts", "Dangerous-Workflow", "Token-Permissions", "Pinned-Dependencies", "Code-Review", "Security-Policy"]
        rows = [[c, str(int(fid.loc[c, "n"])), percent(fid.loc[c, "exact"], 1), percent(fid.loc[c, "within_1"], 1)] for c in keep]
        table(GENERATED / "t_fidelity.tex", "lrrr", ["Check", "$n$", "Exact", "Within 1"], rows)
        m["FidSample"] = str(int(fid.loc["Maintained", "projects"]))
        m["FidMaintExact"] = percent(fid.loc["Maintained", "exact"], 1)
        m["FidMaintWithin"] = percent(fid.loc["Maintained", "within_1"], 1)
    stats_path = PROBES / "scorecard_t0_stats.csv"
    if stats_path.exists():
        stats = pd.read_csv(stats_path).iloc[0]
        m["BackCiResults"] = thousands(stats.ci_results)
        m["BackCiZero"] = thousands(stats.ci_zero)
        m["BackPolicyDropped"] = thousands(stats.policy_dropped)
        m["BackRunsDone"] = thousands(stats.usable)
        m["BackRunsAll"] = thousands(stats.runs)
        m["BackRunsFailed"] = thousands(stats.runs - stats.usable)
        scorecard = pd.read_parquet(ROOT / "data" / "processed" / "features" / "scorecard_2024-08-01.parquet")
        by_rule = scorecard[(scorecard.component == "scorecard_Maintained") & scorecard.value.notna()].project.nunique()
        m["BackRecreated"] = thousands(stats.runs - by_rule)
    stars_path = PROBES / "stars_gharchive_check.csv"
    if stars_path.exists():
        stars = pd.read_csv(stars_path).iloc[0]
        m["StarsRho"] = f"{stars.spearman:.2f}"
        m["StarsRatio"] = f"{stars.ratio_median:.2f}"

    # --- outcomes ---------------------------------------------------------------------
    outcomes = pd.read_parquet(PROCESSED / f"outcomes_{t0}.parquet")
    def events(col: str, frame: pd.DataFrame = outcomes) -> int:
        return int(frame[col].astype("boolean").fillna(False).sum())
    starred = outcomes[outcomes.stratum == "most_starred"]
    sample = outcomes[outcomes.stratum == "random_sample"]
    for name, col in (("Failure", "O1"), ("Archived", "O1a_archived"), ("GoneFrozen", "O1a_gone"), ("Deleted", "O1a_v2"),
                      ("Dormant", "O1b"), ("DormantDemand", "O1b_demand"), ("DormantQuiet", "O1b_quiet"), ("DormantUnknown", "O1b_unknown"),
                      ("Severe", "O2a"), ("SevereVerified", "O2a_verified"), ("Unfixed", "O2b"), ("UnfixedDrafted", "O2b_drafted"),
                      ("Unanswered", "O1c_share"), ("FixedCount", "O1c")):
        m[f"Ev{name}"] = thousands(events(col))
        m[f"Ev{name}Starred"] = thousands(events(col, starred))
        m[f"Ev{name}Sample"] = thousands(events(col, sample))
    m["BaseSevere"] = thousands(outcomes.in_O2_base.sum())
    m["BaseUnfixed"] = thousands(outcomes.in_O2b_base.sum())
    m["BaseUnfixedStarred"] = thousands(starred.in_O2b_base.sum())
    m["BaseUnfixedSample"] = thousands(sample.in_O2b_base.sum())
    share_base = outcomes[outcomes.n_external.ge(10)]
    m["BaseUnanswered"] = thousands(len(share_base))
    m["BaseUnansweredStarred"] = thousands((share_base.stratum == "most_starred").sum())
    m["BaseUnansweredSample"] = thousands((share_base.stratum == "random_sample").sum())
    m["BaseLater"] = thousands(outcomes.I1b.notna().sum())
    m["BaseLaterStarred"] = thousands(starred.I1b.notna().sum())
    m["BaseLaterSample"] = thousands(sample.I1b.notna().sum())
    m["BaseLaterBoth"] = thousands((outcomes.I1b.notna() & outcomes.I1b_t0.notna()).sum())
    both = outcomes.dropna(subset=["I1b", "I1b_t0"])
    m["LaterRankCorr"] = f"{both.I1b.corr(both.I1b_t0, method='spearman'):.2f}"
    m["ImpactFrozen"] = thousands(outcomes.I1.notna().sum())

    table(
        GENERATED / "t_events.tex", "lrrrr", ["Outcome", "All", "Most-starred", "Filtered", "Base"],
        [
            ["Maintenance failure", m["EvFailure"], m["EvFailureStarred"], m["EvFailureSample"], m["Cohort"]],
            ["\\quad archived or gone", m["EvDeleted"], m["EvDeletedStarred"], m["EvDeletedSample"], m["Cohort"]],
            ["\\quad dormant", m["EvDormant"], m["EvDormantStarred"], m["EvDormantSample"], m["Cohort"]],
            ["Unanswered issues", m["EvUnanswered"], m["EvUnansweredStarred"], m["EvUnansweredSample"], m["BaseUnanswered"]],
            ["Unfixed advisory", m["EvUnfixed"], m["EvUnfixedStarred"], m["EvUnfixedSample"], m["BaseUnfixed"]],
        ],
    )
    table(
        GENERATED / "t_dormancy.tex", "lrr", ["Dormant projects", "Most-starred", "Filtered"],
        [
            ["With unanswered demand", m["EvDormantDemandStarred"], m["EvDormantDemandSample"]],
            ["Quiet, no such issue", m["EvDormantQuietStarred"], m["EvDormantQuietSample"]],
            ["No issue data", m["EvDormantUnknownStarred"], m["EvDormantUnknownSample"]],
        ],
        ["Total", m["EvDormantStarred"], m["EvDormantSample"]],
    )

    # The fixed count against the share, by issue volume.
    issues = pd.read_parquet(PROCESSED / f"github_issues_{t0}.parquet", columns=["project", "issue_count"])
    volume = outcomes.merge(issues, on="project", how="inner")
    volume = volume[volume.issue_count.notna()]
    bins = [(10, 49, "10--49"), (50, 199, "50--199"), (200, 999, "200--999"), (1000, 10**9, "1{,}000 or more")]
    rows = []
    for low, high, label in bins:
        part = volume[(volume.issue_count >= low) & (volume.issue_count <= high)]
        in_base = part[part.n_external.ge(10)]
        rows.append([label, thousands(len(part)), percent(events("O1c", part), len(part)),
                     percent(events("O1c_share", in_base), len(in_base))])
    low_bin = volume[(volume.issue_count >= 1000)]
    m["FixedCountTop"] = percent(events("O1c", low_bin), len(low_bin))
    m["FixedCountAll"] = percent(events("O1c", volume), len(volume))
    m["FixedCountBase"] = thousands(len(volume))

    # --- advisories and packages ------------------------------------------------------
    from_raw = pd.read_csv(PROBES / "numbers_from_raw.csv", dtype=str).set_index("macro").value
    m.update(from_raw[~from_raw.index.str.startswith("Case")])

    bq = json.loads((PROBES / "depsdev_bq.json").read_text())
    m["DepsdevSnapshots"] = str(bq["snapshots"]["count"])

    # --- claims -----------------------------------------------------------------------
    with (ROOT / "data" / "claims" / "claims.csv").open(encoding="utf-8") as fh:
        claims = list(csv.DictReader(fh))
    m["ClaimRows"] = str(len(claims))
    crossd = [c for c in claims if c["instrument"] == "CrOSSD"]
    m["ClaimsCrossd"] = str(len(crossd))
    m["ClaimsCrossdRisk"] = str(sum(c["claim_type"] == "risk" for c in crossd))
    chosen = [("OpenSSF Scorecard", "Scorecard", "Maintained", "Maintained", None),
              ("OpenSSF Criticality Score", "Criticality", "score", "Score", None),
              ("openCode badges", "openCode", "Aktive Wartung L1", "Maintenance badge, level 1", "The project meets the minimum requirements for a maintained project."),
              ("CrOSSD", "CrOSSD", "support_rate", "Support rate", None),
              ("CrOSSD", "", "bus_factor_score", "Bus factor", None),
              ("CrOSSD", "", "elephant_factor", "Elephant factor", None),
              ("CrOSSD", "", "criticality_score", "Criticality score", None)]
    outcome_names = (("O1c", "Unanswered issues"), ("O1", "Maintenance failure"), ("O2", "Unfixed advisory"), ("I", "Later dependents"))
    rows = []
    for inst, label, comp, name, translation in chosen:
        rec = next(c for c in claims if c["instrument"] == inst and c["component"] == comp)
        quote = translation or rec["quote"]
        quote = quote.replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")
        if quote.startswith("To less"):
            quote = quote.replace("To less", "To less [sic]")
        tested = next(text for code, text in outcome_names if rec["tested_against"].startswith(code))
        short = {"OpenSSF Scorecard": "Scorecard", "OpenSSF Criticality Score": "Criticality", "openCode badges": "openCode", "CrOSSD": "CrOSSD"}[inst]
        rows.append([f"{short} {name[0].lower() + name[1:] if name != 'Maintained' else name}", f"``{quote}''", tested, "yes" if rec["claim_type"] == "risk" else "no"])
    left = ">{\\raggedright\\arraybackslash}p"
    table(GENERATED / "t_claims.tex", f"{left}{{1.6cm}}{left}{{3.75cm}}{left}{{1.6cm}}c", ["Component", "Claim in its documentation", "Tested against", "Risk"], rows)

    out = GENERATED / "numbers.tex"
    out.write_text("% Generated by analysis/06_paper/export_macros.py. Do not edit.\n" + "".join(
        f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(m.items())
    ))
    print(f"{out.relative_to(ROOT)}: {len(m)} macros")
    for k in ("Cohort", "EvFailure", "EvDormantDemand", "EvDormantQuiet", "EvUnanswered", "BaseUnanswered", "EvUnfixed", "BaseLater", "LaterRankCorr", "FixBeforeAdvisory", "FixOverNinety", "LodashClaims"):
        print(k, m[k])
    return 0


if __name__ == "__main__":
    sys.exit(main())
