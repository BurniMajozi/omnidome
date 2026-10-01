"""Customer 360 View routes — four-tab aggregation endpoints.

Aggregates data from CRM, Billing, Journey, Sales, Support, Lifecycle, and Retention
services via direct cross-service DB reads (all services share the same Supabase Postgres).

Endpoints:
  GET /customers/{id}/360/details  — Tab 1: Customer Details
  GET /customers/{id}/360/cx       — Tab 2: Customer Experience
  GET /customers/{id}/360/crm      — Tab 3: CRM (sales pipeline)
  GET /customers/{id}/360/cvm      — Tab 4: Customer Value Management
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select

from services.common.auth import AuthContext, get_auth_context
from services.crm.access import has_tier, redact_customer
from services.crm.database import get_session
from services.crm.models import (
    AccountHandover,
    Company,
    Customer,
    CustomerNote,
    CustomerTag,
    Lead,
    Property,
    PropertyAccount,
    RetentionPrediction,
)
from services.crm.schemas import (
    BillingAccountInfo,
    CRMResponse,
    CRMSummary,
    CustomerRead,
    CXResponse,
    CXSummary,
    CVMResponse,
    CVMSummary,
    ChurnPredictionInfo,
    CommissionSummary,
    CustomerDetailsResponse,
    DealSummary,
    DeliverySummary,
    FinancialSummary,
    HandoverHistoryItem,
    HealthInfo,
    InvoiceSummary,
    LifecycleInfo,
    OrderSummary,
    PaymentMethodInfo,
    PaymentSummary,
    PropertyAccountInfo,
    PropertyAddress,
    QuoteSummary,
    ServiceAddressInfo,
    SubscriptionInfo,
    SupportTicketSummary,
    TechnicianVisitSummary,
    ActivityTimelineItem,
)

# Cross-service model imports (all share same Supabase Postgres)
from services.billing.models import (
    BillingAccount,
    DunningAction,
    Invoice,
    Payment,
    Subscription,
    SubscriptionTransfer,
    SubscriptionUsage,
)
from services.customer_journey.models import (
    ActivityTimeline,
    CustomerAddress,
    DeliveryTracking,
    Order,
    PaymentMethod,
    TechnicianVisit,
)
from services.sales.models import (
    Contact,
    Deal,
    DealStage,
    Quote,
    Commission,
)
from services.support.database import Ticket
from services.lifecycle.models import (
    CustomerLifecycle,
    LifecycleEvent,
)

router = APIRouter(prefix="/customers", tags=["Customer 360"])
logger = logging.getLogger("crm.customer_360")


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_customer_or_404(session, customer_id: uuid.UUID, tenant_id: uuid.UUID) -> Customer:
    result = await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def _compute_tier(mrr: Decimal, ltv: Decimal) -> str:
    """Compute customer tier from MRR and LTV."""
    if ltv >= Decimal("50000") or mrr >= Decimal("2000"):
        return "PLATINUM"
    if ltv >= Decimal("20000") or mrr >= Decimal("1000"):
        return "GOLD"
    if ltv >= Decimal("5000") or mrr >= Decimal("500"):
        return "SILVER"
    return "BRONZE"


def _compute_value_segment(mrr: Decimal) -> str:
    if mrr >= Decimal("2000"):
        return "HIGH"
    if mrr >= Decimal("500"):
        return "MEDIUM"
    return "STANDARD"


def _compute_risk_segment(churn_probability: Optional[Decimal]) -> str:
    if churn_probability is None:
        return "UNKNOWN"
    if churn_probability >= Decimal("0.7"):
        return "CRITICAL"
    if churn_probability >= Decimal("0.4"):
        return "HIGH"
    if churn_probability >= Decimal("0.2"):
        return "MEDIUM"
    return "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Per-section isolation
# ─────────────────────────────────────────────────────────────────────────────
# Each section runs inside a SAVEPOINT (begin_nested) so a missing table / relation owned by
# another service, or any other DB error, poisons neither the request transaction nor the
# other sections. A failed section comes back as null with a code in `section_errors`, and the
# response carries `partial: true`. Nothing is faked to fill the hole.

def _error_code(exc: Exception) -> str:
    text_ = f"{type(exc).__name__} {exc}".lower()
    if "undefinedtable" in text_ or "does not exist" in text_ or "no such table" in text_:
        return "table_missing"
    if "undefinedcolumn" in text_:
        return "column_missing"
    if "timeout" in text_:
        return "timeout"
    return "section_error"


class _Sections:
    def __init__(self, session, customer_id: uuid.UUID):
        self.session = session
        self.customer_id = customer_id
        self.errors: dict[str, str] = {}

    async def run(self, name: str, fn):
        """Await fn() in a savepoint; on failure record the code and return None."""
        try:
            async with self.session.begin_nested():
                return await fn()
        except Exception as exc:  # noqa: BLE001 - degrade the section, never the response
            code = _error_code(exc)
            self.errors[name] = code
            logger.warning("customer 360 section %s failed for customer %s: %s (%s)",
                           name, self.customer_id, code, type(exc).__name__)
            return None

    @property
    def partial(self) -> bool:
        return bool(self.errors)


async def _rows(session, stmt):
    return (await session.execute(stmt)).scalars().all()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1: Customer Details
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}/360/details", response_model=CustomerDetailsResponse)
async def get_customer_details(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Tab 1: Customer Details — identity, properties, billing, subscriptions, handovers."""
    tid = ctx.tenant_id
    async with get_session() as session:
        customer = await _get_customer_or_404(session, customer_id, tid)
        is_admin = await has_tier(ctx, session, "admin")
        sec = _Sections(session, customer_id)

        async def company():
            if not customer.company_id:
                return None
            comp = (await session.execute(
                select(Company).where(Company.id == customer.company_id, Company.tenant_id == tid)
            )).scalar_one_or_none()
            if not comp:
                return None
            return {
                "id": str(comp.id),
                "name": comp.name,
                "registration_number": comp.registration_number,
                "industry": comp.industry,
                "billing_email": comp.billing_email,
                "payment_terms": comp.payment_terms,
                "credit_limit_zar": float(comp.credit_limit_zar) if comp.credit_limit_zar else None,
            }

        async def properties():
            return [
                PropertyAddress(
                    id=p.id, name=p.name, line1=p.line1, line2=p.line2,
                    city=p.city, province=p.province, postal_code=p.postal_code,
                    property_type=p.property_type, is_active=p.is_active,
                )
                for p in await _rows(session, select(Property).where(
                    Property.owner_customer_id == customer_id, Property.tenant_id == tid))
            ]

        async def property_accounts():
            return [
                PropertyAccountInfo(
                    id=pa.id, account_number=pa.account_number,
                    relationship_type=pa.relationship_type, is_primary=pa.is_primary,
                    is_active=pa.is_active, activated_at=pa.activated_at, company_id=pa.company_id,
                )
                for pa in await _rows(session, select(PropertyAccount).where(
                    PropertyAccount.customer_id == customer_id, PropertyAccount.tenant_id == tid))
            ]

        async def service_addresses():
            return [
                ServiceAddressInfo(
                    id=a.id, address_type=a.address_type, line1=a.line1,
                    city=a.city, postal_code=a.postal_code, is_primary=a.is_primary,
                )
                for a in await _rows(session, select(CustomerAddress).where(
                    CustomerAddress.customer_id == customer_id, CustomerAddress.tenant_id == tid))
            ]

        async def billing_account():
            ba = (await session.execute(select(BillingAccount).where(
                BillingAccount.customer_id == customer_id, BillingAccount.tenant_id == tid,
            ).limit(1))).scalar_one_or_none()
            if not ba:
                return None
            return BillingAccountInfo(
                id=ba.id, account_number=ba.account_number, account_name=ba.account_name,
                billing_email=ba.billing_email, payment_terms=ba.payment_terms,
                credit_limit_zar=ba.credit_limit_zar, status=ba.status, dunning_stage=ba.dunning_stage,
            )

        async def subscriptions():
            return [
                SubscriptionInfo(
                    id=s.id, plan=s.plan, segment=s.segment, status=s.status,
                    billing_interval=s.billing_interval, base_price_zar=s.base_price_zar,
                    property_id=s.property_id,
                )
                for s in await _rows(session, select(Subscription).where(
                    Subscription.customer_id == customer_id, Subscription.tenant_id == tid))
            ]

        async def payment_methods():
            return [
                PaymentMethodInfo(
                    id=pm.id, method_type=pm.method_type, last_four=pm.last_four,
                    card_brand=pm.card_brand, is_default=pm.is_default, is_active=pm.is_active,
                )
                for pm in await _rows(session, select(PaymentMethod).where(
                    PaymentMethod.customer_id == customer_id, PaymentMethod.tenant_id == tid))
            ]

        async def handovers():
            return [
                HandoverHistoryItem(
                    id=h.id, property_id=h.property_id,
                    from_customer_id=h.from_customer_id, to_customer_id=h.to_customer_id,
                    status=h.status, trigger=h.trigger, completed_at=h.completed_at,
                )
                for h in await _rows(session, select(AccountHandover).where(
                    AccountHandover.tenant_id == tid,
                    (AccountHandover.from_customer_id == customer_id)
                    | (AccountHandover.to_customer_id == customer_id),
                ).order_by(AccountHandover.created_at.desc(), AccountHandover.id).limit(50))
            ]

        company_data = await sec.run("company", company)
        props = await sec.run("properties", properties)
        prop_accounts = await sec.run("property_accounts", property_accounts)
        addresses = await sec.run("service_addresses", service_addresses)
        billing = await sec.run("billing_account", billing_account)
        subs = await sec.run("subscriptions", subscriptions)
        methods = await sec.run("payment_methods", payment_methods)
        handover_history = await sec.run("handover_history", handovers)

        customer_view = CustomerRead(**redact_customer(
            CustomerRead.model_validate(customer).model_dump(), is_admin))

    return CustomerDetailsResponse(
        customer=customer_view,
        company=company_data,
        properties=props,
        property_accounts=prop_accounts,
        service_addresses=addresses,
        billing_account=billing,
        subscriptions=subs,
        payment_methods=methods,
        handover_history=handover_history,
        partial=sec.partial,
        section_errors=sec.errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2: Customer Experience (CX)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}/360/cx", response_model=CXResponse)
async def get_customer_cx(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    timeline_limit: int = Query(50, ge=1, le=200),
):
    """Tab 2: Customer Experience — orders, deliveries, visits, tickets, timeline."""
    tid = ctx.tenant_id
    async with get_session() as session:
        customer = await _get_customer_or_404(session, customer_id, tid)
        sec = _Sections(session, customer_id)

        async def orders_():
            return [
                OrderSummary(
                    id=o.id, order_number=o.order_number, status=o.status,
                    total_zar=o.total_zar, payment_status=o.payment_status,
                    confirmed_at=o.confirmed_at, completed_at=o.completed_at,
                )
                for o in await _rows(session, select(Order).where(
                    Order.customer_id == customer_id, Order.tenant_id == tid,
                ).order_by(Order.created_at.desc(), Order.id).limit(50))
            ]

        orders = await sec.run("orders", orders_)

        async def deliveries_():
            if not orders:
                return []
            return [
                DeliverySummary(
                    id=d.id, order_id=d.order_id, courier=d.courier,
                    tracking_number=d.tracking_number, status=d.status,
                    scheduled_date=d.scheduled_date, delivered_at=d.delivered_at,
                )
                for d in await _rows(session, select(DeliveryTracking).where(
                    DeliveryTracking.tenant_id == tid,
                    DeliveryTracking.order_id.in_([o.id for o in orders]),
                ).order_by(DeliveryTracking.created_at.desc(), DeliveryTracking.id).limit(50))
            ]

        async def visits_():
            return [
                TechnicianVisitSummary(
                    id=v.id, visit_type=v.visit_type, status=v.status,
                    scheduled_date=v.scheduled_date, technician_name=v.technician_name,
                    customer_rating=v.customer_rating,
                )
                for v in await _rows(session, select(TechnicianVisit).where(
                    TechnicianVisit.customer_id == customer_id, TechnicianVisit.tenant_id == tid,
                ).order_by(TechnicianVisit.scheduled_date.desc(), TechnicianVisit.id).limit(50))
            ]

        async def tickets_():
            return [
                SupportTicketSummary(
                    id=t.id, subject=t.subject, priority=t.priority, status=t.status,
                    category=t.category, is_fcr=t.is_fcr, created_at=t.created_at,
                    resolved_at=t.resolved_at,
                )
                for t in await _rows(session, select(Ticket).where(
                    Ticket.customer_id == customer_id, Ticket.tenant_id == tid,
                ).order_by(Ticket.created_at.desc(), Ticket.id).limit(50))
            ]

        async def timeline_():
            return [
                ActivityTimelineItem(
                    id=at.id, event_type=at.event_type, event_category=at.event_category,
                    summary=at.summary, source_service=at.source_service, created_at=at.created_at,
                )
                for at in await _rows(session, select(ActivityTimeline).where(
                    ActivityTimeline.customer_id == customer_id, ActivityTimeline.tenant_id == tid,
                ).order_by(ActivityTimeline.created_at.desc(), ActivityTimeline.id).limit(timeline_limit))
            ]

        async def nps_():
            contact = (await session.execute(select(Contact).where(
                Contact.tenant_id == tid, Contact.id == customer_id).limit(1))).scalar_one_or_none()
            if not contact and customer.email:
                contact = (await session.execute(select(Contact).where(
                    Contact.tenant_id == tid, Contact.email == customer.email).limit(1))).scalar_one_or_none()
            return {"nps": contact.nps_score if contact else None}

        async def lifecycle_():
            lc = (await session.execute(select(CustomerLifecycle).where(
                CustomerLifecycle.customer_id == customer_id,
                CustomerLifecycle.tenant_id == tid))).scalar_one_or_none()
            return {"stage": lc.current_stage if lc else None}

        deliveries = await sec.run("deliveries", deliveries_) if orders is not None else None
        if orders is None:
            sec.errors.setdefault("deliveries", "depends_on_orders")
        visits = await sec.run("technician_visits", visits_)
        tickets = await sec.run("support_tickets", tickets_)
        timeline = await sec.run("activity_timeline", timeline_)
        nps = await sec.run("nps", nps_)
        lc_info = await sec.run("lifecycle", lifecycle_)

        ratings = [v.customer_rating for v in (visits or []) if v.customer_rating is not None]

    return CXResponse(
        orders=orders,
        deliveries=deliveries,
        technician_visits=visits,
        support_tickets=tickets,
        activity_timeline=timeline,
        nps_score=nps["nps"] if nps else None,
        cx_summary=CXSummary(
            total_orders=len(orders) if orders is not None else None,
            open_tickets=(sum(1 for t in tickets if (t.status or "").upper() == "OPEN")
                          if tickets is not None else None),
            avg_technician_rating=(sum(ratings) / len(ratings)) if ratings else None,
            last_interaction=timeline[0].created_at if timeline else None,
            lifecycle_stage=lc_info["stage"] if lc_info else None,
        ),
        partial=sec.partial,
        section_errors=sec.errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3: CRM
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}/360/crm", response_model=CRMResponse)
async def get_customer_crm(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Tab 3: CRM — sales pipeline, deals, quotes, commissions, lifecycle."""
    tid = ctx.tenant_id
    async with get_session() as session:
        await _get_customer_or_404(session, customer_id, tid)
        sec = _Sections(session, customer_id)

        async def lead_():
            lead = (await session.execute(select(Lead).where(
                Lead.converted_customer_id == customer_id, Lead.tenant_id == tid,
            ).limit(1))).scalar_one_or_none()
            if not lead:
                return None
            converted_at_val = getattr(lead, "converted_at", None)
            return {
                "id": str(lead.id),
                "source": lead.source,
                "status": lead.status,
                "coverage_area": lead.coverage_area,
                "interested_package": lead.interested_package,
                "converted_at": converted_at_val.isoformat() if converted_at_val else None,
            }

        async def deals_():
            out = []
            rows = (await session.execute(
                select(Deal, DealStage.name.label("stage_name"), DealStage.probability)
                .outerjoin(DealStage, Deal.stage_id == DealStage.id)
                .where(Deal.tenant_id == tid, Deal.contact_id == customer_id)
                .order_by(Deal.created_at.desc(), Deal.id).limit(50)
            )).all()
            for deal, stage_name, probability in rows:
                out.append((DealSummary(
                    id=deal.id, name=deal.name, value_zar=deal.value_zar, status=deal.status,
                    stage_name=stage_name, probability=probability, close_date=deal.close_date,
                ), deal.value_zar or Decimal("0")))
            return out

        async def quotes_():
            return [
                QuoteSummary(
                    id=q.id, total_monthly=q.total_monthly, total_once_off=q.total_once_off,
                    term_months=q.term_months, status=q.status, valid_until=q.valid_until,
                    sent_at=q.sent_at, accepted_at=q.accepted_at,
                )
                for q in await _rows(session, select(Quote).where(
                    Quote.customer_id == customer_id, Quote.tenant_id == tid,
                ).order_by(Quote.created_at.desc(), Quote.id).limit(50))
            ]

        lead_data = await sec.run("lead", lead_)
        deal_rows = await sec.run("deals", deals_)
        deals = [d for d, _ in deal_rows] if deal_rows is not None else None
        quotes = await sec.run("quotes", quotes_)

        async def commissions_():
            deal_ids = [d.id for d in deals or []]
            if not deal_ids:
                return []
            return [
                CommissionSummary(
                    id=c.id, agent_id=c.agent_id, amount_zar=c.amount_zar,
                    rate_percent=c.rate_percent, status=c.status,
                )
                for c in await _rows(session, select(Commission).where(
                    Commission.tenant_id == tid, Commission.deal_id.in_(deal_ids),
                ).order_by(Commission.created_at.desc(), Commission.id).limit(50))
            ]

        async def tags_():
            return [row[0] for row in (await session.execute(select(CustomerTag.tag).where(
                CustomerTag.customer_id == customer_id, CustomerTag.tenant_id == tid))).all()]

        async def notes_():
            return [
                {"id": str(n.id), "content": n.content, "author_id": str(n.author_id),
                 "created_at": n.created_at.isoformat()}
                for n in await _rows(session, select(CustomerNote).where(
                    CustomerNote.customer_id == customer_id, CustomerNote.tenant_id == tid,
                ).order_by(CustomerNote.created_at.desc(), CustomerNote.id).limit(50))
            ]

        async def lifecycle_():
            lc = (await session.execute(select(CustomerLifecycle).where(
                CustomerLifecycle.customer_id == customer_id,
                CustomerLifecycle.tenant_id == tid))).scalar_one_or_none()
            if not lc:
                return None
            return LifecycleInfo(
                current_stage=lc.current_stage, health_score=lc.health_score, is_at_risk=lc.is_at_risk,
                churn_probability=lc.churn_probability, monthly_recurring_revenue=lc.monthly_recurring_revenue,
                first_contact_at=lc.first_contact_at, converted_at=lc.converted_at,
                last_payment_at=lc.last_payment_at,
            )

        commissions = await sec.run("commissions", commissions_)
        tags = await sec.run("tags", tags_)
        notes = await sec.run("notes", notes_)
        lifecycle = await sec.run("lifecycle", lifecycle_)

    deal_rows = deal_rows or []
    statuses = [(d.status or "").upper() for d, _ in deal_rows]
    return CRMResponse(
        lead=lead_data,
        deals=deals,
        quotes=quotes,
        commissions=commissions,
        segments=[],  # populated by segment service
        tags=tags,
        notes=notes,
        lifecycle=lifecycle,
        crm_summary=CRMSummary(
            total_deals_value=sum((v for _, v in deal_rows), Decimal("0")),
            active_deals=statuses.count("OPEN"),
            won_deals=statuses.count("WON"),
            lost_deals=statuses.count("LOST"),
            quotes_sent=len(quotes or []),
            quotes_accepted=sum(1 for q in quotes or [] if (q.status or "").upper() == "ACCEPTED"),
        ),
        partial=sec.partial,
        section_errors=sec.errors,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4: Customer Value Management (CVM)
# ─────────────────────────────────────────────────────────────────────────────

NOT_ASSESSED = "NOT_ASSESSED"


def build_cvm_summary(mrr: Decimal, ltv: Decimal, total_invoices: int, active_subs: int,
                      churn_prob: Optional[Decimal]) -> "CVMSummary":
    """Tier / segments / recommended action. With no subscription and no invoice there is nothing
    to assess, so the summary says NOT_ASSESSED instead of a made-up BRONZE / CROSS_SELL."""
    risk_seg = _compute_risk_segment(churn_prob)
    if total_invoices == 0 and active_subs == 0:
        return CVMSummary(customer_tier=NOT_ASSESSED, value_segment=NOT_ASSESSED,
                          risk_segment=risk_seg, recommended_action=None)
    value_seg = _compute_value_segment(mrr)
    recommended = None
    if risk_seg in ("CRITICAL", "HIGH"):
        recommended = "RETENTION_OUTREACH"
    elif value_seg == "HIGH" and risk_seg == "LOW":
        recommended = "UPSELL"
    elif value_seg == "STANDARD" and total_invoices > 0:
        recommended = "CROSS_SELL"
    return CVMSummary(customer_tier=_compute_tier(mrr, ltv), value_segment=value_seg,
                      risk_segment=risk_seg, recommended_action=recommended)


@router.get("/{customer_id}/360/cvm", response_model=CVMResponse)
async def get_customer_cvm(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Tab 4: Customer Value Management — financial, churn, health, usage."""
    tid = ctx.tenant_id
    async with get_session() as session:
        await _get_customer_or_404(session, customer_id, tid)
        sec = _Sections(session, customer_id)

        async def subs_():
            row = (await session.execute(
                select(func.coalesce(func.sum(Subscription.base_price_zar), 0), func.count(Subscription.id))
                .where(Subscription.customer_id == customer_id, Subscription.tenant_id == tid,
                       Subscription.status.in_(["active", "trial"]))
            )).one()
            return {"mrr": Decimal(row[0] or 0), "count": int(row[1] or 0)}

        async def invoices_():
            # SQL aggregates over ALL of the customer's invoices (not just the latest 100).
            paid = Invoice.status == "paid"
            agg = (await session.execute(
                select(
                    func.count(Invoice.id),
                    func.coalesce(func.sum(case((paid, Invoice.total_zar), else_=0)), 0),
                    func.coalesce(func.sum(case(
                        (Invoice.status.notin_(["paid", "voided"]), Invoice.total_zar - Invoice.amount_paid_zar),
                        else_=0)), 0),
                    func.count(case((paid, 1))),
                    func.count(case((Invoice.status == "overdue", 1))),
                ).where(Invoice.customer_id == customer_id, Invoice.tenant_id == tid)
            )).one()
            recent = await _rows(session, select(Invoice).where(
                Invoice.customer_id == customer_id, Invoice.tenant_id == tid,
            ).order_by(Invoice.created_at.desc(), Invoice.id).limit(20))
            return {"agg": agg, "recent": recent}

        async def payments_():
            return [
                PaymentSummary(id=p.id, amount_zar=p.amount_zar, method=p.method,
                               status=p.status, created_at=p.created_at)
                for p in await _rows(session, select(Payment).where(
                    Payment.customer_id == customer_id, Payment.tenant_id == tid,
                ).order_by(Payment.created_at.desc(), Payment.id).limit(50))
            ]

        async def churn_():
            pred = (await session.execute(select(RetentionPrediction).where(
                RetentionPrediction.customer_id == customer_id, RetentionPrediction.tenant_id == tid,
            ).order_by(RetentionPrediction.created_at.desc()).limit(1))).scalar_one_or_none()
            if not pred:
                return None
            return ChurnPredictionInfo(
                risk_score=pred.risk_score, risk_level=pred.risk_level,
                churn_probability=pred.churn_probability, nps_score=pred.nps_score,
                predicted_at=pred.created_at)

        async def health_():
            lc = (await session.execute(select(CustomerLifecycle).where(
                CustomerLifecycle.customer_id == customer_id,
                CustomerLifecycle.tenant_id == tid))).scalar_one_or_none()
            if not lc:
                return None
            return {
                "health": HealthInfo(
                    score=lc.health_score, is_at_risk=lc.is_at_risk, risk_reason=lc.risk_reason,
                    monthly_recurring_revenue=lc.monthly_recurring_revenue,
                    first_payment_at=lc.first_payment_at, last_payment_at=lc.last_payment_at),
                "churn": lc.churn_probability,
            }

        async def usage_():
            rows = (await session.execute(
                select(
                    SubscriptionUsage.metric,
                    func.sum(SubscriptionUsage.quantity).label("total_quantity"),
                    func.sum(SubscriptionUsage.quantity * SubscriptionUsage.unit_price_zar).label("total_cost"),
                    func.max(SubscriptionUsage.recorded_at).label("last_recorded"),
                )
                .join(Subscription, SubscriptionUsage.subscription_id == Subscription.id)
                .where(Subscription.customer_id == customer_id, Subscription.tenant_id == tid)
                .group_by(SubscriptionUsage.metric)
                .order_by(func.sum(SubscriptionUsage.quantity).desc())
            )).all()
            return [
                {"metric": r[0], "total_quantity": float(r[1] or 0), "total_cost_zar": float(r[2] or 0),
                 "last_recorded": r[3].isoformat() if r[3] else None}
                for r in rows
            ]

        subs = await sec.run("subscriptions", subs_)
        inv = await sec.run("invoices", invoices_)
        payments = await sec.run("payments", payments_)
        churn_prediction = await sec.run("churn_prediction", churn_)
        health_row = await sec.run("health", health_)
        usage_summary = await sec.run("usage", usage_)

    mrr = subs["mrr"] if subs else None
    financial = None
    if subs is not None or inv is not None:
        total_inv = paid_inv = overdue_inv = 0
        ltv = outstanding = None
        if inv is not None:
            total_inv, ltv_raw, out_raw, paid_inv, overdue_inv = inv["agg"]
            ltv, outstanding = Decimal(ltv_raw or 0), Decimal(out_raw or 0)
        financial = FinancialSummary(
            mrr=mrr, arr=(mrr * Decimal("12")) if mrr is not None else None,
            ltv=ltv, outstanding_balance=outstanding,
            payment_reliability_pct=round(paid_inv / total_inv * 100, 1) if total_inv else None,
            total_invoices=total_inv if inv is not None else None,
            paid_invoices=paid_inv if inv is not None else None,
            overdue_invoices=overdue_inv if inv is not None else None,
        )

    cvm_summary = None
    if subs is not None and inv is not None:
        cvm_summary = build_cvm_summary(
            mrr, financial.ltv, financial.total_invoices, subs["count"],
            health_row["churn"] if health_row else None)

    return CVMResponse(
        financial_summary=financial,
        invoices=[
            InvoiceSummary(id=i.id, number=i.number, status=i.status, total_zar=i.total_zar,
                           amount_paid_zar=i.amount_paid_zar, due_date=i.due_date, created_at=i.created_at)
            for i in inv["recent"]
        ] if inv is not None else None,
        payments=payments,
        churn_prediction=churn_prediction,
        health=health_row["health"] if health_row else None,
        usage_summary=usage_summary,
        cvm_summary=cvm_summary,
        partial=sec.partial,
        section_errors=sec.errors,
    )
