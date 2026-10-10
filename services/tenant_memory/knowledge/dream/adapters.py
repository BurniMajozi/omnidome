"""Production adapters for the dream-state ports (operational DB, HTTP to the BI layer, builders).

Everything here talks to Postgres / other services and is therefore NOT exercised by the unit tests except through the
pure helpers (`classify_missing`, `map_log_columns`). See docs/dream-state.md "Verified vs not".
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import text

from services.tenant_memory.knowledge import consolidation
from services.tenant_memory.knowledge.cards import builders_artifacts as _artifacts          # noqa: F401 - registers artifact sources
from services.tenant_memory.knowledge.cards.sources import SOURCES, Page, Source, source_enabled
from services.tenant_memory.knowledge.dream.ports import DreamDeps, Rendered, Telemetry, Usage
from services.tenant_memory.knowledge.metrics import MetricFactIn, upsert_metric_fact

logger = logging.getLogger("knowledge.dream.adapters")

SessionFactory = Callable[[], Any]


def classify_missing(exc: BaseException) -> bool:
    """True when a database error means 'that table/relation is gone' (as opposed to a transient failure)."""
    msg = f"{type(exc).__name__} {exc}".lower()
    return "undefinedtable" in msg or "does not exist" in msg or "no such table" in msg


@asynccontextmanager
async def _default_session():
    from services.common.db import session_scope
    async with session_scope() as s:
        yield s


class SourceCardRenderer:
    """Re-renders cards with the SAME builders/sources the indexer uses. Per run it pages each source once (oldest-updated first,
    capped) into a map; a card outside that window is 'unverifiable', never 'gone'. 'Gone' only when `Source.ids` says the row
    does not exist. A table that cannot be queried yields 'source_missing' and nothing is tombstoned."""

    def __init__(self, sources: Optional[dict[str, Source]] = None, session_factory: Optional[SessionFactory] = None,
                 page_size: int = 50, max_cards_per_source: Optional[int] = None):
        self.sources = sources if sources is not None else SOURCES
        self._session = session_factory or _default_session
        self.page_size = page_size
        self.max_cards = max_cards_per_source or int(os.getenv("DREAM_RENDER_MAX_CARDS_PER_SOURCE", "2000"))
        self.reset()

    def reset(self) -> None:
        self._maps: dict[tuple, dict] = {}
        self._ids: dict[tuple, dict] = {}
        self._broken: dict[tuple, str] = {}

    def _source_for(self, source_type: str) -> Optional[Source]:
        for name, src in self.sources.items():
            if source_type in src.source_types and source_enabled(name):
                return src
        return None

    async def render(self, tenant: str, source_type: str, source_id: str) -> Rendered:
        loader = _artifacts.ROW_LOADERS.get(source_type)
        if loader is not None:
            try:
                async with self._session() as s:
                    card = await _artifacts.load_card(s, tenant, source_type, source_id)
            except ValueError:
                return Rendered("unverifiable", note="id is not renderable")
            except Exception as exc:  # noqa: BLE001
                if classify_missing(exc):
                    return Rendered("source_missing", note=str(exc)[:160])
                raise
            return Rendered("ok", card) if card is not None else Rendered("gone")
        src = self._source_for(source_type)
        if src is None:
            return Rendered("unverifiable", note="no builder for this card type")
        key = (tenant, src.name)
        if key in self._broken:
            return Rendered("source_missing", note=self._broken[key])
        if key not in self._maps:
            try:
                await self._load(tenant, src)
            except Exception as exc:  # noqa: BLE001
                if classify_missing(exc):
                    self._broken[key] = str(exc)[:160]
                    return Rendered("source_missing", note=self._broken[key])
                raise
        ids = self._ids[key].get(source_type)
        if ids is not None and source_id not in ids:
            return Rendered("gone")
        card = self._maps[key].get((source_type, source_id))
        return Rendered("ok", card) if card is not None else Rendered("unverifiable", note="outside this night's render window")

    async def _load(self, tenant: str, src: Source) -> None:
        key = (tenant, src.name)
        async with self._session() as s:
            self._ids[key] = await src.ids(s, tenant)
        cards: dict = {}
        wm = None
        while len(cards) < self.max_cards:
            async with self._session() as s:
                page: Page = await src.fetch(s, tenant, wm, self.page_size)
            for c in page.cards:
                cards[(c.source_type, c.source_id)] = c
            if src.snapshot or page.rows < self.page_size or page.last_ts is None:
                break
            wm = {"last_ts": page.last_ts, "meta": {"last_id": page.last_id}}
        self._maps[key] = cards


# ── operational DB ──────────────────────────────────────────────────────────

def parse_card_id(cid) -> Optional[tuple]:
    """'card:<source_type>:<source_id>' (knowledge_client.card_id) -> (source_type, source_id)."""
    if not isinstance(cid, str) or not cid.startswith("card:"):
        return None
    st, _, sid = cid[5:].partition(":")
    return (st, sid) if st and sid else None


def _cards_of(v) -> list:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []


def usage_from_log(rows: list, usage: dict) -> None:
    """Fold `retrieval_log` rows (docs/insights-and-jev.md: one row per answered turn, `cards` = [{card_id, used, cited,
    judge:{is_current, score}}]) into per-card Usage. A cited card in an answer with a grounded probability counts that
    probability as a quality signal; a card the judge found not current (<0.25) is counted in `not_current`."""
    for r in rows:
        gp = r.get("grounded_prob")
        for c in _cards_of(r.get("cards")):
            key = parse_card_id((c or {}).get("card_id"))
            if key is None:
                continue
            u = usage.setdefault(key, Usage())
            u.retrieved += 1
            u.used += int(bool(c.get("used")))
            u.cited += int(bool(c.get("cited")))
            judge = c.get("judge") or {}
            if judge.get("score") is not None:
                u.jev_sum += float(judge["score"])
                u.jev_n += 1
            if judge.get("is_current") is not None and float(judge["is_current"]) < 0.25:
                u.not_current += 1
            if c.get("cited") and gp is not None:
                u.jev_sum += float(gp)
                u.jev_n += 1
            at = r.get("created_at")
            if isinstance(at, datetime) and (u.last_at is None or at > u.last_at):
                u.last_at = at


def usage_from_feedback(rows: list, usage: dict) -> None:
    """Panel-insight verdicts (helpful/acted = up, not_helpful = down) credited to the cards the insight cited as evidence."""
    for r in rows:
        verdict = r.get("verdict")
        delta = 1 if verdict in ("helpful", "acted") else -1 if verdict == "not_helpful" else 0
        if not delta:
            continue
        doc = r.get("doc")
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except ValueError:
                continue
        doc = doc or {}
        rec = next((x for x in doc.get("recommendations") or [] if x.get("id") == r.get("rec_id")), None) if r.get("rec_id") else None
        for ev in (rec.get("evidence") if rec else (doc.get("evidence") or [])[:6]) or []:
            key = parse_card_id(ev.get("id") if isinstance(ev, dict) else ev)
            if key is not None:
                u = usage.setdefault(key, Usage())
                u.up += delta > 0
                u.down += delta < 0


def _log_hint(first_seen) -> Optional[datetime]:
    if isinstance(first_seen, datetime) and first_seen.tzinfo is None:
        return first_seen.replace(tzinfo=timezone.utc)
    return first_seen if isinstance(first_seen, datetime) else None


class SqlOps:
    def __init__(self, session_factory: Optional[SessionFactory] = None):
        self._session = session_factory or _default_session

    async def metric_facts(self, tenant: str, since_period_end: date) -> list[dict]:
        async with self._session() as s:
            rows = (await s.execute(text("""SELECT id::text AS id, metric_key, dimensions, dimensions_hash, period_start, period_end, grain, value,
                unit, kind, lower_bound, upper_bound, interval_level, model_name, model_version, method, confidence, as_of, written_by
                FROM tenant_metric_facts WHERE tenant_id = CAST(:t AS uuid) AND period_end >= :since ORDER BY metric_key, period_start LIMIT 20000"""),
                                    {"t": tenant, "since": since_period_end})).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("value", "lower_bound", "upper_bound", "interval_level", "confidence"):
                if d.get(k) is not None:
                    d[k] = float(d[k])
            out.append(d)
        return out

    async def write_fact(self, tenant: str, fact: MetricFactIn) -> dict:
        async with self._session() as s:
            return await upsert_metric_fact(s, tenant, fact)

    async def retrieval_telemetry(self, tenant: str, since: datetime) -> Telemetry:
        """retrieval_log (written by the orchestrator, docs/insights-and-jev.md) + panel-insight feedback. Feature-detected: a missing
        table or column means 'no telemetry', never an error."""
        usage: dict = {}
        try:
            async with self._session() as s:
                if not (await s.execute(text("SELECT to_regclass('public.retrieval_log')"))).scalar():
                    return Telemetry(False, note="table retrieval_log does not exist yet")
                cols = {r[0] for r in (await s.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'retrieval_log'"))).all()}
                if not {"tenant_id", "cards", "created_at"} <= cols:
                    return Telemetry(False, note=f"retrieval_log lacks tenant_id/cards/created_at (has: {', '.join(sorted(cols))[:160]})")
                gp = "grounded_prob" if "grounded_prob" in cols else "NULL AS grounded_prob"
                rows = (await s.execute(text(f"SELECT cards, created_at, {gp} FROM retrieval_log WHERE tenant_id = CAST(:t AS uuid) "
                                             "AND created_at >= :since ORDER BY created_at LIMIT 100000"), {"t": tenant, "since": since})).mappings().all()
                first = (await s.execute(text("SELECT min(created_at) FROM retrieval_log WHERE tenant_id = CAST(:t AS uuid)"), {"t": tenant})).scalar()
        except Exception as exc:  # noqa: BLE001
            return Telemetry(False, note=f"retrieval_log could not be read: {type(exc).__name__}")
        usage_from_log([dict(r) for r in rows], usage)
        try:
            async with self._session() as s:
                fb = (await s.execute(text("SELECT f.verdict, f.rec_id, i.doc FROM panel_insight_feedback f JOIN panel_insights i ON i.id = f.insight_id "
                                           "WHERE f.tenant_id = CAST(:t AS uuid) AND f.created_at >= :since LIMIT 5000"), {"t": tenant, "since": since})).mappings().all()
            usage_from_feedback([dict(r) for r in fb], usage)
        except Exception:  # noqa: BLE001 - insights tables are optional
            pass
        return Telemetry(True, usage, _log_hint(first), note="" if rows else "retrieval_log has no rows in the window")

    async def notify(self, tenant: str, title: str, body: str, severity: str, link: Optional[str]) -> None:
        if os.getenv("DREAM_NOTIFY", "true").strip().lower() in {"0", "false", "no", "off"}:
            return
        from services.common.event_bus import notify
        async with self._session() as s:
            await notify(s, tenant, title, body=body, category="memory", severity=severity, link=link, source="dream")


# ── HTTP ports ──────────────────────────────────────────────────────────────

class HttpMetricsRefresher:
    """Asks fno_intelligence to re-run the governed catalog queries now (it upserts ACTUAL facts in place). No LLM involved."""

    def __init__(self, base_url: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._base = (base_url if base_url is not None else os.getenv("DREAM_METRICS_URL", "") or os.getenv("FNO_INTELLIGENCE_SERVICE_URL", "")).rstrip("/")
        self._transport = transport

    def configured(self) -> bool:
        return bool(self._base)

    async def refresh(self, tenant: str, periods: int) -> dict:
        headers = {"X-Tenant-Id": tenant, "X-User-Id": os.getenv("METRICS_SYSTEM_USER_ID", "00000000-0000-0000-0000-000000000001"),
                   "X-Roles": "service,admin", "X-Permissions": "analytics.admin"}
        async with httpx.AsyncClient(timeout=180.0, transport=self._transport) as c:
            r = await c.post(f"{self._base}/api/fno/bi/metrics/snapshot", json={"periods": periods}, headers=headers)
        if r.status_code >= 300:
            raise RuntimeError(f"metrics snapshot HTTP {r.status_code}: {r.text[:120]}")
        return r.json() if r.content else {}


def orchestrator_housekeeping() -> Optional[Callable]:
    """M4/M5 through the orchestrator's own endpoints. Off unless DREAM_HOUSEKEEPING_VIA_ORCHESTRATOR=true (its scheduler already runs nightly)."""
    if os.getenv("DREAM_HOUSEKEEPING_VIA_ORCHESTRATOR", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    base = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://agent-orchestrator:8021").rstrip("/")

    async def call(tenant: str, dry_run: bool) -> dict:
        path = "/api/memory/housekeeping/dry-run" if dry_run else "/api/memory/housekeeping/run"
        headers = {"X-Tenant-Id": tenant, "X-User-Id": os.getenv("METRICS_SYSTEM_USER_ID", "00000000-0000-0000-0000-000000000001"),
                   "X-Roles": "service,admin", "X-Permissions": "agents.manage"}
        async with httpx.AsyncClient(timeout=300.0) as c:
            r = await c.post(f"{base}{path}", headers=headers)
        if r.status_code >= 300:
            raise RuntimeError(f"housekeeping HTTP {r.status_code}")
        return r.json()
    return call


def build_deps(kstore, embedder, *, session_factory: Optional[SessionFactory] = None) -> DreamDeps:
    """Real wiring: Postgres store (or the in-memory one when handed a MemoryStore), builders, HTTP ports, JEV client."""
    from services.tenant_memory.knowledge.dream.jev import HttpJevClient
    from services.tenant_memory.knowledge.dream.store import MemoryDreamStore
    from services.tenant_memory.knowledge.indexer import Indexer
    from services.tenant_memory.knowledge.store_memory import MemoryStore
    if isinstance(kstore, MemoryStore):
        store = MemoryDreamStore(kstore)
    else:
        from services.tenant_memory.knowledge.dream.store_pg import PgDreamStore
        store = PgDreamStore(kstore)

    async def consolidate(tenant: str, dry_run: bool) -> dict:
        async with (session_factory or _default_session)() as s:
            return await consolidation.consolidate_tenant(s, kstore, tenant, dry_run=dry_run)

    return DreamDeps(store=store, embedder=embedder, ops=SqlOps(session_factory), renderer=SourceCardRenderer(session_factory=session_factory),
                     indexer=Indexer(kstore, embedder, session_factory=session_factory), consolidate=consolidate, jev=HttpJevClient(),
                     metrics=HttpMetricsRefresher(), housekeeping=orchestrator_housekeeping())
