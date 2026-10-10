"""Per-phase execution context shared by every dream phase."""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from services.tenant_memory.knowledge.dream.ports import DreamDeps
from services.tenant_memory.knowledge.dream.settings import DreamSettings


class Aborted(Exception):
    """The kill switch was thrown (or the tenant disabled dreaming) while a run was in flight."""


def stable_id(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:20]


@dataclass
class PhaseCtx:
    tenant: str
    run: dict
    deps: DreamDeps
    cfg: DreamSettings
    dry_run: bool
    phase: str = ""
    state: dict = field(default_factory=dict)       # persisted per-phase (cursors, done markers) -> resumable
    shared: dict = field(default_factory=dict)      # cross-phase; keys starting with "_" are transient (not persisted)
    counts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def now(self) -> datetime:
        return self.deps.now()

    def inc(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def note(self, msg: str) -> None:
        if len(self.notes) < 20:
            self.notes.append(msg)

    def error(self, where: str, exc: BaseException) -> None:
        if len(self.errors) < 20:
            self.errors.append(f"{where}: {type(exc).__name__}: {str(exc)[:160]}")
        self.inc("errors")

    def check_kill(self) -> None:
        if self.deps.kill():
            raise Aborted("kill switch")

    async def pause(self) -> None:
        """Between batches: honour the kill switch, persist progress, give the VM a breather."""
        self.check_kill()
        await self.checkpoint()
        if self.cfg.sleep_s > 0:
            await self.deps.sleep(self.cfg.sleep_s)

    async def checkpoint(self) -> None:
        st = dict(self.run.get("state") or {})
        st[self.phase] = copy.deepcopy(self.state)
        st["shared"] = {k: copy.deepcopy(v) for k, v in self.shared.items() if not k.startswith("_")}
        self.run["state"] = st
        await self.deps.store.update_run(self.tenant, self.run["id"], {"state": st})

    # ── findings ──
    async def finding(self, *, type: str, title: str, severity: str = "info", source_type: Optional[str] = None,
                      source_id: Optional[str] = None, detail: Optional[dict] = None, action: Optional[dict] = None,
                      dedupe_key: Optional[str] = None, auto_applied: bool = False, jev: Optional[dict] = None) -> dict:
        """Record a finding. In a dry run nothing was applied, so the row is `proposed` (and says what it WOULD do)."""
        detail = dict(detail or {})
        if self.dry_run:
            status = "proposed"
            if auto_applied:
                detail["would_auto_apply"] = True
            auto_applied = False
        else:
            status = "auto_applied" if auto_applied else "open"
        row = {"run_id": self.run["id"], "phase": self.phase, "type": type, "severity": severity, "status": status,
               "source_type": source_type, "source_id": source_id, "title": title[:300], "detail": detail, "action": action,
               "dedupe_key": dedupe_key or f"{type}:{source_type or '-'}:{source_id or '-'}", "auto_applied": auto_applied}
        if jev is not None:
            row["jev"] = jev
        saved = await self.deps.store.upsert_finding(self.tenant, row)
        self.inc("findings")
        return saved

    # ── JEV bookkeeping lives in shared so it survives a resume ──
    def jev_state(self) -> dict:
        return self.shared.setdefault("jev", {"calls": 0, "cost_usd": 0.0, "cached": 0, "queued_for_review": 0, "decided": 0})
