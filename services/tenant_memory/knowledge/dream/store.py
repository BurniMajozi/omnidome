"""Storage contract of the dream state (runs, findings, settings, JEV cache, card state + chunk-level maintenance ops).

Two implementations: `MemoryDreamStore` (tests, wraps `MemoryStore`) and `store_pg.PgDreamStore` (production, same
`knowledge_db`). Everything is tenant scoped. Run and finding records are plain JSON-friendly dicts (timestamps ISO strings).
"""
from __future__ import annotations

import copy
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from services.tenant_memory.knowledge.kdata import Chunk
from services.tenant_memory.knowledge.store import KnowledgeStore

OPEN_STATES = ("open", "proposed")                      # a human still has to decide / nothing was applied
LOG_STATES = ("open", "proposed", "auto_applied")      # rows that are re-used when the same issue shows up again
SEVERITIES = ("info", "low", "medium", "high", "critical")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
STALE_TAG = "dream:stale"
COLD_TAG = "dream:cold"


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


class DreamStore(ABC):
    kstore: KnowledgeStore

    # ── lifecycle ──
    @abstractmethod
    async def ensure_schema(self) -> None: ...

    # ── runs ──
    @abstractmethod
    async def create_run(self, tenant: str, run: dict) -> dict: ...

    @abstractmethod
    async def update_run(self, tenant: str, run_id: str, patch: dict) -> dict: ...

    @abstractmethod
    async def get_run(self, tenant: str, run_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def list_runs(self, tenant: str, limit: int = 30, include_dry: bool = True) -> list[dict]:
        """Newest first."""

    @abstractmethod
    async def find_resumable(self, tenant: str, run_date: str) -> Optional[dict]:
        """A non-dry run of this local date that was started but never finished (status running/interrupted)."""

    @abstractmethod
    async def nightly_done(self, tenant: str, run_date: str) -> bool:
        """A nightly (non-dry) run of that local date already finished."""

    # ── findings ──
    @abstractmethod
    async def upsert_finding(self, tenant: str, f: dict) -> dict:
        """Insert, or fold into the existing row with the same dedupe_key (see module docstring of engine)."""

    @abstractmethod
    async def list_findings(self, tenant: str, *, status: Optional[str] = None, severity: Optional[str] = None,
                            phase: Optional[str] = None, type: Optional[str] = None, run_id: Optional[str] = None,
                            limit: int = 100) -> list[dict]: ...

    @abstractmethod
    async def get_finding(self, tenant: str, fid: str) -> Optional[dict]: ...

    @abstractmethod
    async def update_finding(self, tenant: str, fid: str, patch: dict) -> Optional[dict]: ...

    @abstractmethod
    async def finding_counts(self, tenant: str) -> dict:
        """{'open': {severity: n}, 'total_open': n}"""

    # ── settings, JEV cache, card state ──
    @abstractmethod
    async def get_settings(self, tenant: str) -> dict: ...

    @abstractmethod
    async def put_settings(self, tenant: str, settings: dict, by: Optional[str]) -> dict: ...

    @abstractmethod
    async def cache_get(self, tenant: str, key: str) -> Optional[dict]: ...

    @abstractmethod
    async def cache_put(self, tenant: str, key: str, result: dict) -> None: ...

    @abstractmethod
    async def get_card_state(self, tenant: str, source_type: str, source_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def put_card_state(self, tenant: str, source_type: str, source_id: str, state: dict) -> None: ...

    # ── chunk-level maintenance (derived data only) ──
    @abstractmethod
    async def scan_cards(self, tenant: str, after: Optional[tuple], limit: int, *, with_embedding: bool = False,
                         first_chunk_only: bool = True) -> list[Chunk]:
        """Live chunks ordered by (source_type, source_id, chunk_no) strictly after `after`."""

    @abstractmethod
    async def get_chunks(self, tenant: str, source_type: str, source_id: str) -> list[Chunk]:
        """Live chunks of one source WITH embeddings."""

    @abstractmethod
    async def top_cards(self, tenant: str, n: int) -> list[Chunk]:
        """Highest-importance public (non-private) live first chunks, deterministic order."""

    @abstractmethod
    async def count_cards(self, tenant: str) -> dict:
        """{'live_chunks','live_sources','tombstoned','stale_tagged','models':{model:n},'source_types':{type:n}}"""

    @abstractmethod
    async def find_stale(self, tenant: str, source_type: str, cutoff: datetime, tag: str, limit: int) -> list[tuple]:
        """[(source_type, source_id, as_of)] live first chunks older than cutoff that do not carry `tag` yet."""

    @abstractmethod
    async def tagged(self, tenant: str, tag: str, limit: int) -> list[tuple]:
        """[(source_type, source_id, as_of)] live first chunks carrying `tag`."""

    @abstractmethod
    async def tag_source(self, tenant: str, source_type: str, source_id: str, add: list[str], remove: list[str]) -> int: ...

    @abstractmethod
    async def set_embedding(self, tenant: str, source_type: str, source_id: str, chunk_no: int, embedding: list[float],
                            model: str, content_hash: str) -> bool: ...

    @abstractmethod
    async def edge_origins(self, tenant: str) -> set[str]: ...

    @abstractmethod
    async def dangling_edges(self, tenant: str, types: list[str], limit: int) -> list[tuple]:
        """[(origin_key, dst_type, dst_id)] edges whose target (of an indexed type) has no live card."""


class MemoryDreamStore(DreamStore):
    """In-process implementation over `MemoryStore` (unit tests)."""

    def __init__(self, kstore: KnowledgeStore):
        self.kstore = kstore
        self.runs: dict[str, dict] = {}
        self.findings: dict[str, dict] = {}
        self.settings: dict[str, dict] = {}
        self.cache: dict[tuple, dict] = {}
        self.card_state: dict[tuple, dict] = {}

    def _now(self) -> str:
        return iso(self.kstore.now())

    async def ensure_schema(self) -> None:
        return None

    # runs
    async def create_run(self, tenant, run):
        r = copy.deepcopy(run)
        r.setdefault("id", str(uuid.uuid4()))
        r["tenant_id"] = tenant
        r.setdefault("started_at", self._now())
        self.runs[r["id"]] = r
        return copy.deepcopy(r)

    async def update_run(self, tenant, run_id, patch):
        r = self.runs[run_id]
        if r["tenant_id"] != tenant:
            raise KeyError(run_id)
        r.update(copy.deepcopy(patch))
        return copy.deepcopy(r)

    async def get_run(self, tenant, run_id):
        r = self.runs.get(run_id)
        return copy.deepcopy(r) if r and r["tenant_id"] == tenant else None

    async def list_runs(self, tenant, limit=30, include_dry=True):
        rows = [r for r in self.runs.values() if r["tenant_id"] == tenant and (include_dry or not r.get("dry_run"))]
        rows.sort(key=lambda r: (r.get("started_at") or "", r["id"]), reverse=True)
        return [copy.deepcopy(r) for r in rows[:limit]]

    async def find_resumable(self, tenant, run_date):
        for r in sorted(self.runs.values(), key=lambda r: r.get("started_at") or "", reverse=True):
            if r["tenant_id"] == tenant and not r.get("dry_run") and r.get("run_date") == run_date \
                    and r.get("status") in ("running", "interrupted"):
                return copy.deepcopy(r)
        return None

    async def nightly_done(self, tenant, run_date):
        return any(r["tenant_id"] == tenant and not r.get("dry_run") and r.get("trigger") == "nightly" and r.get("run_date") == run_date
                   and r.get("status") in ("completed", "completed_with_errors", "aborted") for r in self.runs.values())

    # findings
    async def upsert_finding(self, tenant, f):
        f = copy.deepcopy(f)
        now = self._now()
        key = f.get("dedupe_key")
        if key:
            same = [x for x in self.findings.values() if x["tenant_id"] == tenant and x.get("dedupe_key") == key]
            same.sort(key=lambda x: x["last_seen"], reverse=True)
            cur = same[0] if same else None
            if cur is not None:
                if cur["status"] in ("dismissed", "accepted"):
                    cur["occurrences"] += 1
                    cur["last_seen"] = now
                    return copy.deepcopy(cur)
                if cur["status"] in LOG_STATES:
                    for k in ("run_id", "severity", "title", "detail", "action", "jev", "phase", "type", "source_type", "source_id", "auto_applied"):
                        if k in f:
                            cur[k] = f[k]
                    if f.get("status") and not (cur["status"] == "open" and f["status"] == "proposed"):
                        cur["status"] = f["status"]
                    cur["occurrences"] += 1
                    cur["last_seen"] = now
                    return copy.deepcopy(cur)
        f.setdefault("id", str(uuid.uuid4()))
        f["tenant_id"] = tenant
        f.setdefault("status", "open")
        f.setdefault("severity", "info")
        f.setdefault("occurrences", 1)
        f.setdefault("first_seen", now)
        f["last_seen"] = now
        self.findings[f["id"]] = f
        return copy.deepcopy(f)

    async def list_findings(self, tenant, *, status=None, severity=None, phase=None, type=None, run_id=None, limit=100):
        rows = [f for f in self.findings.values() if f["tenant_id"] == tenant
                and (status is None or f["status"] == status) and (severity is None or f["severity"] == severity)
                and (phase is None or f.get("phase") == phase) and (type is None or f.get("type") == type)
                and (run_id is None or f.get("run_id") == run_id)]
        rows.sort(key=lambda f: (SEV_RANK.get(f["severity"], 0), f["last_seen"]), reverse=True)
        return [copy.deepcopy(f) for f in rows[:limit]]

    async def get_finding(self, tenant, fid):
        f = self.findings.get(fid)
        return copy.deepcopy(f) if f and f["tenant_id"] == tenant else None

    async def update_finding(self, tenant, fid, patch):
        f = self.findings.get(fid)
        if not f or f["tenant_id"] != tenant:
            return None
        f.update(copy.deepcopy(patch))
        return copy.deepcopy(f)

    async def finding_counts(self, tenant):
        out: dict[str, int] = {}
        for f in self.findings.values():
            if f["tenant_id"] == tenant and f["status"] in OPEN_STATES:
                out[f["severity"]] = out.get(f["severity"], 0) + 1
        return {"open": out, "total_open": sum(out.values())}

    # settings / cache / state
    async def get_settings(self, tenant):
        return copy.deepcopy(self.settings.get(tenant, {}))

    async def put_settings(self, tenant, settings, by):
        self.settings[tenant] = copy.deepcopy(settings)
        return copy.deepcopy(settings)

    async def cache_get(self, tenant, key):
        return copy.deepcopy(self.cache.get((tenant, key)))

    async def cache_put(self, tenant, key, result):
        self.cache[(tenant, key)] = copy.deepcopy(result)

    async def get_card_state(self, tenant, source_type, source_id):
        return copy.deepcopy(self.card_state.get((tenant, source_type, source_id)))

    async def put_card_state(self, tenant, source_type, source_id, state):
        self.card_state[(tenant, source_type, source_id)] = copy.deepcopy(state)

    # chunk ops
    def _rows(self, tenant):
        return [c for c in self.kstore._live(tenant)]

    async def scan_cards(self, tenant, after, limit, *, with_embedding=False, first_chunk_only=True):
        rows = [c for c in self._rows(tenant) if (not first_chunk_only or c.chunk_no == 0)]
        rows.sort(key=lambda c: (c.source_type, c.source_id, c.chunk_no))
        if after is not None:
            rows = [c for c in rows if (c.source_type, c.source_id, c.chunk_no) > tuple(after)]
        out = []
        for c in rows[:limit]:
            d = copy.deepcopy(c)
            if not with_embedding:
                d.embedding = None
            out.append(d)
        return out

    async def get_chunks(self, tenant, source_type, source_id):
        rows = [c for c in self._rows(tenant) if c.source_type == source_type and c.source_id == source_id]
        return [copy.deepcopy(c) for c in sorted(rows, key=lambda c: c.chunk_no)]

    async def top_cards(self, tenant, n):
        rows = [c for c in self._rows(tenant) if c.chunk_no == 0 and c.visibility != "private"]
        rows.sort(key=lambda c: (-c.importance, c.source_type, c.source_id))
        return [copy.deepcopy(c) for c in rows[:n]]

    async def count_cards(self, tenant):
        live = self._rows(tenant)
        models: dict[str, int] = {}
        types: dict[str, int] = {}
        for c in live:
            models[c.embedding_model or "none"] = models.get(c.embedding_model or "none", 0) + 1
            if c.chunk_no == 0:
                types[c.source_type] = types.get(c.source_type, 0) + 1
        return {"live_chunks": len(live), "live_sources": len({(c.source_type, c.source_id) for c in live}),
                "tombstoned": sum(1 for c in self.kstore.rows.values() if c.tenant_id == tenant and c.deleted_at),
                "stale_tagged": sum(1 for c in live if c.chunk_no == 0 and STALE_TAG in c.tags), "models": models, "source_types": types}

    async def find_stale(self, tenant, source_type, cutoff, tag, limit):
        rows = [c for c in self._rows(tenant) if c.chunk_no == 0 and c.source_type == source_type and c.as_of is not None
                and c.as_of < cutoff and tag not in c.tags]
        rows.sort(key=lambda c: (c.as_of, c.source_id))
        return [(c.source_type, c.source_id, c.as_of) for c in rows[:limit]]

    async def tagged(self, tenant, tag, limit):
        rows = sorted((c for c in self._rows(tenant) if c.chunk_no == 0 and tag in c.tags), key=lambda c: (c.source_type, c.source_id))
        return [(c.source_type, c.source_id, c.as_of) for c in rows[:limit]]

    async def tag_source(self, tenant, source_type, source_id, add, remove):
        n = 0
        for c in self._rows(tenant):
            if c.source_type == source_type and c.source_id == source_id:
                new = [t for t in c.tags if t not in remove] + [t for t in add if t not in c.tags]
                if new != c.tags:
                    c.tags = new
                    n += 1
        return n

    async def set_embedding(self, tenant, source_type, source_id, chunk_no, embedding, model, content_hash):
        for c in self._rows(tenant):
            if (c.source_type, c.source_id, c.chunk_no) == (source_type, source_id, chunk_no):
                c.embedding, c.embedding_model, c.content_hash = list(embedding), model, content_hash
                return True
        return False

    async def edge_origins(self, tenant):
        pre = f"{tenant}|"
        return {k[len(pre):] for k, es in self.kstore.edges.items() if k.startswith(pre) and es}

    async def dangling_edges(self, tenant, types, limit):
        live = {(c.source_type, c.source_id) for c in self._rows(tenant)}
        out = []
        pre = f"{tenant}|"
        for k, es in sorted(self.kstore.edges.items()):
            if not k.startswith(pre):
                continue
            for e in es:
                if e.dst_type in types and (e.dst_type, e.dst_id) not in live:
                    out.append((k[len(pre):], e.dst_type, e.dst_id))
        return out[:limit]
