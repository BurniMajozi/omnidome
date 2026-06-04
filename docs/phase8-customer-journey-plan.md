# Phase 8: Customer Journey & Lifecycle Redesign — Plan

## Problem Statement
Current system has fragmented customer data across CRM, Sales, Billing with duplicate models (contacts vs customers, two leads tables). Missing entire lifecycle: orders, checkout, delivery, technician tracking, moving house, pause, cancellation with FNO, reverse logistics, early termination fees, self-service portal.

## Fiber Customer Journey (End-to-End)

```
1.  LEAD CAPTURE
    Website form / Sales agent / Walk-in / Referral
    → leads table (source, coverage_area, interested_package)

2.  COVERAGE CHECK
    Address → FNO coverage lookup (Vumatel/Openserve/other)
    → coverage_areas table (FNO, technology, availability)
    → Returns: available packages, estimated speeds

3.  LEAD → CUSTOMER CONVERSION
    Lead qualified → Customer created (account_number, personal info)
    → RICA verification (id_number → Smile ID API)
    → customer_addresses (service address + physical address)

4.  ORDER & CHECKOUT
    Customer selects package + hardware + VAS
    → orders table (cart → pending → confirmed)
    → order_items (package line, hardware lines, VAS lines)
    → Payment (Paystack card/EFT/debit order)
    → payment_methods (stored cards per customer)

5.  FULFILLMENT & DELIVERY
    Order confirmed → delivery scheduled
    → delivery_tracking (courier, tracking_no, status, ETA)
    → Hardware shipped to customer or depot

6.  INSTALLATION & ACTIVATION
    Technician dispatched
    → technician_visits (dispatch, ETA, tracking, completion)
    → ONT installed, signal tested
    → Subscription activated (billing starts)
    → customer_subscriptions (customer + package + address + FNO)

7.  LIVE SERVICE
    Customer uses fiber
    → Usage tracking (data, speed tests)
    → Billing cycle (invoices, payments)
    → Support tickets (fault logging, tracking)
    → Self-service portal (statements, PoP, usage)

8.  SERVICE MANAGEMENT
    Upgrade package → new subscription, old cancelled
    Downgrade package → prorated billing
    Pause service → subscription paused (tenure preserved)
    Moving house → new address, coverage check, technician visit

9.  CANCELLATION (Complex)
    Customer initiates cancel
    → Journey engine evaluates (retention offers)
    → If proceeds: early termination fee calculation
    → Router return (reverse logistics) OR router charge
    → FNO cancellation (browser automation for FNOs without API)
    → Subscription cancelled, final invoice generated

10. POST-CANCELLATION
    Router return tracking
    Refund processing (if applicable)
    Win-back campaigns (retention)
```

## New Tables Required

### Core (replace/augment existing)
- `customers` — keep CRM version as master, add: preferred_contact_channel, referral_code
- `customer_addresses` — service_address, physical_address, GPS coordinates, coverage_area_id
- `customer_subscriptions` — links customer→package→address (enhance existing subscriptions)

### New Journey Tables
- `coverage_areas` — FNO coverage by area, technology, status
- `orders` — full order lifecycle
- `order_items` — line items per order
- `delivery_tracking` — courier, tracking, status per order
- `technician_visits` — dispatch, ETA, GPS tracking, completion, notes
- `payment_methods` — stored payment instruments per customer
- `promotions` — promo codes, referral programs, discounts
- `customer_promotions` — which customer used which promo
- `announcements` — service notifications by area/segment
- `activity_timeline` — unified event log (all touchpoints)

### Cancellation & Reverse Logistics
- `cancellation_requests` — cancel reason, type (voluntary/move/death), status
- `termination_fees` — calculated ETF, router charge, outstanding balance
- `router_returns` — IMEI/serial, condition, return tracking, refund amount
- `fno_cancellations` — FNO portal automation status, reference numbers

## Service Architecture Changes

### Enhanced Services
1. **crm** — Add: coverage check, address management, referral tracking
2. **sales** — Add: order management, checkout flow, payment processing
3. **billing** — Add: ETF calculation, proration, pause billing
4. **support** — Add: ticket→subscription link, self-service portal endpoints
5. **journey_engine** — Add: move-house journey, pause journey (new trigger types)
6. **agent-orchestrator** — Add: FNO browser automation for cancellations

### New Service
7. **customer_journey** — Orchestrates the full lifecycle:
   - Coverage checking
   - Order/checkout/delivery
   - Technician dispatch & tracking
   - Activity timeline aggregation
   - Announcements
   - Promotions & referrals

## Key Business Rules

### Early Termination Fee (ETF)
```
ETF = max(0, remaining_contract_months × monthly_rate × penalty_percentage)
penalty_percentage: 100% if < 6 months remaining, 75% if 6-12 months, 50% if > 12 months
Router charge (if not returned): router_value × depreciation_factor
Depreciation: 100% if < 12 months, 75% if 12-24 months, 50% if > 24 months
Total ETF = ETF + router_charge + outstanding_balance
```

### Moving House
```
1. Customer initiates move
2. New address coverage check
3. If covered: schedule installation at new address, transfer service
4. If not covered: offer alternatives or cancel with reduced ETF
5. Technician visit for new installation
6. Old address service cancelled, new subscription activated
```

### Pause Service
```
1. Customer requests pause (max 3 months)
2. Subscription status → PAUSED
3. Billing suspended (minimum monthly fee may apply)
4. Auto-reactivate after pause period
5. Tenure preserved (contract clock doesn't advance)
```

### FNO Cancellation (Browser Automation)
```
1. System determines FNO (from subscription)
2. If FNO has API → direct API call
3. If no API → agent-orchestrator opens FNO portal
4. Logs in with ISP credentials
5. Navigates to cancellation flow
6. Submits cancellation request
7. Captures reference number
8. Updates fno_cancellations table
```

## Implementation Order
1. New tables (models + migrations)
2. Coverage check endpoints
3. Order/checkout/delivery endpoints
4. Technician visit endpoints
5. Cancellation flow (ETF calc + FNO automation)
6. Pause/move-house journeys
7. Self-service portal endpoints
8. Activity timeline aggregation
9. Promotions & announcements
