# Decision log, full chronological record

The concise summary is `DECISIONS.md` at the top of the repository. This is the complete record it draws on: frozen definitions, amendments, readings and deviations, in the order they were made. Commit hashes refer to the private working repository, and S3 to S5 to steps of the project plan. Notes on project management and on the wording of the manuscript are left out.

## Early decisions and deviations

| Date | Decision | Rationale |
|---|---|---|
| 2026-11-03 | Deviation from the plan: eligibility and the point-in-time rule use `observed_ts`, the time a value was read from GitHub, not the snapshot date | The `bak` worker crawls GitHub when its task runs, up to 29 days after the snapshot. With the snapshot date, 1,751 of 1,943 projects at t0 = 2024-08-01 would carry values read after t0. |
| 2026-11-03 | Deviation from the plan: the frame is the two lists of 2024-04-09 (most-starred, random-sample), reported per stratum; about 1,940 projects, not 3,255 | Later additions do not exist at t0. The lists were fixed before t0, so selection cannot depend on later events. The strata answer different questions. |
| 2026-11-03 | Deviation from the plan: I1 is dependents at t0 from one snapshot, not at each advisory's publication date | `Dependents` costs about 225 GB per snapshot against a 1 TB monthly free tier. |
| 2026-11-03 | After the freeze, no definition changed: I1 computed, known for 127 of the 246 O2a projects (110 most-starred, 17 random) | The other 119 attach through `ranges[].repo` without a package, or their packages have no row in `Dependents`. The stratum rule keeps the random sample descriptive for I1. |
| 2026-11-03 | Finding, definition unchanged: O1c as frozen fires for 999 of 1,550 projects (652 of 743 most-starred, 347 of 807 random) and rises with issue volume, from 0% below 3 issues to 95% at 1,000 or more | A fixed count of 3 measures how many issues a project gets. The crawl itself holds up: in a sample of 30 flagged projects, REST shows no maintainer comment within 90 days on the checked issue. In 7 of those the only association beyond `NONE` is `CONTRIBUTOR`, so maintainers with private org membership may be missed. |
| 2026-11-04 | Correction: `bus_factor_score` is missing mostly for low-activity projects (47% in the lowest commit quartile, under 1% in the highest), not for large ones as first suspected | `probe_crossd_integrity.py`, S2. The 37% against 11% in the earlier row is before the activity filter; in the cohort it is 21% against 11%. |
| 2026-11-04 | Registered on OSF as a preregistration on existing data: osf.io/ft8uw, submitted 2026-11-04 10:36 UTC, embargo until 2028-11-04, can end earlier. This log stays the binding record; if the two differ, that is reported | Timestamps the plan before any score is joined. Foreknowledge stated as "authors have observed the data, but have not performed the proposed analyses". |
| 2026-11-04 | Deviation from the registration: RQ4 (score validity as queryable data, RDF) dropped. Each score is reported with its validity as one table and a file instead | For a clean, straightforward paper. The registered text on OSF still lists the question; the paper states the deviation. Outcomes, cohort and primary tests are unaffected. |

## Freeze

**Freeze commit:** 7950cce6dafd. From here on, a change to anything below is a logged deviation, and the
original is reported as well.

- **Frame:** the lists `most-starred` and `random-sample` of 2024-04-09 (`FH-CrOSSD/crossd`, commit 604a0c6).
- **t0:** 2024-08-01. **Horizon:** 24 months, window (2024-08-01, 2026-08-01]. **Secondary:** t0 2025-01-01,
  12 months, most-starred only, robustness.
- **Eligibility:** `observed_ts` in (t0 − 14 days, t0]; a default-branch commit in the 180 days before t0, or the
  repository is gone today and CrOSSD read it in the window; not archived at t0.
- **Cohort:** `analysis/01_cohort/cohort_2024-08-01.csv`, 1,687 projects (780 most-starred, 907 random),
  sha256 39df43f1c24ab76de6563f1f8555347e21b0ddde8282cc222910b6b55727612b.
- **Values:** from the latest snapshot with `observed_ts` ≤ t0. A missing metric keeps the project in the cohort,
  and each instrument reports its coverage.
- **Outcome data:** OSV and KEV of 2026-11-03; deps.dev snapshot of 2024-07-29 for package links and dependents.
- **Severe advisory:** not withdrawn, not malicious (`MAL-` or CWE-506), CVSS v3 base ≥ 7.0 or GHSA label HIGH or
  CRITICAL.
- **Attachment:** the advisory's `ranges[].repo` or `references` name the repository under its panel name or the
  name GitHub serves now, and the package claims no other repository at deps.dev. Records without a package attach
  through `ranges[].repo` only, and count for O2a but not O2b.
- **O2 denominator:** projects with a plausible package at the snapshot before t0 (an attestation, a name matching
  the repository, or a tagged Go module), plus those with an attached advisory; for O2b, attached through a package.

| ID | Definition | Role |
|---|---|---|
| O1a | `archivedAt` in the window, or the repository gone without a redirect, unless a Software Heritage visit still found it after the window | primary |
| O1b | no default-branch commit, release or tag in the last 12 months of the window | primary |
| O1c | at least 3 issues opened in the window by non-maintainers, with no OWNER, MEMBER or COLLABORATOR comment and not closed within 90 days | sensitivity |
| O2a | at least one severe advisory published in the window and attached to the project | reported, not primary |
| O2b | at least one such advisory attached through a package, with no fixed version listed at the data freeze, at least 90 days after publication, or in CISA KEV. This measures an unfixed advisory, not a slow response | primary |
| I1 | for a project with an O2a advisory: dependents at t0 of its most depended-on affected package | criticality claims |

**Minimum events:** 40 in the pooled cohort for the primary statistics. A stratum gets its own statistics only with
40 events of its own, otherwise it is descriptive.

**Sensitivity variants:** H = 12 months; dormancy of 6 months; CVSS cut-off 9.0; response window 30 days; O1a archived
only; O2a verified only (package claims this repository); O1c as first drafted and without maintainer-filed issues;
O2b as drafted (no listed fixed version released within 90 days of publication, or in KEV).

**Events at the freeze, pooled:** O1a 79, O1b 194, O2a 246 of 650, O2b 52 of 579. Computed afterwards under these definitions: O1c 999 of 1,550, I1 for 127 projects.

## Amendment 1 (2026-11-04)

**Amendment commit:** 3fa3f5df2e66. No score had been joined to any outcome when this was written. The decisions draw on
outcome base rates only. Everything in the Freeze section stays computed and reported; the items below are added or
take over the primary role, as stated. The cohort, t0, horizon and data freeze do not change.

**A1. O1 becomes the primary maintenance outcome:** O1a or O1b (the amended O1a of A4). Reason: O1a has 18 events in
most-starred, so no stratum-level statement would be possible; O1 has 88 and 161. O1a and O1b are reported as components.

**A2. O1c by share (`O1c_share`), primary for claims about responsiveness.** The frozen O1c fires for 64% of projects and rises
from 0% to 95% with issue volume, so it measures volume.
- *Sample:* up to the 25 earliest issues of each of the 8 quarters of the window, opened by anyone other than OWNER, MEMBER or
  COLLABORATOR (external issues).
- *Unanswered:* no comment by OWNER, MEMBER, COLLABORATOR or CONTRIBUTOR within 90 days, and not closed within 90 days.
  CONTRIBUTOR counts because maintainers with private organization membership appear under it, in 7 of 30 checked cases.
- *Event:* at least 10 external issues in the sample and an unanswered share of at least 50%. Below 10 the project is outside
  the base for this outcome, and that base is reported.
- *Variants:* cut-offs 25% and 75%; responders limited to OWNER, MEMBER, COLLABORATOR.

**A3. Dormancy split by demand.** Finished software can stop changing without being abandoned, the main construct objection to O1b.
- `O1b_demand`: O1b, and at least one external issue opened in the last 12 months of the window and unanswered as in A2.
- `O1b_quiet`: O1b, with issues enabled and no such issue.
- `O1b_unknown`: O1b with issues disabled or no data.
The split is reported for every instrument. O1b_demand is tested as a sensitivity variant of O1.

**A4. Dating gone repositories.** A repository gone today is also excluded from O1a if GH Archive holds a public event under its
name after the window (months 2026-08 up to the data freeze). A repository without such evidence stays an event and counts as
undated. Archived-only stays the sensitivity variant. A repository turned private cannot be told apart from a deleted one.

**A5. I1 over all publishers (`I1b`).** The frozen I1 is known for 127 projects, selected on having an advisory. `I1b` is the
dependents, at the last deps.dev snapshot before the window closes (2026-07-27), of the project's most depended-on package,
for every cohort project with a plausible or attached package. Dependents at the snapshot before t0 (2024-07-29) are the
required baseline, because criticality scores use dependents as an input. Count as in the frozen I1. The frozen I1 stays reported.

**A6. Analysis plan, fixed before scoring.**
- *Primary tests,* one Holm family, using whatever S4 can backdate: Scorecard `Maintained`, openCode Aktive Wartung,
  CrOSSD `maturity_level`, `bus_factor_score` and `elephant_factor` against O1; CrOSSD `support_rate` and the openCode issue-response
  criterion against `O1c_share`; Scorecard-t0 aggregate and openCode Sicherheit against O2b; CrOSSD `criticality_score` and OpenSSF
  Criticality Score against `I1b`. Everything else is secondary and labelled so.
- *Direction,* declared now: a low value warns, except criticality scores, where a high value predicts high `I1b`.
- *"Warns":* lower bound of the 95% bootstrap interval for AUROC above 0.60. *"Adds information":* lower bound of the paired
  bootstrap interval for ΔAUROC above 0, and ΔAUROC of at least 0.02.
- *Baseline for O1, O1c_share and O2b:* logistic model on log-transformed stars, age, days since last commit, commits in the 90 days
  before t0, contributors in the 12 months before t0, and dependents. *For I1b:* rank correlation and ΔR² over log dependents at t0.
- *Reporting:* pooled and per stratum where the stratum has 40 events; each instrument with its coverage. 2,000 resamples, fixed seed.
  Results are reported whatever they show, null results and CrOSSD included.
- *Expectations,* written down so they can be wrong: maintenance scores warn of O1 but add little over recent activity; security-practice
  scores do not warn of O2b; criticality scores track `I1b` but add little over dependents at t0.
**A7. Missing metrics are not missing at random (added 2026-11-04, before any join).** `bus_factor_score` goes missing with low
activity, `criticality_score` with few or no issues (54% missing at 0 issues, under 1% at 10 or more). A complete-case analysis alone
would drop quiet projects, the ones most at risk. So:
- `bus_factor_score` is evaluated twice in the primary family's slot: as published (complete cases, with coverage) and with a missing
  value read as a warning. Both are reported. The published reading is the one that counts for the Holm test.
- Criticality scores are evaluated on available values, with coverage, and the gap is named as a limit of the instrument.
- A missing value is itself a result: what a dashboard shows for a quiet project matters to the question of this paper.

## Assumptions about the CrOSSD record (2026-11-04)

These are working assumptions from public code and from tests.
Evidence: `data/probes/crossd_integrity.json`, public repositories `FH-CrOSSD/crossd`, `metrics`, `thesis_metrics`.

| Question | Most likely answer | Confidence | Evidence | How we handle it |
|---|---|---|---|---|
| Were values recomputed or backfilled later? | No | high for raw records, medium for `bak` | Raw records: of 150 projects, 130 within 1% of what GitHub counts today for the read time; all 108 that grew over 2% lie closer to then than to the window's end (median error 0.03% against 22.5%). `bak`: no update path in the code, only `createDocument`; a recomputation would write a new timestamp, and the delay never exceeds 62 days (1 of 15,856 above 60) | S4 adds a historical fidelity check: rebuild a `bak` metric (bus factor, from dated commits) at t0 for a sample and compare. If it fails, CrOSSD is reported as reconstructed, not native |
| Did CrOSSD store Scorecard or other third-party scores? | No | high | No mention in `crossd` or `metrics` code; not in the metric or repo payloads | Scorecard is reconstructed in S4, as planned |
| Why did the random-sample series stop after 2024-08-09? | Job suspended on the cluster, probably because of the queue backlog | high that it was operational, low on the reason | 940 of 961 stop on the same date, 4 continue; the job file stays in the repository and is edited later; delays rise just before (90th percentile from 2 to 25 days) | No effect on validity: the stop is after t0, applies to the list and not to single projects, and outcomes come from GitHub and OSV |
| How was the random list drawn? | A sample from public non-fork GitHub repositories, filtered by a minimum of stars or activity | medium; the frame itself is unknown | Median 164 stars today, 5th percentile 16, 9 of 913 under 10 stars, 3 forks. A plain GitHub sample would have a median near 0 | In the paper: "filtered sample", never a random sample of open source. Report the stars and age distribution. No claim about the OSS population. Reconstruction of the filter stays open |
| Most-starred list? | Top 1,000 by stars on 2024-04-09, as the tag says | high | 5th percentile 25,558 stars today; none created after the list date | As is; range restriction on stars is named |
| Why are metrics missing? | Bus factor: too little commit activity in the look-back. Criticality: no issue data | medium to high | S2 of the integrity probe | A7 |
| Which code computed `bak` in July 2024? | `thesis_metrics` main, unchanged since 2024-06-19 (d98b84d), apart from a licence update in 2025 | high | Image installs main; repository history. The exact image build date is unknown, and could predate 2024-06-19; those commits only touch error handling | Cite that commit for definitions; `metrics` library after the 2025-05-14 revamp differs, so RQ1(c) at a recent date tests a later definition |
| Definitions beyond the metric pages? | The pages suffice | high | `frontend/src/lib/md/metric/*.md`, quoted in `claims.csv` | `Metrics_Definitions.xlsx` is not needed for the claim table |

Note on the tests: `technical_fork.total_forks` falls as often as it rises, so it is not a lifetime count; check what each metric covers before reading it as one.

## Readings of the instruments (2026-11-04, before any score meets any outcome)

The published rules leave these points open. They are fixed here so that the choice cannot follow the results.

**openCode.** The rules are published, the implementation is not. *Issue response:* days to the first comment by someone other than the author, or to closure; an issue still open and unanswered at t0 counts with its age at t0. Bots are not filtered. *No issues in the 3 months before t0:* the criterion counts as met, since there is no evidence of slow response. *No pull requests or tags in the 6 months:* the review and signing criteria count as met. *Contributor absence factor:* the smallest number of contributors making at least half of the commits in 6 months. *Reviewed by a maintainer:* a review by an OWNER, MEMBER or COLLABORATOR other than the author, submitted before the merge, on up to 100 merged pull requests. *Security badge:* branch protection and force pushes (L1) and the vulnerability criteria (L3) cannot be backdated, so we use levels 0 to 2 over the remaining criteria and report this.

**Scorecard Maintained.** As in the source at commit ab792da: (commits + issues with member activity in the last 90 days) / 12, times 10, capped at 10; zero if created in the last 90 days. The live check reads the 30 most recently updated issues; here the order at t0 is not known, so we read issues touched since the window began, up to 100.

**OpenSSF Criticality Score.** The published formula and default weights. `org_count` cannot be backdated and its weight is removed. `dependents_count` is the CrOSSD value at t0, read from the GitHub dependency graph; the original counts mentions in commit messages. `updated_issues_count` counts issues created or commented on in the window, since `updatedAt` is current state; the sample is capped at 100.

**CrOSSD bus factor.** The worker computes the whole block only if the project has commits in the month before the reading (`single_commits`), and the score from commits of the 12 months before it. This explains the missing values. Rebuilding it from dated commits is the fidelity test for the `bak` values.

**Baselines.** Stars from the deps.dev snapshot of 2024-07-29, else stargazers dated by t0, which misses stars removed since. Age from `createdAt`, last commit, commits and contributors from git. Dependents from the CrOSSD value at t0.


## Case panel (2026-11-04, before any case value was read)

The cases illustrate; they enter no statistic and no decision in the analysis. They are selected on the outcome, and the paper says so next to them.

**Selection.** A screen of the panel lists advisories in the CISA catalogue, advisories for malicious code in a legitimate package, and archived or vanished repositories since April 2024 (`analysis/05_cases/screen_incidents.py`). A case needs a date from a primary record and CrOSSD readings on both sides of the event. One case per mechanism where possible: a hijacked release channel (axios, 2026-03-31; Lightning, 2026-04-30), an exploited flaw in the project's own code (React, 2025-12-03; MongoDB, 2025-12-19), an end of maintenance (MinIO, maintenance mode 2025-12-03, archived 2026-04-25). Ultralytics (first public report 2024-12-05, issue 18027) is added because it is the one case from the filtered sample; its series ends on 2024-08-09, so it has the value at t0 and nothing afterwards.

**Reading.** For each case: the value at t0, the last reading at least 26 weeks before the event, the last reading before the event and the first reading at least 4 weeks after it. The components are those of the CrOSSD adapter, dated by `observed_ts`. Readings of the same project before and after the 2025-05-14 revamp of the metric library are compared only where the definition did not change.

**In the paper.** The table shows the readings before and after the event, for readability; all four fixed readings are in `readings.csv`, for the replication package.

**Projects we cannot use.** XZ Utils, tj-actions/changed-files, reviewdog and nx are not in the panel. debug, chalk and eslint-config-prettier joined it on 2026-04-27 or later, after their incidents. They are named as limits of the panel.

**Cohort rows.** The projects stay in the cohort as ordinary rows. The cohort was fixed without reference to any incident, so their inclusion is not selection on the outcome. The case readings add nothing to the statistics.

**Monitoring gap.** The panel holds almost no readings between 2025-10-02 and 2026-01-26, which covers the React and MongoDB disclosures and the MinIO announcement. The readings before those events are two months old. The primary analysis is not affected, since its values are read before t0 and its outcomes do not come from CrOSSD.

**Definition breaks.** Between the `bak` and `metrics` blocks (2025-05 to 2025-07) first response time, support rate and maturity level jump for reasons of definition. Criticality stays within one point. Across that break the case table compares criticality only.

**Compromise advisories in O2a (noted, no change).** The frozen rule excludes advisories marked malicious (`MAL-` or CWE-506). Hijacks are therefore outside O2a by design, in line with O3 being case level. Two PyPA records describe a compromise without the marker: PYSEC-2024-154 (Ultralytics, the project's only attached advisory) and PYSEC-2026-508 (Lightning, an alias of a marked advisory; the project has 12 other attached advisories). So the rule as written counts one project, Ultralytics, in O2a because of its compromise. One event of 246. We apply the rule as frozen and do not relabel.

## Correction: window of the CrOSSD bus factor (2026-11-04, no score met an outcome)

The entry "CrOSSD bus factor" under Readings says the score uses commits of 12 months, as the miner requests. The rebuild shows otherwise: at one month the stored values match exactly for 86.0% of 1,378 projects (97.1% within one, Spearman 0.96), at 6 months, the documented window, for 55.9%, and at 12 months for 50.7%. The later library says "limit commits to the last month" in its code. The code also stops at a running 80% before it counts, so one identity holding that share gives 0, while the documentation gives 1 as the lowest value. The stored value stays the primary reading, as registered, and stays evidence type `recorded`, since the fidelity test passes at one month. The difference between claim and implementation is reported under RQ1. The analysis plan does not change: 0 is the more concentrated end, so the order of the score is kept.

## Rule adapters over the cohort (2026-11-04, no score joined to an outcome)

**Recreated repositories.** GitHub reports `createdAt` after t0 for two cohort projects that existed at t0: `HybridFNBR/Neonite` (2026-10-25) and `jhipster/jhipster-lite` (2025-07-30). The freeze check stopped the run on this. `createdAt` is current state, like the other fields in the point-in-time rule. Git keeps their history, while issues, pull requests and releases before t0 are gone. Scorecard Maintained, the Criticality Score and both openCode badges stay missing for them; baselines use the first commit for age. The frozen labels stay as they are (`jhipster-lite` counts as O1a), and we report the two cases in the threats. Other recreations before t0 would not show here.

**`authorAssociation` is read today.** Maintained and the openCode review share use the association GitHub reports now, not the one at the time of the comment or review. Someone who left the organisation counts as a non-member. This pushes both values down for older activity and goes into the threats. The dates themselves are event time.

**Stars.** GitHub no longer serves the dated stargazer list to outside accounts: FORBIDDEN over GraphQL with the project token, 404 over REST with the account behind `gh`. So the walk planned in `collect_github_t0.py` returned nothing for all 533 projects without a deps.dev row. `collect_stars_gharchive.py` counts `WatchEvent` rows before t0 instead, as the plan already named (about 170 GB). A star removed later still counts, and early years have gaps. The check against the deps.dev snapshot is in `data/probes/stars_gharchive_check.csv`.

## Scorecard at t0: what the source shows (2026-11-04, no score joined to an outcome)

Read from the source at v5.6.0 and the first 484 results. A check that runs with `--commit` can still read today. This corrects the plan and the earlier list of at-commit checks.

- **License excluded.** `clients/githubrepo/licenses.go` calls `GET /repos/{owner}/{repo}/license` without the commit. Today's license state would enter t0.
- **CI-Tests excluded.** 337 of 338 results read 0, on projects that do run CI. We stopped running this check and License after the first 490 projects to save API budget; that sample is the evidence. GitHub deletes checks data after a retention period (docs, "About status checks"), so the check finds nothing on commits of 2024. Reading this as "no CI" would be false.
- **Security-Policy corrected.** With no file in the tree, the check reads the owner's `.github` repository at HEAD. `collect_policy_paths.py` records the tree at the commit and whether the owner had a policy committed by t0. A later policy counts as 0. The content score of an earlier one is still read today, which we accept for a rare case. A file removed again before t0 still counts.
- **Vulnerabilities excluded,** as before: it asks OSV today.
- **Dependency-Update-Tool, Packaging, Signed-Releases, Fuzzing, SAST, SBOM** stay out because the CLI refuses them at a commit (`scorecard_cli.csv`). The plan expected some of them to be rebuildable. Rebuilding them by hand would mean writing our own version of the check, which then tests our code.
- **Aggregate.** Scorecard's own weights over Maintained, Binary-Artifacts, Dangerous-Workflow, Token-Permissions, Pinned-Dependencies, Code-Review and Security-Policy: 50 of 120 weight points. The registered test uses "whatever S4 can backdate", so this is no deviation from the analysis plan. Classes and reasons: `analysis/03_instruments/backdating.py`.

**Run over the cohort (finished 2026-11-04).** 1,642 of 1,646 existing projects have a result. A first pass left 29 errors: 12 authentication failures right after a restart, 8 repositories with paths that differ only by case (they cannot be unpacked on the default macOS volume), 8 timeouts at 20 minutes and one server error. A retry with a 30-minute timeout, on a case-sensitive volume, cleared 25. Four remain missing and stay missing: `CocoaPods/Specs`, `droid-f/fedlex`, `google/material-design-icons`, `opentimestamps/nist-inject`. `collect_scorecard.py --retry-errors` appends, and the adapter keeps the last line per project. These four still have Maintained, which is built by rule. Internal -1 results (Pinned-Dependencies, Binary-Artifacts, Dangerous-Workflow) are treated as missing checks, and the aggregate is taken over the checks that remain.

## Criticality Score: issue signals in the published list (2026-11-04, no score joined to an outcome)

In the list of 2025-07-25, 89.5% of 585,601 repositories have zero for closed issues, updated issues and comment frequency together, among them Kubernetes, React, Rust, VS Code and NumPy. Fidelity therefore cannot test these three signals. Spearman against the published values is -0.19, -0.28 and -0.13, which only says the published values are empty. Signals that do carry values agree well (contributors 0.999, commits 0.996). The score agrees at 0.90 with our issue signals and at 0.93 with the published zeros. We report this as a gap between claim and implementation, without guessing at the cause.

## Criticality Score at t0: the published value is the reading (2026-11-04, no score joined to an outcome)

The files in the bucket `ossf-criticality-score` no longer download (the owner's billing account is gone, turn-down in issue #833). The BigQuery table `openssf.criticality_score_cron.criticality-score-v0` still answers and holds 28 lists, with 2024-07-18 as the last before t0. We froze the cohort rows in `data/raw/criticality/history_cohort_2024-08-01.parquet`.

- **Reading.** The registered test of the OpenSSF Criticality Score against `I1b` uses the value in the last list before t0: recorded at the time, the same logic as the CrOSSD values. It replaces the rebuild named in "Readings of the instruments". The rebuild stays as a sensitivity check. This is fixed before any score meets any outcome.
- **Coverage.** 1,379 of 1,687 (780 of 780 most-starred, 599 of 907 filtered), of which 1,303 from the list of 2024-07-18 and 68 older than 180 days. Evaluated on available values with coverage, as for the other criticality score. Age is stored per project.
- **Fidelity at t0.** Score 0.85 (Spearman), 0.91 with the published mention count; contributors 0.998, commits 0.98; closed issues 0.79, updated issues 0.78, comments 0.64. `updated_since` 0.56: both use the last commit, but the list gives whole months read two weeks before t0, and most projects have a commit in the last month, so little variation remains.
- **Collector counts pull requests.** `FetchIssueCount` in `internal/collector/github/legacy/issues.go` says "This count includes both issues and pull requests", and it filters by last update, while the README says issues closed in the last 90 days. This explains median 74 against our 13. We keep our rebuild as the documented formula.
- **Empty signals over time.** Share of a list with all three issue signals zero: 12% on 2024-05-02, 66% on 2024-05-18, 89% on 2025-04-17, 89.5% on 2025-07-25. Within the cohort at 2024-07-18 only 5 to 8% per signal are zero, so the test at t0 is not affected. Cause not known, and we do not guess.
- **Stars.** The list also carries `star_count` at the time. It agrees with deps.dev (median ratio 1.00), while GH Archive events run about 6% high. So the order is deps.dev, then the list, then events.

## Case panel, extended (2026-11-04, before the new case values were read)

Still illustrations: selected on the outcome, in no statistic. Disclosed: while checking the adapters we saw the t0 values of openCode, Maintained and rebuilt criticality for axios, Ultralytics, MinIO and MongoDB. The other values below had not been read.

**Warning matrix.** One figure. Rows: the six panel cases at t0, then XZ Utils and tj-actions at the day before their event. Columns: CrOSSD bus factor, support rate, maturity level, criticality; Scorecard Maintained and aggregate at t0; published Criticality Score; openCode maintenance and security. Each cell gives the share of the project's list in the cohort at t0 with the same or a worse value (panel cases: their own list; XZ and tj-actions: the filtered sample, with the date difference stated). For the two criticality scores a high value means importance and no warning, so their cell gives the share with the same or a higher value. Ties count towards the share, so a tied value is not made to look rare. No threshold decides anything; the shading marks the worst tenth and quarter for reading. The matrix uses no outcome at cohort level.

**Rows at t0 and not at the event.** t0 is where all instruments exist for the whole cohort under one definition, and it is the design of the paper. The months from reading to event are shown. Readings close to the event are in the CrOSSD table and the mechanism table.

**Mechanism table.** For each case, the component that claims this risk in its own documentation, read at the last commit before the day before the event:

| Case | Event used | Mechanism, per source | Component claiming the risk |
|---|---|---|---|
| axios | 2026-03-31 | stolen npm account credentials (post mortem) | Signed-Releases ("possibility of installing malicious releases"), not backdatable |
| Lightning | 2026-04-30 | compromised PyPI releases; root cause open in the advisory | Signed-Releases, not backdatable |
| Ultralytics | 2024-12-05 | GitHub Actions workflows and their build cache (PyPI analysis) | Dangerous-Workflow ("vulnerable to repository compromise"), Token-Permissions ("vulnerable to malicious code additions") |
| React | 2025-12-03 | flaw in the project's code | Code-Review ("unintentional vulnerabilities"); Fuzzing not backdatable |
| MongoDB | 2025-12-19 | flaw in the project's code | Code-Review; Fuzzing not backdatable |
| MinIO | 2025-12-03 | end of maintenance | Maintained, openCode maintenance |
| XZ Utils | 2024-02-23, the commit with the payload | payload in test files in git, activating code only in release tarballs (Freund) | Code-Review ("possible injection of malicious code"), Binary-Artifacts ("non-reviewable code"), bus factor (rebuilt) |
| tj-actions | 2025-03-14 | version tags moved to a malicious commit (GHSA-mrrh-fwg8-r2c3) | Token-Permissions, Dangerous-Workflow |

**Rebuilt cases.** XZ Utils and tj-actions are not monitored, so they carry no recorded CrOSSD value. Scorecard runs at the commit, Maintained and openCode follow the same rules, the bus factor uses the one-month rebuild, and the Criticality Score is the last list before the event. The paper marks these rows as rebuilt. Log4Shell and Heartbleed stay out, as no more than two rebuilt cases are needed for the point.

## Frozen feature table (2026-11-04, no score joined to an outcome)

`analysis/03_instruments/freeze_features.py` joins all adapter outputs into `data/processed/features_2024-08-01.parquet`: 75,623 rows, 45 components, 1,687 projects, sha256 `5c7807edff66d21ff16b0bd0264a2b2571d8a02478d75efdab30d7cff317f722`. It reads no outcome and fails on any value after t0. Coverage per component and stratum is in `data/probes/feature_coverage_2024-08-01.csv`. A later change to this table is a logged deviation.

The dated star walk is removed from `collect_github_t0.py`, because GitHub closed that route.

## S5: details fixed before the first join (2026-11-04)

Written and committed before `analysis/04_validity/validity.py` first read scores and outcomes together. A6 and A7 stay binding. They leave the points below open, and these are the readings we fix now. Anything changed after this commit is a logged deviation.

**The 11 primary pairs.** Against O1: Scorecard `Maintained`, `opencode_maintenance`, CrOSSD `maturity_level`, `bus_factor`, `elephant_factor`. Against `O1c_share`: CrOSSD `support_rate`, `opencode_response_ok`. Against O2b, within `in_O2b_base`: `scorecard_aggregate_t0`, `opencode_security`. Against I1b: CrOSSD `criticality_score`, published OpenSSF value (`openssf_criticality_published`).

**Values.** Each on the projects where it is known. Gone repositories have recorded CrOSSD values and no reconstructed ones, since their git history is lost, so reconstructed instruments lose most of them. Every maintenance result is therefore also reported on existing repositories only. The verdict uses the registered reading, on available values.

**AUROC.** Mann-Whitney with ties counted half, on the score turned so that a higher number warns. Interval: percentile bootstrap over projects, 2,000 resamples, seed 20240801. Lift: event rate in the worst 10% over the base rate, with a tied group at the boundary counted by its fraction.

**Holm.** The family has 11 pairs and is applied separately to each of the two questions. *Warns:* one-sided bootstrap p for AUROC at most 0.60; for I1b, for a Spearman correlation at most 0. *Adds:* likelihood-ratio test of baseline against baseline plus score. A verdict needs the registered rule and a Holm-adjusted p below 0.05. An item outside the family has no verdict and is labelled secondary.

**Gain over the baseline.** In-sample gains cannot be negative, so we use out-of-sample ones. Point estimate: repeated from one 10-fold stratified split with a fixed seed, AUROC over the pooled predictions. Interval: both models fitted on each bootstrap sample, the difference read on the projects left out of it. Both models are on the projects where the score and all baseline variables are known. Features are log1p of stars, age, days since last commit, commits 90 days, contributors 12 months and dependents, standardised, with an unpenalised logistic fit. The in-sample gain is reported beside it.

**Later dependents.** Base: I1b and I1b_t0 both known, and the score known. Rank correlation with I1b. Gain: R² of log1p(I1b) on log1p(I1b_t0) plus the score against log1p(I1b_t0) alone, read as above. "Adds" uses the same rule: lower bound above 0 and gain at least 0.02. A registered threshold for R² did not exist, so this one is by analogy with AUROC. The list test uses n of at least 40 for this outcome.

**Thresholds.** Documented operating points only: `Maintained` = 0, the reading the Scorecard tracker report uses; the openCode badges at level 0 for maintenance and security; openCode's issue-response criterion failed. Neither Scorecard's aggregate nor any CrOSSD metric documents a number. For bus factor and elephant factor we add the conventional reading "at most 1" and mark it as ours. The aggregate and the other CrOSSD metrics get no threshold.

**Prevalence.** Rogan-Gladen on the flag share. With Se and Sp from the same projects, the estimator returns the observed event share by algebra, so a pooled correction says nothing. We report the pooled flag share, the observed event share and J with its interval, and we then transfer across lists: Se and Sp measured on one list correct the flag share of the other, where the source list has 40 events. The observed share of the target list checks the result. If the interval for J from the source list includes 0, the corrected share is not estimable. The estimate is not clipped in the bootstrap, and it is reported as computed. Population-level transfer is out of scope. The corrected share speaks to the later event, and is not a statement about a project's state at t0.

**Sensitivity.** Variants in `outcome_variants.py`, on the primary pairs of the matching outcome. "Response window 30 days" is read on O2b as drafted (`O2b_drafted_30d`), which is where the code has a window parameter. The O1c share cannot be recomputed at 30 days because the demand crawl stored only the 90-day answer. Under the 40-event rule, `O2b_12m` (28 events) and `O2b_cvss9` (22) are descriptive only. Secondary items: every other component against the outcome its claim names, the bus factor with a missing value read as a warning, the rebuilt bus factor, the rebuilt Criticality Score, each baseline variable alone, O1a, O1b and the dormancy split by demand.

**Robustness at t0 = 2025-01-01.** Decided after the primary run, by what the sources allow; logged either way.

**Direction in "adds".** A logistic model can gain from a score read backwards. "Adds" therefore also requires the score's coefficient to point in the declared warning direction; a gain in the other direction is reported as such. Added before the first join.

## S5: first join and what changed after it (2026-11-04)

The first run used the commit 6e6ac7d319fc. Everything that counts for a verdict is as fixed before it. Added after it, with no change to any registered statistic (the shared columns of `validity_primary.csv` are identical between the runs):

- Intervals for AUROC on existing repositories only, from a separate random generator, because the elephant factor's point estimate fell on them.
- `validity_flags.csv`: who the Maintained flag finds and misses, what a missing bus factor means, and the range of the support rate. These are descriptive.
- *Deviation:* the registered rule calls a corrected share not estimable if the interval for J includes zero. For a J clearly below zero (openCode maintenance without a badge, from the filtered sample) the flag points the wrong way, so we report "J < 0" and give no corrected share. The original rule would have given one.

Verdicts: warns are Scorecard `Maintained`, bus factor, elephant factor (not on existing repositories only) and openCode response; adds is openCode response alone. All three registered expectations held. Results in `data/probes/validity_*.csv`; the measured validity per score in `analysis/04_validity/measured_validity.csv`.

**Open:** the robustness check at t0 = 2025-01-01, 12 months, most-starred list. It needs a cohort at that date and new outcome labels for that window. Maintained and openCode need a GitHub crawl, and the Scorecard aggregate needs another CLI run over 780 repositories. Not yet run.

## Statistics stay simple: deviation from the registered analysis (2026-11-04, after the results were known)

The first author's decision, in line with the other papers of the series: no regression models and no multiple-comparison procedures in the main analysis. This is a deviation from the OSF registration, made after seeing the results, so the simple readings of "adds" are descriptive. The registered analysis stays in the paper, labelled as registered, and in `validity.py`.

- **Warns stays as registered:** lower bound of the AUROC interval above 0.60. Dropping Holm changes no verdict (checked on `validity_primary.csv`).
- **Replaces the logistic baseline in the main text:** (a) the score against each single baseline measure, on the same projects, with a paired bootstrap interval for the difference; (b) AUROC among projects of similar activity: within quartiles of commits in the 90 days before t0, with tied projects kept together, averaged with weights by the number of event and non-event pairs. Same limit: lower bound above 0.60 is called "holds". Quartiles of the days since the last commit are the check on that choice, since the variable was picked after seeing results.
- **Later dependents:** the rank correlation against that of dependents at t0, and the rank correlation within quartiles of dependents at t0. The gain in R² stays only in the registered part.
- **Reported as registered:** the gain table with its Holm-adjusted tests and verdicts. Where a verdict differs between the two readings, the paper names it.

## Registered analysis moves to the package (2026-11-04)

Table and paragraph on the registered logistic model leave the results, to keep the paper simple. This changes the earlier note that it stays in the paper. It now lives in `analysis/04_validity/registered_analysis.csv` and `validity.py`. The Registration paragraph in the analysis plan still states that it was registered, that the simplification came after the results, and the verdicts that differ: only openCode response adds information, while the bus factor and the elephant factor, which hold at similar activity, do not. The discussion of our own instrument repeats that, because the simple reading favours CrOSSD.

## Robustness at t0 = 2025-01-01 (2026-11-05, run after the first results were known)

Registered in the Freeze section. Most-starred list, 12-month window, 759 projects, cohort sha256 `7f4b4d9e2d740c85cfe19e9178334134b861d70acc63df56707e8f9c779387ec`. Frozen files of the first date checked unchanged by checksum afterwards.

Deviations, all logged in the paper too unless marked:
- No Scorecard aggregate: it needs another CLI run over the list. The first author's decision. `Maintained` is built by rule and stays.
- No later dependents: two further deps.dev scans of about 200 GB each, with the BigQuery free tier nearly used.
- GH Archive events for gone repositories cover August 2026 onwards only, reused from the first date. Two gone repositories count as failures, so at most two events are affected.
- Not in the paper, no effect on the table: stars and dependents among the baselines date from the deps.dev snapshot of 2024-07-29, and the Criticality lists from the first date's cohort (720 of 759 covered). The table uses neither.
- Same simple measures as the main analysis; no logistic model at this date.

## After an outside review of the manuscript (2026-11-05, after the results were known)

- **Bus factor as documented.** Added after the results and descriptive; the stored value stays the registered reading. `analysis/03_instruments/bus_factor_readings.py` and `analysis/04_validity/bus_documented.py`. As documented, over six months, it warns and does not hold at similar activity, so the "holds" belongs to the implementation. Reported in the results and the discussion.
- **Versions of the rebuilt instruments.** Scorecard ran as v5.6.0 (2026-10-12); v5.0.0 (2024-07-19) was current at t0. `checks/evaluation/maintained.go` and the probes behind it changed only in a message text, lint and a nil check between the two; other checks changed. v5.0.0 was not run. The openCode rules were read on 2026-11-03; the earliest Wayback capture of the page is 2025-04-27. Stated in the results and the threats.
- **Dropped research question.** The registration lists a fourth question (validity as queryable data). This log said the paper states the deviation, but the sentence was lost when the registration section was shortened. It is back in the Registration paragraph.
- **Line of 0.60.** The paper now says it is our convention and how the count moves: five at 0.55, one at 0.65. The verdicts stay as registered.
- **Table of measured validity.** Later dependents sit below a line and read $\rho>0$ under Warns and Holds, because that test differs from the AUROC rule.
- **Later dependents, wording only.** As registered and computed: the highest count per date over the same packages, so the top package can differ (the same for 295 of 362 projects). Packages attached through an advisory enter that set, and they change the baseline for 17 of 399 projects. A check outside the paper with the package fixed at t0, without those packages: rho 0.51 for CrOSSD and 0.68 for OpenSSF (0.53, 0.67 as registered), within quartiles 0.09 and 0.16 (0.12, 0.17). Same conclusion.
- **Abstract.** Cut to the 250 words JSS allows. It now says that the comparison at similar activity was chosen after the results, that two of the three scores that hold are ours, and that only the openCode response criterion adds information in the registered model. "Popularity and recent activity do at least as well" became "recent activity", because stars alone reach 0.61 on failure against 0.71 for `Maintained`.

## Published Scorecard values, issue sample, base of later dependents (2026-11-05, after the results were known)

- **Published Scorecard scan.** The table `openssf.scorecardcron.scorecard-v2` can still be read, although the project says it is gone (issue #5208), with scans up to 2026-08-24. The scan of 2024-07-29, a build of v5.0.0, is frozen in `data/processed/scorecard_published_2024-07-29.parquet`: 875 of 1,687 projects, 645 and 230 per list. It is a test of the rebuild, reported in RQ1 and for the complete aggregate. The primary values stay as frozen. The sentence that historical values have to be rebuilt because the dataset is gone is corrected. The scan of 2024-12-30 is frozen too, in case the table goes, and is not used.
- **Sample of unanswered issues.** A2 and the registration say the 25 earliest external issues per quarter. The code has drawn the 25 earliest issues and kept the external ones since before the first run. 88% of the sample is external. Of the 107 crawled projects below 10 external issues, 7 have a quarter at the cap, so the base can change by at most 7. A logged deviation from the registered text, stated in the paper; the code stays.
- **Base of later dependents.** A5 names every project with a package; the labels hold a count only where deps.dev has a row. 164 of 579 have none at either date, 69 only at the first and 16 only at the last. Stated in the paper, with a reading of missing as zero (`analysis/04_validity/later_dependents_base.py`), an upper bound since a missing row can also be a system deps.dev does not count. The order of the two scores changes, the earlier count stays ahead of both.
- **First 30 comments.** The crawl reads the first 30 comments of an issue. Not measured; named in the threats.
- **Checked, no effect:** the demand crawl holds all 1,175 projects its code asks for, with no errors, and no dormant project lacks it; no duplicate issues at the quarter limits; no failed lookups among the root files. A1 says O1 has 88 and 161, written before A4; the labels hold 88 and 159.

## Co-author review (2026-11-10, after the results were known)

- **Tables.** Secondary results move from tables into the text; the full results stay in `data/probes/`. The three RQ2 tables become one, with days since the last commit and commits in 90 days as reference rows per outcome and list (`analysis/04_validity/baseline_strata.py`, its own seed, so no earlier number changes). Dormancy by demand joins the events table; the interval at similar activity joins the summary. No number changes.
- **Random list, partial answer.** The list was drawn with the GitHub search API: `stars:>0`, sorted by update, ten pages of 100. The same query on 2026-11-10 returns a median of 2 stars and 787 of 1,000 repositories under 10 stars (`data/probes/random_list_query_2026-11-10.csv`, stars and dates only), against a median of 164 stars today and 9 of 913 under 10 for the list. The query alone does not produce the list, so a further filter applies (the file is `random_samples_filtered.txt`). Open: what that filter was. The paper names the query and says the filter cannot be reconstructed.
- **Support rate above 100.** In the code of 2024 (`thesis_metrics`, `support_rate`), the numerator counts commented issues from the comment data, which may contain issues the denominator does not; an issue missing from the issue list also counts as an issue, not a pull request. In the cached `bak` readings 29 of 14,283 values exceed 100 (up to 326), in the cohort 3 of 1,484 (up to 127). In the `metrics` block since 2025-07 no value exceeds 100 (4,903 readings). The paper states the cause and the count.
- **Decision log in the package.** The public `DECISIONS.md` becomes a concise log kept by hand (timeline, frozen design, every deviation with its timing, about 2,300 words); this full record ships beside it as `docs/decision_log_full.md`. No definition or result changes.
