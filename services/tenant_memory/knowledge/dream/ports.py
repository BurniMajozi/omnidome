"""Seams of the dream state. Production implementations live in `adapters.py` / `jev.py`; tests inject fakes.

    DreamStore      knowledge_db: runs, findings, settings, JEV cache, card state, chunk-level maintenance ops
    CardRenderer    re-renders one card from its live operational source using the EXISTING builders
    OpsPort         operational DB reads/writes the dream needs (metric facts, retrieval telemetry, notifications)
    MetricsRefresher  asks the governed BI layer to recompute ACTUAL facts (never an LLM)
    JevClient       the external calibrated evaluator (budgeted, off by default)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Protocol

from services.tenant_memory.knowledge.cards.base import Card
from services.tenant_memory.knowledge.embeddings import Embedder
from services.tenant_memory.knowledge.indexer import Indexer
from services.tenant_memory.knowledge.metrics import MetricFactIn
from services.tenant_memory.knowledge.dream.settings import DreamSettings, kill_switch_on
from services.tenant_memory.knowledge.dream.store import DreamStore


@dataclass
class Rendered:
    status: str                       # ok | gone | unverifiable | source_missing
    card: Optional[Card] = None
    note: str = ""


class CardRenderer(Protocol):
    def reset(self) -> None: ...
    async def render(self, tenant: str, source_type: str, source_id: str) -> Rendered: ...


@dataclass
class Usage:
    retrieved: int = 0
    used: int = 0
    cited: int = 0
    up: int = 0
    down: int = 0
    not_current: int = 0                 # times the JEV judge found the card out of date (is_current < 0.25)
    jev_sum: float = 0.0
    jev_n: int = 0
    last_at: Optional[datetime] = None

    @property
    def jev_avg(self) -> Optional[float]:
        return self.jev_sum / self.jev_n if self.jev_n else None


@dataclass
class Telemetry:
    available: bool
    usage: dict = field(default_factory=dict)          # {(source_type, source_id): Usage}
    observed_since: Optional[datetime] = None          # earliest event seen: decay needs a long enough window
    note: str = ""


class OpsPort(Protocol):
    async def metric_facts(self, tenant: str, since_period_end: date) -> list[dict]: ...
    async def write_fact(self, tenant: str, fact: MetricFactIn) -> dict: ...
    async def retrieval_telemetry(self, tenant: str, since: datetime) -> Telemetry: ...
    async def notify(self, tenant: str, title: str, body: str, severity: str, link: Optional[str]) -> None: ...


class MetricsRefresher(Protocol):
    def configured(self) -> bool: ...
    async def refresh(self, tenant: str, periods: int) -> dict: ...


@dataclass
class JevAnswer:
    probs: dict                                         # {question_name: probability 0..1}
    cost_usd: float = 0.0
    model: str = ""
    tokens: Optional[int] = None


class JevClient(Protocol):
    def configured(self) -> bool: ...
    async def ask(self, state: dict, questions: dict) -> JevAnswer: ...


ConsolidateFn = Callable[[str, bool], Awaitable[dict]]      # (tenant, dry_run) -> report


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DreamDeps:
    store: DreamStore
    embedder: Embedder
    ops: OpsPort
    renderer: CardRenderer
    indexer: Indexer
    consolidate: ConsolidateFn
    jev: Optional[JevClient] = None
    metrics: Optional[MetricsRefresher] = None
    housekeeping: Optional[ConsolidateFn] = None        # optional orchestrator M4/M5 trigger
    base_settings: Optional[DreamSettings] = None       # None -> environment
    now: Callable[[], datetime] = _utcnow
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    kill: Callable[[], bool] = kill_switch_on
