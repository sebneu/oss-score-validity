# Decision log

What was fixed, when, and what changed afterwards. Every change is dated relative to the first join of scores and outcomes, because that decides whether a choice could follow the results. The full chronological log, with all counts and intermediate checks, is in `docs/decision_log_full.md`. Commit hashes refer to the private working repository; what can be checked publicly is the OSF timestamp and the cohort checksum.

## 1. Timeline

| Date | Step | What was known |
|---|---|---|
| 2026-11-03 | Outcome definitions, t0, horizon and eligibility frozen (commit 7950cce6dafd) | outcome base rates; no score joined to any outcome |
| 2026-11-04 | Amendment 1 (commit 3fa3f5df2e66): composite maintenance outcome, unanswered issues as a share, demand split of dormancy, dating of gone repositories, later dependents for all projects, analysis plan | outcome base rates only |
| 2026-11-04, 10:36 UTC | Registered on OSF as a preregistration on existing data: [osf.io/ft8uw](https://osf.io/ft8uw) | as above |
| 2026-11-04 | Instrument readings and test details fixed (sections 4 and 5) | no score joined |
| 2026-11-04 | First join of scores and outcomes (commit 6e6ac7d319fc) | — |
| 2026-11-05 to 2026-11-10 | Changes and added analyses after the results (sections 6 and 7) | results known |

If the registration and this log differ, the difference is reported.

## 2. Cohort and freeze date

- **Frame:** the CrOSSD lists `most-starred` and `random-sample` of 2024-04-09. Later additions to the panel do not exist at t0. The second list is called the filtered sample: its query is known (GitHub search, `stars:>0`, sorted by update), but the query alone does not produce it, and the further filter is unknown (section 8).
- **t0:** 2024-08-01. **Window:** (2024-08-01, 2026-08-01]. **Second freeze date:** 2025-01-01, 12 months, most-starred list only, as a robustness check.
- **Point in time:** a value is dated by `observed_ts`, the time it was read from GitHub, not by its snapshot date. The reading can follow the snapshot by up to 29 days; with the snapshot date, 1,751 of 1,943 projects would carry values read after t0.
- **Eligibility:** read in the 14 days before t0; a default-branch commit in the 180 days before t0, or the repository is gone today and was read in the window; not archived at t0.
- **Cohort:** 1,687 projects, 780 most-starred and 907 filtered sample, `analysis/01_cohort/cohort_2024-08-01.csv`, SHA-256 `39df43f1c24ab76de6563f1f8555347e21b0ddde8282cc222910b6b55727612b`.
- **Values:** the latest reading with `observed_ts` ≤ t0. A missing value keeps the project in the cohort; each instrument reports its coverage. Feature table frozen before the first join: `data/processed/features_2024-08-01.parquet`, SHA-256 `5c7807edff66d21ff16b0bd0264a2b2571d8a02478d75efdab30d7cff317f722`.
- **Outcome data:** OSV and the CISA KEV catalogue of 2026-11-03; deps.dev snapshots of 2024-07-29 and 2026-07-27.

## 3. Outcomes as registered

| Outcome | Definition |
|---|---|
| Maintenance failure (O1, primary) | O1a or O1b |
| O1a archived or gone | archived in the window, or the repository is gone without a redirect, unless Software Heritage or a GH Archive event shows it existed after the window |
| O1b dormant | no default-branch commit, release or tag in the last 12 months of the window; split into *demand* (an unanswered external issue in those 12 months), *quiet* and *unknown* |
| Unanswered issues (O1c share, primary) | up to 25 issues per quarter of the window, opened by others than owners, members and collaborators; unanswered if not closed and without a comment by an owner, member, collaborator or contributor within 90 days; event if at least 10 such issues and at least half unanswered |
| Unfixed advisory (O2b, primary) | a severe advisory (CVSS v3 ≥ 7.0 or GHSA high or critical; not withdrawn, not malicious) published in the window and attached through a package that names only this repository, with no fixed version listed at the data freeze, at least 90 days after publication, or in KEV |
| Later dependents (I1b) | dependents at 2026-07-27 of the project's most depended-on package; dependents at 2024-07-29 are the baseline |

**Changed before registration (Amendment 1), original still reported:** unanswered issues as a fixed count of three (it measured issue volume: 0% below 3 issues, 95% at 1,000 or more), maintenance failure as two separate outcomes, impact only for projects with an advisory.

**Minimum events:** 40 in the pooled cohort; a list gets its own statistics only with 40 events of its own, otherwise it is descriptive.

**Sensitivity variants:** 12-month window; dormancy of 6 months; CVSS 9.0; response window of 30 days; archived only; verified advisories only; unanswered-issue cut-offs 25% and 75%; responders without contributors; the outcomes as first frozen.

## 4. Analysis plan as registered and fixed before the first join

- **Primary pairs (11):** against failure Scorecard `Maintained`, openCode maintenance badge, CrOSSD maturity level, bus factor, elephant factor; against unanswered issues CrOSSD support rate, openCode response criterion; against unfixed advisories Scorecard aggregate, openCode security badge; against later dependents CrOSSD criticality and the published OpenSSF Criticality Score. Everything else is secondary.
- **Direction:** a low value warns, except for the criticality scores.
- **Warns:** lower bound of the 95% bootstrap interval of the AUROC above 0.60 (Mann-Whitney, ties counted half; percentile bootstrap over projects, 2,000 resamples, seed 20240801). For later dependents: a rank correlation above zero.
- **Adds information (registered):** logistic baseline on log stars, age, days since last commit, commits in 90 days, contributors in 12 months and dependents; out-of-sample gain in AUROC with a lower bound above 0 and at least 0.02, the score's coefficient in the warning direction, Holm correction over the family. For later dependents the gain in R² over log dependents at t0.
- **Missing values:** not missing at random (the bus factor goes missing with low activity, the criticality score with few issues). Each score is tested on available values with its coverage; the bus factor also with a missing value read as a warning.
- **Error rates:** at documented flags only (Maintained = 0; openCode badges absent; openCode response failed), plus "at most 1" for bus and elephant factor, marked as our reading.
- **Prevalence:** Rogan–Gladen. Inside one list it returns the observed share by algebra, so error rates from one list correct the flag share of the other; not estimable if the interval of J from the source list includes 0. Fixed before the first join; it goes beyond the registered text.
- **Expectations, written down beforehand:** maintenance scores warn of failure but add little over recent activity; security scores do not warn of unfixed advisories; criticality scores track later dependents but add little over earlier dependents. All three held.

## 5. Readings of the instruments (fixed before the first join)

| Instrument | Reading at t0 |
|---|---|
| CrOSSD | values as recorded, from the code of `thesis_metrics` at d98b84d. The bus factor was checked against a rebuild from dated commits: it matches for a one-month window (86% exact), not for the documented six months (56%), and gives 0 instead of the documented minimum 1 when one identity holds 80% of commits. The stored value stays the reading; the gap is a result. |
| Scorecard | v5.6.0 run at the last commit before t0. Kept: Maintained (rebuilt by its rule, reading issues active in its 90-day window, up to 100), Binary-Artifacts, Dangerous-Workflow, Token-Permissions, Pinned-Dependencies, Code-Review, Security-Policy (an owner-level policy counts only if committed by t0); 50 of 120 weight points. Excluded because they read today's state even at a commit: License, Vulnerabilities, CI-Tests (337 of 338 results read 0, since GitHub deletes old check data). Excluded because the tool refuses them at a commit: Dependency-Update-Tool, Packaging, Signed-Releases, Fuzzing, SAST, SBOM. |
| OpenSSF Criticality Score | the published list of 2024-07-18, the last before t0, recorded at the time. This replaced our rebuild by the documented formula, before the first join; the rebuild is a sensitivity check. |
| openCode | the published rules, implemented by us; criteria without activity in their window count as met; branch protection and force pushes (level 1) and the vulnerability criteria (level 3) cannot be backdated, so the security badge uses levels 0 to 2 over the remaining criteria. |
| Baselines | stars from deps.dev at 2024-07-29, else from GH Archive star events before t0; age, commits, contributors and last commit from git; dependents from the CrOSSD value at t0. |

## 6. Deviations from the registration

| # | Change | When | Effect |
|---|---|---|---|
| 1 | Fourth research question (validity as queryable data) dropped; each score is reported with its validity as one table and a file | after registration, before the first join | none on cohort, outcomes or tests; stated in the paper |
| 2 | 30-day response window applied to unfixed advisories as drafted; the unanswered share cannot be recomputed at 30 days | before the first join | one variant fewer |
| 3 | A flag with J clearly below zero is reported as "J < 0" instead of a corrected share | after the first join | one corrected share not given |
| 4 | Main text without regression and Holm: "adds information" is read as the score against single measures and as the AUROC within quartiles of activity ("holds" if the lower bound is above 0.60) | after the results | the registered model and Holm tests ship in `analysis/04_validity/registered_analysis.csv`; dropping Holm changes no "warns" verdict; under the registered model only the openCode response criterion adds information, while the bus factor and the elephant factor, which hold at similar activity, do not |
| 5 | The issue sample takes the 25 earliest issues per quarter and keeps the external ones, while the text says the 25 earliest external issues; the code was so before the first run | found after the results | the base can change by at most 7 projects; stated in the paper |
| 6 | Later dependents: projects without a deps.dev row at either date lack a count; reported again with a missing row read as zero, an upper bound | after the results | the order of the two scores changes, the earlier count stays ahead of both |
| 7 | Second freeze date without the Scorecard aggregate and later dependents; GH Archive dating of gone repositories from August 2026 only | after the results | at most two failures affected |

## 7. Analyses added after the results (descriptive)

- AUROC on existing repositories only, from a separate random generator: the elephant factor no longer meets the rule there.
- The 0.60 line moved to 0.55 and 0.65, to show how the count of warning scores depends on it.
- The comparison at similar activity, checked with quartiles of the days since the last commit.
- The published Scorecard scan of 2024-07-29 (v5.0.0, 875 projects) as a test of the rebuild.
- The bus factor as documented (six months): it warns, and does not hold at similar activity.
- Later dependents with the package fixed at t0 (outside the paper): same conclusion.
- Days since the last commit and commits in 90 days per list, as reference rows, from a separate seed.

## 8. What the sources showed

- **CrOSSD records were taken at the time.** No stored field is younger than its reading; the core metrics are only created, never updated; stored merged-PR counts match GitHub's count for the time of reading (130 of 150 within 1%; all 108 that grew by more than 2% lie closer to the earlier count).
- **Support rate above 100.** In the code of 2024 the numerator counts commented issues that the denominator may not contain: 3 of 1,484 cohort values exceed 100 (up to 127). Readings since July 2025 stay within 100.
- **Filtered sample.** The query run again on 2026-11-10 gives a median of 2 stars and 787 of 1,000 repositories under 10 stars; the list has a median of 164 stars today and 9 of 913 under 10. A further filter applies and is unknown (`data/probes/random_list_query_2026-11-10.csv`).
- **The random-sample series stops on 2024-08-09,** after t0, for the whole list; outcomes do not come from CrOSSD, so this has no effect.
- **Criticality Score:** the collector counts pull requests as issues, and the share of published repositories with all issue signals at zero rose from 12% (May 2024) to 89.5% (July 2025). At the 2024-07-18 list only 5 to 8% of cohort values per signal are zero.
- **Current state that cannot be avoided:** the author association of comments and reviews is the one GitHub shows today; two repositories were recreated after t0 and lost their pre-t0 issues; the dated stargazer list is closed to outside accounts, so stars come from deps.dev or GH Archive.
- **One advisory for a compromise** (Ultralytics, PYSEC-2024-154) carries no malicious marker and counts as a severe advisory under the frozen rule; it was not relabelled.

## 9. Case panel

Illustrations only, selected on the outcome, in no statistic. Selected by a screen of the panel for advisories in the KEV catalogue, malicious code in a legitimate package, and archived repositories; one case per mechanism where possible: axios and Lightning (hijacked release), React and MongoDB (exploited flaw), MinIO (end of maintenance), Ultralytics (workflow injection). XZ Utils and tj-actions are not in the panel and are rebuilt at the day before their event. Readings and the component that claims each risk were fixed before the values were read; the t0 values of four cases had been seen while checking the adapters, which is disclosed. The panel has almost no readings from 2025-10-02 to 2026-01-26.
