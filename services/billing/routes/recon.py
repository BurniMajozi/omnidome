"""Reconciliation: is OmniDome's Paystack account solvent against what it owes, and did Paystack do what we asked?

Four independent checks, run by a platform admin or an opt-in worker (RECON_WORKER_ENABLED):

1. **Solvency snapshot** - OmniDome's Paystack ZAR balance (GET /balance) against the sum of the tenants' payout wallets.
   Wallet credits recorded from an EFT never touch Paystack, so someone must top the Paystack balance up; a negative
   headroom means OmniDome could not pay every wallet out today. Ops is alerted when the state flips to `short`.
2. **Balance ledger copy** - every row of GET /balance/ledger is stored (idempotent on Paystack's id), categorised, and the
   running balance is checked for continuity (balance_after == previous balance + difference) so a missing or altered row
   shows up as a gap.
3. **Charge integrity** - every succeeded subaccount charge is verified at Paystack (GET /transaction/verify) and the
   split it actually applied is compared with the one we asked for: the tenant must have received gross - commission, on
   the right subaccount. A tenant being short-changed is the serious case.
4. **In-flight payouts and settlements** - payout items stuck in processing are reconciled against Paystack, and the
   settlements Paystack paid to OmniDome's own bank account are copied for the audit trail.

Everything is read-only against Paystack. Nothing here moves money.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from services.billing import gateway
from services.billing.access import require_tier
from services.billing.database import get_session
from services.billing.models_gateway import GatewayCharge, GatewayLiability, GatewayRefund
from services.billing.models_payouts import PayoutBatch, PayoutItem, PayoutWallet
from services.billing.models_recon import PaystackBalanceSnapshot, PaystackLedgerEntry, PaystackSettlement, ReconRun
from services.billing.routes import gateway as gw, payouts as po
from services.billing.routes.paystack_recurring import _paystack, _secret
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("billing.recon")

router = APIRouter(tags=["Reconciliation"])

TOLERANCE_CENTS = 2          # rounding slack when comparing OmniDome's own share
STALE_PAYOUT_MINUTES = int(os.getenv("RECON_PAYOUT_STALE_MINUTES", "120"))
CATEGORIES = (("reversal", "payout_reversal"), ("refund", "refund"), ("dispute", "dispute"), ("chargeback", "dispute"),
              ("settlement", "settlement"), ("fee", "fee"), ("transfer", "payout"), ("payout", "payout"),
              ("payment", "charge"), ("transaction", "charge"), ("charge", "charge"), ("topup", "topup"), ("top up", "topup"),
              ("deposit", "topup"))


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def categorise(reason: Optional[str]) -> str:
    r = (reason or "").lower()
    for needle, cat in CATEGORIES:
        if needle in r:
            return cat
    return "other"


def _dt(value) -> datetime:
    try:
        return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return datetime.now(timezone.utc)


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 1. Solvency snapshot
# ---------------------------------------------------------------------------

async def take_snapshot() -> Optional[dict]:
    """Record OmniDome's Paystack balance vs the payout wallets. Returns None when the balance cannot be read."""
    balance = await po.provider_balance_cents()
    if balance is None:
        return None
    alert = None
    with get_session() as session:
        wallets = int(session.execute(select(func.coalesce(func.sum(PayoutWallet.balance_cents), 0))).scalar_one())
        liabilities = int(session.execute(select(func.coalesce(func.sum(GatewayLiability.amount_cents), 0)).where(
            GatewayLiability.status == "open")).scalar_one())
        previous = session.execute(select(PaystackBalanceSnapshot).order_by(PaystackBalanceSnapshot.taken_at.desc()).limit(1)).scalar_one_or_none()
        headroom = balance - wallets
        status = "ok" if headroom >= 0 else "short"
        snap = PaystackBalanceSnapshot(balance_cents=balance, wallets_cents=wallets, liabilities_open_cents=liabilities,
                                       headroom_cents=headroom, status=status, taken_at=datetime.now(timezone.utc))
        session.add(snap)
        if status == "short" and (previous is None or previous.status != "short"):
            alert = (balance, wallets, headroom)
        out = snapshot_dict(snap)
    if alert:
        await gw._alert_ops(
            "Paystack balance is below what tenants' payout wallets hold",
            f"<p>Paystack balance <b>R{alert[0] / 100:,.2f}</b> is below the tenants' payout wallets "
            f"<b>R{alert[1] / 100:,.2f}</b> (short by R{-alert[2] / 100:,.2f}). Top up the Paystack balance before payroll or supplier payments run.</p>")
    return out


def snapshot_dict(s: PaystackBalanceSnapshot) -> dict:
    return {"balance_zar": s.balance_cents / 100, "wallets_zar": s.wallets_cents / 100,
            "liabilities_open_zar": s.liabilities_open_cents / 100, "headroom_zar": s.headroom_cents / 100, "status": s.status,
            "taken_at": s.taken_at.isoformat() if s.taken_at else None}


# ---------------------------------------------------------------------------
# 2. Balance ledger copy + continuity
# ---------------------------------------------------------------------------

async def sync_ledger(max_pages: Optional[int] = None) -> dict:
    """Copy new rows of Paystack's balance ledger. Newest first, so stop at the first page that adds nothing."""
    pages = max_pages or int(os.getenv("RECON_LEDGER_PAGES", "10"))
    new = fetched = 0
    for page in range(1, pages + 1):
        res = await _paystack("GET", f"/balance/ledger?perPage=100&page={page}")
        rows = res.get("data") or []
        if not res.get("status") or not rows:
            break
        added = 0
        with get_session() as session:
            known = {pid for (pid,) in session.execute(select(PaystackLedgerEntry.paystack_id).where(
                PaystackLedgerEntry.paystack_id.in_([_int(r.get("id")) for r in rows]))).all()}
            for r in rows:
                pid = _int(r.get("id"))
                fetched += 1
                if not pid or pid in known:
                    continue
                session.add(PaystackLedgerEntry(
                    paystack_id=pid, currency=str(r.get("currency") or "ZAR"), balance_cents=_int(r.get("balance")),
                    difference_cents=_int(r.get("difference")), reason=(r.get("reason") or "")[:200] or None,
                    category=categorise(r.get("reason")), model_responsible=(r.get("model_responsible") or None),
                    model_row=_int(r.get("model_row")) or None, occurred_at=_dt(r.get("createdAt") or r.get("created_at"))))
                added += 1
        new += added
        if added == 0:
            break
    return {"fetched": fetched, "new": new}


def ledger_breaks(session, limit: int = 20) -> list[dict]:
    """Places where the running balance does not follow from the previous row (a missing or altered ledger row)."""
    rows = session.execute(select(PaystackLedgerEntry).order_by(PaystackLedgerEntry.paystack_id)).scalars().all()
    out = []
    for prev, cur in zip(rows, rows[1:]):
        if prev.currency == cur.currency and prev.balance_cents + cur.difference_cents != cur.balance_cents:
            out.append({"after_paystack_id": prev.paystack_id, "paystack_id": cur.paystack_id,
                        "expected_balance_zar": (prev.balance_cents + cur.difference_cents) / 100,
                        "actual_balance_zar": cur.balance_cents / 100, "reason": cur.reason})
    return out[-limit:]


# ---------------------------------------------------------------------------
# 3. Charge integrity
# ---------------------------------------------------------------------------

def evaluate_charge(charge: GatewayCharge, data: dict) -> tuple[str, str, Optional[int], Optional[int]]:
    """(recon_status, note, actual_tenant_cents, actual_integration_cents) from Paystack's verify payload."""
    if str(data.get("status")) != "success":
        return "mismatch", f"Paystack reports status {data.get('status')!r} for a charge we recorded as succeeded", None, None
    if _int(data.get("amount")) != charge.gross_cents:
        return "mismatch", f"Paystack amount {_int(data.get('amount'))} differs from ours {charge.gross_cents}", None, None
    sub = data.get("subaccount") or {}
    code = sub.get("subaccount_code") if isinstance(sub, dict) else None
    if code and code != charge.subaccount_code:
        return "mismatch", f"Settled to subaccount {code}, expected {charge.subaccount_code}", None, None
    split = data.get("fees_split")
    if not isinstance(split, dict) or split.get("subaccount") is None:
        return "no_split_data", "Paystack did not return the split for this charge", None, None
    tenant, integration = _int(split.get("subaccount")), _int(split.get("integration"))
    kept = charge.commission_cents + (charge.commission_vat_cents or 0)        # fee + the VAT added on top
    expected_tenant = charge.gross_cents - kept
    if tenant != expected_tenant:
        return ("mismatch", f"Tenant received {tenant} but should have received {expected_tenant} "
                            f"(gross {charge.gross_cents} - fee {charge.commission_cents} - VAT {charge.commission_vat_cents or 0})",
                tenant, integration)
    fee = _int(data.get("fees")) if data.get("fees") is not None else (charge.paystack_fee_cents or 0)
    expected_ours = kept - fee
    if abs(integration - expected_ours) > TOLERANCE_CENTS:
        return ("mismatch", f"OmniDome's share is {integration}, expected about {expected_ours} "
                            f"(fee + VAT {kept} - Paystack fee {fee})", tenant, integration)
    return "ok", "", tenant, integration


async def reconcile_charges(limit: int = 200) -> dict:
    """Verify succeeded charges not yet reconciled. A charge Paystack cannot find is flagged, never silently skipped."""
    with get_session() as session:
        refs = [r for (r,) in session.execute(select(GatewayCharge.reference).where(
            GatewayCharge.status == "succeeded", GatewayCharge.recon_at.is_(None)).order_by(GatewayCharge.created_at).limit(limit)).all()]
    counts = {"ok": 0, "mismatch": 0, "no_split_data": 0, "unavailable": 0}
    flagged = []
    for ref in refs:
        res = await _paystack("GET", f"/transaction/verify/{ref}")
        if res.get("_http_status", 200) >= 500:
            counts["unavailable"] += 1
            continue                                           # try again next run
        with get_session() as session:
            c = session.execute(select(GatewayCharge).where(GatewayCharge.reference == ref)).scalar_one()
            if res.get("status"):
                status, note, tenant, ours = evaluate_charge(c, res.get("data") or {})
            else:
                status, note, tenant, ours = "mismatch", f"Paystack could not verify this charge: {res.get('message') or 'not found'}", None, None
            c.recon_status, c.recon_note, c.recon_at = status, note[:300] or None, datetime.now(timezone.utc)
            c.actual_tenant_cents, c.actual_integration_cents = tenant, ours
            if status == "mismatch":
                flagged.append((str(c.tenant_id), ref, note))
        counts[status] += 1
    if flagged:
        logger.error("ALERT: %d charge(s) did not settle as instructed: %s", len(flagged), flagged[:3])
        await gw._alert_ops(f"{len(flagged)} Paystack charge(s) did not settle as instructed",
                            "<ul>" + "".join(f"<li>{ref}: {note}</li>" for _, ref, note in flagged[:20]) + "</ul>")
    return {**counts, "checked": len(refs)}


# ---------------------------------------------------------------------------
# 4. Payout sweep + settlements
# ---------------------------------------------------------------------------

async def sweep_payouts() -> dict:
    """Reconcile every batch that still has an item processing/pending after the stale window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_PAYOUT_MINUTES)
    with get_session() as session:
        rows = session.execute(select(PayoutItem.batch_id, PayoutItem.created_at).where(
            PayoutItem.status.in_(("pending", "processing")))).all()
        batches = sorted({b for b, created in rows if _aware(created) < cutoff}, key=str)
    for b in batches:
        await po.reconcile_batch(b)
    return {"batches": len(batches)}


async def sync_settlements(pages: int = 3) -> dict:
    new = 0
    for page in range(1, pages + 1):
        res = await _paystack("GET", f"/settlement?perPage=50&page={page}")
        rows = res.get("data") or []
        if not res.get("status") or not rows:
            break
        added = 0
        with get_session() as session:
            known = {pid for (pid,) in session.execute(select(PaystackSettlement.paystack_id).where(
                PaystackSettlement.paystack_id.in_([_int(r.get("id")) for r in rows]))).all()}
            for r in rows:
                pid = _int(r.get("id"))
                if not pid or pid in known:
                    continue
                session.add(PaystackSettlement(
                    paystack_id=pid, status=r.get("status"), currency=str(r.get("currency") or "ZAR"),
                    total_amount_cents=_int(r.get("total_amount")), total_fees_cents=_int(r.get("total_fees")),
                    total_processed_cents=_int(r.get("total_processed")),
                    settled_on=_dt(r.get("settlement_date") or r.get("settled_at") or r.get("createdAt") or r.get("created_at"))))
                added += 1
        new += added
        if added == 0:
            break
    return {"new": new}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

_RECON_LOCK_KEY = 0x0B111_5EAA


def _lock():
    from sqlalchemy import text
    from services.common.db import get_engine
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return True, None
    conn = engine.connect()
    if not bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _RECON_LOCK_KEY}).scalar()):
        conn.close()
        return False, None
    return True, conn


def _unlock(conn) -> None:
    from sqlalchemy import text
    if conn is not None:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _RECON_LOCK_KEY})
        finally:
            conn.close()


async def run_recon(triggered_by: str) -> dict:
    """Run every check once. One failing step never stops the others; each step's outcome is recorded."""
    if not _secret():
        return {"skipped": "Paystack is not configured"}
    acquired, conn = _lock()
    if not acquired:
        return {"skipped": "another reconciliation is running"}
    try:
        with get_session() as session:
            run = ReconRun(triggered_by=triggered_by)
            session.add(run)
            session.flush()
            run_id = run.id
        summary: dict = {}
        errors = []
        for name, step in (("snapshot", take_snapshot), ("ledger", sync_ledger), ("charges", reconcile_charges),
                           ("payouts", sweep_payouts), ("settlements", sync_settlements)):
            try:
                summary[name] = await step()
            except Exception as exc:  # noqa: BLE001
                logger.exception("reconciliation step %s failed", name)
                summary[name] = {"error": type(exc).__name__}
                errors.append(name)
        with get_session() as session:
            summary["ledger_breaks"] = len(ledger_breaks(session, limit=1000))
            r = session.get(ReconRun, run_id)
            r.finished_at, r.summary = datetime.now(timezone.utc), summary
            r.error = ", ".join(errors) or None
        return {"run_id": str(run_id), **summary}
    finally:
        _unlock(conn)


def worker_enabled() -> bool:
    return os.getenv("RECON_WORKER_ENABLED", "false").strip().lower() == "true"


async def worker_loop(interval_seconds: Optional[int] = None) -> None:
    import asyncio
    interval = interval_seconds or int(os.getenv("RECON_INTERVAL_SECONDS", "3600"))
    logger.info("reconciliation worker started (interval %ss)", interval)
    while True:
        try:
            await run_recon("worker")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reconciliation pass failed")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Platform-admin endpoints
# ---------------------------------------------------------------------------

def _platform_only(ctx: AuthContext) -> None:
    if not gw._is_platform_admin(ctx):
        raise HTTPException(status_code=403, detail="Platform admin only")


@router.get("/recon/overview", dependencies=[Depends(require_tier("admin"))])
async def overview(ctx: AuthContext = Depends(get_auth_context)):
    _platform_only(ctx)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    with get_session() as session:
        snap = session.execute(select(PaystackBalanceSnapshot).order_by(PaystackBalanceSnapshot.taken_at.desc()).limit(1)).scalar_one_or_none()
        wallets = int(session.execute(select(func.coalesce(func.sum(PayoutWallet.balance_cents), 0))).scalar_one())
        liabilities = int(session.execute(select(func.coalesce(func.sum(GatewayLiability.amount_cents), 0)).where(
            GatewayLiability.status == "open")).scalar_one())
        statuses = dict(session.execute(select(GatewayCharge.recon_status, func.count()).where(
            GatewayCharge.status == "succeeded", GatewayCharge.created_at >= since).group_by(GatewayCharge.recon_status)).all())
        unverified = int(session.execute(select(func.count()).select_from(GatewayCharge).where(
            GatewayCharge.status == "succeeded", GatewayCharge.recon_at.is_(None))).scalar_one())
        mismatches = int(session.execute(select(func.count()).select_from(GatewayCharge).where(GatewayCharge.recon_status == "mismatch")).scalar_one())
        stuck = int(session.execute(select(func.count()).select_from(PayoutItem).where(PayoutItem.status.in_(("pending", "processing")))).scalar_one())
        last = session.execute(select(ReconRun).order_by(ReconRun.started_at.desc()).limit(1)).scalar_one_or_none()
        breaks = len(ledger_breaks(session, limit=1000))
        return {
            "snapshot": snapshot_dict(snap) if snap else None, "wallets_now_zar": wallets / 100, "liabilities_open_zar": liabilities / 100,
            "charges_last_30d": {"ok": statuses.get("ok", 0), "mismatch": statuses.get("mismatch", 0),
                                 "no_split_data": statuses.get("no_split_data", 0), "unverified": unverified},
            "open_mismatches": mismatches, "payouts_in_flight": stuck, "ledger_breaks": breaks,
            "last_run": None if last is None else {"at": last.started_at.isoformat() if last.started_at else None,
                                                    "finished": last.finished_at is not None, "error": last.error, "summary": last.summary}}


@router.post("/recon/run", dependencies=[Depends(require_tier("admin"))])
async def run_now(ctx: AuthContext = Depends(get_auth_context)):
    _platform_only(ctx)
    return await run_recon(f"user:{ctx.user_id}")


@router.get("/recon/snapshots", dependencies=[Depends(require_tier("admin"))])
async def snapshots(limit: int = 48, ctx: AuthContext = Depends(get_auth_context)):
    _platform_only(ctx)
    with get_session() as session:
        rows = session.execute(select(PaystackBalanceSnapshot).order_by(PaystackBalanceSnapshot.taken_at.desc())
                               .limit(min(max(limit, 1), 500))).scalars().all()
        return {"snapshots": [snapshot_dict(s) for s in rows]}


@router.get("/recon/ledger", dependencies=[Depends(require_tier("admin"))])
async def ledger(category: Optional[str] = None, limit: int = 100, ctx: AuthContext = Depends(get_auth_context)):
    _platform_only(ctx)
    with get_session() as session:
        q = select(PaystackLedgerEntry)
        if category:
            q = q.where(PaystackLedgerEntry.category == category)
        rows = session.execute(q.order_by(PaystackLedgerEntry.paystack_id.desc()).limit(min(max(limit, 1), 500))).scalars().all()
        totals = session.execute(select(PaystackLedgerEntry.category, func.sum(PaystackLedgerEntry.difference_cents), func.count())
                                 .group_by(PaystackLedgerEntry.category)).all()
        return {"entries": [{"paystack_id": r.paystack_id, "reason": r.reason, "category": r.category, "difference_zar": r.difference_cents / 100,
                             "balance_zar": r.balance_cents / 100, "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None}
                            for r in rows],
                "totals_by_category": [{"category": c, "net_zar": int(s or 0) / 100, "entries": n} for c, s, n in totals],
                "breaks": ledger_breaks(session)}


@router.get("/recon/mismatches", dependencies=[Depends(require_tier("admin"))])
async def mismatches(ctx: AuthContext = Depends(get_auth_context)):
    _platform_only(ctx)
    with get_session() as session:
        rows = session.execute(select(GatewayCharge).where(GatewayCharge.recon_status == "mismatch")
                               .order_by(GatewayCharge.recon_at.desc()).limit(200)).scalars().all()
        return {"mismatches": [{"tenant_id": str(c.tenant_id), "reference": c.reference, "gross_zar": c.gross_cents / 100,
                                "commission_zar": c.commission_cents / 100, "note": c.recon_note,
                                "actual_tenant_zar": None if c.actual_tenant_cents is None else c.actual_tenant_cents / 100,
                                "checked_at": c.recon_at.isoformat() if c.recon_at else None} for c in rows]}


@router.get("/recon/settlements", dependencies=[Depends(require_tier("admin"))])
async def settlements(ctx: AuthContext = Depends(get_auth_context)):
    _platform_only(ctx)
    with get_session() as session:
        rows = session.execute(select(PaystackSettlement).order_by(PaystackSettlement.settled_on.desc()).limit(100)).scalars().all()
        return {"settlements": [{"paystack_id": s.paystack_id, "status": s.status, "total_zar": s.total_amount_cents / 100,
                                 "fees_zar": s.total_fees_cents / 100, "paid_zar": s.total_processed_cents / 100,
                                 "settled_on": s.settled_on.isoformat() if s.settled_on else None} for s in rows]}


# ---------------------------------------------------------------------------
# Tenant statement
# ---------------------------------------------------------------------------

def _month_bounds(period: str) -> tuple[datetime, datetime]:
    year, month = int(period[:4]), int(period[5:7])
    start = datetime(year, month, 1, tzinfo=gateway.SAST)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=gateway.SAST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


@router.get("/gateway/statement", dependencies=[Depends(require_tier("reader"))])
async def statement(period: Optional[str] = None, ctx: AuthContext = Depends(get_auth_context)):
    """What happened to this tenant's money in a month: collected, our commission, what the tenant received, refunds,
    chargebacks, payouts, wallet balance, and how many charges were verified against Paystack."""
    period = period or gateway.period_key()
    if len(period) != 7 or period[4] != "-" or not (period[:4] + period[5:]).isdigit() or not 1 <= int(period[5:]) <= 12:
        raise HTTPException(status_code=400, detail="period must be YYYY-MM")
    start, end = _month_bounds(period)
    in_month = lambda dt: dt is not None and start <= _aware(dt) < end   # noqa: E731
    with get_session() as session:
        charges = session.execute(select(GatewayCharge).where(
            GatewayCharge.tenant_id == ctx.tenant_id, GatewayCharge.period == period, GatewayCharge.status == "succeeded")).scalars().all()
        gross = sum(c.gross_cents for c in charges)
        commission = sum(c.commission_cents for c in charges)
        refunds = [r for r in session.execute(select(GatewayRefund).where(
            GatewayRefund.tenant_id == ctx.tenant_id, GatewayRefund.status == "processed")).scalars() if in_month(r.updated_at)]
        chargebacks = [l for l in session.execute(select(GatewayLiability).where(
            GatewayLiability.tenant_id == ctx.tenant_id, GatewayLiability.kind == "chargeback")).scalars() if in_month(l.created_at)]
        items = session.execute(select(PayoutItem).join(PayoutBatch, PayoutBatch.id == PayoutItem.batch_id).where(
            PayoutItem.tenant_id == ctx.tenant_id, PayoutBatch.period == period, PayoutItem.status.in_(("processing", "success")))).scalars().all()
        wallet = session.execute(select(PayoutWallet).where(PayoutWallet.tenant_id == ctx.tenant_id)).scalar_one_or_none()
        verified = sum(1 for c in charges if c.recon_status == "ok")
        return {"period": period,
                "collections": {"charges": len(charges), "collected_zar": gross / 100, "commission_zar": commission / 100,
                                "commission_vat_zar": sum(c.commission_vat_cents for c in charges) / 100,
                                "you_receive_zar": (gross - commission - sum(c.commission_vat_cents for c in charges)) / 100},
                "refunds": {"count": len(refunds), "total_zar": sum(r.amount_cents for r in refunds) / 100},
                "chargebacks": {"count": len(chargebacks), "total_zar": sum(l.amount_cents for l in chargebacks) / 100},
                "payouts": {"count": len(items), "total_zar": sum(i.amount_cents for i in items) / 100,
                            "fees_zar": sum(i.fee_cents for i in items) / 100,
                            "fees_vat_zar": sum(i.fee_vat_cents for i in items) / 100},
                "fees_exclude_vat": True,
                "payout_wallet_zar": (wallet.balance_cents if wallet else 0) / 100,
                "open_liabilities_zar": po.open_liabilities_cents(session, ctx.tenant_id) / 100,
                "settlement_checks": {"verified": verified, "total": len(charges)}}
