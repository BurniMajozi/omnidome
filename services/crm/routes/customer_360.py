"""Customer 360 View routes — four-tab aggregation endpoints.

Aggregates data from CRM, Billing, Journey, Sales, Support, Lifecycle, and Retention
services via direct cross-service DB reads (all services share the same Supabase Postgres).

Endpoints:
  GET /customers/{id}/360/details  — Tab 1: Customer Details
  GET /customers/{id}/360/cx       — Tab 2: Customer Experience
  GET /customers/{id}/360/crm      — Tab 3: CRM (sales pipeline)
  GET /customers/{id}/360/cvm      — Tab 4: Customer Value Management
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
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
)
from services.crm.schemas import (
    BillingAccountInfo,
    CRMResponse,
    CRMSummary,
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
from services.retention.batch_churn import RetentionPrediction

router = APIRouter(prefix="/customers", tags=["Customer 360"])


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
# Tab 1: Customer Details
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}/360/details", response_model=CustomerDetailsResponse)
async def get_customer_details(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Tab 1: Customer Details — identity, properties, billing, subscriptions, handovers."""
    async with get_session() as session:
        customer = await _get_customer_or_404(session, customer_id, ctx.tenant_id)

        # Company
        company_data = None
        if customer.company_id:
            comp_result = await session.execute(
                select(Company).where(Company.id == customer.company_id)
            )
            comp = comp_result.scalar_one_or_none()
            if comp:
                company_data = {
                    "id": str(comp.id),
                    "name": comp.name,
                    "registration_number": comp.registration_number,
                    "industry": comp.industry,
                    "billing_email": comp.billing_email,
                    "payment_terms": comp.payment_terms,
                    "credit_limit_zar": float(comp.credit_limit_zar) if comp.credit_limit_zar else None,
                }

        # Properties (owned by this customer)
        props_result = await session.execute(
            select(Property).where(
                Property.owner_customer_id == customer_id,
                Property.tenant_id == ctx.tenant_id,
            )
        )
        properties = [
            PropertyAddress(
                id=p.id, name=p.name, line1=p.line1, line2=p.line2,
                city=p.city, province=p.province, postal_code=p.postal_code,
                property_type=p.property_type, is_active=p.is_active,
            )
            for p in props_result.scalars().all()
        ]

        # Property accounts (customer's service accounts at properties)
        pa_result = await session.execute(
            select(PropertyAccount).where(
                PropertyAccount.customer_id == customer_id,
                PropertyAccount.tenant_id == ctx.tenant_id,
            )
        )
        property_accounts = [
            PropertyAccountInfo(
                id=pa.id, account_number=pa.account_number,
                relationship_type=pa.relationship_type, is_primary=pa.is_primary,
                is_active=pa.is_active, activated_at=pa.activated_at,
                company_id=pa.company_id,
            )
            for pa in pa_result.scalars().all()
        ]

        # Service addresses (from journey service)
        addr_result = await session.execute(
            select(CustomerAddress).where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.tenant_id == ctx.tenant_id,
            )
        )
        service_addresses = [
            ServiceAddressInfo(
                id=a.id, address_type=a.address_type, line1=a.line1,
                city=a.city, postal_code=a.postal_code, is_primary=a.is_primary,
            )
            for a in addr_result.scalars().all()
        ]

        # Billing account
        ba_result = await session.execute(
            select(BillingAccount).where(
                BillingAccount.customer_id == customer_id,
                BillingAccount.tenant_id == ctx.tenant_id,
            )
        )
        ba = ba_result.scalar_one_or_none()
        billing_account = None
        if ba:
            billing_account = BillingAccountInfo(
                id=ba.id, account_number=ba.account_number,
                account_name=ba.account_name, billing_email=ba.billing_email,
                payment_terms=ba.payment_terms,
                credit_limit_zar=ba.credit_limit_zar,
                status=ba.status, dunning_stage=ba.dunning_stage,
            )

        # Subscriptions
        sub_result = await session.execute(
            select(Subscription).where(
                Subscription.customer_id == customer_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )
        subscriptions = [
            SubscriptionInfo(
                id=s.id, plan=s.plan, segment=s.segment, status=s.status,
                billing_interval=s.billing_interval, base_price_zar=s.base_price_zar,
                property_id=s.property_id,
            )
            for s in sub_result.scalars().all()
        ]

        # Payment methods
        pm_result = await session.execute(
            select(PaymentMethod).where(
                PaymentMethod.customer_id == customer_id,
                PaymentMethod.tenant_id == ctx.tenant_id,
            )
        )
        payment_methods = [
            PaymentMethodInfo(
                id=pm.id, method_type=pm.method_type, last_four=pm.last_four,
                card_brand=pm.card_brand, is_default=pm.is_default, is_active=pm.is_active,
            )
            for pm in pm_result.scalars().all()
        ]

        # Handover history
        ho_result = await session.execute(
            select(AccountHandover).where(
                AccountHandover.tenant_id == ctx.tenant_id,
                (AccountHandover.from_customer_id == customer_id) |
                (AccountHandover.to_customer_id == customer_id),
            ).order_by(AccountHandover.created_at.desc()).limit(50)
        )
        handover_history = [
            HandoverHistoryItem(
                id=h.id, property_id=h.property_id,
                from_customer_id=h.from_customer_id, to_customer_id=h.to_customer_id,
                status=h.status, trigger=h.trigger, completed_at=h.completed_at,
            )
            for h in ho_result.scalars().all()
        ]

    return CustomerDetailsResponse(
        customer=CustomerRead.model_validate(customer),
        company=company_data,
        properties=properties,
        property_accounts=property_accounts,
        service_addresses=service_addresses,
        billing_account=billing_account,
        subscriptions=subscriptions,
        payment_methods=payment_methods,
        handover_history=handover_history,
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
    async with get_session() as session:
        await _get_customer_or_404(session, customer_id, ctx.tenant_id)

        # Orders
        orders_result = await session.execute(
            select(Order).where(
                Order.customer_id == customer_id,
                Order.tenant_id == ctx.tenant_id,
            ).order_by(Order.created_at.desc()).limit(50)
        )
        orders = [
            OrderSummary(
                id=o.id, order_number=o.order_number, status=o.status,
                total_zar=o.total_zar, payment_status=o.payment_status,
                confirmed_at=o.confirmed_at, completed_at=o.completed_at,
            )
            for o in orders_result.scalars().all()
        ]

        # Deliveries
        deliveries_result = await session.execute(
            select(DeliveryTracking).where(
                DeliveryTracking.tenant_id == ctx.tenant_id,
            ).where(
                DeliveryTracking.order_id.in_([o.id for o in orders])
            ).order_by(DeliveryTracking.created_at.desc()).limit(50)
        )
        deliveries = [
            DeliverySummary(
                id=d.id, order_id=d.order_id, courier=d.courier,
                tracking_number=d.tracking_number, status=d.status,
                scheduled_date=d.scheduled_date, delivered_at=d.delivered_at,
            )
            for d in deliveries_result.scalars().all()
        ]

        # Technician visits
        visits_result = await session.execute(
            select(TechnicianVisit).where(
                TechnicianVisit.customer_id == customer_id,
                TechnicianVisit.tenant_id == ctx.tenant_id,
            ).order_by(TechnicianVisit.scheduled_date.desc()).limit(50)
        )
        visits = [
            TechnicianVisitSummary(
                id=v.id, visit_type=v.visit_type, status=v.status,
                scheduled_date=v.scheduled_date, technician_name=v.technician_name,
                customer_rating=v.customer_rating,
            )
            for v in visits_result.scalars().all()
        ]

        # Support tickets
        tickets_result = await session.execute(
            select(Ticket).where(
                Ticket.customer_id == customer_id,
                Ticket.tenant_id == ctx.tenant_id,
            ).order_by(Ticket.created_at.desc()).limit(50)
        )
        tickets = [
            SupportTicketSummary(
                id=t.id, subject=t.subject, priority=t.priority, status=t.status,
                category=t.category, is_fcr=t.is_fcr, created_at=t.created_at,
                resolved_at=t.resolved_at,
            )
            for t in tickets_result.scalars().all()
        ]

        # Activity timeline
        timeline_result = await session.execute(
            select(ActivityTimeline).where(
                ActivityTimeline.customer_id == customer_id,
                ActivityTimeline.tenant_id == ctx.tenant_id,
            ).order_by(ActivityTimeline.created_at.desc()).limit(timeline_limit)
        )
        timeline = [
            ActivityTimelineItem(
                id=at.id, event_type=at.event_type, event_category=at.event_category,
                summary=at.summary, source_service=at.source_service,
                created_at=at.created_at,
            )
            for at in timeline_result.scalars().all()
        ]

        # NPS score from contacts
        contact_result = await session.execute(
            select(Contact).where(
                Contact.tenant_id == ctx.tenant_id,
            ).order_by(Contact.created_at.desc()).limit(1)
        )
        contact = contact_result.scalar_one_or_none()
        nps_score = contact.nps_score if contact else None

        # CX summary
        open_tickets = sum(1 for t in tickets if t.status == "OPEN")
        ratings = [v.customer_rating for v in visits if v.customer_rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        # Lifecycle stage
        lc_result = await session.execute(
            select(CustomerLifecycle).where(
                CustomerLifecycle.customer_id == customer_id,
                CustomerLifecycle.tenant_id == ctx.tenant_id,
            )
        )
        lc = lc_result.scalar_one_or_none()
        lifecycle_stage = lc.current_stage if lc else None

        last_interaction = None
        if timeline:
            last_interaction = timeline[0].created_at

    return CXResponse(
        orders=orders,
        deliveries=deliveries,
        technician_visits=visits,
        support_tickets=tickets,
        activity_timeline=timeline,
        nps_score=nps_score,
        cx_summary=CXSummary(
            total_orders=len(orders),
            open_tickets=open_tickets,
            avg_technician_rating=avg_rating,
            last_interaction=last_interaction,
            lifecycle_stage=lifecycle_stage,
        ),
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
    async with get_session() as session:
        await _get_customer_or_404(session, customer_id, ctx.tenant_id)

        # Lead (converted to this customer)
        lead_result = await session.execute(
            select(Lead).where(
                Lead.converted_customer_id == customer_id,
                Lead.tenant_id == ctx.tenant_id,
            )
        )
        lead = lead_result.scalar_one_or_none()
        lead_data = None
        if lead:
            lead_data = {
                "id": str(lead.id),
                "source": lead.source,
                "status": lead.status,
                "coverage_area": lead.coverage_area,
                "interested_package": lead.interested_package,
                "converted_at": lead.converted_at.isoformat() if lead.converted_at else None,
            }

        # Deals (via contact → customer link)
        deals_result = await session.execute(
            select(Deal, DealStage.name.label("stage_name"), DealStage.probability)
            .outerjoin(DealStage, Deal.stage_id == DealStage.id)
            .where(Deal.tenant_id == ctx.tenant_id)
            .order_by(Deal.created_at.desc()).limit(50)
        )
        deals = []
        total_value = Decimal("0")
        active_count = won_count = lost_count = 0
        for row in deals_result.all():
            deal, stage_name, probability = row
            deals.append(DealSummary(
                id=deal.id, name=deal.name, value_zar=deal.value_zar,
                status=deal.status, stage_name=stage_name,
                probability=probability, close_date=deal.close_date,
            ))
            total_value += deal.value_zar or Decimal("0")
            if deal.status == "OPEN":
                active_count += 1
            elif deal.status == "WON":
                won_count += 1
            elif deal.status == "LOST":
                lost_count += 1

        # Quotes
        quotes_result = await session.execute(
            select(Quote).where(
                Quote.customer_id == customer_id,
                Quote.tenant_id == ctx.tenant_id,
            ).order_by(Quote.created_at.desc()).limit(50)
        )
        quotes = [
            QuoteSummary(
                id=q.id, total_monthly=q.total_monthly, total_once_off=q.total_once_off,
                term_months=q.term_months, status=q.status, valid_until=q.valid_until,
                sent_at=q.sent_at, accepted_at=q.accepted_at,
            )
            for q in quotes_result.scalars().all()
        ]

        # Commissions
        comm_result = await session.execute(
            select(Commission).where(
                Commission.tenant_id == ctx.tenant_id,
            ).order_by(Commission.created_at.desc()).limit(50)
        )
        commissions = [
            CommissionSummary(
                id=c.id, agent_id=c.agent_id, amount_zar=c.amount_zar,
                rate_percent=c.rate_percent, status=c.status,
            )
            for c in comm_result.scalars().all()
        ]

        # Tags
        tags_result = await session.execute(
            select(CustomerTag.tag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
            )
        )
        tags = [row[0] for row in tags_result.all()]

        # Notes
        notes_result = await session.execute(
            select(CustomerNote).where(
                CustomerNote.customer_id == customer_id,
                CustomerNote.tenant_id == ctx.tenant_id,
            ).order_by(CustomerNote.created_at.desc()).limit(50)
        )
        notes = [
            {"id": str(n.id), "content": n.content, "author_id": str(n.author_id), "created_at": n.created_at.isoformat()}
            for n in notes_result.scalars().all()
        ]

        # Lifecycle
        lc_result = await session.execute(
            select(CustomerLifecycle).where(
                CustomerLifecycle.customer_id == customer_id,
                CustomerLifecycle.tenant_id == ctx.tenant_id,
            )
        )
        lc = lc_result.scalar_one_or_none()
        lifecycle = None
        if lc:
            lifecycle = LifecycleInfo(
                current_stage=lc.current_stage,
                health_score=lc.health_score,
                is_at_risk=lc.is_at_risk,
                churn_probability=lc.churn_probability,
                monthly_recurring_revenue=lc.monthly_recurring_revenue,
                first_contact_at=lc.first_contact_at,
                converted_at=lc.converted_at,
                last_payment_at=lc.last_payment_at,
            )

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
            total_deals_value=total_value,
            active_deals=active_count,
            won_deals=won_count,
            lost_deals=lost_count,
            quotes_sent=len(quotes),
            quotes_accepted=sum(1 for q in quotes if q.status == "ACCEPTED"),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4: Customer Value Management (CVM)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{customer_id}/360/cvm", response_model=CVMResponse)
async def get_customer_cvm(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Tab 4: Customer Value Management — financial, churn, health, usage."""
    async with get_session() as session:
        await _get_customer_or_404(session, customer_id, ctx.tenant_id)

        # Subscriptions → MRR
        subs_result = await session.execute(
            select(Subscription).where(
                Subscription.customer_id == customer_id,
                Subscription.tenant_id == ctx.tenant_id,
                Subscription.status.in_(["active", "trial"]),
            )
        )
        active_subs = subs_result.scalars().all()
        mrr = sum(s.base_price_zar for s in active_subs)
        arr = mrr * Decimal("12")

        # Invoices → LTV, outstanding, reliability
        inv_result = await session.execute(
            select(Invoice).where(
                Invoice.customer_id == customer_id,
                Invoice.tenant_id == ctx.tenant_id,
            ).order_by(Invoice.created_at.desc()).limit(100)
        )
        invoices = inv_result.scalars().all()
        ltv = sum(i.total_zar for i in invoices if i.status == "paid")
        outstanding = sum(
            i.total_zar - i.amount_paid_zar
            for i in invoices
            if i.status not in ("paid", "voided")
        )
        total_inv = len(invoices)
        paid_inv = sum(1 for i in invoices if i.status == "paid")
        overdue_inv = sum(1 for i in invoices if i.status == "overdue")
        reliability = (paid_inv / total_inv * 100) if total_inv > 0 else 100.0

        # Payments
        pay_result = await session.execute(
            select(Payment).where(
                Payment.customer_id == customer_id,
                Payment.tenant_id == ctx.tenant_id,
            ).order_by(Payment.created_at.desc()).limit(50)
        )
        payments = [
            PaymentSummary(
                id=p.id, amount_zar=p.amount_zar, method=p.method,
                status=p.status, created_at=p.created_at,
            )
            for p in pay_result.scalars().all()
        ]

        # Churn prediction (latest)
        pred_result = await session.execute(
            select(RetentionPrediction).where(
                RetentionPrediction.customer_id == customer_id,
                RetentionPrediction.tenant_id == ctx.tenant_id,
            ).order_by(RetentionPrediction.created_at.desc()).limit(1)
        )
        pred = pred_result.scalar_one_or_none()
        churn_prediction = None
        if pred:
            churn_prediction = ChurnPredictionInfo(
                risk_score=pred.risk_score,
                risk_level=pred.risk_level,
                churn_probability=pred.churn_probability,
                nps_score=pred.nps_score,
                predicted_at=pred.created_at,
            )

        # Lifecycle health
        lc_result = await session.execute(
            select(CustomerLifecycle).where(
                CustomerLifecycle.customer_id == customer_id,
                CustomerLifecycle.tenant_id == ctx.tenant_id,
            )
        )
        lc = lc_result.scalar_one_or_none()
        health = HealthInfo()
        churn_prob = None
        if lc:
            health = HealthInfo(
                score=lc.health_score,
                is_at_risk=lc.is_at_risk,
                risk_reason=lc.risk_reason,
                monthly_recurring_revenue=lc.monthly_recurring_revenue,
                first_payment_at=lc.first_payment_at,
                last_payment_at=lc.last_payment_at,
            )
            churn_prob = lc.churn_probability

        # Usage summary
        usage_result = await session.execute(
            select(
                SubscriptionUsage.metric,
                func.sum(SubscriptionUsage.quantity).label("total_quantity"),
                func.sum(SubscriptionUsage.quantity * SubscriptionUsage.unit_price_zar).label("total_cost"),
                func.max(SubscriptionUsage.recorded_at).label("last_recorded"),
            )
            .join(Subscription, SubscriptionUsage.subscription_id == Subscription.id)
            .where(Subscription.customer_id == customer_id)
            .group_by(SubscriptionUsage.metric)
            .order_by(func.sum(SubscriptionUsage.quantity).desc())
        )
        usage_summary = [
            {
                "metric": row[0],
                "total_quantity": float(row[1]),
                "total_cost_zar": float(row[2]),
                "last_recorded": row[3].isoformat() if row[3] else None,
            }
            for row in usage_result.all()
        ]

        # CVM summary
        tier = _compute_tier(mrr, ltv)
        value_seg = _compute_value_segment(mrr)
        risk_seg = _compute_risk_segment(churn_prob)

        # Recommended action
        recommended = None
        if risk_seg in ("CRITICAL", "HIGH"):
            recommended = "RETENTION_OUTREACH"
        elif value_seg == "HIGH" and risk_seg == "LOW":
            recommended = "UPSELL"
        elif value_seg == "STANDARD":
            recommended = "CROSS_SELL"

    return CVMResponse(
        financial_summary=FinancialSummary(
            mrr=mrr, arr=arr, ltv=ltv, outstanding_balance=outstanding,
            payment_reliability_pct=round(reliability, 1),
            total_invoices=total_inv, paid_invoices=paid_inv, overdue_invoices=overdue_inv,
        ),
        invoices=[
            InvoiceSummary(
                id=i.id, number=i.number, status=i.status, total_zar=i.total_zar,
                amount_paid_zar=i.amount_paid_zar, due_date=i.due_date, created_at=i.created_at,
            )
            for i in invoices[:20]
        ],
        payments=payments,
        churn_prediction=churn_prediction,
        health=health,
        usage_summary=usage_summary,
        cvm_summary=CVMSummary(
            customer_tier=tier,
            value_segment=value_seg,
            risk_segment=risk_seg,
            recommended_action=recommended,
        ),
    )
