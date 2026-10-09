"""Consolidation: short-term -> long-term promotion, episodic -> semantic roll-up, near-duplicate merge,
importance decay/archive, and the POPIA erase path.

Respects the M5 retention settings (MEMORY_ROLLUP_DAYS, MEMORY_LOW_IMPORTANCE_DAYS, same env names as
the orchestrator's nightly housekeeping). The roll-up here runs ROLLUP_GRACE_DAYS later than M5 so it is a
safety net for tenants M5 has not reached, not a competitor. All steps are idempotent and report what they did.
Planners are pure functions; executors take sessions/stores so tests can drive them.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID

from services.tenant_memory.knowledge import tiers
from services.tenant_memory.knowledge.store import KnowledgeStore

logger = logging.getLogger("knowledge.consolidation")

ROLLUP_DAYS = int(os.getenv("MEMORY_ROLLUP_DAYS", "30"))
LOW_IMPORTANCE_DAYS = int(os.getenv("MEMORY_LOW_IMPORTANCE_DAYS", "90"))
ROLLUP_GRACE_DAYS = int(os.getenv("CONSOLIDATION_ROLLUP_GRACE_DAYS", "30"))
MERGE_THRESHOLD = float(os.getenv("CONSOLIDATION_MERGE_COSINE", "0.97"))
DECAY_HALF_LIFE_DAYS = float(os.getenv("CONSOLIDATION_DECAY_HALF_LIFE_DAYS", "180"))
IMPORTANCE_FLOOR = 0.1

Summariser = Callable[[str, list[dict]], Awaitable[tuple[str, str]]]    # (previous_summary, entries) -> (text, method)


# ── pure planners ──────────────────────────────────────────────────────────

def merge_groups(pairs: list[tuple[str, str, float]], threshold: float) -> list[list[str]]:
    """Union-find over near-duplicate pairs with cosine >= threshold. Deterministic (sorted ids)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, sim in pairs:
        if sim >= threshold:
            parent[find(a)] = find(b)
    groups: dict[str, list[str]] = defaultdict(list)
    for x in list(parent):
        groups[find(x)].append(x)
    return [sorted(g) for g in sorted(groups.values()) if len(g) > 1]


def choose_canonical(entries: list[dict]) -> dict:
    """Keep the most important, then earliest, entry; the rest are archived with a pointer to it."""
    rank = {"critical": 3, "high": 2, "normal": 1, "low": 0}
    return sorted(entries, key=lambda e: (-rank.get(str(e.get("importance")), 1), str(e.get("occurred_at")), str(e["id"])))[0]


def decayed_importance(importance: float, age_days: float, half_life_days: float = DECAY_HALF_LIFE_DAYS, floor: float = IMPORTANCE_FLOOR) -> float:
    return max(floor, round(importance * (0.5 ** (max(0.0, age_days) / half_life_days)), 4)) if importance > floor else importance


def plan_rollup(entries: list[dict], now: datetime, days: Optional[int] = None) -> dict[tuple[str, str], list[dict]]:
    """Unarchived, non-pinned episodic entries old enough to be folded into a semantic summary, by (module, scope)."""
    cutoff = now - timedelta(days=days if days is not None else ROLLUP_DAYS + ROLLUP_GRACE_DAYS)
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in entries:
        occ = e.get("occurred_at")
        if e.get("archived_at") or not occ or occ > cutoff or str(e.get("importance")) == "critical":
            continue
        out[(str(e.get("module") or "general"), str(e.get("scope_key") or "default"))].append(e)
    return dict(out)


def deterministic_summary(previous: str, entries: list[dict]) -> str:
    lines = [previous.strip()] if previous.strip() else []
    for e in sorted(entries, key=lambda e: (str(e.get("occurred_at")), str(e["id"]))):
        brief = (e.get("summary") or e.get("content") or "")[:160].replace("\n", " ")
        lines.append(f"- {str(e.get('occurred_at'))[:10]} {e.get('title')}: {brief}")
    return "\n".join(lines)


async def llm_summariser(previous: str, entries: list[dict]) -> tuple[str, str]:
    """OpenRouter chain with the deterministic fallback. Summaries are narrative; figures stay in governed queries."""
    from services.common import openrouter

    body = "\n\n".join(f"[{str(e.get('occurred_at'))[:10]}] {e.get('title')}: {(e.get('content') or '')[:600]}" for e in entries)
    prompt = ("Merge these older memories into the existing summary. Keep decisions, preferences, dates, outcomes and who/what they concern. "
              "Do not invent facts or compute new figures. Be concise.\n\nExisting summary:\n" + (previous or "(none)") + "\n\nMemories:\n" + body)
    try:
        res = await openrouter.chat_completion({"messages": [{"role": "user", "content": prompt}], "max_tokens": 700}, timeout=45.0)
        if res:
            content = str(res[0]["choices"][0]["message"]["content"] or "").strip()
            if content:
                return content, f"llm:{res[1]}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("summariser LLM failed, using deterministic fallback: %s", exc)
    return deterministic_summary(previous, entries), "deterministic"


# ── executors ──────────────────────────────────────────────────────────────

async def rollup_episodic(session, tenant: str, summariser: Summariser = llm_summariser, now: Optional[datetime] = None,
                          dry_run: bool = False) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = [dict(r) for r in (await session.execute(text("""
        SELECT id::text AS id, module, scope_key, title, content, summary, importance, occurred_at, archived_at
        FROM tenant_memory_entries WHERE tenant_id = CAST(:t AS uuid) AND archived_at IS NULL ORDER BY occurred_at"""), {"t": tenant})).mappings().all()]
    groups = plan_rollup(rows, now)
    report = {"groups": len(groups), "entries": sum(len(v) for v in groups.values()), "dry_run": dry_run, "summaries": []}
    if dry_run:
        return report
    for (module, scope), entries in groups.items():
        prev = (await session.execute(text("SELECT summary, source_entry_ids FROM tenant_memory_summaries WHERE tenant_id = CAST(:t AS uuid) AND scope_key = :s"),
                                      {"t": tenant, "s": scope})).mappings().first()
        previous = prev["summary"] if prev else ""
        new_text, method = await summariser(previous, entries)
        ids = sorted({*(str(x) for x in (prev["source_entry_ids"] if prev else [])), *(e["id"] for e in entries)})
        await session.execute(text("""
            INSERT INTO tenant_memory_summaries (tenant_id, scope_key, module, title, summary, source_entry_ids, metadata)
            VALUES (CAST(:t AS uuid), :s, :m, :title, :sum, :ids, :meta)
            ON CONFLICT (tenant_id, scope_key) DO UPDATE SET summary = EXCLUDED.summary, source_entry_ids = EXCLUDED.source_entry_ids,
                metadata = tenant_memory_summaries.metadata || EXCLUDED.metadata, updated_at = now()""").bindparams(
            bindparam("ids", type_=ARRAY(PG_UUID(as_uuid=True))), bindparam("meta", type_=JSONB)),
            {"t": tenant, "s": scope, "m": module, "title": f"Summary: {scope}"[:240], "sum": new_text, "ids": ids,
             "meta": {"consolidation": {"method": method, "at": now.isoformat(), "entries_added": len(entries)}}})
        await session.execute(text("UPDATE tenant_memory_entries SET archived_at = now(), updated_at = now() "
                                   "WHERE tenant_id = CAST(:t AS uuid) AND id = ANY(CAST(:ids AS uuid[]))"),
                              {"t": tenant, "ids": [e["id"] for e in entries]})
        report["summaries"].append({"scope_key": scope, "module": module, "entries": len(entries), "method": method})
    return report


async def merge_near_duplicates(session, store: KnowledgeStore, tenant: str, threshold: float = MERGE_THRESHOLD, limit: int = 200,
                                dry_run: bool = False) -> dict:
    pairs = await store.near_duplicates(tenant, "memory_entry", threshold, limit)
    groups = merge_groups(pairs, threshold)
    report = {"groups": len(groups), "archived": 0, "dry_run": dry_run, "merged": []}
    for g in groups:
        rows = [dict(r) for r in (await session.execute(text(
            "SELECT id::text AS id, importance, occurred_at FROM tenant_memory_entries WHERE tenant_id = CAST(:t AS uuid) "
            "AND id = ANY(CAST(:ids AS uuid[])) AND archived_at IS NULL"), {"t": tenant, "ids": g})).mappings().all()]
        if len(rows) < 2:
            continue
        keep = choose_canonical(rows)
        drop = [r["id"] for r in rows if r["id"] != keep["id"]]
        report["merged"].append({"kept": keep["id"], "archived": drop})
        if dry_run:
            continue
        await session.execute(text("""UPDATE tenant_memory_entries SET archived_at = now(), updated_at = now(),
            metadata = metadata || CAST(:meta AS jsonb) WHERE tenant_id = CAST(:t AS uuid) AND id = ANY(CAST(:ids AS uuid[]))"""),
            {"t": tenant, "ids": drop, "meta": '{"merged_into": "%s", "merge_reason": "near-duplicate"}' % keep["id"]})
        for d in drop:
            await store.tombstone_source(tenant, "memory_entry", d)
        report["archived"] += len(drop)
    return report


async def apply_decay(session, store: KnowledgeStore, tenant: str, now: Optional[datetime] = None, dry_run: bool = False) -> dict:
    """Lower retrieval importance of old episodic memories (never critical) and archive old low-importance ones (M5 rule)."""
    now = now or datetime.now(timezone.utc)
    rows = [dict(r) for r in (await session.execute(text(
        "SELECT id::text AS id, importance, occurred_at FROM tenant_memory_entries WHERE tenant_id = CAST(:t AS uuid) AND archived_at IS NULL"),
        {"t": tenant})).mappings().all()]
    base = {"low": 0.25, "normal": 0.5, "high": 0.75, "critical": 1.0}
    archived, decayed = [], 0
    for r in rows:
        age = (now - r["occurred_at"]).total_seconds() / 86400 if r.get("occurred_at") else 0
        if r["importance"] == "low" and age >= LOW_IMPORTANCE_DAYS:
            archived.append(r["id"])
        elif r["importance"] in ("normal", "high") and age > 14 and not dry_run:
            decayed += await store.set_importance(tenant, "memory_entry", r["id"], decayed_importance(base[r["importance"]], age))
    if archived and not dry_run:
        await session.execute(text("UPDATE tenant_memory_entries SET archived_at = now(), updated_at = now() "
                                   "WHERE tenant_id = CAST(:t AS uuid) AND id = ANY(CAST(:ids AS uuid[]))"), {"t": tenant, "ids": archived})
        for a in archived:
            await store.tombstone_source(tenant, "memory_entry", a)
    return {"archived_low_importance": len(archived), "chunks_decayed": decayed, "dry_run": dry_run}


async def consolidate_tenant(session, store: KnowledgeStore, tenant: str, *, summariser: Summariser = llm_summariser,
                             now: Optional[datetime] = None, dry_run: bool = False) -> dict:
    """The nightly job body for one tenant. Order matters: promote, merge, roll up, decay, purge tombstones."""
    now = now or datetime.now(timezone.utc)
    out: dict[str, Any] = {"tenant_id": tenant, "at": now.isoformat(), "dry_run": dry_run}
    out["promotion"] = {"skipped": "dry_run"} if dry_run else await tiers.promote_working(session, tenant, now)
    out["merge"] = await merge_near_duplicates(session, store, tenant, dry_run=dry_run)
    out["rollup"] = await rollup_episodic(session, tenant, summariser, now, dry_run)
    out["decay"] = await apply_decay(session, store, tenant, now, dry_run)
    if not dry_run:
        out["purged_tombstones"] = await store.purge_tombstones(tenant, now - timedelta(days=int(os.getenv("KNOWLEDGE_TOMBSTONE_DAYS", "30"))))
    return out


async def erase_tenant_knowledge(store: KnowledgeStore, tenant: str, *, source_type: Optional[str] = None,
                                 source_id: Optional[str] = None, module: Optional[str] = None) -> dict:
    """POPIA erasure / tenant offboarding: HARD delete of derived rows (chunks, edges, watermarks). The operational
    source rows are the data controller's to delete; because the index is derived, rebuilding from them cannot
    resurrect erased data once the source rows are gone."""
    return await store.erase(tenant, source_type=source_type, source_id=source_id, module=module)
