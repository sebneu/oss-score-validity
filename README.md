# Would the Score Have Warned Us?

Replication package for *Would the Score Have Warned Us? A Point-in-Time Validity Audit of Open-Source Health and Security Scores* (Sebastian Neumaier, Tobias Dam).

## Reproduce

Python 3.13. Runs offline in about five minutes and regenerates the tables, figures and numbers of the paper from the derived data in this repository.

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python analysis/run_all.py --reproduce
```

`analysis/run_all.py` without the flag rebuilds the derived data from the sources. This needs the raw downloads, a GitHub token, BigQuery and the Scorecard CLI (`.env.example`). Sources and checksums are in `data/README.md`. Raw data are not redistributed.

## Contents

| Path | What it holds |
|---|---|
| `analysis/01_cohort/` | Cohort manifests. `cohort_2024-08-01.csv` is the list with the SHA-256 in the registration (osf.io/ft8uw) |
| `analysis/02_outcomes/`, `03_instruments/` | Outcome labels and one adapter per instrument, each at the freeze date |
| `analysis/04_validity/` | Validity statistics, `measured_validity.csv` (the summary table as a file), `registered_analysis.csv` (the registered model with Holm correction) |
| `analysis/05_cases/` | Case panel, outside the statistics |
| `data/processed/` | Frozen features and outcome labels |
| `data/probes/` | Results behind each table, among them PR-AUC and lift (`validity_primary.csv`) and all sensitivity variants (`validity_sensitivity.csv`) |
| `paper/` | Generated tables, number macros and figures |
| `DECISIONS.md` | Decision log: frozen definitions, amendments, deviations |

## Licence

Code: MIT. Derived data, tables and figures: CC BY 4.0.
