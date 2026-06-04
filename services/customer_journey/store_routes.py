"""Store routes — hardware + VAS shopping cart, catalog, and checkout.

Extends the customer_journey service with store functionality:
- Product catalog (categories, products, bundles, reviews)
- Shopping cart (add, update, remove, apply promo)
- Cart → Order checkout flow
- Wishlist management
- Product reviews
- Store seed data (routers, ONTs, mesh nodes, VAS add-ons)
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import get_current_tenant_id
from services.customer_journey.database import get_session
from services.customer_journey.models import (
    ActivityTimeline,
    Order,
    OrderItem,
    Promotion,
    ShoppingCart,
    ShoppingCartItem,
    StoreBundle,
    StoreBundleItem,
    StoreCategory,
    StoreProduct,
    StoreWishlist,
    ProductReview,
)

router = APIRouter(prefix="/store", tags=["Store"])


# ════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════

def _recalculate_cart(cart: ShoppingCart, items: list[ShoppingCartItem]) -> None:
    cart.item_count = sum(i.quantity for i in items)
    cart.subtotal_zar = sum(i.total_price_zar for i in items)
    cart.total_zar = cart.subtotal_zar - cart.discount_zar


# ════════════════════════════════════════════════════════════════════════
# CATEGORIES
# ════════════════════════════════════════════════════════════════════════

class CategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    icon_url: Optional[str] = None
    sort_order: int = 0


@router.post("/categories")
async def create_category(
    payload: CategoryCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    cat = StoreCategory(
        tenant_id=tenant_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        parent_id=uuid.UUID(payload.parent_id) if payload.parent_id else None,
        icon_url=payload.icon_url,
        sort_order=payload.sort_order,
    )
    db.add(cat)
    await db.flush()
    return {"id": str(cat.id), "name": cat.name, "slug": cat.slug}


@router.get("/categories")
async def list_categories(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    parent_id: Optional[str] = None,
    is_active: bool = True,
):
    query = select(StoreCategory).where(StoreCategory.tenant_id == tenant_id)
    if parent_id:
        query = query.where(StoreCategory.parent_id == uuid.UUID(parent_id))
    else:
        query = query.where(StoreCategory.parent_id == None)
    if is_active:
        query = query.where(StoreCategory.is_active == True)
    query = query.order_by(StoreCategory.sort_order, StoreCategory.name)
    result = await db.execute(query)
    cats = result.scalars().all()
    return [
        {
            "id": str(c.id), "name": c.name, "slug": c.slug,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "sort_order": c.sort_order, "is_active": c.is_active,
        }
        for c in cats
    ]


# ════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ════════════════════════════════════════════════════════════════════════

class ProductCreate(BaseModel):
    sku: str
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    category_id: Optional[str] = None
    product_type: str
    once_off_price_zar: float = 0
    monthly_price_zar: float = 0
    stock_quantity: int = 0
    low_stock_threshold: int = 5
    track_inventory: bool = True
    allow_backorder: bool = False
    image_urls: list[str] = Field(default_factory=list)
    specs: dict = Field(default_factory=dict)
    is_active: bool = True
    is_featured: bool = False
    requires_subscription: bool = False
    compatible_packages: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    once_off_price_zar: Optional[float] = None
    monthly_price_zar: Optional[float] = None
    stock_quantity: Optional[int] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None


@router.post("/products")
async def create_product(
    payload: ProductCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    product = StoreProduct(
        tenant_id=tenant_id, sku=payload.sku, name=payload.name, slug=payload.slug,
        description=payload.description, short_description=payload.short_description,
        category_id=uuid.UUID(payload.category_id) if payload.category_id else None,
        product_type=payload.product_type,
        once_off_price_zar=Decimal(str(payload.once_off_price_zar)),
        monthly_price_zar=Decimal(str(payload.monthly_price_zar)),
        stock_quantity=payload.stock_quantity, low_stock_threshold=payload.low_stock_threshold,
        track_inventory=payload.track_inventory, allow_backorder=payload.allow_backorder,
        image_urls=payload.image_urls, specs=payload.specs,
        is_active=payload.is_active, is_featured=payload.is_featured,
        requires_subscription=payload.requires_subscription,
        compatible_packages=payload.compatible_packages,
    )
    db.add(product)
    await db.flush()
    return {"id": str(product.id), "sku": product.sku, "name": product.name}


@router.get("/products")
async def list_products(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    category_id: Optional[str] = None,
    product_type: Optional[str] = None,
    is_active: bool = True,
    is_featured: Optional[bool] = None,
    search: Optional[str] = None,
    in_stock: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(StoreProduct).where(StoreProduct.tenant_id == tenant_id)
    if category_id:
        query = query.where(StoreProduct.category_id == uuid.UUID(category_id))
    if product_type:
        query = query.where(StoreProduct.product_type == product_type)
    if is_active:
        query = query.where(StoreProduct.is_active == True)
    if is_featured is not None:
        query = query.where(StoreProduct.is_featured == is_featured)
    if in_stock:
        query = query.where(StoreProduct.stock_quantity > 0)
    if search:
        query = query.where(
            StoreProduct.name.ilike(f"%{search}%") | StoreProduct.sku.ilike(f"%{search}%")
        )
    query = query.order_by(StoreProduct.sort_order, StoreProduct.name).limit(limit).offset(offset)
    result = await db.execute(query)
    products = result.scalars().all()
    return [
        {
            "id": str(p.id), "sku": p.sku, "name": p.name, "slug": p.slug,
            "product_type": p.product_type, "once_off_price_zar": float(p.once_off_price_zar),
            "monthly_price_zar": float(p.monthly_price_zar), "stock_quantity": p.stock_quantity,
            "is_active": p.is_active, "is_featured": p.is_featured,
            "image_urls": p.image_urls, "specs": p.specs,
            "requires_subscription": p.requires_subscription,
        }
        for p in products
    ]


@router.get("/products/{product_id}")
async def get_product(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(StoreProduct).where(
            StoreProduct.id == product_id, StoreProduct.tenant_id == tenant_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    rating_result = await db.execute(
        select(func.avg(ProductReview.rating), func.count(ProductReview.id)).where(
            ProductReview.product_id == product_id,
            ProductReview.is_published == True,
        )
    )
    avg_rating, review_count = rating_result.one()

    return {
        "id": str(p.id), "sku": p.sku, "name": p.name, "slug": p.slug,
        "description": p.description, "short_description": p.short_description,
        "product_type": p.product_type, "once_off_price_zar": float(p.once_off_price_zar),
        "monthly_price_zar": float(p.monthly_price_zar), "stock_quantity": p.stock_quantity,
        "reserved_quantity": p.reserved_quantity, "low_stock_threshold": p.low_stock_threshold,
        "track_inventory": p.track_inventory, "allow_backorder": p.allow_backorder,
        "image_urls": p.image_urls, "specs": p.specs, "is_active": p.is_active,
        "is_featured": p.is_featured, "requires_subscription": p.requires_subscription,
        "compatible_packages": p.compatible_packages,
        "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
        "review_count": review_count,
    }


@router.put("/products/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(StoreProduct).where(
            StoreProduct.id == product_id, StoreProduct.tenant_id == tenant_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.name is not None: p.name = payload.name
    if payload.description is not None: p.description = payload.description
    if payload.once_off_price_zar is not None: p.once_off_price_zar = Decimal(str(payload.once_off_price_zar))
    if payload.monthly_price_zar is not None: p.monthly_price_zar = Decimal(str(payload.monthly_price_zar))
    if payload.stock_quantity is not None: p.stock_quantity = payload.stock_quantity
    if payload.is_active is not None: p.is_active = payload.is_active
    if payload.is_featured is not None: p.is_featured = payload.is_featured
    await db.flush()
    return {"id": str(p.id), "sku": p.sku, "name": p.name}


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(StoreProduct).where(
            StoreProduct.id == product_id, StoreProduct.tenant_id == tenant_id,
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.delete(p)


# ════════════════════════════════════════════════════════════════════════
# SHOPPING CART
# ════════════════════════════════════════════════════════════════════════

class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = Field(1, ge=1, le=99)
    target_subscription_id: Optional[str] = None


class CartItemUpdate(BaseModel):
    quantity: int = Field(1, ge=1, le=99)


@router.get("/cart")
async def get_cart(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    result = await db.execute(
        select(ShoppingCart).where(
            ShoppingCart.tenant_id == tenant_id,
            ShoppingCart.customer_id == uuid.UUID(customer_id),
            ShoppingCart.status == "active",
        )
    )
    cart = result.scalar_one_or_none()
    if not cart:
        return {"status": "empty", "items": [], "item_count": 0, "total_zar": 0}

    items_result = await db.execute(
        select(ShoppingCartItem).where(ShoppingCartItem.cart_id == cart.id)
    )
    items = items_result.scalars().all()
    return {
        "id": str(cart.id), "status": cart.status, "item_count": cart.item_count,
        "subtotal_zar": float(cart.subtotal_zar), "discount_zar": float(cart.discount_zar),
        "total_zar": float(cart.total_zar), "promo_code": cart.promo_code,
        "expires_at": cart.expires_at.isoformat() if cart.expires_at else None,
        "items": [
            {
                "id": str(i.id), "product_id": str(i.product_id),
                "product_name": i.product_name_snapshot, "product_sku": i.product_sku_snapshot,
                "product_type": i.product_type, "quantity": i.quantity,
                "unit_price_zar": float(i.unit_price_zar), "total_price_zar": float(i.total_price_zar),
                "target_subscription_id": str(i.target_subscription_id) if i.target_subscription_id else None,
            }
            for i in items
        ],
    }


@router.post("/cart/items")
async def add_to_cart(
    payload: CartItemAdd,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    cust_id = uuid.UUID(customer_id)
    prod_id = uuid.UUID(payload.product_id)

    prod_result = await db.execute(
        select(StoreProduct).where(
            StoreProduct.id == prod_id, StoreProduct.tenant_id == tenant_id,
            StoreProduct.is_active == True,
        )
    )
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.track_inventory and not product.allow_backorder:
        available = product.stock_quantity - product.reserved_quantity
        if available < payload.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {available}")

    cart_result = await db.execute(
        select(ShoppingCart).where(
            ShoppingCart.tenant_id == tenant_id, ShoppingCart.customer_id == cust_id,
            ShoppingCart.status == "active",
        )
    )
    cart = cart_result.scalar_one_or_none()
    if not cart:
        cart = ShoppingCart(
            tenant_id=tenant_id, customer_id=cust_id, status="active",
            expires_at=datetime.utcnow() + timedelta(hours=48),
        )
        db.add(cart)
        await db.flush()

    existing_result = await db.execute(
        select(ShoppingCartItem).where(
            ShoppingCartItem.cart_id == cart.id, ShoppingCartItem.product_id == prod_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.quantity += payload.quantity
        existing.total_price_zar = existing.unit_price_zar * existing.quantity
    else:
        price = product.once_off_price_zar if product.product_type == "hardware" else product.monthly_price_zar
        item = ShoppingCartItem(
            cart_id=cart.id, product_id=prod_id, product_type=product.product_type,
            quantity=payload.quantity, unit_price_zar=price, total_price_zar=price * payload.quantity,
            product_name_snapshot=product.name, product_sku_snapshot=product.sku,
            target_subscription_id=uuid.UUID(payload.target_subscription_id) if payload.target_subscription_id else None,
        )
        db.add(item)

    await db.flush()
    items_result = await db.execute(select(ShoppingCartItem).where(ShoppingCartItem.cart_id == cart.id))
    items = items_result.scalars().all()
    _recalculate_cart(cart, items)
    cart.last_activity_at = datetime.utcnow()
    await db.flush()
    return {"cart_id": str(cart.id), "item_count": cart.item_count, "total_zar": float(cart.total_zar)}


@router.put("/cart/items/{item_id}")
async def update_cart_item(
    item_id: uuid.UUID,
    payload: CartItemUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    item_result = await db.execute(select(ShoppingCartItem).where(ShoppingCartItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    item.quantity = payload.quantity
    item.total_price_zar = item.unit_price_zar * payload.quantity
    await db.flush()

    cart_result = await db.execute(select(ShoppingCart).where(ShoppingCart.id == item.cart_id))
    cart = cart_result.scalar_one()
    items_result = await db.execute(select(ShoppingCartItem).where(ShoppingCartItem.cart_id == cart.id))
    _recalculate_cart(cart, items_result.scalars().all())
    await db.flush()
    return {"item_id": str(item.id), "quantity": item.quantity, "total_zar": float(cart.total_zar)}


@router.delete("/cart/items/{item_id}", status_code=204)
async def remove_cart_item(
    item_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    item_result = await db.execute(select(ShoppingCartItem).where(ShoppingCartItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    cart_id = item.cart_id
    await db.delete(item)
    await db.flush()

    cart_result = await db.execute(select(ShoppingCart).where(ShoppingCart.id == cart_id))
    cart = cart_result.scalar_one_or_none()
    if cart:
        items_result = await db.execute(select(ShoppingCartItem).where(ShoppingCartItem.cart_id == cart_id))
        items = items_result.scalars().all()
        if items:
            _recalculate_cart(cart, items)
        else:
            cart.item_count = 0
            cart.subtotal_zar = Decimal("0.00")
            cart.total_zar = Decimal("0.00")
        await db.flush()


@router.post("/cart/apply-promo")
async def apply_promo_code(
    promo_code: str = Query(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    cart_result = await db.execute(
        select(ShoppingCart).where(
            ShoppingCart.tenant_id == tenant_id,
            ShoppingCart.customer_id == uuid.UUID(customer_id),
            ShoppingCart.status == "active",
        )
    )
    cart = cart_result.scalar_one_or_none()
    if not cart:
        raise HTTPException(status_code=404, detail="No active cart found")

    promo_result = await db.execute(
        select(Promotion).where(
            Promotion.tenant_id == tenant_id, Promotion.promo_code == promo_code,
        )
    )
    promo = promo_result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=400, detail="Invalid or expired promo code")

    discount = Decimal("0.00")
    params = promo.parameters or {}
    if promo.promo_type == "percentage_discount":
        pct = Decimal(str(params.get("percent", 0)))
        discount = cart.subtotal_zar * pct / Decimal("100")
        max_disc = params.get("max_discount_zar")
        if max_disc:
            discount = min(discount, Decimal(str(max_disc)))
    elif promo.promo_type == "fixed_discount":
        discount = Decimal(str(params.get("amount_zar", 0)))

    cart.promo_code = promo_code
    cart.promotion_id = promo.id
    cart.discount_zar = discount
    cart.total_zar = cart.subtotal_zar - discount
    await db.flush()
    return {"promo_code": promo_code, "discount_zar": float(discount), "total_zar": float(cart.total_zar)}


# ════════════════════════════════════════════════════════════════════════
# CART → CHECKOUT
# ════════════════════════════════════════════════════════════════════════

class CheckoutRequest(BaseModel):
    customer_id: str
    service_address_id: Optional[str] = None
    billing_address_id: Optional[str] = None
    payment_method_id: Optional[str] = None
    preferred_contact_channel: str = "sms"
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    customer_notes: Optional[str] = None


@router.post("/cart/checkout")
async def checkout_cart(
    payload: CheckoutRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    cust_id = uuid.UUID(payload.customer_id)

    cart_result = await db.execute(
        select(ShoppingCart).where(
            ShoppingCart.tenant_id == tenant_id, ShoppingCart.customer_id == cust_id,
            ShoppingCart.status == "active",
        )
    )
    cart = cart_result.scalar_one_or_none()
    if not cart:
        raise HTTPException(status_code=404, detail="No active cart found")

    items_result = await db.execute(select(ShoppingCartItem).where(ShoppingCartItem.cart_id == cart.id))
    cart_items = items_result.scalars().all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    order_count_result = await db.execute(
        select(func.count(Order.id)).where(Order.tenant_id == tenant_id)
    )
    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{(order_count_result.scalar() or 0) + 1:06d}"

    order = Order(
        tenant_id=tenant_id, customer_id=cust_id, account_number="",
        order_number=order_number, status="pending",
        service_address_id=uuid.UUID(payload.service_address_id) if payload.service_address_id else None,
        billing_address_id=uuid.UUID(payload.billing_address_id) if payload.billing_address_id else None,
        payment_method_id=uuid.UUID(payload.payment_method_id) if payload.payment_method_id else None,
        subtotal_zar=cart.subtotal_zar, discount_zar=cart.discount_zar, total_zar=cart.total_zar,
        promotion_id=cart.promotion_id, promo_code=cart.promo_code,
        preferred_contact_channel=payload.preferred_contact_channel,
        contact_phone=payload.contact_phone, contact_email=payload.contact_email,
        customer_notes=payload.customer_notes,
    )
    db.add(order)
    await db.flush()

    for ci in cart_items:
        db.add(OrderItem(
            order_id=order.id, item_type=ci.product_type, product_id=ci.product_id,
            description=ci.product_name_snapshot or "", quantity=ci.quantity,
            unit_price_zar=ci.unit_price_zar, total_price_zar=ci.total_price_zar,
            package_name=ci.product_name_snapshot if ci.product_type == "vas" else None,
            monthly_recurring_zar=ci.unit_price_zar if ci.product_type == "vas" else Decimal("0.00"),
            once_off_zar=ci.unit_price_zar if ci.product_type == "hardware" else Decimal("0.00"),
        ))
        if ci.product_type == "hardware":
            prod_result = await db.execute(select(StoreProduct).where(StoreProduct.id == ci.product_id))
            prod = prod_result.scalar_one_or_none()
            if prod and prod.track_inventory:
                prod.reserved_quantity += ci.quantity

    cart.status = "converted_to_order"

    db.add(ActivityTimeline(
        tenant_id=tenant_id, customer_id=cust_id, event_type="order_placed",
        event_category="sales", summary=f"Store order {order_number} placed. Total: R{cart.total_zar}",
        source_service="customer_journey", source_id=order.id, order_id=order.id,
    ))

    await db.flush()
    return {
        "order_id": str(order.id), "order_number": order_number,
        "status": order.status, "total_zar": float(order.total_zar), "item_count": len(cart_items),
    }


# ════════════════════════════════════════════════════════════════════════
# WISHLIST
# ════════════════════════════════════════════════════════════════════════

@router.post("/wishlist")
async def add_to_wishlist(
    product_id: str = Query(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    db.add(StoreWishlist(tenant_id=tenant_id, customer_id=uuid.UUID(customer_id), product_id=uuid.UUID(product_id)))
    await db.flush()
    return {"product_id": product_id, "added": True}


@router.get("/wishlist")
async def get_wishlist(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    result = await db.execute(
        select(StoreProduct).join(StoreWishlist, and_(
            StoreWishlist.product_id == StoreProduct.id,
            StoreWishlist.tenant_id == tenant_id,
            StoreWishlist.customer_id == uuid.UUID(customer_id),
        ))
    )
    products = result.scalars().all()
    return [
        {"id": str(p.id), "sku": p.sku, "name": p.name, "product_type": p.product_type,
         "once_off_price_zar": float(p.once_off_price_zar), "monthly_price_zar": float(p.monthly_price_zar),
         "is_active": p.is_active}
        for p in products
    ]


@router.delete("/wishlist/{product_id}", status_code=204)
async def remove_from_wishlist(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    result = await db.execute(
        select(StoreWishlist).where(
            StoreWishlist.tenant_id == tenant_id,
            StoreWishlist.customer_id == uuid.UUID(customer_id),
            StoreWishlist.product_id == product_id,
        )
    )
    item = result.scalar_one_or_none()
    if item:
        await db.delete(item)


# ════════════════════════════════════════════════════════════════════════
# REVIEWS
# ════════════════════════════════════════════════════════════════════════

class ReviewCreate(BaseModel):
    product_id: str
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = None
    body: Optional[str] = None
    order_id: Optional[str] = None


@router.post("/reviews")
async def create_review(
    payload: ReviewCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    customer_id: str = Query(...),
):
    review = ProductReview(
        tenant_id=tenant_id, product_id=uuid.UUID(payload.product_id),
        customer_id=uuid.UUID(customer_id),
        order_id=uuid.UUID(payload.order_id) if payload.order_id else None,
        rating=payload.rating, title=payload.title, body=payload.body,
        is_verified_purchase=payload.order_id is not None,
    )
    db.add(review)
    await db.flush()
    return {"id": str(review.id), "rating": review.rating}


@router.get("/products/{product_id}/reviews")
async def list_reviews(
    product_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(20, le=100),
    offset: int = 0,
):
    result = await db.execute(
        select(ProductReview).where(
            ProductReview.product_id == product_id,
            ProductReview.tenant_id == tenant_id,
            ProductReview.is_published == True,
        ).order_by(desc(ProductReview.created_at)).limit(limit).offset(offset)
    )
    reviews = result.scalars().all()
    return [
        {"id": str(r.id), "rating": r.rating, "title": r.title, "body": r.body,
         "is_verified_purchase": r.is_verified_purchase,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in reviews
    ]


# ════════════════════════════════════════════════════════════════════════
# BUNDLES
# ════════════════════════════════════════════════════════════════════════

class BundleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    total_once_off_zar: float = 0
    total_monthly_zar: float = 0
    bundle_discount_pct: float = 0
    image_url: Optional[str] = None
    product_ids: list[str] = Field(default_factory=list)


@router.post("/bundles")
async def create_bundle(
    payload: BundleCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    bundle = StoreBundle(
        tenant_id=tenant_id, name=payload.name, description=payload.description,
        total_once_off_zar=Decimal(str(payload.total_once_off_zar)),
        total_monthly_zar=Decimal(str(payload.total_monthly_zar)),
        bundle_discount_pct=Decimal(str(payload.bundle_discount_pct)),
        image_url=payload.image_url,
    )
    db.add(bundle)
    await db.flush()
    for pid in payload.product_ids:
        db.add(StoreBundleItem(bundle_id=bundle.id, product_id=uuid.UUID(pid)))
    await db.flush()
    return {"id": str(bundle.id), "name": bundle.name}


@router.get("/bundles")
async def list_bundles(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
    is_active: bool = True,
):
    query = select(StoreBundle).where(StoreBundle.tenant_id == tenant_id)
    if is_active:
        query = query.where(StoreBundle.is_active == True)
    query = query.order_by(StoreBundle.sort_order, StoreBundle.name)
    result = await db.execute(query)
    bundles = result.scalars().all()
    return [
        {"id": str(b.id), "name": b.name, "description": b.description,
         "total_once_off_zar": float(b.total_once_off_zar), "total_monthly_zar": float(b.total_monthly_zar),
         "bundle_discount_pct": float(b.bundle_discount_pct), "image_url": b.image_url}
        for b in bundles
    ]


@router.get("/bundles/{bundle_id}")
async def get_bundle(
    bundle_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    bundle_result = await db.execute(
        select(StoreBundle).where(StoreBundle.id == bundle_id, StoreBundle.tenant_id == tenant_id)
    )
    bundle = bundle_result.scalar_one_or_none()
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")

    items_result = await db.execute(
        select(StoreProduct).join(StoreBundleItem, StoreBundleItem.product_id == StoreProduct.id)
        .where(StoreBundleItem.bundle_id == bundle_id)
    )
    products = items_result.scalars().all()
    return {
        "id": str(bundle.id), "name": bundle.name, "description": bundle.description,
        "total_once_off_zar": float(bundle.total_once_off_zar),
        "total_monthly_zar": float(bundle.total_monthly_zar),
        "bundle_discount_pct": float(bundle.bundle_discount_pct), "image_url": bundle.image_url,
        "products": [
            {"id": str(p.id), "sku": p.sku, "name": p.name, "product_type": p.product_type,
             "once_off_price_zar": float(p.once_off_price_zar), "monthly_price_zar": float(p.monthly_price_zar)}
            for p in products
        ],
    }


# ════════════════════════════════════════════════════════════════════════
# SEED DATA
# ════════════════════════════════════════════════════════════════════════

@router.post("/seed")
async def seed_store(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_session),
):
    existing = await db.execute(
        select(func.count(StoreProduct.id)).where(StoreProduct.tenant_id == tenant_id)
    )
    if existing.scalar() > 0:
        return {"status": "already_seeded"}

    categories = [
        ("Routers", "routers", "WiFi routers and gateways"),
        ("ONTs", "onts", "Optical Network Terminals"),
        ("Mesh & Extenders", "mesh", "Mesh WiFi and range extenders"),
        ("Accessories", "accessories", "Cables, adapters, brackets"),
        ("Value Added Services", "vas", "Static IP, security, parental controls"),
    ]
    cat_ids = {}
    for name, slug, desc in categories:
        cat = StoreCategory(tenant_id=tenant_id, name=name, slug=slug, description=desc)
        db.add(cat)
        await db.flush()
        cat_ids[slug] = cat.id

    hardware_products = [
        ("RT-TP-AX55", "TP-Link Archer AX55", "tp-link-archer-ax55", "routers", 1299.00, 50,
         {"Manufacturer": "TP-Link", "Model": "Archer AX55", "Speed": "AX3000", "Ports": 4, "WiFi": "WiFi 6"}),
        ("RT-TP-AX73", "TP-Link Archer AX73", "tp-link-archer-ax73", "routers", 1899.00, 30,
         {"Manufacturer": "TP-Link", "Model": "Archer AX73", "Speed": "AX5400", "Ports": 4, "WiFi": "WiFi 6"}),
        ("RT-ASUS-AX58U", "ASUS RT-AX58U", "asus-rt-ax58u", "routers", 1699.00, 25,
         {"Manufacturer": "ASUS", "Model": "RT-AX58U", "Speed": "AX3000", "Ports": 4, "WiFi": "WiFi 6"}),
        ("RT-MI-AX3000", "Xiaomi Mi Router AX3000", "xiaomi-ax3000", "routers", 799.00, 100,
         {"Manufacturer": "Xiaomi", "Model": "AX3000", "Speed": "AX3000", "Ports": 3, "WiFi": "WiFi 6"}),
        ("ONT-NOKIA-G240G", "Nokia G-240G-A ONT", "nokia-g240g-ont", "onts", 899.00, 200,
         {"Manufacturer": "Nokia", "Model": "G-240G-A", "GPON": True, "Ports": 4, "WiFi": False}),
        ("ONT-HW-E8827V", "Huawei EchoLife EG8827V", "huawei-eg8827v", "onts", 749.00, 150,
         {"Manufacturer": "Huawei", "Model": "EG8827V", "GPON": True, "Ports": 4, "WiFi": "WiFi 5"}),
        ("MS-TP-DECO-X50", "TP-Link Deco X50 (3-pack)", "tp-link-deco-x50", "mesh", 3499.00, 20,
         {"Manufacturer": "TP-Link", "Model": "Deco X50", "Speed": "AX3000", "Coverage": "500m²", "Units": 3}),
        ("MS-TP-DECO-M4", "TP-Link Deco M4 (2-pack)", "tp-link-deco-m4", "mesh", 1799.00, 35,
         {"Manufacturer": "TP-Link", "Model": "Deco M4", "Speed": "AC1200", "Coverage": "300m²", "Units": 2}),
        ("AC-CAT6-5M", "Cat6 Ethernet Cable 5m", "cat6-cable-5m", "accessories", 89.00, 500,
         {"Type": "Cat6", "Length": "5m", "Color": "White"}),
        ("AC-PWR-12V", "12V Power Adapter", "power-adapter-12v", "accessories", 149.00, 300,
         {"Voltage": "12V", "Current": "2A", "Connector": "5.5x2.1mm"}),
        ("AC-BRACKET", "Wall Mount Bracket", "wall-bracket", "accessories", 199.00, 200,
         {"Material": "Steel", "Weight": "500g"}),
    ]

    for sku, name, slug, cat_slug, price, stock, specs in hardware_products:
        db.add(StoreProduct(
            tenant_id=tenant_id, sku=sku, name=name, slug=slug,
            category_id=cat_ids.get(cat_slug), product_type="hardware",
            once_off_price_zar=Decimal(str(price)), stock_quantity=stock,
            specs=specs, is_active=True, is_featured=price > 1000,
        ))

    vas_products = [
        ("VAS-STATIC-IP", "Static IP Address", "static-ip", "vas", 0, 99.00,
         {"Description": "Dedicated static IPv4 address", "Billing": "Monthly"}, True, ["all"]),
        ("VAS-ANTIVIRUS", "Norton 360 Security", "norton-360", "vas", 0, 69.00,
         {"Description": "Antivirus for up to 5 devices", "Billing": "Monthly"}, True, ["all"]),
        ("VAS-PARENTAL", "Parental Controls", "parental-controls", "vas", 0, 39.00,
         {"Description": "Content filtering and screen time", "Billing": "Monthly"}, True, ["all"]),
        ("VAS-CLOUD-100", "Cloud Backup 100GB", "cloud-backup-100", "vas", 0, 49.00,
         {"Description": "100GB encrypted cloud storage", "Billing": "Monthly"}, True, ["all"]),
        ("VAS-VPN", "Secure VPN", "secure-vpn", "vas", 0, 59.00,
         {"Description": "Unlimited VPN for all devices", "Billing": "Monthly"}, True, ["all"]),
        ("VAS-PRIORITY", "Priority Support", "priority-support", "vas", 0, 99.00,
         {"Description": "24/7 priority technical support", "Billing": "Monthly"}, True, ["all"]),
    ]

    for sku, name, slug, cat_slug, once_off, monthly, specs, req_sub, compat in vas_products:
        db.add(StoreProduct(
            tenant_id=tenant_id, sku=sku, name=name, slug=slug,
            category_id=cat_ids.get(cat_slug), product_type="vas",
            once_off_price_zar=Decimal(str(once_off)), monthly_price_zar=Decimal(str(monthly)),
            specs=specs, is_active=True, requires_subscription=req_sub, compatible_packages=compat,
        ))

    for name, desc, once_off, monthly, discount in [
        ("Complete WiFi Setup", "Router + Mesh + Installation", 5398.00, 0, 10),
        ("Basic Router Package", "Router + ONT + Cables", 2287.00, 0, 5),
        ("Security Bundle", "Static IP + Antivirus + VPN", 0, 227.00, 15),
    ]:
        db.add(StoreBundle(
            tenant_id=tenant_id, name=name, description=desc,
            total_once_off_zar=Decimal(str(once_off)), total_monthly_zar=Decimal(str(monthly)),
            bundle_discount_pct=Decimal(str(discount)),
        ))

    await db.flush()
    return {
        "status": "seeded", "categories": len(categories),
        "hardware": len(hardware_products), "vas": len(vas_products), "bundles": 3,
    }
