#!/usr/bin/env python3
"""Collect what each instrument claims to measure (RQ1a).

Quotes are cut out of the downloaded documentation by anchors instead of being typed in,
so a quote cannot drift from its source. A missing anchor is an error. The documents are
pinned to a commit where one exists and cached in `data/raw/docs/`; `accessed` is the
date of the first download.

`tested_against` is our mapping of the claim to an outcome (the outcomes of the paper), not
part of the quote. `claim_type` says whether the documentation states a risk or
consequence ("risk") or only says what the value describes ("descriptive"). That
distinction is ours too, and it decides how far a validity test applies to the claim.

Output: data/claims/claims.csv
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "data" / "raw" / "docs"
OUT = ROOT / "data" / "claims" / "claims.csv"

SCORECARD = "ab792da5b906666164d82faa3378374fc664aad0"
CRITICALITY = "0e76c6a99d865dddcbd89dff4117f0a54b1abfb8"
CROSSD = "604a0c664f9998d4945aa9f4fe221888d8768675"

SCORECARD_RAW = f"https://raw.githubusercontent.com/ossf/scorecard/{SCORECARD}"
CRITICALITY_RAW = f"https://raw.githubusercontent.com/ossf/criticality_score/{CRITICALITY}"
CROSSD_RAW = (
    f"https://raw.githubusercontent.com/FH-CrOSSD/crossd/{CROSSD}/frontend/src/lib/md/metric"
)
OPENCODE = "https://opencode.de/de/wissen/softwareverzeichnis/badges"
CROSSD_PUBLIC = "https://health.crossd.tech/doc"

# Plan §3 groups: which outcome each Scorecard check is tested against, and whether the
# check can be backdated at all (`—` = excluded and reported).
SCORECARD_CHECKS = {
    "Maintained": "O1",
    "Security-Policy": "O2",
    "License": "O2",
    "Binary-Artifacts": "O2",
    "Dangerous-Workflow": "O2",
    "Token-Permissions": "O2",
    "Pinned-Dependencies": "O2",
    "Dependency-Update-Tool": "O2",
    "Packaging": "O2",
    "Code-Review": "O2",
    "Signed-Releases": "O2",
    "Vulnerabilities": "O2",
    "Fuzzing": "O2",
    "Branch-Protection": "—",
    "Contributors": "—",
    "Webhooks": "—",
    "CI-Tests": "—",
    "SAST": "—",
    "CII-Best-Practices": "—",
    "SBOM": "—",
}

# instrument, component, document, start anchor, end anchor, tested against, claim type
ANCHORED = [
    ("OpenSSF Scorecard", "aggregate", "scorecard_readme",
     "Scorecard also produces an aggregate score", "weighted by risk.", "O2", "descriptive"),
    ("OpenSSF Scorecard", "aggregate (documented caveat)", "scorecard_readme",
     "Aggregate scores in particular", "a repository is or is not doing.", "O2", "descriptive"),
    ("OpenSSF Scorecard", "all checks (documented caveat)", "scorecard_readme",
     "The checks themselves are heuristics", "false negatives.", "—", "descriptive"),
    ("OpenSSF Criticality Score", "score", "criticality_readme",
     "A project's criticality score defines", "of a project.", "I1", "descriptive"),
    ("openCode badges", "Aktive Wartung L1", "opencode",
     "Das Projekt erfüllt die Mindestanforderungen", "gewartetes Projekt.", "O1", "descriptive"),
    ("openCode badges", "Aktive Wartung L2", "opencode",
     "Das Projekt erfüllt die Anforderungen für ein zuverlässig", "gewartetes Projekt.", "O1",
     "descriptive"),
    ("openCode badges", "Aktive Wartung L3", "opencode",
     "Das Projekt erfüllt die Anforderungen für ein krisensicher", "gewartetes Projekt.", "O1",
     "descriptive"),
    ("openCode badges", "Sicherheit L1-L3", "opencode",
     "Das Sicherheitsbadge gibt Auskunft", "Repositorys.", "O2", "descriptive"),
    ("CrOSSD", "criticality_score", "crossd_criticality_score",
     "This metric represents a project's influence", "importance.", "I1", "descriptive"),
    ("CrOSSD", "maturity_level", "crossd_maturity_level",
     "The returned level score represents", "the maturity.", "O1", "descriptive"),
    ("CrOSSD", "support_rate", "crossd_support_rate",
     "A high support rate implies", "and developers.", "O1c", "descriptive"),
    ("CrOSSD", "project_velocity", "crossd_project_velocity",
     "Velocity refers to the development speed", "GitHub repositories.", "O1", "descriptive"),
    ("CrOSSD", "bus_factor_score", "crossd_contributions_distributions",
     "To less maintainers propose", "project to stall", "O1", "risk"),
    ("CrOSSD", "elephant_factor", "crossd_elephant_factor",
     "a project with a low elephant factor", "small number of companies.", "O1", "risk"),
    ("CrOSSD", "github_community_health_percentage", "crossd_github_community_health_percentage",
     "This percentage score represents", "contributing file.", "O1", "descriptive"),
]

SOURCES = {
    "scorecard_checks": (f"{SCORECARD_RAW}/docs/checks.md", SCORECARD),
    "scorecard_readme": (f"{SCORECARD_RAW}/README.md", SCORECARD),
    "criticality_readme": (f"{CRITICALITY_RAW}/README.md", CRITICALITY),
    "opencode": (OPENCODE, ""),
}
for _metric in (
    "criticality_score",
    "maturity_level",
    "support_rate",
    "project_velocity",
    "contributions_distributions",
    "elephant_factor",
    "github_community_health_percentage",
):
    SOURCES[f"crossd_{_metric}"] = (f"{CROSSD_RAW}/{_metric}.md", CROSSD)


def fetch(key: str) -> tuple[str, str]:
    """Document text and the date it was first downloaded."""
    url = SOURCES[key][0]
    suffix = ".html" if key == "opencode" else ".md"
    path = DOCS / f"{key}{suffix}"
    stamp = path.with_suffix(path.suffix + ".accessed")
    if not path.exists():
        DOCS.mkdir(parents=True, exist_ok=True)
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        stamp.write_text(f"{datetime.now(UTC):%Y-%m-%d}\n")
    return path.read_text(encoding="utf-8"), stamp.read_text().strip()


def plain(text: str, is_html: bool) -> str:
    """Collapse to running text: tags and link targets go, the words stay untouched."""
    if is_html:
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    else:
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[\^[^\]]*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([.,;:])", r"\1", text)


def scorecard_rows(doc: str) -> list[dict]:
    """First sentence and stated risk level of every check section."""
    rows = []
    sections = re.split(r"^## ", doc, flags=re.M)
    by_name = {s.split(None, 1)[0]: s for s in sections[1:]}
    if set(by_name) != set(SCORECARD_CHECKS):
        raise SystemExit(f"Scorecard checks changed: {set(by_name) ^ set(SCORECARD_CHECKS)}")
    for name, tested in SCORECARD_CHECKS.items():
        section = by_name[name]
        risk = re.search(r"Risk: `(\w+)`\s*\(([^)]*)\)", section, flags=re.S)
        if not risk:
            raise SystemExit(f"no risk line in Scorecard check {name}")
        body = plain(section[risk.end() :], is_html=False)
        sentence = re.match(r"(.+?\.)(?=\s+[A-Z]|\s*$)", body)
        if not sentence:
            raise SystemExit(f"no first sentence in Scorecard check {name}")
        rows.append(
            {
                "instrument": "OpenSSF Scorecard",
                "component": name,
                "quote": sentence.group(1),
                "stated_risk": f"{risk.group(1)}: {' '.join(risk.group(2).split())}",
                "document": "scorecard_checks",
                "tested_against": tested,
                "claim_type": "risk",
            }
        )
    return rows


def main() -> int:
    texts: dict[str, str] = {}
    accessed: dict[str, str] = {}
    for key in SOURCES:
        raw, accessed[key] = fetch(key)
        texts[key] = raw

    rows = scorecard_rows(texts["scorecard_checks"])
    for instrument, component, key, start, end, tested, claim_type in ANCHORED:
        text = plain(texts[key], is_html=key == "opencode")
        i = text.find(start)
        j = text.find(end, i)
        if i < 0 or j < 0:
            raise SystemExit(f"anchor not found: {instrument} / {component} in {key}")
        rows.append(
            {
                "instrument": instrument,
                "component": component,
                "quote": text[i : j + len(end)],
                "stated_risk": "",
                "document": key,
                "tested_against": tested,
                "claim_type": claim_type,
            }
        )

    for row in rows:
        key = row.pop("document")
        url, commit = SOURCES[key]
        row["source_url"] = CROSSD_PUBLIC if key.startswith("crossd_") else url
        row["source_file"] = url if key.startswith("crossd_") else ""
        row["commit"] = commit
        row["accessed"] = accessed[key]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} rows, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
