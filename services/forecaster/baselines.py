"""Statistical baseline forecasters in pure numpy (no torch, no statsmodels).

Each model is `fn(y, h, m) -> np.ndarray(h)` of POINT forecasts; `y` is a 1-D float history, `h` the horizon and
`m` the season length (1 = no seasonality). Seasonal variants are only eligible with >= 2 full seasons of history
(`eligible()`), so a 12-point monthly series is forecast with the non-seasonal models only.

Prediction intervals are NOT produced here: they come from empirical backtest residuals (see `select.py`).
"""
from __future__ import annotations

from typing import Callable

import numpy as np

Model = Callable[[np.ndarray, int, int], np.ndarray]


# ── building blocks ──────────────────────────────────────────────────────────

def _ses_fit(y: np.ndarray) -> tuple:
    """Simple exponential smoothing with alpha chosen by one-step SSE. Returns (alpha, final level)."""
    best = (np.inf, 0.5, float(y[0]))
    for alpha in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99):
        level, sse = float(y[0]), 0.0
        for v in y[1:]:
            sse += (v - level) ** 2
            level = alpha * v + (1 - alpha) * level
        if sse < best[0]:
            best = (sse, alpha, level)
    return best[1], best[2]


def _seasonal_indices(y: np.ndarray, m: int) -> np.ndarray:
    """Additive seasonal component (length m, sums to ~0) from the detrended series."""
    n = len(y)
    t = np.arange(n)
    slope, intercept = np.polyfit(t, y, 1)
    detr = y - (slope * t + intercept)
    s = np.array([detr[i::m].mean() for i in range(m)])
    return s - s.mean()


def eligible(n: int, m: int) -> bool:
    return m > 1 and n >= 2 * m


# ── models ───────────────────────────────────────────────────────────────────

def naive(y: np.ndarray, h: int, m: int = 1) -> np.ndarray:
    return np.full(h, float(y[-1]))


def seasonal_naive(y: np.ndarray, h: int, m: int) -> np.ndarray:
    return np.array([y[len(y) - m + (i % m)] for i in range(h)], dtype=float)


def drift(y: np.ndarray, h: int, m: int = 1) -> np.ndarray:
    if len(y) < 2:
        return naive(y, h)
    slope = (y[-1] - y[0]) / (len(y) - 1)
    return y[-1] + slope * np.arange(1, h + 1)


def ses(y: np.ndarray, h: int, m: int = 1) -> np.ndarray:
    _, level = _ses_fit(y)
    return np.full(h, level)


def holt_damped(y: np.ndarray, h: int, m: int = 1) -> np.ndarray:
    """Damped-trend Holt (ETS(A,Ad,N)), small grid search on one-step SSE."""
    best = (np.inf, None)
    for alpha in (0.2, 0.4, 0.6, 0.8):
        for beta in (0.05, 0.15, 0.3):
            for phi in (0.8, 0.9, 0.98):
                level, trend, sse = float(y[0]), float(y[1] - y[0]) if len(y) > 1 else 0.0, 0.0
                for v in y[1:]:
                    pred = level + phi * trend
                    sse += (v - pred) ** 2
                    new_level = alpha * v + (1 - alpha) * pred
                    trend = beta * (new_level - level) + (1 - beta) * phi * trend
                    level = new_level
                if sse < best[0]:
                    best = (sse, (level, trend, phi))
    level, trend, phi = best[1]
    damp = np.cumsum(phi ** np.arange(1, h + 1))
    return level + damp * trend


def holt_winters(y: np.ndarray, h: int, m: int) -> np.ndarray:
    """Additive Holt-Winters (ETS(A,A,A)); needs >= 2 seasons. Small grid on one-step SSE."""
    n = len(y)
    best = (np.inf, None)
    level0 = float(y[:m].mean())
    trend0 = float((y[m:2 * m].mean() - y[:m].mean()) / m)
    season0 = y[:m] - level0
    for alpha in (0.2, 0.5, 0.8):
        for beta in (0.01, 0.1):
            for gamma in (0.1, 0.3, 0.6):
                level, trend, season, sse = level0, trend0, season0.copy(), 0.0
                for i in range(m, n):
                    pred = level + trend + season[i % m]
                    err = y[i] - pred
                    sse += err * err
                    new_level = alpha * (y[i] - season[i % m]) + (1 - alpha) * (level + trend)
                    trend = beta * (new_level - level) + (1 - beta) * trend
                    season[i % m] = gamma * (y[i] - new_level) + (1 - gamma) * season[i % m]
                    level = new_level
                if sse < best[0]:
                    best = (sse, (level, trend, season.copy()))
    level, trend, season = best[1]
    return np.array([level + (i + 1) * trend + season[(n + i) % m] for i in range(h)])


def theta(y: np.ndarray, h: int, m: int = 1) -> np.ndarray:
    """Standard Theta method (SES + half the linear-trend slope); additive seasonal adjustment when eligible."""
    n = len(y)
    seas = _seasonal_indices(y, m) if eligible(n, m) else None
    adj = y - (np.resize(seas, n) if seas is not None else 0.0)
    alpha, level = _ses_fit(adj)
    b = np.polyfit(np.arange(n), adj, 1)[0]
    steps = np.arange(1, h + 1)
    f = level + 0.5 * b * (steps - 1 + 1.0 / alpha - ((1 - alpha) ** n) / alpha)
    if seas is not None:
        f = f + np.array([seas[(n + i) % m] for i in range(h)])
    return f


ALL: dict = {
    "naive": (naive, False),
    "drift": (drift, False),
    "ses": (ses, False),
    "holt_damped": (holt_damped, False),
    "theta": (theta, False),
    "seasonal_naive": (seasonal_naive, True),
    "holt_winters": (holt_winters, True),
}


def candidates(n: int, m: int) -> dict:
    """Models usable for a history of length n and season length m."""
    out = {}
    for name, (fn, seasonal) in ALL.items():
        if seasonal and not eligible(n, m):
            continue
        if name in ("holt_damped", "theta", "drift") and n < 4:
            continue
        out[name] = fn
    return out
