"""forecast_runs: the queue/log the forecaster batch job works from. The API only inserts a 'queued' row
(no compute); `python -m services.forecaster.run --pending` claims and executes it. New table only."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from services.fno_intelligence.analytics_models import JSONType
from services.fno_intelligence.models import Base


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued", index=True)  # queued|running|done|failed
    metric_keys: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)   # null = every forecastable metric
    horizon: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    summary: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)       # per-metric outcome written by the job
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


FORECAST_TABLES = [ForecastRun.__table__]
