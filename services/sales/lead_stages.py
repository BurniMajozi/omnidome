"""Lead stage rules — one stage model for the lead table and the pipeline board.

SPEC-lead-lifecycle.md. Pure logic (no DB) so the rules are unit-tested.

    Lead phase:      NEW → CONTACTED → QUALIFIED      (DISQUALIFIED = closed)
    Pipeline phase:  the lead has a deal; the deal's board stage is the truth.
                     Lead status mirrors it: CONVERTED (open), WON, LOST.
"""

from __future__ import annotations

import re
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


def _rank(status: str, deal_stage: Optional[str], stage_names: Sequence[str]) -> Optional[int]:
    """Position on the journey; None for closed leads. Lead phase 0..2, board 3.."""
    if deal_stage:
        open_stages = _open_stages(stage_names)
        return 3 + open_stages.index(deal_stage) if deal_stage in open_stages else None
    order = {"NEW": 0, "CONTACTED": 1, "QUALIFIED": 2}
    return order.get((status or "").upper())


def is_forward_move(
    *,
    current_status: str,
    deal_stage: Optional[str],
    stage_names: Sequence[str],
    target_status: Optional[str] = None,
    target_stage: Optional[str] = None,
) -> bool:
    """Automations only ever advance a lead: never backwards, never a closed lead,
    never onto a closing stage (a person decides won/lost)."""
    current = _rank(current_status, deal_stage, stage_names)
    if current is None:
        return False
    if target_stage:
        try:
            stage = _canonical_stage(target_stage, stage_names)
        except StageChangeError:
            return False
        target = _rank("", stage, stage_names)
    else:
        target = _rank(target_status or "", None, stage_names)
    return target is not None and target > current


# ── Channel normalization (ONE mapping: schema.py's SQL backfill mirrors it) ──

SALES_CHANNELS = (
    "MARKETING",
    "INBOUND_EMAIL",
    "CALL_CENTER_INBOUND",
    "CALL_CENTER_OUTBOUND",
    "PORTAL_WEBSITE",
    "FIELD_SALES",
    "WALK_IN",
    "REFERRAL",
    "COMPANY_SEARCH",
    "TENDER",
    "OTHER",
)

# Whole-word keyword groups, checked in this order. Matching is on WORDS (split
# on anything that is not a letter or digit), never on substrings: "BROADBAND"
# is not "AD", "DIALING" is not "IN", "CALLING" is not inbound.
_FIELD_WORDS = {"FIELD", "DOOR", "VISIT", "CANVASS", "CANVASSING"}
_CALL_WORDS = {"CALL", "CALLS", "CALLING", "PHONE"}
_INBOUND_WORDS = {"INBOUND", "IN", "INCOMING"}
_OUTBOUND_WORDS = {"OUTBOUND", "OUT", "OUTGOING", "TELE", "TELESALES", "TELEMARKETING", "COLD"}
_MARKETING_WORDS = {"MARKET", "MARKETING", "CAMPAIGN", "SOCIAL", "AD", "ADS", "ADVERT", "ADVERTS",
                    "ADVERTISING", "ADVERTISEMENT"}
_PORTAL_WORDS = {"PORTAL", "WEB", "WEBSITE", "WEBFORM", "ONLINE", "SITE"}
_TENDER_WORDS = {"TENDER", "TENDERS", "RFQ", "RFP", "PROCUREMENT"}
_EMAIL_WORDS = {"EMAIL", "MAIL", "EMAILS"}
_WALK_WORDS = {"WALK", "WALKIN", "WALKINS", "BRANCH", "STORE"}
_REFERRAL_WORDS = {"REFERRAL", "REFERRALS", "REFER", "REFERRED", "PARTNER", "AFFILIATE"}


def _tokens(value: str) -> list[str]:
    return [w for w in re.split(r"[^A-Z0-9]+", (value or "").upper()) if w]


def _match_channel(raw: str) -> Optional[str]:
    """Allow-listed channel for one raw string, or None when nothing matches."""
    tokens = _tokens(raw)
    if not tokens:
        return None
    words = set(tokens)
    if "_".join(tokens) in SALES_CHANNELS:
        return "_".join(tokens)
    if "COMPANY" in words:
        return "COMPANY_SEARCH"
    if words & _FIELD_WORDS:
        return "FIELD_SALES"
    if words & _CALL_WORDS:
        return "CALL_CENTER_INBOUND" if words & _INBOUND_WORDS else "CALL_CENTER_OUTBOUND"
    if words & _OUTBOUND_WORDS:
        return "CALL_CENTER_OUTBOUND"
    if words & _MARKETING_WORDS:
        return "MARKETING"
    if words & _PORTAL_WORDS:
        return "PORTAL_WEBSITE"
    if words & _TENDER_WORDS:
        return "TENDER"
    if words & _EMAIL_WORDS:
        return "INBOUND_EMAIL"
    if words & _WALK_WORDS:
        return "WALK_IN"
    if words & _REFERRAL_WORDS:
        return "REFERRAL"
    return None


def normalize_channel(
    channel: Optional[str] = None,
    source: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Canonical sales channel for a raw channel / legacy source string.

    The result is ALWAYS one of SALES_CHANNELS: an unknown value becomes OTHER
    (it is never passed through raw)."""
    for raw in (channel, source):
        found = _match_channel((raw or "").strip())
        if found:
            return found
    if notes and "company search" in notes.lower():
        return "COMPANY_SEARCH"
    return "OTHER"


# ── Funnel stage buckets (ONE mapping for the funnel and the board) ───────────

# Order of the fixed funnel. Keys are the labels the web already renders.
STANDARD_FUNNEL_STAGES: tuple[str, ...] = (
    "NEW", "CONTACTED", "QUALIFIED", "Prospecting", "Proposal", "Negotiation", "Closed Won", "Closed Lost",
)
_CANONICAL_BY_KEY = {s.upper(): s for s in STANDARD_FUNNEL_STAGES}
# Synonyms, keyed by trimmed upper-case text with runs of "_"/whitespace collapsed to one space.
_STAGE_SYNONYMS = {
    "WON": "Closed Won",
    "LOST": "Closed Lost",
    "DISQUALIFIED": "Closed Lost",
    "CLOSED WON": "Closed Won",
    "CLOSED LOST": "Closed Lost",
}
OPEN_FUNNEL_ORDER: tuple[str, ...] = ("NEW", "CONTACTED", "QUALIFIED", "Prospecting", "Proposal", "Negotiation")


def stage_key(name: Optional[str]) -> str:
    """Case-insensitive, trimmed identity of a stage name."""
    return re.sub(r"[\s_]+", " ", (name or "").strip()).upper()


def canonical_stage(name: Optional[str]) -> Optional[str]:
    """The standard funnel label for a stage or lead status ('Qualified' and
    'QUALIFIED' are the same stage), or None for a tenant-defined custom stage."""
    key = stage_key(name)
    return _STAGE_SYNONYMS.get(key) or _CANONICAL_BY_KEY.get(key)


def funnel_bucket(
    lead_status: Optional[str],
    deal_status: Optional[str] = None,
    deal_stage: Optional[str] = None,
    has_deal: Optional[bool] = None,
) -> tuple[str, bool, bool]:
    """(bucket label, is_won, is_lost) for one lead. Every lead lands in exactly
    one bucket, so bucket counts always add up to the number of leads.

    With a deal, the deal is the truth (status first, then its board stage);
    without one the lead status is. A custom board stage keeps its own label."""
    if has_deal is None:
        has_deal = deal_status is not None or deal_stage is not None
    if has_deal:
        status_key = stage_key(deal_status)
        stage_std = canonical_stage(deal_stage)
        if status_key == "WON" or stage_std == "Closed Won":
            return "Closed Won", True, False
        if status_key == "LOST" or stage_std == "Closed Lost":
            return "Closed Lost", False, True
        if stage_std:
            return stage_std, False, False
        custom = re.sub(r"\s+", " ", (deal_stage or "").strip())
        return (custom or "Prospecting"), False, False
    std = canonical_stage(lead_status)
    if std == "Closed Won":
        return std, True, False
    if std == "Closed Lost":
        return std, False, True
    if std:
        return std, False, False
    if stage_key(lead_status) == "CONVERTED":
        return "CONVERTED", False, False  # in the pipeline but its deal row is missing
    custom = re.sub(r"\s+", " ", (lead_status or "").strip())
    return (custom or "NEW"), False, False


def cohort_conversion(counts: dict[str, int]) -> dict[str, dict[str, float]]:
    """Stage-to-stage conversion on COHORT counts.

    cohort[stage] = leads that reached that stage or went further (open leads at
    or past it, plus every won lead). Lost leads are excluded: we do not know
    where they dropped out. conversion_from_previous = cohort / previous cohort,
    clamped to 0..100 (0 when the previous cohort is empty)."""
    by_key = {stage_key(k): v for k, v in counts.items()}
    won = by_key.get("CLOSED WON", 0)
    open_counts = [by_key.get(stage_key(s), 0) for s in OPEN_FUNNEL_ORDER]
    out: dict[str, dict[str, float]] = {}
    previous: Optional[int] = None
    labels = list(OPEN_FUNNEL_ORDER) + ["Closed Won"]
    for i, label in enumerate(labels):
        cohort = won + (sum(open_counts[i:]) if i < len(open_counts) else 0)
        if previous is None:
            pct = 100.0 if cohort > 0 else 0.0
        else:
            pct = (cohort / previous * 100.0) if previous > 0 else 0.0
        out[label] = {"cohort": cohort, "conversion_from_previous_pct": round(max(0.0, min(100.0, pct)), 1)}
        previous = cohort
    return out
