# Data directory

Raw downloads are not redistributed. Each one has a row in the provenance table below: what it is, where it came from,
when it was downloaded, its checksum (SHA-256) and its licence.

Checksums are computed with `shasum -a 256 <file>`.

## Provenance

| File | What it is | Source | Download date | SHA-256 | Licence |
|---|---|---|---|---|---|
| `raw/crossd/index_20261103.json` | project list and snapshot timestamps | CrOSSD API `health.crossd.tech/api` | 2026-11-03 | `7b1005ae2b0ba89a8fbc77dbc17ba6e95c04dc034313e16974040af64f54f99e` | see CrOSSD terms |
| `raw/crossd/metrics.jsonl.gz` | raw `/api/metrics` responses, append-only cache | CrOSSD API `health.crossd.tech/api` | 2026-11-03 | `9ae1d92ed367cfcb27071a83ad2b5fbab1b6eb99b26908745326fefc751085ad` | see CrOSSD terms |
| `raw/crossd/strata/most-starred-repos.yaml` | crawl list of 2024-04-09 | `FH-CrOSSD/crossd` at 604a0c6, `cronjobs/` | 2026-11-03 | `9c51f0bb9859d2793e9102cca9bfc9e2a4b2692d3f32dd1b41102d140679ef81` | Apache-2.0 |
| `raw/crossd/strata/random-sample-repos.yaml` | crawl list of 2024-04-09 | `FH-CrOSSD/crossd` at 604a0c6, `cronjobs/` | 2026-11-03 | `e4013e98731732063047541010837254961a61ebcc6260226f9e190ced1d322e` | Apache-2.0 |
| `raw/crossd/strata/netidee_configmap.yaml` | crawl list, from 2025-07 | `FH-CrOSSD/crossd` at 604a0c6, `cronjobs/` | 2026-11-03 | `8ff0b3e955767b6e75f3018ba1234ccedbf6375dcb145d1f561f1eea44e6e7c5` | Apache-2.0 |
| `raw/depsdev/projects_2026-11-03.jsonl` | repository to package versions, current state | deps.dev API v3 | 2026-11-03 | `01eda5f67aa93a8894dc3932e2476ba58c825dfed41fddebd991fb59be0398e4` | CC-BY 4.0 |
| `raw/depsdev/package_details_2026-11-03.jsonl` | release dates and claimed repository per package | deps.dev API v3 | 2026-11-03 | `bb9e0cb4f91f68b9ea7d9326574e92ba5b15db37707c480b86ff80a314c4fde2` | CC-BY 4.0 |
| `raw/kev/2026-11-03/known_exploited_vulnerabilities.json` | CISA KEV, outcome data freeze | cisa.gov feed | 2026-11-03 | `3aa9cf3c01f116362a29d111702979175453c425e3733bde80fc4f6f8e2294e5` | see source |
| `raw/osv/2026-11-03/npm_all.zip` | OSV advisories, npm, outcome data freeze | `gs://osv-vulnerabilities/npm/all.zip` | 2026-11-03 | `3814a131180280397ac3a17212b53e28b621bd86047573179d29912e7574a1d2` | see OSV; per source database |
| `raw/osv/2026-11-03/PyPI_all.zip` | OSV advisories, PyPI, outcome data freeze | `gs://osv-vulnerabilities/PyPI/all.zip` | 2026-11-03 | `e2647e224466cf6fad09908fc315b12d2612fbeb2126222216bf323d35a546a4` | see OSV; per source database |
| `raw/osv/2026-11-03/Go_all.zip` | OSV advisories, Go, outcome data freeze | `gs://osv-vulnerabilities/Go/all.zip` | 2026-11-03 | `099078f900df9f2218d486bbe94bdccd9ac536b692d54d3fe86c7d163df2bbd1` | see OSV; per source database |
| `raw/osv/2026-11-03/Maven_all.zip` | OSV advisories, Maven, outcome data freeze | `gs://osv-vulnerabilities/Maven/all.zip` | 2026-11-03 | `8cf2d62ea80e51b24ba795c781ad4070129be4c7e7b5a841950ba9e307048a78` | see OSV; per source database |
| `raw/osv/2026-11-03/crates.io_all.zip` | OSV advisories, crates.io, outcome data freeze | `gs://osv-vulnerabilities/crates.io/all.zip` | 2026-11-03 | `af80c73772740b5dd2f00380da7635ee1618fc7480a7596466193b530e2ae88e` | see OSV; per source database |
| `raw/osv/2026-11-03/NuGet_all.zip` | OSV advisories, NuGet, outcome data freeze | `gs://osv-vulnerabilities/NuGet/all.zip` | 2026-11-03 | `1fa3623416c8f30b19c902b702a61e8c1bc385f628f333051502b333cbaebf6e` | see OSV; per source database |
| `raw/osv/2026-11-03/RubyGems_all.zip` | OSV advisories, RubyGems, outcome data freeze | `gs://osv-vulnerabilities/RubyGems/all.zip` | 2026-11-03 | `8e865fd8adb4f53b8ffe19c8e9ab1ae73fb3da5153d9d358b1d6e0e81656ed81` | see OSV; per source database |
| `raw/osv/2026-11-03/Packagist_all.zip` | OSV advisories, Packagist, outcome data freeze | `gs://osv-vulnerabilities/Packagist/all.zip` | 2026-11-03 | `56889ad3ba42a3d594541af4e387e0cd4ba64c6956abd0d15f73f4b6dd936bae` | see OSV; per source database |
| `raw/osv/2026-11-03/GIT_all.zip` | OSV advisories, GIT, outcome data freeze | `gs://osv-vulnerabilities/GIT/all.zip` | 2026-11-03 | `d2773742619e840200b45fb1473dfc5ede116c2953758c708252c0a8cacfa027` | see OSV; per source database |
| `raw/osv/2026-11-03/OSS-Fuzz_all.zip` | OSV advisories, OSS-Fuzz, outcome data freeze | `gs://osv-vulnerabilities/OSS-Fuzz/all.zip` | 2026-11-03 | `79dc9901ae41c2c19b0f6df947da0d65cce9881a473edcf9a4d6b7f91fb61aa6` | see OSV; per source database |
| `raw/docs/*` (11 files) | instrument documentation for the claim table; digest over the sorted file digests | commits pinned in `collect_claims.py`; opencode.de badge page | 2026-11-03 | `54d4f886bbed946e6133ce56c91359c1419e88d68ea1b8c6b820cea2564a4bb2` | per source |
| `raw/depsdev/package_links_2024-07-29.parquet` | repository to package links at the snapshot before t0 | BigQuery `deps_dev_v1.PackageVersionToProject` | 2026-11-03 | `32af5b8e5f0ada27ebbdd2dbf3cd35230e9d310089577593cf6358cf8eb109dc` | CC-BY 4.0 |
| `raw/depsdev/projects_2024-07-29.parquet` | stars and OSS-Fuzz coverage at the snapshot before t0 | BigQuery `deps_dev_v1.Projects` | 2026-11-03 | `5355ed71d915de5c7ac0f15fcb39dd7244193f398b9a1a7ed69e351d43d15db7` | CC-BY 4.0 |
| `raw/github/meta_2024-08-01.jsonl` | rename, archive date, commit counts, releases per repository, current state of history | GitHub GraphQL | 2026-11-03 | `b960c9ac134e7114d75993894653cf453b5173e902cdd3f4966191fd5cf29a1c` | GitHub terms |
| `raw/github/tags_2024-08-01.jsonl` | tag dates of quiet repositories | GitHub GraphQL | 2026-11-03 | `15600141f614d2d693fc2252fcdc1148be19ab683418cb43c3a048360beb36f7` | GitHub terms |
| `raw/github/fix_tags_2024-08-01.jsonl` | tags naming fixed versions missing from the registry | GitHub GraphQL | 2026-11-03 | `139e42077c870b78e56642a32cd0dc028492f183f032349da9db8a0eefa97bab` | GitHub terms |
| `raw/github/gone_2024-08-01.jsonl` | Software Heritage visits of repositories gone from GitHub | Software Heritage API | 2026-11-03 | `dd13852b631e84b768b19704693d494c9d44007eb10a776978624075ca0aa86e` | CC-BY 4.0 |
| `raw/depsdev/dependents_2024-07-29.parquet` | dependents per package at the snapshot before t0, for I1 | BigQuery `deps_dev_v1.Dependents` | 2026-11-03 | `754131ca1262c12033812c1961af82162a97a749eded1ad21af960a36a8cb45c` | CC-BY 4.0 |
| `raw/github/issues_2024-08-01.jsonl` | issues opened in the window, with maintainer response within 90 days; stops at 3 under the strictest reading | GitHub GraphQL | 2026-11-03 | `1c615e55e25b6e8caec274a784ccef6b2b3e6916a5c67b92d80741925c11e898` | GitHub terms |

Derived files under `data/probes/`, `data/processed/` and `data/claims/` are regenerated by
`analysis/run_all.py` and carry no checksum here.

## Outcome-data freeze dates

OSV and KEV: 2026-11-03. Recorded in the table above and, once frozen, in
`DECISIONS.md`.
Every script that reads an outcome input takes the freeze date as an argument and fails
on rows later than it.

## Published values for fidelity and freshness (accessed 2026-11-04, never a feature at t0)

| Source | File | Checksum (sha256) |
|---|---|---|
| BigQuery `openssf.criticality_score_cron.criticality-score-v0`, 28 lists from 2022-11-11 to 2025-07-25, cohort rows only, read 2026-11-04 | `data/raw/criticality/history_cohort_2024-08-01.parquet`, `data/probes/criticality_lists.csv` | table may vanish, so the parquet is the frozen copy |
| Case panel: Scorecard CLI, GraphQL, git, BigQuery for eight incident projects, read 2026-11-04 | `data/raw/cases/instruments.jsonl`, `data/raw/cases/criticality_lists.parquet` | illustrations only |
| GH Archive `WatchEvent` rows, 2011 to 2024-07, 170 GB scan, read 2026-11-04 | `data/raw/gharchive/stars_2024-08-01.parquet` | counts only |
| `ossf/criticality_score`, `data/20250725_all.csv.gz` (30.2 MB) | `data/raw/criticality/20250725_all.csv.gz` | `86f635183dfdbf023af3d48f499c3f5cb574cc5902d966b20fa38cb35dad61f4` |
| Scorecard CLI v5.6.0 at the last commit before t0, seven checks, read 2026-11-04 | `data/raw/scorecard/t0_2024-08-01.jsonl` | last line per project counts; 1,642 of 1,646 with a result |
| Frozen feature table, from the adapters | `data/processed/features_2024-08-01.parquet` | `5c7807edff66d21ff16b0bd0264a2b2571d8a02478d75efdab30d7cff317f722` |
| `api.scorecard.dev`, one request per cohort repository | `data/raw/scorecard/published_2026-11-04.jsonl` | none: rebuilt by `collect_published.py`, kept as collected |

Second freeze date (2025-01-01, robustness): the same sources read 2026-11-04/05 under `*_2025-01-01*`. `gone_events` and `history_cohort` are copies from the first date (`analysis/04_validity/prepare_second_date.py`).

