"""Customer Journey API routes — coverage, orders, delivery, technician, promotions, announcements."""

import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from services.customer_journey.models import (
    CoverageArea, CustomerAddress, PaymentMethod,
    Order, OrderItem, DeliveryTracking, TechnicianVisit,
    ActivityTimeline, Promotion, CustomerPromotion, Announcement,
    COVERAGE_STATUS, FNO_TECHNOLOGY, ORDER_STATUS, ORDER_ITEM_TYPE,
    DELIVERY_STATUS, TECH_VISIT_STATUS, TECH_VISIT_TYPE,
    PROMO_TYPE, PROMO_STATUS, ANNOUNCEMENT_TYPE, ANNOUNCEMENT_AUDIENCE,
    CONTACT_CHANNEL,
)
from services.customer_journey.database import get_session
from services.common.auth import AuthContext, get_auth_context

logger = logging.getLogger("customer_journey.api")

router = APIRouter(prefix="/journey", tags=["Customer Journey"])


# ════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ════════════════════════════════════════════════════════════════════════

class CoverageCheckRequest(BaseModel):
    address: Optional[str] = None
    postal_code: Optional[str] = None
    gps_lat: Optional[Decimal] = None
    gps_lng: Optional[Decimal] = None


class CoverageAreaResponse(BaseModel):
    id: str
    fno_name: str
    technology: str
    area_name: str
    suburb: Optional[str]
    city: str
    status: str
    max_speed_mbps: int
    available_packages: list
    estimated_install_days: int


class OrderCreateRequest(BaseModel):
    customer_id: uuid.UUID
    service_address_id: Optional[uuid.UUID] = None
    billing_address_id: Optional[uuid.UUID] = None
    items: List["OrderItemRequest"]
    preferred_contact_channel: str = "sms"
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    customer_notes: Optional[str] = None
    promo_code: Optional[str] = None


class OrderItemRequest(BaseModel):
    item_type: str  # package, hardware, vas, installation, delivery
    product_id: Optional[uuid.UUID] = None
    description: str
    quantity: int = 1
    unit_price_zar: Decimal
    package_name: Optional[str] = None
    monthly_recurring_zar: Decimal = Decimal("0.00")
    once_off_zar: Decimal = Decimal("0.00")


class OrderResponse(BaseModel):
    order_id: str
    order_number: str
    status: str
    total_zar: Decimal
    payment_url: Optional[str] = None


class DeliveryTrackResponse(BaseModel):
    order_id: str
    tracking_number: Optional[str]
    courier: Optional[str]
    status: Optional[str]
    scheduled_date: Optional[str]
    estimated_delivery: Optional[str]
    current_location: Optional[dict] = None


class TechVisitScheduleRequest(BaseModel):
    customer_id: uuid.UUID
    order_id: Optional[uuid.UUID] = None
    subscription_id: Optional[uuid.UUID] = None
    ticket_id: Optional[uuid.UUID] = None
    visit_type: str = "installation"
    scheduled_date: date
    scheduled_time_slot: str = "08:00-12:00"
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    postal_code: str
    gps_lat: Optional[Decimal] = None
    gps_lng: Optional[Decimal] = None
    work_description: Optional[str] = None


class TechVisitResponse(BaseModel):
    visit_id: str
    status: str
    scheduled_date: date
    scheduled_time_slot: str
    technician_name: Optional[str] = None
    tracking_url: Optional[str] = None


class TechVisitGPSUpdate(BaseModel):
    visit_id: uuid.UUID
    gps_lat: Decimal
    gps_lng: Decimal
    status: Optional[str] = None


class TechVisitCompleteRequest(BaseModel):
    visit_id: uuid.UUID
    work_completed: str
    parts_used: Optional[list] = None
    customer_rating: Optional[int] = None
    customer_signature_url: Optional[str] = None


class Customer360Response(BaseModel):
    customer_id: str
    account_number: str
    personal_info: dict
    addresses: list
    subscriptions: list
    active_orders: list
    recent_tickets: list
    payment_methods: list
    recent_timeline: list
    lifetime_value_zar: Decimal


# ════════════════════════════════════════════════════════════════════════
# COVERAGE CHECK
# ════════════════════════════════════════════════════════════════════════

@router.post("/coverage-check", response_model=List[CoverageAreaResponse])
async def check_coverage(
    body: CoverageCheckRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Check FNO coverage at an address or GPS coordinate."""
    from sqlalchemy import select, and_, func
    from services.customer_journey.database import get_session

    async with get_session() as session:
        stmt = select(CoverageArea).where(CoverageArea.tenant_id == ctx.tenant_id)

        if body.postal_code:
            stmt = stmt.where(CoverageArea.postal_code == body.postal_code)
        elif body.gps_lat and body.gps_lng:
            # Find nearest coverage area within ~5km
            stmt = stmt.where(
                func.abs(CoverageArea.gps_lat - body.gps_lat) < Decimal("0.05"),
                func.abs(CoverageArea.gps_lng - body.gps_lng) < Decimal("0.05"),
            )
        elif body.address:
            # Search by area name
            stmt = stmt.where(CoverageArea.area_name.ilike(f"%{body.address}%"))

        results = (await session.execute(stmt)).scalars().all()

        return [
            CoverageAreaResponse(
                id=str(r.id),
                fno_name=r.fno_name,
                technology=r.technology,
                area_name=r.area_name,
                suburb=r.suburb,
                city=r.city,
                status=r.status,
                max_speed_mbps=r.max_speed_mbps,
                available_packages=r.available_packages or [],
                estimated_install_days=r.estimated_install_days,
            )
            for r in results
        ]


# ════════════════════════════════════════════════════════════════════════
# ORDERS & CHECKOUT
# ════════════════════════════════════════════════════════════════════════

@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new order (cart → pending → payment)."""
    from services.customer_journey.database import get_session

    async with get_session() as session:
        # Generate order number
        order_num = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

        # Validate promotion
        discount_zar = Decimal("0.00")
        promo_id = None
        if body.promo_code:
            from sqlalchemy import select
            promo = (await session.execute(
                select(Promotion).where(
                    Promotion.promo_code == body.promo_code,
                    Promotion.tenant_id == ctx.tenant_id,
                    Promotion.status == "active",
                )
            )).scalar_one_or_none()
            if promo:
                promo_id = promo.id
                # Calculate discount
                if promo.promo_type == "percentage_discount":
                    subtotal = sum(item.unit_price_zar * item.quantity for item in body.items)
                    pct = Decimal(str(promo.parameters.get("percent", 0))) / 100
                    discount_zar = (subtotal * pct).quantize(Decimal("0.01"))

        # Calculate totals
        subtotal_zar = sum(item.unit_price_zar * item.quantity for item in body.items)
        vat_zar = ((subtotal_zar - discount_zar) * Decimal("0.15")).quantize(Decimal("0.01"))
        total_zar = subtotal_zar - discount_zar + vat_zar

        order = Order(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            account_number="ACC-0001",  # Would come from customer
            order_number=order_num,
            status="pending",
            service_address_id=body.service_address_id,
            billing_address_id=body.billing_address_id,
            subtotal_zar=subtotal_zar,
            vat_zar=vat_zar,
            discount_zar=discount_zar,
            total_zar=total_zar,
            promotion_id=promo_id,
            promo_code=body.promo_code,
            preferred_contact_channel=body.preferred_contact_channel,
            contact_phone=body.contact_phone,
            contact_email=body.contact_email,
            customer_notes=body.customer_notes,
        )
        session.add(order)
        await session.flush()

        # Add order items
        for item in body.items:
            item_total = item.unit_price_zar * item.quantity
            oi = OrderItem(
                order_id=order.id,
                item_type=item.item_type,
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit_price_zar=item.unit_price_zar,
                total_price_zar=item_total,
                package_name=item.package_name,
                monthly_recurring_zar=item.monthly_recurring_zar,
                once_off_zar=item.once_off_zar,
            )
            session.add(oi)

        await session.commit()

        return OrderResponse(
            order_id=str(order.id),
            order_number=order_num,
            status="pending",
            total_zar=total_zar,
        )


@router.post("/orders/{order_id}/confirm")
async def confirm_order(
    order_id: uuid.UUID,
    payment_method_id: Optional[uuid.UUID] = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Confirm order and initiate payment."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        order = (await session.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.status != "pending":
            raise HTTPException(status_code=400, detail=f"Order is {order.status}, cannot confirm")

        order.status = "confirmed"
        order.payment_method_id = payment_method_id
        order.confirmed_at = datetime.utcnow()
        await session.commit()

        # Log to timeline
        timeline = ActivityTimeline(
            tenant_id=ctx.tenant_id,
            customer_id=order.customer_id,
            account_number=order.account_number,
            event_type="order_confirmed",
            event_category="sales",
            summary=f"Order {order.order_number} confirmed. Total: R{order.total_zar}",
            source_service="customer_journey",
            source_id=order.id,
            order_id=order.id,
        )
        session.add(timeline)
        await session.commit()

        return {
            "order_id": str(order_id),
            "order_number": order.order_number,
            "status": "confirmed",
            "total_zar": float(order.total_zar),
            "message": "Order confirmed. Awaiting payment.",
        }


@router.get("/orders/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get full order details with items and delivery status."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        order = (await session.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = (await session.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )).scalars().all()

        delivery = (await session.execute(
            select(DeliveryTracking).where(DeliveryTracking.order_id == order_id)
        ).scalar_one_or_none())

        return {
            "order": {
                "id": str(order.id),
                "order_number": order.order_number,
                "status": order.status,
                "total_zar": float(order.total_zar),
                "discount_zar": float(order.discount_zar),
                "promo_code": order.promo_code,
                "preferred_contact_channel": order.preferred_contact_channel,
            },
            "items": [
                {
                    "description": i.description,
                    "item_type": i.item_type,
                    "quantity": i.quantity,
                    "unit_price_zar": float(i.unit_price_zar),
                    "monthly_recurring_zar": float(i.monthly_recurring_zar),
                    "once_off_zar": float(i.once_off_zar),
                }
                for i in items
            ],
            "delivery": {
                "status": delivery.status if delivery else None,
                "tracking_number": delivery.tracking_number if delivery else None,
                "courier": delivery.courier if delivery else None,
                "scheduled_date": delivery.scheduled_date.isoformat() if delivery and delivery.scheduled_date else None,
                "estimated_delivery": delivery.estimated_delivery.isoformat() if delivery and delivery.estimated_delivery else None,
            } if delivery else None,
        }


# ════════════════════════════════════════════════════════════════════════
# DELIVERY TRACKING
# ════════════════════════════════════════════════════════════════════════

@router.post("/orders/{order_id}/delivery")
async def create_delivery(
    order_id: uuid.UUID,
    courier: str = Query(...),
    scheduled_date: date = Query(...),
    scheduled_time_slot: str = Query("08:00-12:00"),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Schedule delivery for an order."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        order = (await session.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == ctx.tenant_id)
        )).scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Get service address
        addr = None
        if order.service_address_id:
            addr = (await session.execute(
                select(CustomerAddress).where(CustomerAddress.id == order.service_address_id)
            )).scalar_one_or_none()

        delivery = DeliveryTracking(
            tenant_id=ctx.tenant_id,
            order_id=order_id,
            courier=courier,
            tracking_number=f"TRK-{str(uuid.uuid4())[:8].upper()}",
            status="courier_assigned",
            delivery_address_line1=addr.line1 if addr else "TBD",
            delivery_city=addr.city if addr else "TBD",
            delivery_postal_code=addr.postal_code if addr else "0000",
            delivery_gps_lat=addr.gps_lat if addr else None,
            delivery_gps_lng=addr.gps_lng if addr else None,
            scheduled_date=scheduled_date,
            scheduled_time_slot=scheduled_time_slot,
            recipient_name="Customer",  # Would come from customer record
            recipient_phone=order.contact_phone,
        )
        session.add(delivery)

        order.status = "shipped"
        await session.commit()

        return {
            "delivery_id": str(delivery.id),
            "tracking_number": delivery.tracking_number,
            "courier": courier,
            "scheduled_date": scheduled_date.isoformat(),
            "scheduled_time_slot": scheduled_time_slot,
            "status": "courier_assigned",
        }


@router.get("/delivery/{tracking_number}", response_model=DeliveryTrackResponse)
async def track_delivery(
    tracking_number: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Track a delivery by tracking number."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        delivery = (await session.execute(
            select(DeliveryTracking).where(
                DeliveryTracking.tracking_number == tracking_number,
                DeliveryTracking.tenant_id == ctx.tenant_id,
            )
        )).scalar_one_or_none()
        if not delivery:
            raise HTTPException(status_code=404, detail="Tracking number not found")

        return DeliveryTrackResponse(
            order_id=str(delivery.order_id),
            tracking_number=delivery.tracking_number,
            courier=delivery.courier,
            status=delivery.status,
            scheduled_date=delivery.scheduled_date.isoformat() if delivery.scheduled_date else None,
            estimated_delivery=delivery.estimated_delivery.isoformat() if delivery.estimated_delivery else None,
        )


@router.patch("/delivery/{delivery_id}/status")
async def update_delivery_status(
    delivery_id: uuid.UUID,
    new_status: str = Query(...),
    notes: Optional[str] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update delivery status (called by courier webhook or admin)."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        delivery = (await session.execute(
            select(DeliveryTracking).where(
                DeliveryTracking.id == delivery_id,
                DeliveryTracking.tenant_id == ctx.tenant_id,
            )
        )).scalar_one_or_none()
        if not delivery:
            raise HTTPException(status_code=404, detail="Delivery not found")

        delivery.status = new_status
        if notes:
            delivery.delivery_notes = notes

        if new_status == "delivered":
            delivery.delivered_at = datetime.utcnow()
            # Update order status
            order = (await session.execute(
                select(Order).where(Order.id == delivery.order_id)
            )).scalar_one_or_none()
            if order:
                order.status = "delivered"

        await session.commit()
        return {"delivery_id": str(delivery_id), "status": new_status}


# ════════════════════════════════════════════════════════════════════════
# TECHNICIAN VISITS
# ════════════════════════════════════════════════════════════════════════

@router.post("/technician-visits", response_model=TechVisitResponse, status_code=status.HTTP_201_CREATED)
async def schedule_technician_visit(
    body: TechVisitScheduleRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Schedule a technician visit (installation, repair, survey, etc.)."""
    from services.customer_journey.database import get_session

    async with get_session() as session:
        visit = TechnicianVisit(
            tenant_id=ctx.tenant_id,
            customer_id=body.customer_id,
            order_id=body.order_id,
            subscription_id=body.subscription_id,
            ticket_id=body.ticket_id,
            visit_type=body.visit_type,
            status="scheduled",
            scheduled_date=body.scheduled_date,
            scheduled_time_slot=body.scheduled_time_slot,
            address_line1=body.address_line1,
            address_line2=body.address_line2,
            city=body.city,
            postal_code=body.postal_code,
            gps_lat=body.gps_lat,
            gps_lng=body.gps_lng,
            work_description=body.work_description,
        )
        session.add(visit)
        await session.commit()

        return TechVisitResponse(
            visit_id=str(visit.id),
            status="scheduled",
            scheduled_date=body.scheduled_date,
            scheduled_time_slot=body.scheduled_time_slot,
            tracking_url=f"/journey/technician-visits/{visit.id}/track",
        )


@router.get("/technician-visits/{visit_id}")
async def get_technician_visit(
    visit_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get technician visit details with live GPS tracking."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        visit = (await session.execute(
            select(TechnicianVisit).where(
                TechnicianVisit.id == visit_id,
                TechnicianVisit.tenant_id == ctx.tenant_id,
            )
        )).scalar_one_or_none()
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")

        return {
            "visit_id": str(visit.id),
            "visit_type": visit.visit_type,
            "status": visit.status,
            "scheduled_date": visit.scheduled_date.isoformat(),
            "scheduled_time_slot": visit.scheduled_time_slot,
            "technician_name": visit.technician_name,
            "technician_phone": visit.technician_phone,
            "gps": {
                "lat": float(visit.current_gps_lat) if visit.current_gps_lat else None,
                "lng": float(visit.current_gps_lng) if visit.current_gps_lng else None,
                "last_update": visit.last_gps_update.isoformat() if visit.last_gps_update else None,
            },
            "timestamps": {
                "dispatched": visit.dispatch_time.isoformat() if visit.dispatch_time else None,
                "en_route": visit.en_route_time.isoformat() if visit.en_route_time else None,
                "on_site": visit.on_site_time.isoformat() if visit.on_site_time else None,
                "completed": visit.completed_time.isoformat() if visit.completed_time else None,
            },
            "work_completed": visit.work_completed,
            "customer_rating": visit.customer_rating,
        }


@router.post("/technician-visits/{visit_id}/gps")
async def update_technician_gps(
    visit_id: uuid.UUID,
    body: TechVisitGPSUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update technician GPS location (called by mobile app)."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        visit = (await session.execute(
            select(TechnicianVisit).where(TechnicianVisit.id == visit_id)
        )).scalar_one_or_none()
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")

        visit.current_gps_lat = body.gps_lat
        visit.current_gps_lng = body.gps_lng
        visit.last_gps_update = datetime.utcnow()
        if body.status:
            visit.status = body.status
            if body.status == "en_route":
                visit.en_route_time = datetime.utcnow()
            elif body.status == "on_site":
                visit.on_site_time = datetime.utcnow()

        await session.commit()
        return {"visit_id": str(visit_id), "gps_updated": True}


@router.post("/technician-visits/{visit_id}/complete")
async def complete_technician_visit(
    visit_id: uuid.UUID,
    body: TechVisitCompleteRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Complete a technician visit with work details."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        visit = (await session.execute(
            select(TechnicianVisit).where(TechnicianVisit.id == visit_id)
        )).scalar_one_or_none()
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")

        visit.status = "completed"
        visit.completed_time = datetime.utcnow()
        visit.work_completed = body.work_completed
        visit.parts_used = body.parts_used
        visit.customer_rating = body.customer_rating
        visit.customer_signature_url = body.customer_signature_url

        # If installation, update order and subscription
        if visit.visit_type == "installation" and visit.order_id:
            order = (await session.execute(
                select(Order).where(Order.id == visit.order_id)
            )).scalar_one_or_none()
            if order:
                order.status = "installed"
                order.completed_at = datetime.utcnow()

        await session.commit()

        return {
            "visit_id": str(visit_id),
            "status": "completed",
            "completed_at": visit.completed_time.isoformat(),
        }


@router.get("/technician-visits")
async def list_technician_visits(
    status: Optional[str] = Query(None),
    technician_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List technician visits with filters."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        stmt = select(TechnicianVisit).where(TechnicianVisit.tenant_id == ctx.tenant_id)
        if status:
            stmt = stmt.where(TechnicianVisit.status == status)
        if technician_id:
            stmt = stmt.where(TechnicianVisit.technician_id == technician_id)
        if date_from:
            stmt = stmt.where(TechnicianVisit.scheduled_date >= date_from)
        if date_to:
            stmt = stmt.where(TechnicianVisit.scheduled_date <= date_to)

        visits = (await session.execute(stmt.order_by(TechnicianVisit.scheduled_date))).scalars().all()

        return [
            {
                "visit_id": str(v.id),
                "visit_type": v.visit_type,
                "status": v.status,
                "scheduled_date": v.scheduled_date.isoformat(),
                "scheduled_time_slot": v.scheduled_time_slot,
                "technician_name": v.technician_name,
                "customer_id": str(v.customer_id),
            }
            for v in visits
        ]


# ════════════════════════════════════════════════════════════════════════
# PROMOTIONS
# ════════════════════════════════════════════════════════════════════════

@router.post("/promotions", status_code=status.HTTP_201_CREATED)
async def create_promotion(
    name: str = Query(...),
    promo_code: Optional[str] = Query(None),
    promo_type: str = Query(...),
    parameters: str = Query(...),  # JSON string
    valid_from: date = Query(...),
    valid_until: Optional[date] = Query(None),
    max_total_redemptions: Optional[int] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new promotion."""
    import json
    from services.customer_journey.database import get_session

    async with get_session() as session:
        promo = Promotion(
            tenant_id=ctx.tenant_id,
            name=name,
            promo_code=promo_code,
            promo_type=promo_type,
            parameters=json.loads(parameters),
            valid_from=valid_from,
            valid_until=valid_until,
            max_total_redemptions=max_total_redemptions,
        )
        session.add(promo)
        await session.commit()
        return {"promotion_id": str(promo.id), "promo_code": promo_code}


@router.get("/promotions")
async def list_promotions(
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List promotions."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        stmt = select(Promotion).where(Promotion.tenant_id == ctx.tenant_id)
        if status:
            stmt = stmt.where(Promotion.status == status)
        promos = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "promo_code": p.promo_code,
                "type": p.promo_type,
                "status": p.status,
                "valid_from": p.valid_from.isoformat(),
                "valid_until": p.valid_until.isoformat() if p.valid_until else None,
                "redemptions": p.total_redemptions,
            }
            for p in promos
        ]


# ════════════════════════════════════════════════════════════════════════
# ANNOUNCEMENTS
# ════════════════════════════════════════════════════════════════════════

@router.post("/announcements", status_code=status.HTTP_201_CREATED)
async def create_announcement(
    title: str = Query(...),
    body: str = Query(...),
    announcement_type: str = Query("general"),
    audience: str = Query("all"),
    channels: str = Query("sms"),  # comma-separated
    target_areas: Optional[str] = Query(None),  # comma-separated
    target_segments: Optional[str] = Query(None),  # comma-separated
    scheduled_at: Optional[datetime] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create and optionally schedule an announcement."""
    from services.customer_journey.database import get_session

    async with get_session() as session:
        announcement = Announcement(
            tenant_id=ctx.tenant_id,
            title=title,
            body=body,
            announcement_type=announcement_type,
            audience=audience,
            channels=[c.strip() for c in channels.split(",")],
            target_areas=[a.strip() for a in target_areas.split(",")] if target_areas else [],
            target_segments=[s.strip() for s in target_segments.split(",")] if target_segments else [],
            scheduled_at=scheduled_at,
        )
        session.add(announcement)

        # If not scheduled, send immediately
        if not scheduled_at:
            announcement.sent_at = datetime.utcnow()
            announcement.is_active = True
            # In production: dispatch to SMS/WhatsApp/email providers
            announcement.sent_count = 1  # Mock

        await session.commit()
        return {
            "announcement_id": str(announcement.id),
            "status": "sent" if not scheduled_at else "scheduled",
        }


@router.get("/announcements")
async def list_announcements(
    announcement_type: Optional[str] = Query(None),
    active_only: bool = Query(True),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List announcements."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        stmt = select(Announcement).where(Announcement.tenant_id == ctx.tenant_id)
        if announcement_type:
            stmt = stmt.where(Announcement.announcement_type == announcement_type)
        if active_only:
            stmt = stmt.where(Announcement.is_active == True)
        announcements = (await session.execute(stmt.order_by(Announcement.created_at.desc()))).scalars().all()
        return [
            {
                "id": str(a.id),
                "title": a.title,
                "type": a.announcement_type,
                "audience": a.audience,
                "channels": a.channels,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                "sent_count": a.sent_count,
            }
            for a in announcements
        ]


# ════════════════════════════════════════════════════════════════════════
# ACTIVITY TIMELINE
# ════════════════════════════════════════════════════════════════════════

@router.get("/customers/{customer_id}/timeline")
async def get_customer_timeline(
    customer_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get unified activity timeline for a customer."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session

    async with get_session() as session:
        stmt = select(ActivityTimeline).where(
            ActivityTimeline.tenant_id == ctx.tenant_id,
            ActivityTimeline.customer_id == customer_id,
        )
        if event_type:
            stmt = stmt.where(ActivityTimeline.event_type == event_type)

        events = (await session.execute(
            stmt.order_by(ActivityTimeline.created_at.desc()).limit(limit)
        )).scalars().all()

        return [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "event_category": e.event_category,
                "summary": e.summary,
                "details": e.details,
                "source_service": e.source_service,
                "actor_type": e.actor_type,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]


@router.post("/customers/{customer_id}/timeline")
async def add_timeline_event(
    customer_id: uuid.UUID,
    event_type: str = Query(...),
    event_category: str = Query(...),
    summary: str = Query(...),
    details: Optional[str] = Query(None),  # JSON string
    source_service: str = Query("customer_journey"),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Add a timeline event (called by other services)."""
    import json
    from services.customer_journey.database import get_session

    async with get_session() as session:
        event = ActivityTimeline(
            tenant_id=ctx.tenant_id,
            customer_id=customer_id,
            event_type=event_type,
            event_category=event_category,
            summary=summary,
            details=json.loads(details) if details else None,
            source_service=source_service,
            actor_id=ctx.user_id,
            actor_type="agent",
        )
        session.add(event)
        await session.commit()
        return {"event_id": str(event.id)}


# ════════════════════════════════════════════════════════════════════════
# CUSTOMER 360
# ════════════════════════════════════════════════════════════════════════

@router.get("/customers/{customer_id}/360", response_model=Customer360Response)
async def get_customer_360(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get full 360-degree customer view across all services."""
    from sqlalchemy import select, func
    from services.customer_journey.database import get_session

    async with get_session() as session:
        # Addresses
        addresses = (await session.execute(
            select(CustomerAddress).where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.tenant_id == ctx.tenant_id,
            )
        )).scalars().all()

        # Payment methods
        pay_methods = (await session.execute(
            select(PaymentMethod).where(
                PaymentMethod.customer_id == customer_id,
                PaymentMethod.tenant_id == ctx.tenant_id,
                PaymentMethod.is_active == True,
            )
        )).scalars().all()

        # Active orders
        orders = (await session.execute(
            select(Order).where(
                Order.customer_id == customer_id,
                Order.tenant_id == ctx.tenant_id,
                Order.status.notin_(["completed", "cancelled"]),
            ).order_by(Order.created_at.desc()).limit(5)
        )).scalars().all()

        # Recent timeline
        timeline = (await session.execute(
            select(ActivityTimeline).where(
                ActivityTimeline.customer_id == customer_id,
                ActivityTimeline.tenant_id == ctx.tenant_id,
            ).order_by(ActivityTimeline.created_at.desc()).limit(20)
        )).scalars().all()

        # Lifetime value (sum of all order totals)
        ltv = (await session.execute(
            select(func.sum(Order.total_zar)).where(
                Order.customer_id == customer_id,
                Order.tenant_id == ctx.tenant_id,
                Order.status.in_(["completed", "installed", "delivered"]),
            )
        ).scalar()) or Decimal("0.00")

        return Customer360Response(
            customer_id=str(customer_id),
            account_number="ACC-0001",  # Would come from customer record
            personal_info={},  # Would come from CRM
            addresses=[
                {
                    "type": a.address_type,
                    "line1": a.line1,
                    "city": a.city,
                    "postal_code": a.postal_code,
                    "is_primary": a.is_primary,
                }
                for a in addresses
            ],
            subscriptions=[],  # Would come from billing
            active_orders=[
                {
                    "order_number": o.order_number,
                    "status": o.status,
                    "total_zar": float(o.total_zar),
                }
                for o in orders
            ],
            recent_tickets=[],  # Would come from support
            payment_methods=[
                {
                    "type": pm.method_type,
                    "last_four": pm.last_four,
                    "is_default": pm.is_default,
                }
                for pm in pay_methods
            ],
            recent_timeline=[
                {
                    "event_type": t.event_type,
                    "summary": t.summary,
                    "created_at": t.created_at.isoformat(),
                }
                for t in timeline
            ],
            lifetime_value_zar=ltv,
        )


# ════════════════════════════════════════════════════════════════════════
# SELF-SERVICE PORTAL
# ════════════════════════════════════════════════════════════════════════

@router.get("/portal/customers/{customer_id}/statements")
async def get_customer_statements(
    customer_id: uuid.UUID,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get customer billing statements (invoices + payments)."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session
    from services.billing.models import Invoice, Payment

    async with get_session() as session:
        stmt = select(Invoice).where(
            Invoice.customer_id == customer_id,
            Invoice.tenant_id == ctx.tenant_id,
        )
        if date_from:
            stmt = stmt.where(Invoice.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.created_at <= date_to)

        invoices = (await session.execute(stmt.order_by(Invoice.created_at.desc()))).scalars().all()

        return {
            "customer_id": str(customer_id),
            "statements": [
                {
                    "id": str(inv.id),
                    "number": inv.number,
                    "status": inv.status,
                    "subtotal_zar": float(inv.subtotal_zar),
                    "vat_zar": float(inv.vat_zar),
                    "total_zar": float(inv.total_zar),
                    "amount_paid_zar": float(inv.amount_paid_zar),
                    "balance_zar": float(inv.total_zar - inv.amount_paid_zar),
                    "due_date": inv.due_date.isoformat() if inv.due_date else None,
                    "created_at": inv.created_at.isoformat() if inv.created_at else None,
                }
                for inv in invoices
            ],
        }


@router.get("/portal/customers/{customer_id}/proof-of-payment")
async def get_proof_of_payment(
    customer_id: uuid.UUID,
    invoice_id: Optional[uuid.UUID] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get proof of payment for a specific invoice or latest payment."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session
    from services.billing.models import Payment, Invoice

    async with get_session() as session:
        if invoice_id:
            payment = (await session.execute(
                select(Payment).where(
                    Payment.invoice_id == invoice_id,
                    Payment.tenant_id == ctx.tenant_id,
                    Payment.status == "completed",
                )
            )).scalar_one_or_none()
        else:
            payment = (await session.execute(
                select(Payment).where(
                    Payment.customer_id == customer_id,
                    Payment.tenant_id == ctx.tenant_id,
                    Payment.status == "completed",
                ).order_by(Payment.created_at.desc())
            )).scalar_one_or_none()

        if not payment:
            raise HTTPException(status_code=404, detail="No payment found")

        invoice = (await session.execute(
            select(Invoice).where(Invoice.id == payment.invoice_id)
        )).scalar_one_or_none()

        return {
            "payment_id": str(payment.id),
            "invoice_number": invoice.number if invoice else None,
            "amount_zar": float(payment.amount_zar),
            "method": payment.method,
            "reference": payment.reference or payment.paystack_ref,
            "paid_at": payment.created_at.isoformat() if payment.created_at else None,
            "status": payment.status,
        }


@router.get("/portal/customers/{customer_id}/usage")
async def get_usage_summary(
    customer_id: uuid.UUID,
    period: Optional[str] = Query(None),  # YYYY-MM
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get customer usage summary (speed tests, data usage)."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session
    from services.billing.models import Subscription, SubscriptionUsage

    async with get_session() as session:
        subs = (await session.execute(
            select(Subscription).where(
                Subscription.customer_id == customer_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )).scalars().all()

        usage_data = []
        for sub in subs:
            usage_records = (await session.execute(
                select(SubscriptionUsage).where(
                    SubscriptionUsage.subscription_id == sub.id,
                ).order_by(SubscriptionUsage.recorded_at.desc()).limit(30)
            )).scalars().all()

            usage_data.append({
                "subscription_id": str(sub.id),
                "plan": sub.plan,
                "status": sub.status,
                "usage": [
                    {
                        "metric": u.metric,
                        "quantity": float(u.quantity),
                        "unit_price_zar": float(u.unit_price_zar),
                        "recorded_at": u.recorded_at.isoformat() if u.recorded_at else None,
                    }
                    for u in usage_records
                ],
            })

        return {
            "customer_id": str(customer_id),
            "period": period or "all",
            "subscriptions": usage_data,
        }


@router.get("/portal/customers/{customer_id}/account")
async def get_account_summary(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get full account summary for self-service portal."""
    from sqlalchemy import select, func
    from services.customer_journey.database import get_session
    from services.billing.models import Subscription, Invoice, Payment

    async with get_session() as session:
        # Active subscriptions
        subs = (await session.execute(
            select(Subscription).where(
                Subscription.customer_id == customer_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )).scalars().all()

        # Outstanding balance
        outstanding = (await session.execute(
            select(func.sum(Invoice.total_zar - Invoice.amount_paid_zar)).where(
                Invoice.customer_id == customer_id,
                Invoice.tenant_id == ctx.tenant_id,
                Invoice.status.in_(["sent", "overdue", "partially_paid"]),
            )
        ).scalar()) or Decimal("0.00")

        # Last payment
        last_payment = (await session.execute(
            select(Payment).where(
                Payment.customer_id == customer_id,
                Payment.tenant_id == ctx.tenant_id,
                Payment.status == "completed",
            ).order_by(Payment.created_at.desc())
        )).scalar_one_or_none()

        # Payment methods
        pay_methods = (await session.execute(
            select(PaymentMethod).where(
                PaymentMethod.customer_id == customer_id,
                PaymentMethod.tenant_id == ctx.tenant_id,
                PaymentMethod.is_active == True,
            )
        )).scalars().all()

        return {
            "customer_id": str(customer_id),
            "subscriptions": [
                {
                    "id": str(s.id),
                    "plan": s.plan,
                    "status": s.status,
                    "monthly_zar": float(s.base_price_zar),
                    "billing_interval": s.billing_interval,
                    "next_billing": s.current_period_end.isoformat() if s.current_period_end else None,
                }
                for s in subs
            ],
            "outstanding_balance_zar": float(outstanding),
            "last_payment": {
                "amount_zar": float(last_payment.amount_zar),
                "method": last_payment.method,
                "date": last_payment.created_at.isoformat() if last_payment.created_at else None,
            } if last_payment else None,
            "payment_methods": [
                {
                    "id": str(pm.id),
                    "type": pm.method_type,
                    "last_four": pm.last_four,
                    "is_default": pm.is_default,
                }
                for pm in pay_methods
            ],
        }


# ════════════════════════════════════════════════════════════════════════
# UPGRADE / DOWNGRADE PACKAGES
# ════════════════════════════════════════════════════════════════════════

class UpgradeRequest(BaseModel):
    subscription_id: uuid.UUID
    target_plan: str
    effective_date: Optional[date] = None


class UpgradeResponse(BaseModel):
    subscription_id: str
    old_plan: str
    new_plan: str
    old_monthly_zar: Decimal
    new_monthly_zar: Decimal
    prorated_charge_zar: Decimal
    effective_date: date
    message: str


@router.post("/subscriptions/upgrade", response_model=UpgradeResponse)
async def upgrade_subscription(
    body: UpgradeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Upgrade customer to a higher-tier package."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session
    from services.billing.models import Subscription, Invoice

    async with get_session() as session:
        sub = (await session.execute(
            select(Subscription).where(
                Subscription.id == body.subscription_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        old_plan = sub.plan
        old_price = sub.base_price_zar

        # Get new plan pricing (would come from a plans table in production)
        PLAN_PRICING = {
            "Home 50Mbps": Decimal("799.00"),
            "Home 100Mbps": Decimal("999.00"),
            "Home 200Mbps": Decimal("1299.00"),
            "Home 500Mbps": Decimal("1799.00"),
            "Home 1000Mbps": Decimal("2499.00"),
            "Uncapped 50Mbps": Decimal("1099.00"),
            "Uncapped 100Mbps": Decimal("1499.00"),
            "Uncapped 200Mbps": Decimal("1999.00"),
        }

        new_price = PLAN_PRICING.get(body.target_plan)
        if not new_price:
            raise HTTPException(status_code=400, detail=f"Unknown plan: {body.target_plan}")
        if new_price <= old_price:
            raise HTTPException(status_code=400, detail="Use /downgrade for lower-tier plans")

        # Calculate prorated charge
        effective = body.effective_date or date.today()
        if sub.current_period_end and sub.current_period_start:
            days_in_period = (sub.current_period_end - sub.current_period_start).days
            days_remaining = max(0, (sub.current_period_end - effective).days)
            daily_old = old_price / Decimal(str(max(1, days_in_period)))
            daily_new = new_price / Decimal(str(max(1, days_in_period)))
            prorated = (daily_new * Decimal(str(days_remaining))) - (daily_old * Decimal(str(days_remaining)))
            prorated = prorated.quantize(Decimal("0.01"))
        else:
            prorated = Decimal("0.00")

        # Update subscription
        sub.plan = body.target_plan
        sub.base_price_zar = new_price
        sub.current_period_start = effective

        # Generate prorated invoice if charge > 0
        if prorated > 0:
            inv = Invoice(
                tenant_id=ctx.tenant_id,
                customer_id=sub.customer_id,
                subscription_id=sub.id,
                number=f"PROR-{str(sub.id)[:8]}",
                status="sent",
                subtotal_zar=prorated,
                vat_zar=(prorated * Decimal("0.15")).quantize(Decimal("0.01")),
                total_zar=(prorated * Decimal("1.15")).quantize(Decimal("0.01")),
                due_date=date.today() + timedelta(days=14),
                line_items=[{
                    "description": f"Prorated upgrade: {old_plan} → {body.target_plan}",
                    "quantity": 1,
                    "unit_price_zar": str(prorated),
                }],
            )
            session.add(inv)

        await session.commit()

        # Log timeline
        timeline = ActivityTimeline(
            tenant_id=ctx.tenant_id,
            customer_id=sub.customer_id,
            event_type="subscription_upgraded",
            event_category="lifecycle",
            summary=f"Upgraded from {old_plan} to {body.target_plan}",
            source_service="customer_journey",
            subscription_id=sub.id,
        )
        session.add(timeline)
        await session.commit()

        return UpgradeResponse(
            subscription_id=str(sub.id),
            old_plan=old_plan,
            new_plan=body.target_plan,
            old_monthly_zar=old_price,
            new_monthly_zar=new_price,
            prorated_charge_zar=prorated,
            effective_date=effective,
            message=f"Upgraded to {body.target_plan}. New monthly fee: R{new_price}",
        )


@router.post("/subscriptions/downgrade", response_model=UpgradeResponse)
async def downgrade_subscription(
    body: UpgradeRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Downgrade customer to a lower-tier package."""
    from sqlalchemy import select
    from services.customer_journey.database import get_session
    from services.billing.models import Subscription

    async with get_session() as session:
        sub = (await session.execute(
            select(Subscription).where(
                Subscription.id == body.subscription_id,
                Subscription.tenant_id == ctx.tenant_id,
            )
        )).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        old_plan = sub.plan
        old_price = sub.base_price_zar

        PLAN_PRICING = {
            "Home 50Mbps": Decimal("799.00"),
            "Home 100Mbps": Decimal("999.00"),
            "Home 200Mbps": Decimal("1299.00"),
            "Home 500Mbps": Decimal("1799.00"),
            "Home 1000Mbps": Decimal("2499.00"),
            "Uncapped 50Mbps": Decimal("1099.00"),
            "Uncapped 100Mbps": Decimal("1499.00"),
            "Uncapped 200Mbps": Decimal("1999.00"),
        }

        new_price = PLAN_PRICING.get(body.target_plan)
        if not new_price:
            raise HTTPException(status_code=400, detail=f"Unknown plan: {body.target_plan}")
        if new_price >= old_price:
            raise HTTPException(status_code=400, detail="Use /upgrade for higher-tier plans")

        effective = body.effective_date or date.today()

        sub.plan = body.target_plan
        sub.base_price_zar = new_price
        sub.current_period_start = effective

        await session.commit()

        timeline = ActivityTimeline(
            tenant_id=ctx.tenant_id,
            customer_id=sub.customer_id,
            event_type="subscription_downgraded",
            event_category="lifecycle",
            summary=f"Downgraded from {old_plan} to {body.target_plan}",
            source_service="customer_journey",
            subscription_id=sub.id,
        )
        session.add(timeline)
        await session.commit()

        return UpgradeResponse(
            subscription_id=str(sub.id),
            old_plan=old_plan,
            new_plan=body.target_plan,
            old_monthly_zar=old_price,
            new_monthly_zar=new_price,
            prorated_charge_zar=Decimal("0.00"),
            effective_date=effective,
            message=f"Downgraded to {body.target_plan}. New monthly fee: R{new_price}. Effective next billing cycle.",
        )
