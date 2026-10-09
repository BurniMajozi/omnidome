"""Metric facts: deterministic numbers attached to memory.

Write path is deliberately narrow: only code paths that compute a number deterministically
(`bi_semantic` query runs, `forecast_run` jobs, `system`) may write, identified by `written_by`, enforced by
a DB CHECK and by the API requiring the `metrics.write` permission (agents/LLM tools are not granted it).
A fact must say HOW it was produced (`method`) and, for forecasts, which model/version.
The embedded card is context; the exact value is always re-fetched via `source_query` (a bi_semantic QuerySpec).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

WRITERS = ("bi_semantic", "forecast_run", "system")


class MetricFactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_key: str = Field(..., pattern=r"^[a-z][a-z0-9_.]{0,118}$")
    label: Optional[str] = Field(None, max_length=160)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    period_start: date
    period_end: date
    grain: Optional[str] = Field(None, pattern=r"^(day|week|month|quarter|year)$")
    value: float
    unit: str = Field("count", max_length=20)
    kind: str = Field("actual", pattern=r"^(actual|forecast|target)$")
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    interval_level: Optional[float] = Field(None, gt=0, lt=1)
    model_name: Optional[str] = Field(None, max_length=120)
    model_version: str = Field("", max_length=60)
    method: str = Field(..., min_length=2, max_length=80)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    source_query: Optional[dict[str, Any]] = None      # a bi_semantic QuerySpec (by reference; not executed here)
    as_of: Optional[datetime] = None
    written_by: str = Field(..., pattern=r"^(bi_semantic|forecast_run|system)$")

    @model_validator(mode="after")
    def _check(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end before period_start")
        if self.kind == "forecast" and not (self.model_name and self.model_version):
            raise ValueError("forecast facts need model_name and model_version")
        if self.kind == "actual" and self.written_by == "forecast_run":
            raise ValueError("forecast runs cannot write actuals")
        if self.kind == "forecast" and self.written_by == "bi_semantic":
            raise ValueError("bi_semantic runs write actuals/targets, not forecasts")
        if (self.lower_bound is None) != (self.upper_bound is None):
            raise ValueError("give both lower_bound and upper_bound or neither")
        if self.lower_bound is not None and not (self.lower_bound <= self.upper_bound):
            raise ValueError("lower_bound > upper_bound")
        if self.source_query is not None and not (isinstance(self.source_query.get("dataset"), str) and self.source_query.get("measures")):
            raise ValueError("source_query must be a bi_semantic QuerySpec with dataset and measures")
        return self


def dimensions_hash(dims: dict) -> str:
    return hashlib.sha256(json.dumps(dims, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:32]


def query_key(spec: Optional[dict]) -> Optional[str]:
    """Same recipe as bi_semantic.canonical_key (sha256 of canonical JSON, first 24 chars) so the key matches
    the BI layer's cache key when the spec is given in its by-alias JSON form."""
    if not spec:
        return None
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


async def upsert_metric_fact(session, tenant: str, fact: MetricFactIn) -> dict:
    dims = fact.dimensions or {}
    row = (await session.execute(text("""
        INSERT INTO tenant_metric_facts (id, tenant_id, metric_key, label, dimensions, dimensions_hash, period_start, period_end, grain,
            value, unit, kind, lower_bound, upper_bound, interval_level, model_name, model_version, method, confidence,
            source_query, source_query_key, as_of, written_by)
        VALUES (CAST(:id AS uuid), CAST(:t AS uuid), :mk, :label, :dims, :dh, :ps, :pe, :grain, :value, :unit, :kind, :lo, :hi, :lvl,
            :mn, :mv, :method, :conf, :sq, :sqk, :asof, :wb)
        ON CONFLICT (tenant_id, metric_key, dimensions_hash, period_start, period_end, kind, model_version) DO UPDATE SET
            label = EXCLUDED.label, value = EXCLUDED.value, unit = EXCLUDED.unit, lower_bound = EXCLUDED.lower_bound,
            upper_bound = EXCLUDED.upper_bound, interval_level = EXCLUDED.interval_level, method = EXCLUDED.method,
            confidence = EXCLUDED.confidence, source_query = EXCLUDED.source_query, source_query_key = EXCLUDED.source_query_key,
            as_of = EXCLUDED.as_of, written_by = EXCLUDED.written_by, updated_at = now()
        RETURNING id::text AS id, (xmax = 0) AS inserted""").bindparams(bindparam("dims", type_=JSONB), bindparam("sq", type_=JSONB)),
        {"id": str(uuid.uuid4()), "t": tenant, "mk": fact.metric_key, "label": fact.label, "dims": dims, "dh": dimensions_hash(dims),
         "ps": fact.period_start, "pe": fact.period_end, "grain": fact.grain, "value": fact.value, "unit": fact.unit,
         "kind": fact.kind, "lo": fact.lower_bound, "hi": fact.upper_bound, "lvl": fact.interval_level,
         "mn": fact.model_name, "mv": fact.model_version, "method": fact.method, "conf": fact.confidence,
         "sq": fact.source_query, "sqk": query_key(fact.source_query), "asof": fact.as_of or datetime.now(timezone.utc),
         "wb": fact.written_by})).mappings().one()
    return dict(row)
