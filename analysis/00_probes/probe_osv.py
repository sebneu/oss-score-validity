#!/usr/bin/env python3
"""Download the outcome advisory data once and profile it.

Advisory data is backfilled, so it is fixed at one download. `--freeze-date` is the outcome
data freeze: the zips are kept in `data/raw/osv/<freeze-date>/` and never refreshed, and a
later date means a new folder. Records with `published` after the freeze date raise an
error, because then the folder and the date disagree.

Flattens every advisory record to one row per advisory x package:
  id, source prefix, published, modified, withdrawn, malicious (`MAL-` or CWE-506),
  severity (CVSS vector and GHSA label), fixed versions, repositories from `ranges[].repo`
  and, separately, from GitHub links in `references`.

CVSS base scores are computed with a small v3 calculator; v2 and v4 vectors are kept as
text and counted, since the plan's cut-off of 7.0 also accepts the GHSA label.

Outputs:
  data/raw/osv/<freeze-date>/<ecosystem>_all.zip
  data/raw/kev/<freeze-date>/known_exploited_vulnerabilities.json
  data/processed/osv_advisories.parquet
  data/probes/osv_profile.csv

Usage:
    python analysis/00_probes/probe_osv.py --freeze-date 2026-11-03
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
BUCKET = "https://storage.googleapis.com/osv-vulnerabilities"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

# Package ecosystems deps.dev can map, plus the two whose records name repositories.
ECOSYSTEMS = ("npm", "PyPI", "Go", "Maven", "crates.io", "NuGet", "RubyGems", "Packagist", "GIT",
              "OSS-Fuzz")

GITHUB_REPO = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?]|$)")

V3_WEIGHTS = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}
V3_PR = {"U": {"N": 0.85, "L": 0.62, "H": 0.27}, "C": {"N": 0.85, "L": 0.68, "H": 0.5}}


def cvss3_base(vector: str) -> float | None:
    """CVSS v3.x base score, per the FIRST specification. None if not a full v3 vector."""
    if not vector.startswith("CVSS:3"):
        return None
    try:
        parts = dict(p.split(":") for p in vector.split("/")[1:])
        impact_base = 1 - (
            (1 - V3_WEIGHTS["C"][parts["C"]])
            * (1 - V3_WEIGHTS["I"][parts["I"]])
            * (1 - V3_WEIGHTS["A"][parts["A"]])
        )
        changed = parts["S"] == "C"
        impact = (
            7.52 * (impact_base - 0.029) - 3.25 * (impact_base - 0.02) ** 15
            if changed
            else 6.42 * impact_base
        )
        exploitability = (
            8.22
            * V3_WEIGHTS["AV"][parts["AV"]]
            * V3_WEIGHTS["AC"][parts["AC"]]
            * V3_PR[parts["S"]][parts["PR"]]
            * V3_WEIGHTS["UI"][parts["UI"]]
        )
    except (KeyError, ValueError):
        return None
    if impact <= 0:
        return 0.0
    raw = min((impact + exploitability) * (1.08 if changed else 1), 10)
    return math.ceil(raw * 10 - 1e-9) / 10


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        tmp = path.with_suffix(path.suffix + ".part")
        with tmp.open("wb") as out:
            for chunk in resp.iter_content(1 << 20):
                out.write(chunk)
    tmp.rename(path)


def repos_in(urls: list[str]) -> str:
    repos = set()
    for url in urls:
        if match := GITHUB_REPO.search(url):
            repos.add(f"{match.group(1)}/{match.group(2)}".lower())
    return "|".join(sorted(repos))


def rows_of(record: dict, ecosystem: str, freeze: datetime) -> list[dict]:
    published = record.get("published")
    if published and datetime.fromisoformat(published.replace("Z", "+00:00")) > freeze:
        raise SystemExit(f"{record['id']} published {published}, after the freeze date")

    specific = record.get("database_specific") or {}
    cwes = {str(c).upper() for c in specific.get("cwe_ids") or []}
    severities = list(record.get("severity") or [])
    rows = []
    for affected in record.get("affected") or [{}]:
        block = affected.get("database_specific") or {}
        cwes |= {str(c.get("cweId", "")).upper() for c in block.get("cwes") or []}
        severities += affected.get("severity") or []
        fixed = [
            event["fixed"]
            for r in affected.get("ranges") or []
            for event in r.get("events") or []
            if "fixed" in event
        ]
        vectors = [s.get("score", "") for s in severities]
        v3 = [v for v in (cvss3_base(x) for x in vectors) if v is not None]
        rows.append(
            {
                "id": record["id"],
                "dump": ecosystem,
                "prefix": record["id"].split("-")[0],
                "package_ecosystem": (affected.get("package") or {}).get("ecosystem"),
                "package": (affected.get("package") or {}).get("name"),
                "published": published,
                "modified": record.get("modified"),
                "withdrawn": record.get("withdrawn"),
                "malicious": record["id"].startswith("MAL-") or "CWE-506" in cwes,
                "cvss3_base": max(v3) if v3 else None,
                "cvss_vectors": "|".join(sorted(set(vectors))),
                "ghsa_severity": (specific.get("severity") or "").upper() or None,
                "fixed_versions": "|".join(fixed),
                "n_fixed": len(fixed),
                "aliases": "|".join(record.get("aliases") or []),
                # A `ranges[].repo` names the affected code. A reference can be any repository
                # that discusses the flaw, so the two are kept apart.
                "range_repos": repos_in(
                    [r.get("repo", "") for r in affected.get("ranges") or []]
                ),
                "reference_repos": repos_in(
                    [r.get("url", "") for r in record.get("references") or []]
                ),
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--freeze-date", required=True, help="outcome data freeze, YYYY-MM-DD")
    args = ap.parse_args()
    freeze = datetime.fromisoformat(args.freeze_date).replace(
        hour=23, minute=59, second=59, tzinfo=UTC
    )

    folder = ROOT / "data" / "raw" / "osv" / args.freeze_date
    kev_path = ROOT / "data" / "raw" / "kev" / args.freeze_date / KEV.rsplit("/", 1)[1]
    provenance = []
    rows: list[dict] = []
    for ecosystem in ECOSYSTEMS:
        path = folder / f"{ecosystem}_all.zip"
        download(f"{BUCKET}/{ecosystem}/all.zip", path)
        provenance.append((path, f"OSV advisories, {ecosystem}", f"{BUCKET}/{ecosystem}/all.zip"))
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".json")]
            for name in names:
                rows += rows_of(json.loads(archive.read(name)), ecosystem, freeze)
        print(f"{ecosystem}: {len(names)} records, {path.stat().st_size / 1e6:.1f} MB", flush=True)
    download(KEV, kev_path)
    provenance.append((kev_path, "CISA Known Exploited Vulnerabilities", KEV))

    advisories = pd.DataFrame(rows)
    processed = ROOT / "data" / "processed" / "osv_advisories.parquet"
    processed.parent.mkdir(parents=True, exist_ok=True)
    advisories.to_parquet(processed, index=False)

    def stats(group: pd.DataFrame) -> pd.Series:
        unique = group.drop_duplicates("id")
        return pd.Series(
            {
                "advisories": len(unique),
                "malicious": int(unique.malicious.sum()),
                "withdrawn": int(unique.withdrawn.notna().sum()),
                "with_cvss3": int(unique.cvss3_base.notna().sum()),
                "with_ghsa_label": int(unique.ghsa_severity.notna().sum()),
                "no_severity_at_all": int(
                    ((unique.cvss_vectors == "") & unique.ghsa_severity.isna()).sum()
                ),
                "with_range_repo": int((unique.range_repos != "").sum()),
                "with_reference_repo": int((unique.reference_repos != "").sum()),
                "with_fixed": int((unique.n_fixed > 0).sum()),
            }
        )

    profile = advisories.groupby("dump")[advisories.columns.tolist()].apply(stats)
    profile.to_csv(ROOT / "data" / "probes" / "osv_profile.csv")
    print(profile.to_string())

    print("\nprovenance rows for data/README.md:")
    for path, what, url in provenance:
        rel = path.relative_to(ROOT / "data")
        print(f"| `{rel}` | {what} | {url} | {args.freeze_date} | `{sha256(path)}` | see source |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
