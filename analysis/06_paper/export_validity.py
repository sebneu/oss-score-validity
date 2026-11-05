#!/usr/bin/env python3
"""Tables and macros of the validity results, from data/probes/validity_*.csv.

Outputs:
  paper/generated/validity.tex             macros
  paper/generated/t_v_*.tex                one table per sub-aspect
  analysis/04_validity/measured_validity.csv   the measured validity of each score, for the replication package
  analysis/04_validity/registered_analysis.csv the registered logistic baseline and Holm correction, for the same

Usage:
    python analysis/06_paper/export_validity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROBES = ROOT / "data" / "probes"
GENERATED = ROOT / "paper" / "generated"

KEYS = {"Scorecard Maintained": "Mnt", "openCode maintenance": "Ocm", "CrOSSD maturity": "Mat", "CrOSSD bus factor": "Bus", "CrOSSD elephant factor": "Ele",
        "CrOSSD support rate": "Sup", "openCode issue response": "Ocr", "Scorecard aggregate": "Agg", "openCode security": "Ocs", "CrOSSD criticality": "Crc", "OpenSSF Criticality": "Cro"}
NAMES = {"Scorecard Maintained": "Scorecard Maintained", "openCode maintenance": "openCode maintenance", "CrOSSD maturity": "CrOSSD maturity",
         "CrOSSD bus factor": "CrOSSD bus factor", "CrOSSD elephant factor": "CrOSSD elephant factor", "CrOSSD support rate": "CrOSSD support rate",
         "openCode issue response": "openCode response", "Scorecard aggregate": "Scorecard aggregate", "openCode security": "openCode security",
         "CrOSSD criticality": "CrOSSD criticality", "OpenSSF Criticality": "OpenSSF Criticality"}
OUTCOMES = {"O1": "Maintenance failure", "O1c_share": "Unanswered issues", "O2b": "Unfixed advisory", "I1b": "Later dependents"}
EVIDENCE = {"recorded": "recorded", "reconstructed": "rebuilt"}


def n(value: float) -> str:
    return f"{int(value):,}".replace(",", "{,}")


def f2(value: float) -> str:
    return f"{value:.2f}".replace("-", "$-$")


def f3(value: float) -> str:
    text = f"{value:.3f}"
    return ("0.000" if text == "-0.000" else text).replace("-", "$-$")


def pc(value: float, digits: int = 0) -> str:
    return f"{100 * value:.{digits}f}\\%".replace("-", "$-$")


def ci(point: float, lo: float, hi: float, fmt=f2) -> str:
    return f"{fmt(point)} ({fmt(lo)}, {fmt(hi)})"


def pvalue(value: float) -> str:
    return "$<$0.01" if value < 0.01 else f2(value)


def yes(flag: bool) -> str:
    return "yes" if flag else "no"


def table(path: Path, spec: str, header: list[str], rows: list[list[str]]) -> None:
    lines = [f"\\begin{{tabular}}{{{spec}}}", "\\toprule", " & ".join(header) + " \\\\", "\\midrule"]
    lines += [" & ".join(r) + " \\\\" for r in rows]
    lines += ["\\bottomrule", "\\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    primary = pd.read_csv(PROBES / "validity_primary.csv").set_index("score")
    strata = pd.read_csv(PROBES / "validity_strata.csv").set_index(["score", "stratum"])
    secondary = pd.read_csv(PROBES / "validity_secondary.csv")
    sensitivity = pd.read_csv(PROBES / "validity_sensitivity.csv")
    baseline = pd.read_csv(PROBES / "validity_baseline.csv").set_index(["outcome", "stratum"])
    thresholds = pd.read_csv(PROBES / "validity_thresholds.csv").set_index("operating_point")
    prevalence = pd.read_csv(PROBES / "validity_prevalence.csv")
    simple = pd.read_csv(PROBES / "validity_simple.csv").set_index("score")
    flags = pd.read_csv(PROBES / "validity_flags.csv", index_col=0)["value"]
    features = pd.read_parquet(ROOT / "data" / "processed" / "features_2024-08-01.parquet")
    m: dict[str, str] = {}

    def side(name: str, outcome: str) -> pd.Series:
        return secondary[(secondary.score == name) & (secondary.outcome == outcome)].iloc[0]

    def per_list(score: str, stratum: str) -> str:
        row = strata.loc[(score, stratum)]
        text = f2(row.auroc)
        return text if row.own_statistics else f"({text})"

    # --- macros per primary pair --------------------------------------------------------
    for score, key in KEYS.items():
        r = primary.loc[score]
        m[f"V{key}N"] = n(r.n)
        m[f"V{key}Gain"] = f3(r.gain)
        m[f"V{key}GainLo"] = f3(r.gain_lo)
        m[f"V{key}GainHi"] = f3(r.gain_hi)
        if r.outcome == "I1b":
            m[f"V{key}Rho"] = f2(r.rho)
            m[f"V{key}RhoLo"] = f2(r.rho_lo)
            m[f"V{key}RhoHi"] = f2(r.rho_hi)
            continue
        m[f"V{key}Ev"] = n(r.events)
        m[f"V{key}Auc"] = f2(r.auroc)
        m[f"V{key}Lo"] = f2(r.auroc_lo)
        m[f"V{key}Hi"] = f2(r.auroc_hi)
        m[f"V{key}Starred"] = f2(strata.loc[(score, "most_starred")].auroc)
        m[f"V{key}Sample"] = f2(strata.loc[(score, "random_sample")].auroc)
        if not np.isnan(r.get("auroc_existing", np.nan)):
            m[f"V{key}Ex"] = f2(r.auroc_existing)
            m[f"V{key}ExLo"] = f2(r.existing_lo)
            m[f"V{key}ExHi"] = f2(r.existing_hi)

    binary = primary[primary.outcome != "I1b"]
    words = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
    for score, key in KEYS.items():
        r = simple.loc[score]
        if r.outcome == "I1b":
            m |= {f"V{key}Sim": f2(r.within_rho), f"V{key}SimLo": f2(r.within_rho_lo), f"V{key}SimHi": f2(r.within_rho_hi),
                  f"V{key}RhoDiff": f2(r.rho_diff), f"V{key}RhoDiffLo": f2(r.rho_diff_lo), f"V{key}RhoDiffHi": f2(r.rho_diff_hi)}
            continue
        m |= {f"V{key}Same": f2(r.auroc), f"V{key}SameDays": f2(r.days_since_last_commit_auroc), f"V{key}SameCommits": f2(r.commits_90d_auroc),
              f"V{key}DiffDays": f2(r.days_since_last_commit_diff), f"V{key}DiffDaysLo": f2(r.days_since_last_commit_diff_lo), f"V{key}DiffDaysHi": f2(r.days_since_last_commit_diff_hi),
              f"V{key}Sim": f2(r.within_commits), f"V{key}SimLo": f2(r.within_commits_lo), f"V{key}SimHi": f2(r.within_commits_hi),
              f"V{key}SimDays": f2(r.within_days), f"V{key}SimDaysLo": f3(r.within_days_lo)}
    held = simple[simple.outcome != "I1b"]
    m["VHoldCount"] = words[int(held.holds.astype(bool).sum())]
    m["VHoldCap"] = m["VHoldCount"].capitalize()
    m["VHoldDaysCount"] = words[int(held.holds_days.astype(bool).sum())]
    m["VBeatDays"] = words[int((held[held.outcome != "O2b"].days_since_last_commit_diff_lo > 0).sum())]
    m["VWarnCount"] = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(int(binary.warns.sum()), str(int(binary.warns.sum())))
    m["VWarnCap"] = m["VWarnCount"].capitalize()
    at_low, at_high = binary[binary.auroc_lo > 0.55], binary[binary.auroc_lo > 0.65]
    if set(at_low.index) - set(binary[binary.warns].index) != {"CrOSSD maturity"} or list(at_high.index) != ["Scorecard Maintained"]:
        raise SystemExit("the text names the maturity level at 0.55 and Maintained alone at 0.65")
    m["VWarnAtLow"] = words[len(at_low)]
    m["VAddCount"] = {0: "none", 1: "one", 2: "two", 3: "three"}.get(int(primary.adds.sum()), str(int(primary.adds.sum())))
    m["VBusCover"] = pc(primary.loc["CrOSSD bus factor"].coverage)
    m["VMntPLrt"] = pvalue(primary.loc["Scorecard Maintained"].p_adds_holm)

    # --- Maintained as the worked example ---------------------------------------------
    t = thresholds.loc["Scorecard Maintained = 0"]
    m |= {"VExN": n(t.n), "VExEv": n(t.events), "VExBase": pc(t.event_share, 1), "VExFlag": n(t.tp + t.fp), "VExFlagShare": pc(t.flag_share, 1), "VExTp": n(t.tp),
          "VExFp": n(t.fp), "VExFn": n(t.fn), "VExPpv": pc(t.ppv), "VExSe": pc(t.sensitivity), "VExSp": pc(t.specificity), "VExLift": f"{primary.loc['Scorecard Maintained'].lift:.1f}",
          "VExFpShare": pc(t.fp / (t.tp + t.fp))}
    m["VFailedTop"] = n(flags.failed_top)
    m["VFailedTopShare"] = pc(flags.failed_top / flags.failed)
    m["VOthersTop"] = pc(flags.others_top_share)
    m["VFailedTopStarred"] = pc(flags.failed_top_most_starred)
    m["VFailedTopSample"] = pc(flags.failed_top_random_sample)
    m["VAlarmFew"] = n(flags.alarms_at_most_5)
    m["VAlarmOne"] = n(flags.alarms_one_commit)
    m["VAlarmShareKnown"] = n(flags.alarms_share_known)
    m["VAlarmShareEvent"] = n(flags.alarms_share_event)
    m["VGoneEvents"] = n(flags.gone_events)
    m["VBusMissing"] = n(flags.bus_missing)
    m["VBusMissingEv"] = n(flags.bus_missing_events)
    m["VBusMissingRate"] = pc(flags.bus_missing_rate)
    m["VBusKnownRate"] = pc(flags.bus_known_rate)
    m["VSupMax"] = f"{flags.support_max:.0f}"
    m["VSupRho"] = f2(flags.support_rho)
    m["VSupRhoVol"] = f2(flags.support_rho_volume)

    # --- secondary ---------------------------------------------------------------------
    missing = side("CrOSSD bus factor (missing warns)", "O1")
    m |= {"VBusMissAuc": f2(missing.auroc), "VBusMissLo": f2(missing.auroc_lo), "VBusMissHi": f2(missing.auroc_hi), "VBusMissGain": f3(missing.gain)}
    m["VOcrFailure"] = f2(side("openCode issue response", "O1").auroc)
    days = side("openCode response days", "O1c_share")
    m |= {"VDaysAuc": f2(days.auroc), "VDaysLo": f2(days.auroc_lo), "VDaysHi": f2(days.auroc_hi), "VDaysGain": f3(days.gain)}
    first = side("CrOSSD first response", "O1c_share")
    m |= {"VFirstAuc": f2(first.auroc), "VFirstGain": f3(first.gain)}
    aggregate = side("Scorecard aggregate", "O1")
    m |= {"VAggFailAuc": f2(aggregate.auroc), "VAggFailLo": f2(aggregate.auroc_lo), "VAggFailHi": f2(aggregate.auroc_hi), "VAggFailGain": f3(aggregate.gain)}
    for check, key in (("Security-Policy", "Policy"), ("Code-Review", "Review")):
        m[f"VCheck{key}"] = f2(side(f"Scorecard {check}", "O2b").auroc)
    checks = secondary[secondary.score.str.startswith("Scorecard ") & secondary.outcome.eq("O2b") & secondary.component.str.contains("-")]
    m["VChecksMax"] = f2(checks.auroc.max())
    m["VChecksMaxLo"] = f2(checks.auroc_lo.max())
    m["VChecksCount"] = {6: "six"}.get(len(checks), str(len(checks)))
    for name, key in (("Baseline days_since_last_commit", "Days"), ("Baseline commits_90d", "Commits"), ("Baseline contributors_12m", "Contrib"), ("Baseline stars", "Stars")):
        m[f"VBase{key}"] = f2(side(name, "O1").auroc)
    m["VBaseStarsUnfixed"] = f2(side("Baseline stars", "O2b").auroc)
    m["VBaseContribUnfixed"] = f2(side("Baseline contributors_12m", "O2b").auroc)
    m["VMntUnfixed"] = f2(side("Scorecard Maintained", "O2b").auroc)
    m["VRhoTzero"] = f2(primary.loc["CrOSSD criticality"].rho_t0)
    m["VRTwoBase"] = f2(primary.loc["CrOSSD criticality"].base_r2)
    for key, outcome in (("Failure", "O1"), ("Unanswered", "O1c_share"), ("Unfixed", "O2b")):
        m[f"VBaseline{key}"] = f2(baseline.loc[(outcome, "all")].auroc)

    # --- RQ2 tables ---------------------------------------------------------------------
    def rq2_rows(outcome: str, verdict: bool = True) -> list[list[str]]:
        rows = []
        for score, r in primary[primary.outcome == outcome].iterrows():
            value = ci(r.auroc, r.auroc_lo, r.auroc_hi)
            rows.append([NAMES[score], n(r.events), f"\\textbf{{{value}}}" if r.warns else value, per_list(score, "most_starred"), per_list(score, "random_sample")])
        return rows

    head = ["Score", "Events", "AUROC (95\\% CI)", "Starred", "Filtered"]
    for outcome, name in (("O1", "failure"), ("O1c_share", "unanswered"), ("O2b", "unfixed")):
        table(GENERATED / f"t_v_{name}.tex", "lrlrr", head, rq2_rows(outcome))
    rows = []
    for score, key in KEYS.items():
        if primary.loc[score].outcome != "O1":
            continue
        rows.append([NAMES[score]] + [f2(side(score, o).auroc) if side(score, o).events >= 40 else f"({f2(side(score, o).auroc)})" for o in ("O1a_v2", "O1b_demand", "O1b_quiet")])
    table(GENERATED / "t_v_split.tex", "lrrr", ["Score", "Gone", "Demand", "Quiet"], rows)
    for o, key in (("O1a_v2", "Gone"), ("O1b_demand", "Demand"), ("O1b_quiet", "Quiet")):
        for score, k in (("Scorecard Maintained", "Mnt"), ("openCode maintenance", "Ocm"), ("CrOSSD elephant factor", "Ele"), ("CrOSSD bus factor", "Bus")):
            m[f"V{k}{key}"] = f2(side(score, o).auroc)
    table(GENERATED / "t_v_later.tex", "lrlrl",
          ["Score", "$n$", "$\\rho$ (95\\% CI)", "At $t_0$", "Similar (95\\% CI)"],
          [[NAMES[s], n(r.n), ci(r.rho, r.rho_lo, r.rho_hi), f2(r.rho_t0), ci(simple.loc[s].within_rho, simple.loc[s].within_rho_lo, simple.loc[s].within_rho_hi)] for s, r in primary[primary.outcome == "I1b"].iterrows()])

    # --- RQ3 tables ---------------------------------------------------------------------
    singles = (("Baseline days_since_last_commit", "Days"), ("Baseline commits_90d", "Commits"), ("Baseline contributors_12m", "Contrib."), ("Baseline age_days", "Age"), ("Baseline stars", "Stars"), ("Baseline dependents", "Dep."))
    rows = [[OUTCOMES[o], *[f2(side(name, o).auroc) for name, _ in singles]] for o in ("O1", "O1c_share", "O2b")]
    table(GENERATED / "t_v_baseline.tex", "lrrrrrr", ["Outcome", *[label for _, label in singles]], rows)
    for outcome, key in (("O1c_share", "Unanswered"), ("O2b", "Unfixed")):
        m[f"VSingleDays{key}"] = f2(side("Baseline days_since_last_commit", outcome).auroc)
        m[f"VSingleCommits{key}"] = f2(side("Baseline commits_90d", outcome).auroc)

    rows = []
    for score, r in simple[simple.outcome != "I1b"].iterrows():
        rows.append([NAMES[score], OUTCOMES[r.outcome], f2(r.auroc), f2(r.days_since_last_commit_auroc), f2(r.commits_90d_auroc), ci(r.within_commits, r.within_commits_lo, r.within_commits_hi), yes(bool(r.holds))])
    table(GENERATED / "t_v_similar.tex", "llrrrlc", ["Score", "Outcome", "AUROC", "Days", "Commits", "Similar activity (95\\% CI)", "Holds"], rows)

    rows = []
    for score, r in primary.iterrows():
        base, plus = (r.base_r2, r.plus_r2) if r.outcome == "I1b" else (r.base_auroc, r.plus_auroc)
        rows.append([NAMES[score], OUTCOMES[r.outcome], f2(base), f2(plus), ci(r.gain, r.gain_lo, r.gain_hi, f3), pvalue(r.p_adds_holm), yes(r.adds)])
    registered = primary.reset_index()[["score", "outcome", "n", "base_auroc", "plus_auroc", "base_r2", "plus_r2", "gain", "gain_lo", "gain_hi", "gain_in_sample", "coef", "p_lrt", "p_adds_holm", "adds", "p_warn_holm", "warns"]]
    registered.round(4).to_csv(ROOT / "analysis" / "04_validity" / "registered_analysis.csv", index=False)

    short = {"Scorecard Maintained = 0": "Maintained $=0$", "openCode maintenance, no badge": "oC maint., no badge",
             "openCode maintenance below L2": "oC maint., below L2", "openCode maintenance below L3": "oC maint., below L3",
             "openCode response criterion failed": "oC response failed", "openCode security, no badge": "oC security, no badge",
             "CrOSSD bus factor at most 1": "Bus factor $\\leq 1$", "CrOSSD elephant factor at most 1": "Elephant factor $\\leq 1$"}
    table(GENERATED / "t_v_thresholds.tex", "lrrrlr", ["Flag", "Flagged", "Se", "Sp", "$J$ (95\\% CI)", "PPV"],
          [[short[k], f"{100 * t.flag_share:.0f}", f"{100 * t.sensitivity:.0f}", f"{100 * t.specificity:.0f}", ci(t.J, t.J_lo, t.J_hi), f"{100 * t.ppv:.0f}"] for k, t in thresholds.iterrows()])
    for k, key in (("openCode maintenance, no badge", "OcmFlag"), ("openCode security, no badge", "OcsFlag"), ("openCode maintenance below L3", "OcmThree")):
        m[f"V{key}Share"] = pc(thresholds.loc[k].flag_share)
        m[f"V{key}J"] = f2(thresholds.loc[k].J)

    list_names = {"most_starred": "S", "random_sample": "F"}
    rows = []
    for _, p in prevalence[prevalence.status != "source below 40 events"].iterrows():
        route = f"{list_names[p.source_list]} $\\to$ {list_names[p.target_list]}"
        if p.status == "estimated":
            corrected = f"{100 * p.corrected:.1f} ({100 * p.corrected_lo:.1f}, {100 * p.corrected_hi:.1f})".replace("-", "$-$")
        else:
            corrected = "not estimable" if p.status == "not estimable" else "$J<0$"
        rows.append([short[p.operating_point], route, f"{100 * p.flag_share:.1f}", corrected, f"{100 * p.observed_share:.1f}"])
    table(GENERATED / "t_v_prevalence.tex", "llrlr", ["Flag", "Route", "Flag.", "Corrected (95\\% CI)", "Obs."], rows)
    done = prevalence[prevalence.status == "estimated"]
    m["VPrevDone"] = n(len(done))
    m["VPrevOpen"] = n((prevalence.status != "estimated").sum())
    m["VPrevCover"] = n(((done.corrected_lo <= done.observed_share) & (done.corrected_hi >= done.observed_share)).sum())
    m["VPrevOutside"] = n(((done.corrected < 0) | (done.corrected > 1)).sum())
    a = prevalence[(prevalence.operating_point == "Scorecard Maintained = 0")].set_index("target_list")
    for target, key in (("random_sample", "Sample"), ("most_starred", "Starred")):
        p = a.loc[target]
        m |= {f"VPrev{key}Flag": pc(p.flag_share, 1), f"VPrev{key}Corr": pc(p.corrected, 1), f"VPrev{key}Lo": pc(p.corrected_lo, 1), f"VPrev{key}Hi": pc(p.corrected_hi, 1), f"VPrev{key}Obs": pc(p.observed_share, 1)}

    # --- sensitivity ------------------------------------------------------------------
    rows = []
    for score, part in sensitivity.groupby("score", sort=False):
        counted = part[part.own_statistics.astype(bool)]
        if primary.loc[score].outcome == "I1b":
            rows.append([NAMES[score], "1", f2(part.rho.iloc[0]), "--"])
            continue
        above = int((counted.auroc_lo > 0.60).sum())
        rows.append([NAMES[score], str(len(counted)), f"{f2(counted.auroc.min())} to {f2(counted.auroc.max())}", f"{above} of {len(counted)}"])
    table(GENERATED / "t_v_sensitivity.tex", "lrlc", ["Score", "Variants", "AUROC or $\\rho$", "Warns"], rows)
    below = sensitivity[~sensitivity.own_statistics.astype(bool)]
    m["VSensBelow"] = n(below.outcome.nunique())

    # --- second freeze date ------------------------------------------------------------
    bus = pd.read_csv(PROBES / "validity_bus_documented.csv").set_index("score")
    for key, name in (("VBusDoc", "documented_6"), ("VBusDocSame", "documented_6_same"), ("VBusImpl", "implemented_6")):
        row = bus.loc[name]
        m |= {key + "N": n(row.n), key + "Auc": f2(row.auroc), key + "Lo": f2(row.auroc_lo), key + "Hi": f2(row.auroc_hi),
              key + "Sim": f2(row.within_commits), key + "SimLo": f2(row.within_commits_lo), key + "SimHi": f2(row.within_commits_hi)}
    agreement = pd.read_csv(PROBES / "scorecard_published_agreement.csv", index_col=0)["value"]
    pub = pd.read_csv(PROBES / "validity_scorecard_published.csv").set_index("score")
    pub_checks = pub[pub.index.str.startswith("check ")].dropna(subset=["auroc"])
    m |= {"VPubN": n(int(agreement["published"])), "VPubStarred": n(int(agreement["published_most_starred"])), "VPubSample": n(int(agreement["published_filtered"])),
          "VPubMntExact": f"{100 * float(agreement['maintained_exact']):.0f}\\%", "VPubMntWithin": f"{100 * float(agreement['maintained_within_1']):.0f}\\%",
          "VPubMntRho": f2(float(agreement["maintained_rho"])), "VPubAggRho": f2(float(agreement["aggregate_rho"])),
          "VPubMntAuc": f2(pub.loc["published Maintained"].auroc), "VPubMntRebuilt": f2(pub.loc["rebuilt Maintained"].auroc),
          "VPubAggAuc": f2(pub.loc["published aggregate"].auroc), "VPubAggLo": f2(pub.loc["published aggregate"].auroc_lo), "VPubAggHi": f2(pub.loc["published aggregate"].auroc_hi),
          "VPubAggRebuilt": f2(pub.loc["rebuilt aggregate"].auroc), "VPubAggN": n(pub.loc["published aggregate"].n), "VPubAggEv": n(pub.loc["published aggregate"].events),
          "VPubChecksN": n(len(pub_checks)), "VPubChecksMax": f2(pub_checks.auroc.max())}
    later_base = pd.read_csv(PROBES / "later_dependents_base.csv").set_index("score")
    m |= {"VLatWithPackage": n(later_base.loc["counts"].with_package), "VLatBoth": n(later_base.loc["counts"].both), "VLatCrc": f2(later_base.loc["CrOSSD criticality"].rho),
          "VLatCro": f2(later_base.loc["OpenSSF Criticality"].rho), "VLatDep": f2(later_base.loc["CrOSSD criticality"].rho_t0)}
    robust = pd.read_csv(PROBES / "validity_robustness.csv").set_index("score")
    second = pd.read_parquet(ROOT / "data" / "processed" / "outcomes_2025-01-01.parquet")
    m |= {"VSecProjects": n(len(second)), "VSecFailures": n(second.O1.sum()), "VSecGone": words[int(second.O1a_gone.sum())], "VSecUnanswered": n(second.O1c_share.astype("boolean").sum()), "VSecUnansweredBase": n(second.O1c_share.notna().sum()),
          "VSecBusEv": n(robust.loc["CrOSSD bus factor"].events_all), "VSecMntAuc": f2(robust.loc["Scorecard Maintained"].auroc_all), "VSecMntLo": f2(robust.loc["Scorecard Maintained"].auroc_all_lo), "VSecMntHi": f2(robust.loc["Scorecard Maintained"].auroc_all_hi),
          "VSecDays": f2(robust.loc["Scorecard Maintained"].days_since_last_commit_auroc), "VSecOcrAuc": f2(robust.loc["openCode issue response"].auroc_all), "VSecOcrLo": f2(robust.loc["openCode issue response"].auroc_all_lo),
          "VSecOcrSim": f2(robust.loc["openCode issue response"].within_commits), "VSecOcrSimLo": f2(robust.loc["openCode issue response"].within_commits_lo), "VSecSupAuc": f2(robust.loc["CrOSSD support rate"].auroc_all), "VSecSupSim": f2(robust.loc["CrOSSD support rate"].within_commits),
          "VSecMntSim": f2(robust.loc["Scorecard Maintained"].within_commits), "VSecMntSimLo": f3(robust.loc["Scorecard Maintained"].within_commits_lo)}
    rows = []
    for score, r in robust.iterrows():
        value = ci(r.auroc_all, r.auroc_all_lo, r.auroc_all_hi)
        value = (f"\\textbf{{{value}}}" if r.auroc_all_lo > 0.60 else value) if r.own_statistics else f"({f2(r.auroc_all)})"
        rows.append([NAMES[score], n(r.events_all), value, per_list(score, "most_starred"), f2(r.within_commits)])
    table(GENERATED / "t_v_second.tex", "lrlrr", ["Score", "Events", "AUROC (95\\% CI)", "2024", "Similar"], rows)

    # --- the summary table and its file --------------------------------------------------
    evidence = features.groupby(["instrument", "component"]).evidence.agg(lambda s: s[s != "not_backdatable"].mode().iloc[0] if (s != "not_backdatable").any() else "not_backdatable")
    points = {"Scorecard Maintained": "Scorecard Maintained = 0", "openCode maintenance": "openCode maintenance, no badge", "CrOSSD bus factor": "CrOSSD bus factor at most 1",
              "CrOSSD elephant factor": "CrOSSD elephant factor at most 1", "openCode issue response": "openCode response criterion failed", "openCode security": "openCode security, no badge"}
    rows, records = [], []
    for score, r in primary.iterrows():
        kind = evidence.loc[(r.instrument, r.component)]
        point = points.get(score)
        se = thresholds.loc[point].sensitivity if point else np.nan
        sp = thresholds.loc[point].specificity if point else np.nan
        measure = f"$\\rho$ {f2(r.rho)}" if r.outcome == "I1b" else f2(r.auroc)
        sim = simple.loc[score]
        similar = sim.within_rho if r.outcome == "I1b" else sim.within_commits
        rows.append([NAMES[score], OUTCOMES[r.outcome], EVIDENCE.get(kind, kind), pc(r.coverage), measure, f"{pc(se)} / {pc(sp)}" if point else "--", "$\\rho>0$" if r.outcome == "I1b" and r.warns else yes(r.warns), f2(similar), "$\\rho>0$" if r.outcome == "I1b" and sim.holds else yes(bool(sim.holds))])
        records.append({"score": score, "component": r.component, "outcome": r.outcome, "horizon_months": 24, "evidence": kind, "coverage": round(r.coverage, 4), "n": int(r.n),
                        "auroc": None if r.outcome == "I1b" else round(r.auroc, 4), "auroc_lo": None if r.outcome == "I1b" else round(r.auroc_lo, 4), "auroc_hi": None if r.outcome == "I1b" else round(r.auroc_hi, 4),
                        "rank_correlation": round(r.rho, 4) if r.outcome == "I1b" else None, "operating_point": point, "sensitivity": None if pd.isna(se) else round(se, 4), "specificity": None if pd.isna(sp) else round(sp, 4),
                        "pr_auc": None if r.outcome == "I1b" else round(r.pr_auc, 4), "lift_worst_decile": None if r.outcome == "I1b" else round(r.lift, 4),
                        "registered_gain": round(r.gain, 4), "registered_gain_lo": round(r.gain_lo, 4), "registered_gain_hi": round(r.gain_hi, 4), "warns": bool(r.warns), "similar_activity": round(similar, 4), "holds_at_similar_activity": bool(sim.holds), "adds_registered_model": bool(r.adds)})
    table(GENERATED / "t_v_summary.tex", "llrrrccrc", ["Score", "Outcome", "Evidence", "Coverage", "AUROC", "Se / Sp", "Warns", "Similar", "Holds"], rows)
    summary = GENERATED / "t_v_summary.tex"
    summary.write_text(summary.read_text().replace(f"{NAMES['CrOSSD criticality']} &", f"\\midrule\n{NAMES['CrOSSD criticality']} &"))
    pd.DataFrame(records).to_csv(ROOT / "analysis" / "04_validity" / "measured_validity.csv", index=False)

    out = GENERATED / "validity.tex"
    out.write_text("% Generated by analysis/06_paper/export_validity.py. Do not edit.\n" + "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(m.items())))
    print(f"{out.relative_to(ROOT)}: {len(m)} macros")
    return 0


if __name__ == "__main__":
    sys.exit(main())
