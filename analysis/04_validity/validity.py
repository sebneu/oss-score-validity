#!/usr/bin/env python3
"""RQ2 and RQ3: scores at t0 against later events.

The first script that reads scores and outcomes together. The readings are fixed in DECISIONS.md: Freeze,
Amendment 1 (A6, A7) and "S5: details fixed before the first join" (commit c8a5a1212fbb).

Outputs, all in data/probes/:
  validity_primary.csv      the 11 primary pairs, pooled, with rules, Holm and verdicts
  validity_strata.csv       the same pairs per list; below 40 events they are marked descriptive
  validity_secondary.csv    every other pairing, labelled secondary
  validity_sensitivity.csv  primary pairs on the outcome variants
  validity_baseline.csv     the baseline model per outcome and list
  validity_thresholds.csv   documented operating points: Se, Sp, J, PPV
  validity_prevalence.csv   flag share, observed share and the correction across lists
  validity_flags.csv        who the Maintained flag finds and misses, and missing bus factors

Usage:
    python analysis/04_validity/validity.py --t0 2024-08-01 --resamples 2000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2, rankdata
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
PROBES = ROOT / "data" / "probes"
SEED = 20240801
MIN_EVENTS = 40
BASELINE = ["stars", "age_days", "days_since_last_commit", "commits_90d", "contributors_12m", "dependents"]

# id, instrument, component, outcome, sign: -1 means a low value warns
PRIMARY = [
    ("Scorecard Maintained", "scorecard", "scorecard_Maintained", "O1", -1),
    ("openCode maintenance", "opencode", "opencode_maintenance", "O1", -1),
    ("CrOSSD maturity", "crossd", "maturity_level", "O1", -1),
    ("CrOSSD bus factor", "crossd", "bus_factor", "O1", -1),
    ("CrOSSD elephant factor", "crossd", "elephant_factor", "O1", -1),
    ("CrOSSD support rate", "crossd", "support_rate", "O1c_share", -1),
    ("openCode issue response", "opencode", "opencode_response_ok", "O1c_share", -1),
    ("Scorecard aggregate", "scorecard", "scorecard_aggregate_t0", "O2b", -1),
    ("openCode security", "opencode", "opencode_security", "O2b", -1),
    ("CrOSSD criticality", "crossd", "criticality_score", "I1b", 1),
    ("OpenSSF Criticality", "criticality_published", "openssf_criticality_published", "I1b", 1),
]

CHECKS = ["Binary-Artifacts", "Code-Review", "Dangerous-Workflow", "Pinned-Dependencies", "Security-Policy", "Token-Permissions"]
SECONDARY = [
    *[(f"Scorecard {c}", "scorecard", f"scorecard_{c}", "O2b", -1) for c in CHECKS],
    *[(f"Scorecard {c}", "scorecard", f"scorecard_{c}", "O2a", -1) for c in CHECKS],
    ("Scorecard Maintained", "scorecard", "scorecard_Maintained", "O2b", -1),
    ("Scorecard Maintained", "scorecard", "scorecard_Maintained", "O2a", -1),
    ("Scorecard aggregate", "scorecard", "scorecard_aggregate_t0", "O2a", -1),
    ("Scorecard aggregate", "scorecard", "scorecard_aggregate_t0", "O1", -1),
    ("openCode security", "opencode", "opencode_security", "O2a", -1),
    ("openCode security policy", "opencode", "opencode_security_policy", "O2b", -1),
    ("openCode reviewed share", "opencode", "opencode_reviewed_share", "O2b", -1),
    ("openCode response days", "opencode", "opencode_response_days", "O1c_share", 1),
    ("openCode issue response", "opencode", "opencode_response_ok", "O1", -1),
    ("CrOSSD community health", "crossd", "community_health", "O1", -1),
    ("CrOSSD velocity ratio", "crossd", "project_velocity_ratio_closed", "O1", -1),
    ("CrOSSD support rate", "crossd", "support_rate", "O1", -1),
    ("CrOSSD first response", "crossd", "first_response_days", "O1c_share", 1),
    ("CrOSSD maturity", "crossd", "maturity_level", "O2b", -1),
    ("CrOSSD bus factor (rebuilt)", "crossd_rebuilt", "bus_factor", "O1", -1),
    ("CrOSSD bus factor (missing warns)", "crossd", "bus_factor:missing", "O1", -1),
    ("OpenSSF Criticality (rebuilt)", "criticality", "openssf_criticality", "I1b", 1),
    *[(f"Baseline {b}", "baselines", b, outcome, 1 if b == "days_since_last_commit" else -1) for b in BASELINE for outcome in ("O1", "O1c_share", "O2b")],
    *[(name, inst, comp, outcome, sign) for name, inst, comp, o, sign in PRIMARY if o == "O1" for outcome in ("O1a_v2", "O1b", "O1b_demand", "O1b_quiet")],
]

VARIANTS = {
    "O1": ["O1_12m", "O1_dormant6m", "O1_archived", "O1_demand"],
    "O1c_share": ["O1c_share_25", "O1c_share_75", "O1c_share_narrow", "O1c", "O1c_drafted", "O1c_external"],
    "O2b": ["O2b_drafted", "O2b_drafted_30d", "O2b_12m", "O2b_cvss9"],
    "I1b": ["I1"],
}

# name, instrument, component, outcome, the flag, documented or our reading
THRESHOLDS = [
    ("Scorecard Maintained = 0", "scorecard", "scorecard_Maintained", "O1", lambda v: v == 0, "documented"),
    ("openCode maintenance, no badge", "opencode", "opencode_maintenance", "O1", lambda v: v == 0, "documented"),
    ("openCode maintenance below L2", "opencode", "opencode_maintenance", "O1", lambda v: v < 2, "documented"),
    ("openCode maintenance below L3", "opencode", "opencode_maintenance", "O1", lambda v: v < 3, "documented"),
    ("openCode response criterion failed", "opencode", "opencode_response_ok", "O1c_share", lambda v: v == 0, "documented"),
    ("openCode security, no badge", "opencode", "opencode_security", "O2b", lambda v: v == 0, "documented"),
    ("CrOSSD bus factor at most 1", "crossd", "bus_factor", "O1", lambda v: v <= 1, "ours"),
    ("CrOSSD elephant factor at most 1", "crossd", "elephant_factor", "O1", lambda v: v <= 1, "ours"),
]


def auroc(score: np.ndarray, y: np.ndarray) -> float:
    pos = y.sum()
    neg = len(y) - pos
    if pos == 0 or neg == 0:
        return np.nan
    return (rankdata(score)[y].sum() - pos * (pos + 1) / 2) / (pos * neg)


def lift_top(score: np.ndarray, y: np.ndarray, share: float = 0.10) -> float:
    """Event rate in the worst share over the base rate; a tied group at the boundary counts by its fraction."""
    frame = pd.DataFrame({"s": score, "y": y}).groupby("s", sort=True).y.agg(["size", "sum"]).iloc[::-1]
    room, events = share * len(y), 0.0
    for size, hits in zip(frame["size"], frame["sum"]):
        take = min(room, size)
        events += hits * take / size
        room -= take
        if room <= 0:
            break
    return (events / (share * len(y))) / y.mean()


def interval(values: np.ndarray) -> tuple[float, float]:
    return tuple(np.nanpercentile(values, [2.5, 97.5]))


def fit_logit(X: np.ndarray, y: np.ndarray, iterations: int = 30) -> np.ndarray:
    """Logistic regression by Newton steps, with a negligible ridge for stability under separation."""
    beta = np.zeros(X.shape[1])
    ridge = 1e-8 * np.eye(X.shape[1])
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-np.clip(X @ beta, -30, 30)))
        w = np.maximum(p * (1 - p), 1e-9)
        step = np.linalg.solve((X.T * w) @ X + ridge, X.T @ (y - p))
        beta += step
        if np.abs(step).max() < 1e-7:
            break
    return beta


def log_lik(X: np.ndarray, y: np.ndarray, beta: np.ndarray) -> float:
    eta = np.clip(X @ beta, -30, 30)
    return float((y * eta - np.log1p(np.exp(eta))).sum())


def design(columns: list[np.ndarray]) -> np.ndarray:
    Z = np.column_stack(columns).astype(float)
    sd = Z.std(axis=0)
    Z = (Z - Z.mean(axis=0)) / np.where(sd > 0, sd, 1)
    return np.column_stack([np.ones(len(Z)), Z])


def resamples(n: int, count: int, rng: np.random.Generator) -> np.ndarray:
    return rng.integers(0, n, size=(count, n))


def score_stats(score: np.ndarray, y: np.ndarray, count: int, rng: np.random.Generator, with_pr: bool = True) -> dict:
    """AUROC, PR-AUC and lift, with percentile intervals and the one-sided test against 0.60."""
    out = {"n": len(y), "events": int(y.sum()), "base_rate": y.mean(), "auroc": auroc(score, y), "lift": lift_top(score, y)}
    draws = resamples(len(y), count, rng)
    aucs = np.array([auroc(score[i], y[i]) for i in draws])
    out["auroc_lo"], out["auroc_hi"] = interval(aucs)
    out["p_warn"] = (np.sum(~(aucs > 0.60)) + 1) / (count + 1)
    if with_pr:
        out["pr_auc"] = average_precision_score(y, score)
        prs = np.array([average_precision_score(y[i], score[i]) if y[i].any() else np.nan for i in draws])
        out["pr_lo"], out["pr_hi"] = interval(prs)
    return out


def gain_stats(score: np.ndarray, y: np.ndarray, base: np.ndarray, count: int, rng: np.random.Generator) -> dict:
    """Gain in AUROC over the baseline: out of sample, with a paired bootstrap, plus the likelihood-ratio test."""
    known = ~np.isnan(score) & ~np.isnan(base).any(axis=1)
    s, t, B = score[known], y[known], base[known]
    out = {"gain_n": len(t), "gain_events": int(t.sum())}
    if t.sum() < 5 or len(np.unique(s)) < 2:
        return out
    X0, X1 = design([B]), design([B, s])
    b0, b1 = fit_logit(X0, t), fit_logit(X1, t)
    out["base_auroc_in"], out["plus_auroc_in"] = auroc(X0 @ b0, t), auroc(X1 @ b1, t)
    out["gain_in_sample"] = out["plus_auroc_in"] - out["base_auroc_in"]
    stat = max(0.0, 2 * (log_lik(X1, t, b1) - log_lik(X0, t, b0)))
    out["p_lrt"] = float(chi2.sf(stat, 1))
    # the sign of the score's coefficient, turned so that positive means in the warning direction
    out["coef"] = float(b1[-1])
    pred0, pred1 = np.zeros(len(t)), np.zeros(len(t))
    for train, test in StratifiedKFold(10, shuffle=True, random_state=SEED).split(X0, t):
        pred0[test] = X0[test] @ fit_logit(X0[train], t[train])
        pred1[test] = X1[test] @ fit_logit(X1[train], t[train])
    out["base_auroc"], out["plus_auroc"] = auroc(pred0, t), auroc(pred1, t)
    out["gain"] = out["plus_auroc"] - out["base_auroc"]
    gains = []
    for idx in resamples(len(t), count, rng):
        left = np.setdiff1d(np.arange(len(t)), idx, assume_unique=False)
        if t[idx].sum() < 2 or t[left].sum() < 2 or t[left].all():
            continue
        c0, c1 = fit_logit(X0[idx], t[idx]), fit_logit(X1[idx], t[idx])
        gains.append(auroc(X1[left] @ c1, t[left]) - auroc(X0[left] @ c0, t[left]))
    out["gain_lo"], out["gain_hi"] = interval(np.array(gains))
    return out


def ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def r2(y: np.ndarray, pred: np.ndarray) -> float:
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    return np.corrcoef(rankdata(a), rankdata(b))[0, 1]


def dependents_stats(score: np.ndarray, later: np.ndarray, at_t0: np.ndarray, count: int, rng: np.random.Generator) -> dict:
    """Rank correlation with later dependents, and the gain in R² over dependents at t0."""
    known = ~np.isnan(score) & ~np.isnan(later) & ~np.isnan(at_t0)
    s, l, d = score[known], np.log1p(later[known]), np.log1p(at_t0[known])
    n = len(s)
    out = {"n": n, "events": n, "rho": spearman(s, l), "rho_t0": spearman(d, l), "gain_n": n}
    draws = resamples(n, count, rng)
    rhos = np.array([spearman(s[i], l[i]) for i in draws])
    out["rho_lo"], out["rho_hi"] = interval(rhos)
    out["p_warn"] = (np.sum(~(rhos > 0)) + 1) / (count + 1)
    X0, X1 = design([d]), design([d, s])
    b0, b1 = ols(X0, l), ols(X1, l)
    sse0, sse1 = ((l - X0 @ b0) ** 2).sum(), ((l - X1 @ b1) ** 2).sum()
    out["r2_base_in"], out["r2_plus_in"] = r2(l, X0 @ b0), r2(l, X1 @ b1)
    out["gain_in_sample"] = out["r2_plus_in"] - out["r2_base_in"]
    out["p_lrt"] = float(chi2.sf(max(0.0, n * np.log(sse0 / sse1)), 1))
    out["coef"] = float(b1[-1])
    pred0, pred1 = np.zeros(n), np.zeros(n)
    folds = np.random.default_rng(SEED).permutation(n) % 10
    for fold in range(10):
        test, train = folds == fold, folds != fold
        pred0[test] = X0[test] @ ols(X0[train], l[train])
        pred1[test] = X1[test] @ ols(X1[train], l[train])
    out["base_r2"], out["plus_r2"] = r2(l, pred0), r2(l, pred1)
    out["gain"] = out["plus_r2"] - out["base_r2"]
    gains = []
    for idx in draws:
        left = np.setdiff1d(np.arange(n), idx)
        if len(left) < 5:
            continue
        p0 = X0[left] @ ols(X0[idx], l[idx])
        p1 = X1[left] @ ols(X1[idx], l[idx])
        gains.append(r2(l[left], p1) - r2(l[left], p0))
    out["gain_lo"], out["gain_hi"] = interval(np.array(gains))
    return out


def holm(p: pd.Series) -> pd.Series:
    known = p.dropna().sort_values()
    m = len(known)
    adjusted, running = {}, 0.0
    for i, (key, value) in enumerate(known.items()):
        running = max(running, min(1.0, (m - i) * value))
        adjusted[key] = running
    return pd.Series(adjusted).reindex(p.index)


class Data:
    def __init__(self, t0: str) -> None:
        self.t0 = t0
        features = pd.read_parquet(PROCESSED / f"features_{t0}.parquet")
        self.features = features
        self.outcomes = pd.read_parquet(PROCESSED / f"outcomes_{t0}.parquet").set_index("project")
        path = PROCESSED / f"outcome_variants_{t0}.parquet"
        self.labels = self.outcomes.join(pd.read_parquet(path).set_index("project").drop(columns="stratum")) if path.exists() else self.outcomes
        self.projects = self.labels.index
        self.existing = pd.read_parquet(PROCESSED / f"github_meta_{t0}.parquet").set_index("project").resolved.reindex(self.projects).fillna(False).astype(bool)
        self.base = np.column_stack([np.log1p(self.values("baselines", b)) for b in BASELINE])

    def values(self, instrument: str, component: str) -> np.ndarray:
        missing_warns = component.endswith(":missing")
        name = component.removesuffix(":missing")
        part = self.features[(self.features.instrument == instrument) & (self.features.component == name)]
        series = part.set_index("project").value.reindex(self.projects).astype(float)
        if missing_warns:
            series = series.fillna(series.min() - 1)
        return series.to_numpy()

    def event_mask(self, outcome: str) -> tuple[np.ndarray, np.ndarray]:
        """The event and the projects that form the base of this outcome."""
        column = self.labels[outcome].astype("boolean")
        base = column.notna().to_numpy()
        if outcome.startswith("O2b"):
            base = base & self.labels.in_O2b_base.to_numpy()
        elif outcome.startswith("O2a"):
            base = base & self.labels.in_O2_base.to_numpy()
        return column.fillna(False).to_numpy(dtype=bool), base


def evaluate(data: Data, spec: tuple, mask: np.ndarray, count: int, rng: np.random.Generator, gain: bool = True, with_pr: bool = True) -> dict:
    name, instrument, component, outcome, sign = spec
    row = {"score": name, "instrument": instrument, "component": component, "outcome": outcome}
    values = data.values(instrument, component)
    if outcome in ("I1b", "I1"):
        later = pd.to_numeric(data.labels[outcome], errors="coerce").to_numpy(dtype=float)
        at_t0 = pd.to_numeric(data.labels.I1b_t0, errors="coerce").to_numpy(dtype=float)
        if outcome == "I1":  # dependents at t0 of the affected package: no earlier value to compare with
            known = ~np.isnan(values) & ~np.isnan(later) & mask
            row |= {"n": int(known.sum()), "events": int(known.sum()), "rho": spearman(values[known], later[known]) if known.sum() > 2 else np.nan}
            draws = resamples(int(known.sum()), count, rng)
            rhos = np.array([spearman(values[known][i], later[known][i]) for i in draws])
            row["rho_lo"], row["rho_hi"] = interval(rhos)
            return row
        in_base = mask & ~np.isnan(later) & ~np.isnan(at_t0)
        row["known_of_base"] = int(in_base.sum())
        row |= dependents_stats(values[in_base], later[in_base], at_t0[in_base], count, rng)
        row["coverage"] = row["n"] / row["known_of_base"]
        return row
    event, base = data.event_mask(outcome)
    in_base = mask & base
    known = in_base & ~np.isnan(values)
    row["known_of_base"] = int(in_base.sum())
    row["coverage"] = known.sum() / in_base.sum()
    row["events_in_base"] = int(event[in_base].sum())
    row |= score_stats(sign * values[known], event[known], count, rng, with_pr)
    if gain:
        row |= gain_stats(sign * values[in_base], event[in_base], data.base[in_base], count, rng)
    if data.existing[in_base].sum() < in_base.sum():
        keep = known & data.existing.to_numpy()
        row["auroc_existing"] = auroc(sign * values[keep], event[keep])
        row["n_existing"] = int(keep.sum())
        row["events_existing"] = int(event[keep].sum())
        # A separate generator, so that this interval leaves the stream of the registered statistics alone.
        side = np.random.default_rng([SEED, 1])
        aucs = np.array([auroc(sign * values[keep][i], event[keep][i]) for i in resamples(int(keep.sum()), count, side)])
        row["existing_lo"], row["existing_hi"] = interval(aucs)
    return row


def verdicts(table: pd.DataFrame) -> pd.DataFrame:
    table = table.copy()
    table["p_warn_holm"] = holm(table.p_warn)
    table["p_adds_holm"] = holm(table.p_lrt)
    # On I1b the registered question is the rank correlation.
    warn_rule = table.apply(lambda r: r.rho_lo > 0 if r.outcome == "I1b" else r.auroc_lo > 0.60, axis=1)
    table["warns"] = warn_rule & table.p_warn_holm.lt(0.05)
    table["adds"] = table.gain_lo.gt(0) & table.gain.ge(0.02) & table.p_adds_holm.lt(0.05) & table.coef.gt(0)
    return table


def thresholds_and_prevalence(data: Data, count: int, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, prevalence = [], []
    strata = data.labels.stratum.to_numpy()

    def rates(flag: np.ndarray, y: np.ndarray) -> tuple[float, float]:
        return flag[y].mean() if y.any() else np.nan, (~flag[~y]).mean() if (~y).any() else np.nan

    for name, instrument, component, outcome, rule, source in THRESHOLDS:
        values = data.values(instrument, component)
        event, base = data.event_mask(outcome)
        known = base & ~np.isnan(values)
        flag, y = rule(values[known]), event[known]
        se, sp = rates(flag, y)
        draws = resamples(len(y), count, rng)
        js = np.array([sum(rates(flag[i], y[i])) - 1 for i in draws])
        lo, hi = interval(js)
        rows.append({"operating_point": name, "source": source, "outcome": outcome, "n": len(y), "events": int(y.sum()), "flag_share": flag.mean(),
                     "event_share": y.mean(), "tp": int((flag & y).sum()), "fp": int((flag & ~y).sum()), "fn": int((~flag & y).sum()), "tn": int((~flag & ~y).sum()),
                     "sensitivity": se, "specificity": sp, "J": se + sp - 1, "J_lo": lo, "J_hi": hi, "ppv": y[flag].mean() if flag.any() else np.nan,
                     "npv": (~y[~flag]).mean() if (~flag).any() else np.nan})
        for src, dst in (("most_starred", "random_sample"), ("random_sample", "most_starred")):
            s, d = strata[known] == src, strata[known] == dst
            if y[s].sum() < MIN_EVENTS:
                prevalence.append({"operating_point": name, "outcome": outcome, "source_list": src, "target_list": dst, "source_events": int(y[s].sum()),
                                   "flag_share": flag[d].mean(), "observed_share": y[d].mean(), "status": "source below 40 events"})
                continue
            fs, ys, fd, yd = flag[s], y[s], flag[d], y[d]
            se_s, sp_s = rates(fs, ys)
            j = se_s + sp_s - 1
            estimates, jays = [], []
            for a, b in zip(resamples(len(ys), count, rng), resamples(len(yd), count, rng)):
                se_b, sp_b = rates(fs[a], ys[a])
                jays.append(se_b + sp_b - 1)
                estimates.append((fd[b].mean() + sp_b - 1) / jays[-1] if jays[-1] != 0 else np.nan)
            j_lo, j_hi = interval(np.array(jays))
            lo_c, hi_c = interval(np.array(estimates))
            estimable = j_lo > 0
            prevalence.append({"operating_point": name, "outcome": outcome, "source_list": src, "target_list": dst, "source_events": int(ys.sum()),
                               "target_n": len(yd), "flag_share": fd.mean(), "observed_share": yd.mean(), "J": j, "J_lo": j_lo, "J_hi": j_hi,
                               "corrected": (fd.mean() + sp_s - 1) / j if estimable else np.nan, "corrected_lo": lo_c if estimable else np.nan,
                               "corrected_hi": hi_c if estimable else np.nan, "status": "estimated" if estimable else ("J below zero" if j_hi < 0 else "not estimable")})
    return pd.DataFrame(rows), pd.DataFrame(prevalence)


def flag_profile(data: Data) -> dict:
    """Who the Maintained flag finds and misses, and what a missing bus factor means."""
    labels = data.labels
    meta = pd.read_parquet(PROCESSED / f"github_meta_{data.t0}.parquet").set_index("project")
    maintained = pd.Series(data.values("scorecard", "scorecard_Maintained"), index=labels.index)
    known = maintained.notna()
    failed = known & labels.O1
    alarms = known & maintained.eq(0) & ~labels.O1
    recent = meta.commits_last_12m.reindex(labels.index)[alarms]
    bus = pd.Series(data.values("crossd", "bus_factor"), index=labels.index)
    support = pd.Series(data.values("crossd", "support_rate"), index=labels.index)
    in_base = labels.O1c_share.notna() & support.notna()
    out = {
        "failed": int(failed.sum()), "failed_top": int(maintained[failed].eq(10).sum()), "others_top_share": maintained[known & ~labels.O1].eq(10).mean(),
        "alarms": int(alarms.sum()), "alarms_at_most_5": int(recent.le(5).sum()), "alarms_one_commit": int(recent.eq(1).sum()),
        "alarms_share_known": int(labels.O1c_share[alarms].notna().sum()), "alarms_share_event": int(labels.O1c_share[alarms].astype("boolean").sum()),
        "gone_events": int((labels.O1 & ~data.existing).sum()),
        "bus_missing": int(bus.isna().sum()), "bus_missing_rate": labels.O1[bus.isna()].mean(), "bus_known_rate": labels.O1[bus.notna()].mean(), "bus_missing_events": int(labels.O1[bus.isna()].sum()),
        "support_max": support.max(), "support_rho": spearman(support[in_base].to_numpy(), labels.share_unanswered[in_base].to_numpy()),
        "support_rho_volume": spearman(support[in_base].to_numpy(), labels.n_external[in_base].to_numpy()),
    }
    for stratum in ("most_starred", "random_sample"):
        here = labels.stratum.eq(stratum)
        out[f"failed_top_{stratum}"] = maintained[failed & here].eq(10).mean()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default="2024-08-01")
    ap.add_argument("--resamples", type=int, default=2000)
    args = ap.parse_args()
    data = Data(args.t0)
    count = args.resamples
    everyone = np.ones(len(data.projects), dtype=bool)
    rng = np.random.default_rng(SEED)
    strata = data.labels.stratum.to_numpy()

    rows = []
    for spec in PRIMARY:
        rows.append(evaluate(data, spec, everyone, count, rng))
        print("primary", spec[0], spec[3], flush=True)
    primary = verdicts(pd.DataFrame(rows))
    primary.to_csv(PROBES / "validity_primary.csv", index=False)

    rows = []
    for spec in PRIMARY:
        for stratum in ("most_starred", "random_sample"):
            row = evaluate(data, spec, strata == stratum, count, rng)
            row["stratum"] = stratum
            row["own_statistics"] = row.get("events", 0) >= MIN_EVENTS
            rows.append(row)
    pd.DataFrame(rows).to_csv(PROBES / "validity_strata.csv", index=False)
    print("strata done", flush=True)

    rows = []
    for spec in SECONDARY:
        row = evaluate(data, spec, everyone, count, rng, gain=spec[1] != "baselines", with_pr=False)
        row["own_statistics"] = row.get("events", 0) >= MIN_EVENTS
        rows.append(row)
    pd.DataFrame(rows).to_csv(PROBES / "validity_secondary.csv", index=False)
    print("secondary done", flush=True)

    rows = []
    for spec in PRIMARY:
        for variant in VARIANTS[spec[3]]:
            row = evaluate(data, (*spec[:3], variant, spec[4]), everyone, count, rng, with_pr=False)
            row["own_statistics"] = row.get("events", 0) >= MIN_EVENTS
            row["primary_outcome"] = spec[3]
            rows.append(row)
    pd.DataFrame(rows).to_csv(PROBES / "validity_sensitivity.csv", index=False)
    print("sensitivity done", flush=True)

    rows = []
    for outcome in ("O1", "O1c_share", "O2b"):
        event, base = data.event_mask(outcome)
        for stratum, mask in (("all", everyone), ("most_starred", strata == "most_starred"), ("random_sample", strata == "random_sample")):
            in_base = base & mask & ~np.isnan(data.base).any(axis=1)
            y = event[in_base]
            X = design([data.base[in_base]])
            pred = np.zeros(len(y))
            for train, test in StratifiedKFold(10, shuffle=True, random_state=SEED).split(X, y):
                pred[test] = X[test] @ fit_logit(X[train], y[train])
            aucs = []
            for idx in resamples(len(y), count, rng):
                left = np.setdiff1d(np.arange(len(y)), idx)
                if y[left].any() and y[idx].any() and not y[left].all():
                    aucs.append(auroc(X[left] @ fit_logit(X[idx], y[idx]), y[left]))
            lo, hi = interval(np.array(aucs))
            rows.append({"outcome": outcome, "stratum": stratum, "n": len(y), "events": int(y.sum()), "auroc": auroc(pred, y), "auroc_lo": lo, "auroc_hi": hi, "own_statistics": y.sum() >= MIN_EVENTS})
    pd.DataFrame(rows).to_csv(PROBES / "validity_baseline.csv", index=False)
    print("baseline done", flush=True)

    thresholds, prevalence = thresholds_and_prevalence(data, count, rng)
    thresholds.to_csv(PROBES / "validity_thresholds.csv", index=False)
    prevalence.to_csv(PROBES / "validity_prevalence.csv", index=False)
    pd.Series(flag_profile(data)).to_csv(PROBES / "validity_flags.csv", header=["value"])
    print(primary[["score", "outcome", "n", "events", "auroc", "auroc_lo", "auroc_hi", "rho", "rho_lo", "base_auroc", "gain", "gain_lo", "gain_hi", "p_warn_holm", "p_adds_holm", "warns", "adds"]].round(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
