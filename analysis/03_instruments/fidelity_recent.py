#!/usr/bin/env python3
"""Reconstruction fidelity at the date of the published values (RQ1c).

We apply the same reconstruction as at t0 to a seeded sample, at the date a value was published, and compare.

Scorecard: the pinned CLI at the commit of the published result, for the checks that run at a commit, and our rule
for `Maintained` at the date of the result. Only results of the same CLI version within 30 days of access.
Criticality: our signals at the collection date of the last published list. Score A uses the published mention count
in the place of dependents and tests our other signals. Score B uses the CrOSSD dependents at the nearest snapshot,
as at t0, and exists only where CrOSSD has a snapshot then. No outcomes are read.

Outputs:
  data/raw/fidelity/{scorecard,criticality}_<accessed>.jsonl    one line per project, resumable
  data/probes/fidelity_scorecard.csv, data/probes/fidelity_criticality.csv

Usage:
    python analysis/03_instruments/fidelity_recent.py --accessed 2026-11-04 --sample 150
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_probes"))

import collect_github_t0 as events  # noqa: E402
import probe_crossd_coverage as cov  # noqa: E402
import probe_github  # noqa: E402
import rule_adapters as rules  # noqa: E402
from base import PROCESSED, RAW, ROOT, add_months, cohort, days_before, parse  # noqa: E402
from collect_git import CLONES, git, hashed  # noqa: E402
from collect_scorecard import CHECKS, run  # noqa: E402

SEED = 20261104
T0 = "2024-08-01"
OUT = RAW / "fidelity"
LIST = RAW / "criticality" / "20250725_all.csv.gz"


def commit_times(project: str, when: datetime) -> tuple[list[int], int, float | None]:
    """Commit times in the 12 months before a date, all-time authors and the last commit, from the clone."""
    clone = CLONES / f"{project.replace('/', '__')}.git"
    until = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    log = git("log", "HEAD", f"--until={until}", "--format=%ct %ae", cwd=clone)
    stamps, authors = [], set()
    for line in log.stdout.splitlines():
        stamp, _, email = line.partition(" ")
        if int(stamp) <= when.timestamp():
            stamps.append(int(stamp))
            authors.add(hashed(email))
    lo = add_months(when, -12).timestamp()
    return [s for s in stamps if s > lo], len(authors), max(stamps) if stamps else None


def dated_events(client, repo: str, when: datetime) -> dict:
    owner, name = repo.split("/", 1)
    lo90, lo12 = days_before(when, 90), add_months(when, -12)
    end = events.iso(when)
    issues, _, _ = events.search(client, f"repo:{repo} is:issue created:{events.iso(lo90)}..{end} sort:created-asc", events.ISSUE, events.MAX_ISSUES)
    activity, _, _ = events.search(client, f"repo:{repo} is:issue updated:>={events.iso(lo90)} created:<={end} sort:updated-asc", events.ACTIVITY, events.MAX_ACTIVITY)
    _, closed, _ = events.search(client, f"repo:{repo} is:issue closed:{events.iso(lo90)}..{end}", "... on Issue { number }", 1)
    rel, _ = events.releases(client, owner, name, lo12)
    return {"issues": issues, "activity": activity, "closed_90d": closed, "releases": rel}


def done_of(path: Path) -> dict:
    return {json.loads(line)["project"]: json.loads(line) for line in path.open()} if path.exists() else {}


def agreement(frame: pd.DataFrame, a: str, b: str) -> dict:
    both = frame[[a, b]].dropna()
    if not len(both):
        return {"n": 0}
    return {"n": len(both), "exact": (both[a] == both[b]).mean(), "within_1": ((both[a] - both[b]).abs() <= 1).mean(),
            "spearman": spearmanr(both[a], both[b]).statistic if both[a].nunique() > 1 and both[b].nunique() > 1 else None}


def scorecard(args, client, created: dict, canonical: dict) -> None:
    published = pd.read_json(RAW / "scorecard" / f"published_{args.accessed}.jsonl", lines=True)
    published = published[published.status == 200].copy()
    published["when"] = pd.to_datetime(published.date, utc=True, format="ISO8601", errors="coerce")
    access = pd.Timestamp(args.accessed, tz="UTC")
    fresh = published[(published.version == "v5.6.0") & (published.when >= access - pd.Timedelta(days=30))]
    sample = fresh.sample(min(args.sample, len(fresh)), random_state=SEED)
    print(f"Scorecard: {len(published)} published, {len(fresh)} fresh, sample {len(sample)}", flush=True)
    path = OUT / f"scorecard_{args.accessed}.jsonl"
    done = done_of(path)
    with path.open("a") as out:
        for n, r in enumerate(sample.itertuples(), 1):
            if r.project in done:
                continue
            when = r.when.to_pydatetime()
            result = run(canonical[r.project], r.commit, 1200)
            times, _, _ = commit_times(r.project, when)
            ev = dated_events(client, canonical[r.project], when)
            commits_90 = sum(t > days_before(when, 90).timestamp() for t in times)
            rebuilt = rules.maintained_value(commits_90, ev["activity"], created[r.project], when)
            ours = {k: v["score"] for k, v in (result.get("checks") or {}).items()}
            line = {"project": r.project, "date": r.date, "commit": r.commit, "error": result.get("error"),
                    "published": r.checks, "ours": ours, "maintained_rebuilt": rebuilt}
            out.write(json.dumps(line) + "\n")
            out.flush()
            if n % 25 == 0:
                print(f"  scorecard {n}/{len(sample)}", flush=True)
    rows = [r for r in done_of(path).values() if r["project"] in set(sample.project)]
    results = []
    for check in CHECKS + ["Maintained"]:
        table = pd.DataFrame([{"published": r["published"].get(check), "ours": r["maintained_rebuilt"] if check == "Maintained" else r["ours"].get(check)} for r in rows])
        applicable = table[(table.published != -1) & (table.ours != -1)]
        results.append({"check": check, "projects": len(rows),
                        "same_inapplicable": int(((table.published == -1) & (table.ours == -1)).sum()),
                        "one_inapplicable": int(((table.published == -1) ^ (table.ours == -1)).sum()),
                        **agreement(applicable, "published", "ours")})
    frame = pd.DataFrame(results)
    frame.to_csv(ROOT / "data" / "probes" / "fidelity_scorecard.csv", index=False)
    print(frame.round(3).to_string(index=False), flush=True)


def crossd_dependents(project: str, when: datetime) -> float | None:
    session = requests.Session()
    stamps = cov.post(session, "snapshots", {"term": project})
    stamps = [s if isinstance(s, (int, float)) else s.get("timestamp") for s in (stamps.get("snapshots") if isinstance(stamps, dict) else stamps) or []]
    near = [s for s in stamps if s and abs(s - when.timestamp()) < 21 * 86400]
    if not near:
        return None
    response = cov.post(session, "metrics", {"term": project, "timestamp": min(near, key=lambda s: abs(s - when.timestamp()))})
    value = (response.get("metrics") or {}).get("dependents_count")
    return float(value) if isinstance(value, (int, float)) else None


def criticality(args, client, created: dict, canonical: dict) -> None:
    table = pd.read_csv(LIST, compression="gzip")
    table["key"] = table["repo.url"].str.replace("https://github.com/", "", regex=False).str.lower()
    by_lower = {v.lower(): k for k, v in canonical.items()}
    table = table[table.key.isin(by_lower)]
    print(f"Criticality: {len(table)} of {len(canonical)} cohort repositories in the list", flush=True)
    sample = table.sample(min(args.sample, len(table)), random_state=SEED)
    path = OUT / f"criticality_{args.accessed}.jsonl"
    done = done_of(path)
    with path.open("a") as out:
        for n, r in enumerate(sample.to_dict("records"), 1):
            project = by_lower[r["key"]]
            if project in done:
                continue
            when = parse(r["collection_date"])
            times, authors, last = commit_times(project, when)
            ev = dated_events(client, canonical[project], when)
            rel = [d for d in ev["releases"] if add_months(when, -12) < parse(d) <= when]
            base = created[project]
            mention = float(r["legacy.github_mention_count"] or 0)
            signals = rules.criticality_signals(base, last or base.timestamp(), float(authors), len(times), len(rel), ev, when, mention)
            dependents = crossd_dependents(project, when)
            line = {"project": project, "date": r["collection_date"], "published": r["default_score"], "signals": signals,
                    "score_a": rules.criticality_score(signals),
                    "score_b": None if dependents is None else rules.criticality_score({**signals, "dependents_count": dependents}),
                    "crossd_dependents": dependents,
                    "published_signals": {k: r[k] for k in r if k.startswith("legacy.")}}
            out.write(json.dumps(line) + "\n")
            out.flush()
            if n % 25 == 0:
                print(f"  criticality {n}/{len(sample)}", flush=True)
    wanted = {by_lower[k] for k in sample.key}
    rows = [r for r in done_of(path).values() if r["project"] in wanted]
    frame = pd.DataFrame([{"project": r["project"], "published": r["published"], "score_a": r["score_a"], "score_b": r["score_b"], **{f"ours_{k}": v for k, v in r["signals"].items()},
                           **{k.replace("legacy.", "pub_"): v for k, v in r["published_signals"].items()}} for r in rows])
    pairs = [("score_a", "published"), ("score_b", "published"), ("ours_created_since", "pub_created_since"), ("ours_updated_since", "pub_updated_since"),
             ("ours_contributor_count", "pub_contributor_count"), ("ours_commit_frequency", "pub_commit_frequency"), ("ours_recent_releases_count", "pub_recent_release_count"),
             ("ours_closed_issues_count", "pub_closed_issues_count"), ("ours_updated_issues_count", "pub_updated_issues_count"), ("ours_comment_frequency", "pub_issue_comment_frequency")]
    out_rows = []
    for a, b in pairs:
        both = frame[[a, b]].dropna()
        out_rows.append({"ours": a, "published": b, "n": len(both), "spearman": spearmanr(both[a], both[b]).statistic if len(both) > 2 else None,
                         "median_abs_diff": (both[a] - both[b]).abs().median()})
    result = pd.DataFrame(out_rows)
    result.to_csv(ROOT / "data" / "probes" / "fidelity_criticality.csv", index=False)
    print(result.round(3).to_string(index=False), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--accessed", required=True)
    ap.add_argument("--sample", type=int, default=150)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    members = cohort(T0)
    members = members[~members.gone_now & members.canonical.notna()]
    canonical = dict(zip(members.project, members.canonical))
    meta = pd.read_parquet(PROCESSED / f"github_meta_{T0}.parquet", columns=["project", "createdAt"])
    created = {r.project: parse(r.createdAt) for r in meta.itertuples() if isinstance(r.createdAt, str)}
    client = probe_github.Client()
    criticality(args, client, created, canonical)
    scorecard(args, client, created, canonical)
    return 0


if __name__ == "__main__":
    sys.exit(main())
