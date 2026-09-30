"""Nightly memory housekeeping and roll-up (SPEC-orchestrator-memory-hardening.md, M5).

Rules:
1. Roll entries older than ROLLUP_DAYS (default 30) in each (module, scope_key)
   into that scope's summary (one LLM call per scope).
2. Archive the rolled-up entries (archived_at = now()).
3. Merge exact duplicates (matching title + content within same scope): keep the
   earliest occurred_at, archive the duplicates.
4. Archive importance='low' entries older than LOW_IMPORTANCE_DAYS (default 90).
5. Support dry_run: returns what would change without modifying database records.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import text

logger = logging.getLogger(__name__)

ROLLUP_DAYS = int(os.getenv("MEMORY_ROLLUP_DAYS", "30"))
LOW_IMPORTANCE_DAYS = int(os.getenv("MEMORY_LOW_IMPORTANCE_DAYS", "90"))

Summariser = Callable[[str, List[Dict[str, Any]]], Awaitable[str]]

SUMMARY_PROMPT = (
    "Incorporate these older archived memories into the existing summary for this scope. "
    "Keep key facts, decisions, preferences, dates, amounts, and outcomes. Keep it organized, "
    "concise, and objective without conversational commentary."
)

# Run history in Postgres, not process memory: the orchestrator runs several
# uvicorn workers, so an in-process "already ran tonight" marker let each
# worker run the nightly job, and the Agent Manager's "last run" depended on
# which worker answered (and vanished on restart).
#   tenant_id NULL + trigger 'nightly' = the night's claim (unique per date)
#   tenant_id set                       = one tenant's report (nightly or manual)
SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS memory_housekeeping_runs (
        id UUID PRIMARY KEY,
        tenant_id UUID,
        trigger VARCHAR(20) NOT NULL,
        run_date DATE NOT NULL,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ,
        report JSONB
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_memory_housekeeping_nightly
        ON memory_housekeeping_runs (run_date) WHERE tenant_id IS NULL AND trigger = 'nightly'
    """,
    "CREATE INDEX IF NOT EXISTS ix_memory_housekeeping_tenant ON memory_housekeeping_runs (tenant_id, finished_at DESC)",
]


async def ensure_schema(session: Any) -> None:
    for statement in SCHEMA_SQL:
        await session.execute(text(statement))


async def claim_nightly(session: Any, run_date: Any) -> bool:
    """True for exactly one caller per date (any worker, any restart)."""
    row = (await session.execute(
        text("""
            INSERT INTO memory_housekeeping_runs (id, tenant_id, trigger, run_date)
            VALUES (:id, NULL, 'nightly', :run_date)
            ON CONFLICT DO NOTHING
            RETURNING id
        """),
        {"id": str(uuid.uuid4()), "run_date": run_date},
    )).first()
    return row is not None


async def finish_nightly(session: Any, run_date: Any) -> None:
    await session.execute(
        text("""
            UPDATE memory_housekeeping_runs SET finished_at = now()
             WHERE tenant_id IS NULL AND trigger = 'nightly' AND run_date = :run_date
        """),
        {"run_date": run_date},
    )


async def _record_run(session: Any, tenant_id: str, trigger: str, now: datetime, report: Dict[str, Any]) -> None:
    await session.execute(
        text("""
            INSERT INTO memory_housekeeping_runs (id, tenant_id, trigger, run_date, started_at, finished_at, report)
            VALUES (:id, :tenant_id, :trigger, :run_date, :now, now(), CAST(:report AS jsonb))
        """),
        {"id": str(uuid.uuid4()), "tenant_id": tenant_id, "trigger": trigger, "run_date": now.date(),
         "now": now, "report": json.dumps(report, default=str)},
    )


def find_duplicates(entries: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Identify duplicate entries with identical (module, scope_key, title, content).
    Keeps the earliest occurred_at/created_at, marks later ones to be archived."""
    seen: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    duplicate_ids: List[str] = []
    unique_entries: List[Dict[str, Any]] = []

    # Sort so earlier occurred_at comes first
    sorted_entries = sorted(
        entries,
        key=lambda e: (e.get("occurred_at") or datetime.min.replace(tzinfo=timezone.utc), str(e.get("id"))),
    )

    for e in sorted_entries:
        key = (
            str(e.get("module") or "").strip().lower(),
            str(e.get("scope_key") or "").strip().lower(),
            str(e.get("title") or "").strip().lower(),
            str(e.get("content") or "").strip().lower(),
        )
        if key in seen:
            duplicate_ids.append(str(e["id"]))
        else:
            seen[key] = e
            unique_entries.append(e)

    return duplicate_ids, unique_entries


def find_low_importance_stale(
    entries: List[Dict[str, Any]],
    now: datetime,
    max_days: int = LOW_IMPORTANCE_DAYS,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Find unarchived low-importance entries older than max_days."""
    cutoff = now - timedelta(days=max_days)
    stale_ids: List[str] = []
    remaining: List[Dict[str, Any]] = []

    for e in entries:
        occ = e.get("occurred_at")
        if occ and occ <= cutoff and str(e.get("importance", "")).lower() == "low":
            stale_ids.append(str(e["id"]))
        else:
            remaining.append(e)

    return stale_ids, remaining


def group_for_rollup(
    entries: List[Dict[str, Any]],
    now: datetime,
    rollup_days: int = ROLLUP_DAYS,
) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Group entries older than rollup_days by (module, scope_key)."""
    cutoff = now - timedelta(days=rollup_days)
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)

    for e in entries:
        occ = e.get("occurred_at")
        if occ and occ <= cutoff:
            mod = str(e.get("module") or "general")
            scope = str(e.get("scope_key") or "default")
            groups[(mod, scope)].append(e)

    return dict(groups)


def plan_housekeeping(
    entries: List[Dict[str, Any]],
    now: datetime,
    rollup_days: int = ROLLUP_DAYS,
    low_importance_days: int = LOW_IMPORTANCE_DAYS,
) -> Dict[str, Any]:
    """Calculate the housekeeping plan: duplicates to merge, low importance to archive,
    and groups to roll into summaries."""
    # 1. Exact duplicates
    duplicate_ids, after_dups = find_duplicates(entries)

    # 2. Stale low-importance entries
    low_importance_ids, after_low = find_low_importance_stale(after_dups, now=now, max_days=low_importance_days)

    # 3. Entries older than rollup_days to roll into summaries
    groups = group_for_rollup(after_low, now=now, rollup_days=rollup_days)

    rollups_list = []
    total_rolled_up = 0
    for (module, scope_key), grp_entries in groups.items():
        entry_ids = [str(e["id"]) for e in grp_entries]
        total_rolled_up += len(entry_ids)
        rollups_list.append({
            "module": module,
            "scope_key": scope_key,
            "entry_count": len(entry_ids),
            "entry_ids": entry_ids,
            "entries": grp_entries,
        })

    return {
        "duplicates_count": len(duplicate_ids),
        "duplicate_ids": duplicate_ids,
        "low_importance_count": len(low_importance_ids),
        "low_importance_ids": low_importance_ids,
        "rollups_count": len(rollups_list),
        "entries_rolled_up": total_rolled_up,
        "rollups": rollups_list,
        "total_archived_count": len(duplicate_ids) + len(low_importance_ids) + total_rolled_up,
    }


async def default_summariser(previous_summary: str, entries: List[Dict[str, Any]]) -> str:
    """Uses agent_orchestrator llm_client to update the summary for older rolled up entries."""
    from services.agent_orchestrator.llm import llm_client

    entries_text = "\n\n".join(
        f"[{e.get('occurred_at')}] {e.get('title')}: {e.get('content')}"
        for e in entries
    )
    prompt = (
        f"{SUMMARY_PROMPT}\n\n"
        f"Existing summary:\n{previous_summary or '(none)'}\n\n"
        f"Entries to incorporate:\n{entries_text}"
    )

    resp = await llm_client.chat(
        agent_type="assistant",
        messages=[{"role": "user", "content": prompt}],
        tools=None,
        purpose="housekeeping",
    )
    if resp.get("unavailable"):
        # Fallback to appending brief notes
        return (previous_summary + "\n" if previous_summary else "") + "\n".join(
            f"- {e.get('title')}: {e.get('summary') or e.get('content')[:120]}"
            for e in entries
        )
    return str(resp.get("content") or "").strip()


async def execute_housekeeping_plan(
    entries: List[Dict[str, Any]],
    existing_summaries: Dict[Tuple[str, str], str],
    now: datetime,
    dry_run: bool = False,
    rollup_days: int = ROLLUP_DAYS,
    low_importance_days: int = LOW_IMPORTANCE_DAYS,
    summariser: Optional[Summariser] = None,
) -> Dict[str, Any]:
    """Execute the calculated plan or preview it."""
    plan = plan_housekeeping(entries, now=now, rollup_days=rollup_days, low_importance_days=low_importance_days)
    new_summaries: Dict[Tuple[str, str], str] = {}

    if not dry_run:
        sum_fn = summariser or default_summariser
        for r in plan["rollups"]:
            mod, scope = r["module"], r["scope_key"]
            prev = existing_summaries.get((mod, scope), "")
            try:
                new_sum = await sum_fn(prev, r["entries"])
                new_summaries[(mod, scope)] = new_sum
            except Exception as exc:  # noqa: BLE001
                logger.warning("Summariser failed for (%s, %s): %s", mod, scope, exc)

    return {
        "dry_run": dry_run,
        "executed_at": now.isoformat(),
        "duplicates_count": plan["duplicates_count"],
        "duplicate_ids": plan["duplicate_ids"],
        "low_importance_count": plan["low_importance_count"],
        "low_importance_ids": plan["low_importance_ids"],
        "groups_rolled_up": plan["rollups_count"],
        "entries_rolled_up": plan["entries_rolled_up"],
        "total_archived": plan["total_archived_count"],
        "rollups": [
            {
                "module": r["module"],
                "scope_key": r["scope_key"],
                "entry_count": r["entry_count"],
                "entry_ids": r["entry_ids"],
            }
            for r in plan["rollups"]
        ],
        "new_summaries": [
            {"module": m, "scope_key": s, "summary": sum_text}
            for (m, s), sum_text in new_summaries.items()
        ],
    }


async def run_tenant_housekeeping(
    session: Any,
    tenant_id: uuid.UUID | str,
    dry_run: bool = False,
    summariser: Optional[Summariser] = None,
    now: Optional[datetime] = None,
    trigger: str = "manual",
) -> Dict[str, Any]:
    """Run housekeeping for a tenant against the PostgreSQL database. A real
    run (not dry_run) is recorded in memory_housekeeping_runs as `trigger`."""
    current_time = now or datetime.now(timezone.utc)
    t_id_str = str(tenant_id)

    # 1. Fetch unarchived entries
    res_entries = await session.execute(
        text(
            """
            SELECT id, tenant_id, module, scope_key, title, content, summary,
                   importance, occurred_at, archived_at, created_at, metadata
            FROM tenant_memory_entries
            WHERE tenant_id = :tenant_id AND archived_at IS NULL
            ORDER BY occurred_at ASC
            """
        ),
        {"tenant_id": t_id_str},
    )
    entries = [dict(r) for r in res_entries.mappings().all()]

    # 2. Fetch existing summaries
    res_sums = await session.execute(
        text(
            """
            SELECT module, scope_key, summary
            FROM tenant_memory_summaries
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": t_id_str},
    )
    existing_summaries = {
        (str(r["module"] or "general"), str(r["scope_key"])): str(r["summary"] or "")
        for r in res_sums.mappings().all()
    }

    # 3. Plan and execute
    result = await execute_housekeeping_plan(
        entries=entries,
        existing_summaries=existing_summaries,
        now=current_time,
        dry_run=dry_run,
        summariser=summariser,
    )
    result["tenant_id"] = t_id_str

    if not dry_run:
        # Step A: Archive duplicates
        if result["duplicate_ids"]:
            await session.execute(
                text(
                    """
                    UPDATE tenant_memory_entries
                    SET archived_at = :now,
                        metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{archived_reason}', '"duplicate"')
                    WHERE id = ANY(:ids) AND tenant_id = :tenant_id
                    """
                ),
                {"now": current_time, "ids": [uuid.UUID(i) for i in result["duplicate_ids"]], "tenant_id": t_id_str},
            )

        # Step B: Archive low importance
        if result["low_importance_ids"]:
            await session.execute(
                text(
                    """
                    UPDATE tenant_memory_entries
                    SET archived_at = :now,
                        metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{archived_reason}', '"low_importance_retention"')
                    WHERE id = ANY(:ids) AND tenant_id = :tenant_id
                    """
                ),
                {"now": current_time, "ids": [uuid.UUID(i) for i in result["low_importance_ids"]], "tenant_id": t_id_str},
            )

        # Step C: Upsert new summaries & archive rolled-up entries
        for r in result["rollups"]:
            mod, scope = r["module"], r["scope_key"]
            sum_text = next(
                (s["summary"] for s in result["new_summaries"] if s["module"] == mod and s["scope_key"] == scope),
                "",
            )
            if sum_text and r["entry_ids"]:
                entry_uuids = [uuid.UUID(i) for i in r["entry_ids"]]
                await session.execute(
                    text(
                        """
                        INSERT INTO tenant_memory_summaries (id, tenant_id, scope_key, module, title, summary, source_entry_ids, updated_at)
                        VALUES (:id, :tenant_id, :scope_key, :module, :title, :summary, :source_entry_ids, :now)
                        ON CONFLICT (tenant_id, scope_key) DO UPDATE
                        SET summary = EXCLUDED.summary,
                            source_entry_ids = array_cat(tenant_memory_summaries.source_entry_ids, EXCLUDED.source_entry_ids),
                            updated_at = EXCLUDED.updated_at
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": t_id_str,
                        "scope_key": scope,
                        "module": mod,
                        "title": f"Summary for {scope}",
                        "summary": sum_text,
                        "source_entry_ids": entry_uuids,
                        "now": current_time,
                    },
                )
                await session.execute(
                    text(
                        """
                        UPDATE tenant_memory_entries
                        SET archived_at = :now,
                            metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{archived_reason}', '"rolled_up_to_summary"')
                        WHERE id = ANY(:ids) AND tenant_id = :tenant_id
                        """
                    ),
                    {"now": current_time, "ids": entry_uuids, "tenant_id": t_id_str},
                )

        await _record_run(session, t_id_str, trigger, current_time, result)
        await session.flush()

    return result


async def get_last_run(session: Any, tenant_id: str) -> Optional[Dict[str, Any]]:
    """The tenant's most recent real run (nightly or manual), from any worker."""
    row = (await session.execute(
        text("""
            SELECT trigger, finished_at, report FROM memory_housekeeping_runs
             WHERE tenant_id = :t ORDER BY finished_at DESC NULLS LAST LIMIT 1
        """),
        {"t": str(tenant_id)},
    )).mappings().first()
    if not row:
        return None
    return {**(row["report"] or {}), "trigger": row["trigger"],
            "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None}
