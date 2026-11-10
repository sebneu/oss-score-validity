#!/usr/bin/env python3
"""Warning matrix and mechanism table of the case panel, from the readings fixed in docs/decision_log_full.md.

Each cell of the matrix gives the share of the project's list in the cohort at t0 with the same or a worse value. A low
share means the instrument stood out, and a high share means many other projects looked the same. No outcome is read at
cohort level, and nothing here enters the validity statistics.

Outputs:
  paper/figures/case_matrix.pdf, paper/generated/t_mechanism.tex, paper/generated/cases_matrix.tex
  data/processed/cases/matrix.csv     values and shares, for the replication package

Usage:
    python analysis/05_cases/case_matrix.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "data" / "processed" / "features"
CASES = ROOT / "data" / "processed" / "cases"
RAW = ROOT / "data" / "raw" / "cases"
GENERATED = ROOT / "paper" / "generated"
FIGURES = ROOT / "paper" / "figures"
T0 = "2024-08-01"

ROWS = [("axios/axios", "axios"), ("Lightning-AI/pytorch-lightning", "Lightning"), ("ultralytics/ultralytics", "Ultralytics"), ("facebook/react", "React"),
        ("mongodb/mongo", "MongoDB"), ("minio/minio", "MinIO"), ("tukaani-project/xz", "XZ Utils*"), ("tj-actions/changed-files", "tj-actions*")]
COLUMNS = [  # table, component, label, a high value warns less (True) or means importance (False)
    ("crossd", "bus_factor", "Bus factor", True), ("crossd", "support_rate", "Support rate", True), ("crossd", "maturity_level", "Maturity", True),
    ("scorecard", "scorecard_Maintained", "Maintained", True), ("scorecard", "scorecard_aggregate_t0", "Scorecard", True),
    ("opencode", "opencode_maintenance", "oC maint.", True), ("opencode", "opencode_security", "oC security", True),
    ("crossd", "criticality_score", "CrOSSD crit.", False), ("criticality_published", "openssf_criticality_published", "OpenSSF crit.", False),
]
# Worst tenth, worst quarter, worst half, rest: one hue, dark means the instrument stood out.
BINS = [(0.10, "#0d4f8b", "white"), (0.25, "#4a8fd1", "white"), (0.50, "#bcd7f0", "#0b0b0b"), (1.01, "#f1f0ec", "#52514e")]
INK, INK_2 = "#0b0b0b", "#52514e"

MECHANISM = [
    ("axios", "Stolen npm account", [("Signed-Releases", None)]),
    ("Lightning", "PyPI releases, cause open", [("Signed-Releases", None)]),
    ("Ultralytics", "Actions workflows, build cache", [("Dangerous-Workflow", "check"), ("Token-Permissions", "check")]),
    ("React", "Flaw in own code", [("Code-Review", "check"), ("Fuzzing", None)]),
    ("MongoDB", "Flaw in own code", [("Code-Review", "check"), ("Fuzzing", None)]),
    ("MinIO", "End of maintenance", [("Maintained", "check"), ("openCode maintenance", "opencode_maintenance")]),
    ("XZ Utils*", "Payload in test files, trigger in tarballs", [("Code-Review", "check"), ("Binary-Artifacts", "check"), ("Bus factor", "bus")]),
    ("tj-actions*", "Version tags moved", [("Token-Permissions", "check"), ("Dangerous-Workflow", "check")]),
]


def wide(table: str) -> pd.DataFrame:
    frame = pd.read_parquet(FEATURES / f"{table}_{T0}.parquet")
    return frame.pivot_table(index="project", columns="component", values="value", aggfunc="first")


def main() -> int:
    members = pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{T0}.csv").set_index("project")
    tables = {name: wide(name) for name in ("crossd", "scorecard", "opencode", "criticality_published")}
    with (RAW / "instruments.jsonl").open() as fh:
        rebuilt = {}
        for line in fh:
            rec = json.loads(line)
            rebuilt[rec["project"]] = rec
    lists = pd.read_parquet(RAW / "criticality_lists.parquet")
    lists["when"] = pd.to_datetime(lists.collection_date, utc=True)

    def outside_value(project: str, component: str):
        rec = rebuilt[project]
        checks = rec.get("checks") or {}
        if component == "scorecard_Maintained":
            return checks.get("Maintained")
        if component == "scorecard_aggregate_t0":
            weights = {"Maintained": 7.5, "Binary-Artifacts": 7.5, "Dangerous-Workflow": 10, "Token-Permissions": 7.5, "Pinned-Dependencies": 5, "Code-Review": 7.5, "Security-Policy": 5}
            usable = {k: w for k, w in weights.items() if checks.get(k) is not None and checks[k] >= 0}
            return sum(w * checks[k] for k, w in usable.items()) / sum(usable.values()) if usable else None
        if component in ("opencode_maintenance", "opencode_security"):
            return rec["opencode"].get(component)
        if component == "openssf_criticality_published":
            part = lists[(lists.url == f"https://github.com/{project}".lower()) & (lists.when < pd.Timestamp(rec["reading"], tz="UTC"))].sort_values("when")
            return part.default_score.iloc[-1] if len(part) else None
        return None

    cells = []
    for project, label in ROWS:
        inside = project in members.index
        stratum = members.loc[project, "stratum"] if inside else "random_sample"
        peers = members.index[members.stratum == stratum]
        for table, component, name, low_warns in COLUMNS:
            frame = tables[table]
            distribution = frame.reindex(peers)[component].dropna() if component in frame else pd.Series(dtype=float)
            value = (frame.loc[project, component] if project in frame.index and component in frame else None) if inside else outside_value(project, component)
            share = None
            if value is not None and not pd.isna(value) and len(distribution):
                share = float((distribution <= value).mean() if low_warns else (distribution >= value).mean())
            cells.append({"project": project, "label": label, "component": name, "value": value, "share": share, "peers": len(distribution), "list": stratum})
    table = pd.DataFrame(cells)
    CASES.mkdir(parents=True, exist_ok=True)
    table.to_csv(CASES / "matrix.csv", index=False)

    # Months from the reading to the event, shown next to the row label.
    months = {}
    for project, _ in ROWS:
        rec = rebuilt[project]
        start = pd.Timestamp(T0, tz="UTC") if project in members.index else pd.Timestamp(rec["reading"], tz="UTC")
        months[project] = max(round((pd.Timestamp(rec["event"], tz="UTC") - start).days / 30.44), 0)

    labels = [name for _, _, name, _ in COLUMNS]
    fig, ax = plt.subplots(figsize=(3.5, 2.75), constrained_layout=True)
    for y, (project, label) in enumerate(ROWS):
        for x, name in enumerate(labels):
            share = table[(table.project == project) & (table.component == name)].share.iloc[0]
            if share is None or pd.isna(share):
                ax.add_patch(plt.Rectangle((x, y), 1, 1, facecolor="white", edgecolor="white", linewidth=1.5))
                ax.text(x + 0.5, y + 0.5, "–", ha="center", va="center", fontsize=6.5, color=INK_2)
                continue
            fill, ink = next((f, i) for limit, f, i in BINS if share <= limit)
            ax.add_patch(plt.Rectangle((x, y), 1, 1, facecolor=fill, edgecolor="white", linewidth=1.5))
            ax.text(x + 0.5, y + 0.5, f"{100 * share:.0f}", ha="center", va="center", fontsize=6.5, color=ink)
    ax.set_xlim(0, len(labels))
    ax.set_ylim(len(ROWS), 0)
    ax.set_xticks([i + 0.5 for i in range(len(labels))], labels, rotation=55, ha="left", fontsize=6.5, color=INK)
    ax.xaxis.tick_top()
    ax.set_yticks([i + 0.5 for i in range(len(ROWS))], [f"{label} ({months[project]})" for project, label in ROWS], fontsize=7, color=INK)
    ax.tick_params(length=0, pad=2)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.axvline(7, color=INK_2, linewidth=0.8)
    ax.axhline(6, color=INK_2, linewidth=0.8)
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "case_matrix.pdf")
    fig.savefig(CASES / "case_matrix.png", dpi=200)

    def shown(value) -> str:
        return "--" if value is None or pd.isna(value) else f"{value:.0f}"

    def reference(project: str, component: str) -> pd.Series:
        stratum = members.loc[project, "stratum"] if project in members.index else "random_sample"
        peers = members.index[members.stratum == stratum]
        if component == "Bus factor":
            frame, column = tables["crossd"], "bus_factor"
        elif component == "openCode maintenance":
            frame, column = tables["opencode"], "opencode_maintenance"
        else:
            frame, column = tables["scorecard"], f"scorecard_{component}"
        return frame.reindex(peers)[column].dropna()

    shares = {}
    lines = ["\\setlength{\\tabcolsep}{3pt}", "\\begin{tabular}{>{\\raggedright\\arraybackslash}p{1.35cm}>{\\raggedright\\arraybackslash}p{2.15cm}>{\\raggedright\\arraybackslash}p{2.45cm}rr}", "\\toprule", "Case & Mechanism & Component & Value & Share \\\\", "\\midrule"]
    for label, mechanism, components in MECHANISM:
        project = next(p for p, name in ROWS if name == label)
        rec = rebuilt[project]
        for i, (component, source) in enumerate(components):
            number = None
            if source == "check":
                number = (rec.get("checks") or {}).get(component)
                number = None if number is None or number < 0 else number
            elif source == "bus":
                number = rec.get("bus_factor_rebuilt")
            elif source:
                number = rec["opencode"].get(source)
            if source is None:
                value, share = "--", "--"
            else:
                distribution = reference(project, component)
                ratio = float((distribution <= number).mean()) if number is not None and len(distribution) else None
                shares[(label, component)] = ratio
                value, share = shown(number), "--" if ratio is None else f"{100 * ratio:.0f}\\%"
            lines.append((f"{label} & {mechanism}" if i == 0 else " & ") + f" & {component} & {value} & {share} \\\\")
        if label != MECHANISM[-1][0]:
            lines.append("\\addlinespace[2pt]")
    lines += ["\\bottomrule", "\\end{tabular}"]
    (GENERATED / "t_mechanism.tex").write_text("\n".join(lines) + "\n")

    health = table[table.component.isin(labels[:7]) & table.share.notna()]
    maintained = table[table.component == "Maintained"]
    if not (maintained.share == 1).all():
        raise SystemExit("the text says Maintained is at the top value for every case")

    from_raw = pd.read_csv(ROOT / "data" / "probes" / "numbers_from_raw.csv", dtype=str).set_index("macro").value
    xz = rebuilt["tukaani-project/xz"]

    def rate(label: str, component: str) -> str:
        return f"{100 * shares[(label, component)]:.0f}\\%"

    def number(project: str, check: str) -> str:
        return shown(rebuilt[project]["checks"].get(check))

    cell = table.set_index(["project", "component"])
    macros = {
        "CaseMatrixCells": str(len(health)), "CaseMatrixQuarter": str(int((health.share <= 0.25).sum())), "CaseMatrixHalf": str(int((health.share > 0.5).sum())),
        "CaseUltraDw": number("ultralytics/ultralytics", "Dangerous-Workflow"), "CaseUltraDwShare": rate("Ultralytics", "Dangerous-Workflow"),
        "CaseReactReview": number("facebook/react", "Code-Review"), "CaseMongoReview": number("mongodb/mongo", "Code-Review"), "CaseMongoReviewShare": rate("MongoDB", "Code-Review"),
        "CaseMinioMaintained": number("minio/minio", "Maintained"), "CaseMinioOc": shown(rebuilt["minio/minio"]["opencode"]["opencode_maintenance"]),
        "CaseXzReview": number("tukaani-project/xz", "Code-Review"), "CaseXzReviewShare": rate("XZ Utils*", "Code-Review"), "CaseXzBus": shown(xz["bus_factor_rebuilt"]), "CaseXzBusShare": rate("XZ Utils*", "Bus factor"),
        "CaseXzOc": shown(xz["opencode"]["opencode_maintenance"]), "CaseXzTan": from_raw["CaseXzTan"], "CaseXzCommits": from_raw["CaseXzCommits"],
        "CaseXzCrit": f"{cell.loc[('tukaani-project/xz', 'OpenSSF crit.'), 'value']:.2f}", "CaseXzCritShare": f"{100 * cell.loc[('tukaani-project/xz', 'OpenSSF crit.'), 'share']:.0f}\\%",
        "CaseTjToken": number("tj-actions/changed-files", "Token-Permissions"), "CaseTjTokenShare": rate("tj-actions*", "Token-Permissions"), "CaseTjWorkflow": number("tj-actions/changed-files", "Dangerous-Workflow"),
        "CaseAxiosToken": number("axios/axios", "Token-Permissions"),
    }
    (GENERATED / "cases_matrix.tex").write_text("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in macros.items()))
    print(table.pivot(index="label", columns="component", values="share").reindex([l for _, l in ROWS])[labels].round(2).to_string())
    print(macros)
    print("\n".join(lines[5:-2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
