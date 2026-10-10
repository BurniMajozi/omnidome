"""Optional Chronos foundation-model adapter (Apache-2.0 weights: amazon/chronos-bolt-{tiny,mini,small,base}, amazon/chronos-2).

Feature-detected: `load()` returns None (and says why) unless BOTH the `chronos-forecasting` package (which needs
torch) is importable AND the model weights are already on disk under FORECAST_MODEL_DIR. It never downloads: the
batch job must be useful offline, so weights are pulled once by an operator (see docs/forecasting.md).

Layout expected:  $FORECAST_MODEL_DIR/<model-dir>/config.json  (+ weights), e.g. /models/chronos-bolt-small
Select with FORECAST_CHRONOS_MODEL (default chronos-bolt-small); FORECAST_CHRONOS=off disables it entirely.

NOT verified in this repo's CI (no torch / weights there). The calling code is defensive: any failure here
falls back to the numpy baselines. TimesFM 3.0 is deliberately NOT supported (license: commercial use restricted to
Google Cloud); TimesFM <= 2.5 (Apache-2.0) would be a second adapter behind FORECAST_TIMESFM=on - not implemented.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("forecaster.chronos")
ALLOWED = ("chronos-bolt-tiny", "chronos-bolt-mini", "chronos-bolt-small", "chronos-bolt-base", "chronos-2")


def model_dir() -> Path:
    return Path(os.getenv("FORECAST_MODEL_DIR", "/models"))


def status() -> tuple:
    """(available, reason). Cheap: does not import torch unless the package is present."""
    if os.getenv("FORECAST_CHRONOS", "auto").strip().lower() in ("off", "0", "false", "no"):
        return False, "disabled by FORECAST_CHRONOS=off"
    name = os.getenv("FORECAST_CHRONOS_MODEL", "chronos-bolt-small")
    if name not in ALLOWED:
        return False, f"{name!r} is not an allowed Chronos model ({', '.join(ALLOWED)})"
    path = model_dir() / name
    if not (path / "config.json").is_file():
        return False, f"weights not found at {path} (pull them once; see docs/forecasting.md)"
    try:
        import chronos  # noqa: F401
        import torch  # noqa: F401
    except Exception as exc:
        return False, f"chronos-forecasting/torch not importable ({exc.__class__.__name__})"
    return True, name


class ChronosModel:
    """Wraps a Chronos-Bolt / Chronos-2 pipeline. predict() -> (median, lower, upper) for the given interval level."""

    def __init__(self, name: str, path: Path):
        import chronos
        import torch
        self._torch = torch
        self.name = name
        cfg = (path / "config.json").read_bytes()
        self.version = f"{getattr(chronos, '__version__', 'x')}+{hashlib.sha256(cfg).hexdigest()[:8]}"[:60]
        torch.set_num_threads(max(1, int(os.getenv("FORECAST_THREADS", "2"))))
        if name == "chronos-2":
            from chronos import Chronos2Pipeline
            self._pipe = Chronos2Pipeline.from_pretrained(str(path), device_map="cpu")
        else:
            from chronos import BaseChronosPipeline
            self._pipe = BaseChronosPipeline.from_pretrained(str(path), device_map="cpu", torch_dtype=torch.float32)

    def predict(self, y: np.ndarray, h: int, level: float) -> tuple:
        torch = self._torch
        a = (1 - level) / 2
        qs = [a, 0.5, 1 - a]
        ctx = torch.tensor(np.asarray(y, dtype=np.float32))
        with torch.no_grad():
            if self.name == "chronos-2":
                out, _ = self._pipe.predict_quantiles([ctx.reshape(1, -1)], prediction_length=h, quantile_levels=qs)
                q = out[0][0].cpu().numpy()                    # (h, 3)
            else:
                out, _ = self._pipe.predict_quantiles(context=ctx, prediction_length=h, quantile_levels=qs)
                q = out[0].cpu().numpy()                       # (h, 3)
        return q[:, 1].astype(float), q[:, 0].astype(float), q[:, 2].astype(float)


def load() -> Optional[ChronosModel]:
    ok, why = status()
    if not ok:
        log.info("Chronos not used: %s", why)
        return None
    try:
        return ChronosModel(why, model_dir() / why)
    except Exception as exc:                                  # broken install / corrupt weights: degrade, do not crash the job
        log.warning("Chronos failed to load (%s); using statistical baselines", exc)
        return None
