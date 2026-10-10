"""Rolling-origin backtest, model selection and prediction intervals.

Selection metric: MASE (scaled by the in-sample seasonal-naive / naive MAE), ties broken by sMAPE. The chosen
model's backtest error is what gets recorded on the forecast fact, so a reader can see how trustworthy it was.

Baseline intervals are EMPIRICAL: quantiles of the chosen model's rolling-origin errors at each horizon step
(pooled when a step has too few samples, scaled by sqrt(step) beyond the backtest horizon), inflated slightly for
the small sample and forced to contain the point forecast. A foundation model (Chronos) supplies its own quantiles.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional, Protocol

import numpy as np

from services.forecaster import baselines

log = logging.getLogger("forecaster.selection")
MIN_POINTS = 8          # hard floor regardless of catalog (a backtest needs something to train and test on)


class InsufficientHistory(ValueError):
    pass


class FoundationModel(Protocol):
    name: str
    version: str

    def predict(self, y: np.ndarray, h: int, level: float) -> tuple: ...   # (median, lower, upper), each len h


@dataclass
class Forecast:
    model_name: str
    model_version: str
    point: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    level: float
    smape: float                     # percent, backtest
    mase: float
    n_origins: int
    scores: dict = field(default_factory=dict)       # model -> {"mase","smape"} for every scored candidate
    notes: list = field(default_factory=list)


def smape(actual: np.ndarray, pred: np.ndarray) -> float:
    denom = np.abs(actual) + np.abs(pred)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(denom == 0, 0.0, 200.0 * np.abs(actual - pred) / denom)
    return float(np.mean(r))


def mase_scale(y: np.ndarray, m: int) -> float:
    lag = m if baselines.eligible(len(y), m) else 1
    s = float(np.mean(np.abs(y[lag:] - y[:-lag]))) if len(y) > lag else 0.0
    if s <= 1e-12:
        s = float(np.mean(np.abs(y))) or 1.0
    return s


def _origins(n: int, h_bt: int, min_train: int, cap: int = 8) -> list:
    """Training-set end indices, most recent first."""
    ends = [n - h_bt - k for k in range(cap) if n - h_bt - k >= min_train]
    return ends


def _run_model(fn, y: np.ndarray, ends: list, h_bt: int, m: int) -> tuple:
    errs, preds, acts = [], [], []
    for e in ends:
        p = np.asarray(fn(y[:e], h_bt, m), dtype=float)
        a = y[e:e + h_bt]
        errs.append(a - p)
        preds.append(p)
        acts.append(a)
    return np.array(errs), np.concatenate(preds), np.concatenate(acts)


def _empirical_interval(point: np.ndarray, errs: np.ndarray, h: int, level: float) -> tuple:
    """errs: (origins, h_bt) matrix of actual - forecast."""
    k, h_bt = errs.shape
    a = (1 - level) / 2
    infl = 1.0 + 1.5 / math.sqrt(max(k, 1))
    lo = np.zeros(h)
    hi = np.zeros(h)
    pooled = errs.reshape(-1)
    for i in range(1, h + 1):
        j = min(i, h_bt) - 1
        col = errs[:, j]
        scale = 1.0
        if len(col) < 5:
            col = pooled
        if i > h_bt:
            scale = math.sqrt(i / h_bt)
        q_lo, q_hi = np.quantile(col, a), np.quantile(col, 1 - a)
        lo[i - 1] = min(q_lo, 0.0) * scale * infl
        hi[i - 1] = max(q_hi, 0.0) * scale * infl
    # uncertainty cannot shrink with horizon: enforce monotone half-widths (per-step samples are few and noisy)
    lo, hi = np.minimum.accumulate(lo), np.maximum.accumulate(hi)
    return point + lo, point + hi


def forecast_series(y, h: int, m: int, *, level: float = 0.8, foundation: Optional[FoundationModel] = None,
                    foundation_origins: int = 3, nonnegative: bool = True) -> Forecast:
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < MIN_POINTS:
        raise InsufficientHistory(f"{n} points < {MIN_POINTS}")
    if h < 1:
        raise ValueError("horizon must be >= 1")
    h_bt = max(1, min(h, 6, n // 4))
    min_train = max(6, n // 2)
    ends = _origins(n, h_bt, min_train)
    if not ends:
        raise InsufficientHistory(f"{n} points leave no backtest origin")
    notes: list = []

    # Seasonal models are only scored when >= 3 origins can train them; then everyone is scored on those origins.
    seasonal_ends = [e for e in ends if baselines.eligible(e, m)]
    use_seasonal = m > 1 and len(seasonal_ends) >= 3
    common = seasonal_ends if use_seasonal else ends
    models = {k: f for k, f in baselines.candidates(min(common), m).items()
              if use_seasonal or k not in ("seasonal_naive", "holt_winters")}
    scale = mase_scale(y[:n - h_bt], m)

    score_ends = common[:foundation_origins] if foundation is not None else common
    scores: dict = {}
    errs_by_model: dict = {}
    for name, fn in models.items():
        try:
            errs_full, _, _ = _run_model(fn, y, common, h_bt, m)
            errs, p, a = _run_model(fn, y, score_ends, h_bt, m)
        except Exception as exc:                     # a numerical failure on one model must not sink the series
            log.warning("baseline %s failed: %s", name, exc)
            continue
        if not np.all(np.isfinite(errs_full)):
            continue
        errs_by_model[name] = errs_full
        scores[name] = {"mase": float(np.mean(np.abs(errs)) / scale), "smape": smape(a, p)}

    foundation_pred: Optional[tuple] = None
    if foundation is not None:
        try:
            ferrs, fp, fa = [], [], []
            for e in score_ends:
                med, _, _ = foundation.predict(y[:e], h_bt, level)
                med = np.asarray(med, dtype=float)
                a_ = y[e:e + h_bt]
                ferrs.append(a_ - med); fp.append(med); fa.append(a_)
            ferr = np.array(ferrs)
            if np.all(np.isfinite(ferr)):
                scores[foundation.name] = {"mase": float(np.mean(np.abs(ferr)) / scale), "smape": smape(np.concatenate(fa), np.concatenate(fp))}
                foundation_pred = foundation.predict(y, h, level)
        except Exception as exc:
            notes.append(f"{foundation.name} unavailable at run time ({exc.__class__.__name__}); baselines used")
            log.warning("foundation model %s failed: %s", foundation.name, exc)
            scores.pop(foundation.name, None)
    if not scores:
        raise InsufficientHistory("no model could be backtested")

    best = min(scores, key=lambda k: (round(scores[k]["mase"], 6), scores[k]["smape"]))
    if foundation is not None and best == foundation.name and foundation_pred is not None:
        med, lo, hi = (np.asarray(v, dtype=float) for v in foundation_pred)
        name, version = foundation.name, foundation.version
        point, lower, upper = med, np.minimum(lo, med), np.maximum(hi, med)
    else:
        fn = models[best]
        point = np.asarray(fn(y, h, m), dtype=float)
        lower, upper = _empirical_interval(point, errs_by_model[best], h, level)
        name, version = f"baseline-{best}", f"{best}-{BASELINE_VERSION}"
    if nonnegative:
        point, lower, upper = np.maximum(point, 0.0), np.maximum(lower, 0.0), np.maximum(upper, 0.0)
        lower, upper = np.minimum(lower, point), np.maximum(upper, point)
    return Forecast(name, version, point, lower, upper, level, scores[best]["smape"], scores[best]["mase"], len(score_ends),
                    scores, notes)


BASELINE_VERSION = "1"
