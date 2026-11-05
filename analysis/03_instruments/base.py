"""Shared rules for the instrument adapters.

Point-in-time rule: nothing timestamped after t0 enters a feature. `before_t0` and
`assert_not_after` make that a failure in the code rather than a habit.

Every adapter writes one long table, data/processed/features/<instrument>_<t0>.parquet, with one row
per project and component: value, evidence type and the time the value rests on. Evidence types are
`recorded` (stored at the time), `reconstructed` (rebuilt from dated events) and `not_backdatable`.

No adapter reads outcomes. Scores and outcomes meet in `analysis/04_validity/` only.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FEATURES = PROCESSED / "features"

RECORDED = "recorded"
RECONSTRUCTED = "reconstructed"
NOT_BACKDATABLE = "not_backdatable"


class AfterFreezeDate(RuntimeError):
    """An input carries a time after the freeze date."""


def freeze(t0: str) -> datetime:
    return datetime.fromisoformat(t0).replace(tzinfo=UTC)


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_not_after(when: datetime | float, t0: datetime, what: str = "input") -> None:
    stamp = datetime.fromtimestamp(when, UTC) if isinstance(when, (int, float)) else when
    if stamp > t0:
        raise AfterFreezeDate(f"{what} at {stamp.isoformat()} is after the freeze date {t0.date()}")


def add_months(date: datetime, months: int) -> datetime:
    index = date.month - 1 + months
    year, month = date.year + index // 12, index % 12 + 1
    return date.replace(year=year, month=month, day=min(date.day, monthrange(year, month)[1]))


def days_before(t0: datetime, days: int) -> datetime:
    return t0 - timedelta(days=days)


def git_dir(t0: str) -> Path:
    """Derived commit tables per freeze date; the frozen date keeps its original folder."""
    return PROCESSED / ("git" if t0 == "2024-08-01" else f"git_{t0}")


def cohort(t0: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / "analysis" / "01_cohort" / f"cohort_{t0}.csv")


def row(project: str, component: str, value, evidence: str, as_of: float | None = None) -> dict:
    return {"project": project, "component": component,
            "value": None if value is None else float(value),
            "evidence": evidence, "as_of": as_of}


def write_features(instrument: str, t0: str, rows: list[dict]) -> Path:
    table = pd.DataFrame(rows)
    limit = freeze(t0).timestamp()
    late = table[table.as_of.notna() & (table.as_of > limit)]
    if len(late):
        raise AfterFreezeDate(f"{instrument}: {len(late)} values rest on data after the freeze date")
    FEATURES.mkdir(parents=True, exist_ok=True)
    path = FEATURES / f"{instrument}_{t0}.parquet"
    table.to_parquet(path, index=False)
    covered = table[table["value"].notna()].groupby("component").project.nunique()
    print(f"{path.relative_to(ROOT)}: {len(table)} rows")
    print(covered.to_string())
    return path
