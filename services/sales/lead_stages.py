"""Lead stage rules — one stage model for the lead table and the pipeline board.

SPEC-lead-lifecycle.md. Pure logic (no DB) so the rules are unit-tested.

    Lead phase:      NEW → CONTACTED → QUALIFIED      (DISQUALIFIED = closed)
    Pipeline phase:  the lead has a deal; the deal's board stage is the truth.
                     Lead status mirrors it: CONVERTED (open), WON, LOST.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

LEAD_PHASE_STATUSES = ("NEW", "CONTACTED", "QUALIFIED", "DISQUALIFIED")
WON_STAGE = "Closed Won"
LOST_STAGE = "Closed Lost"

# Status values the old UI / field app send that really mean a board stage.
_LEGACY_TO_STAGE = {"PROPOSAL": "Proposal", "NEGOTIATION": "Negotiation", "WON": WON_STAGE}


class StageChangeError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class StagePlan:
    lead_status: str
    create_deal_at: Optional[str] = None
    move_deal_to: Optional[str] = None
    close_deal: Optional[str] = None  # "won" | "lost"
    closed: bool = False
    reason: Optional[str] = None


def format_reference(ref_no: Optional[int]) -> Optional[str]:
    return f"LD-{ref_no:06d}" if ref_no is not None else None


def lead_status_for_deal(deal_status: str) -> str:
    return {"WON": "WON", "LOST": "LOST"}.get((deal_status or "").upper(), "CONVERTED")


def _canonical_stage(name: str, stage_names: Sequence[str]) -> str:
    for stage in stage_names:
        if stage.lower() == (name or "").strip().lower():
            return stage
    raise StageChangeError(f"Unknown pipeline stage '{name}'")


def _open_stages(stage_names: Sequence[str]) -> list[str]:
    return [s for s in stage_names if s not in (WON_STAGE, LOST_STAGE)]


def _require_reason(reason: Optional[str]) -> str:
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise StageChangeError("A reason (at least 3 characters) is required to close a lead as lost")
    return reason


def plan_stage_change(
    *,
    current_status: str,
    deal_status: Optional[str],
    stage_names: Sequence[str],
    target_status: Optional[str] = None,
    target_stage: Optional[str] = None,
    reason: Optional[str] = None,
) -> StagePlan:
    """Decide what a stage change does. `deal_status` is None when the lead has
    no deal, else the deal's status (OPEN / WON / LOST). Exactly one of
    `target_status` (lead phase) or `target_stage` (board stage) is given."""
    if bool(target_status) == bool(target_stage):
        raise StageChangeError("Give either a lead status or a pipeline stage")

    has_deal = deal_status is not None
    deal_open = (deal_status or "").upper() == "OPEN"

    if target_status:
        status = target_status.strip().upper()
        if status in _LEGACY_TO_STAGE:
            target_stage = _LEGACY_TO_STAGE[status]
        elif status == "CONVERTED":
            if has_deal:
                return StagePlan(lead_status=lead_status_for_deal(deal_status))
            target_stage = _open_stages(stage_names)[0]
        elif status == "LOST":
            if deal_open:
                target_stage = LOST_STAGE
            else:
                status = "DISQUALIFIED"
        if not target_stage:
            if status not in LEAD_PHASE_STATUSES:
                raise StageChangeError(f"Unknown lead status '{target_status}'")
            if has_deal:
                raise StageChangeError(
                    "This lead is on the pipeline board; move its deal instead", status_code=409)
            closed = status == "DISQUALIFIED"
            return StagePlan(lead_status=status, closed=closed,
                             reason=(reason or "").strip() or None if closed else None)

    stage = _canonical_stage(target_stage, stage_names)

    if not has_deal:
        if stage == LOST_STAGE:
            return StagePlan(lead_status="DISQUALIFIED", closed=True, reason=_require_reason(reason))
        if stage == WON_STAGE:
            return StagePlan(lead_status="WON", create_deal_at=_open_stages(stage_names)[0],
                             close_deal="won", closed=True)
        return StagePlan(lead_status="CONVERTED", create_deal_at=stage)

    if not deal_open:
        raise StageChangeError("The deal for this lead is already closed", status_code=409)
    if stage == WON_STAGE:
        return StagePlan(lead_status="WON", close_deal="won", closed=True)
    if stage == LOST_STAGE:
        return StagePlan(lead_status="LOST", close_deal="lost", closed=True, reason=_require_reason(reason))
    return StagePlan(lead_status="CONVERTED", move_deal_to=stage)
