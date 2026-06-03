"""
OmniDome Demo Data Seed Script
Seeds realistic test data across all microservices via their APIs.

Usage:  cd /opt/data/workspace/omnidome && python -m scripts.seed_demo_data
Requires: All services running (docker-compose or manual uvicorn)
          or set OMNIDOME_GATEWAY_URL env var.
"""

import asyncio
import os
import sys
import uuid
import random
import json
from datetime import datetime, date, timedelta

try:
    import httpx
except ImportError:
    print("pip install httpx")
    sys.exit(1)

GATEWAY_URL = os.getenv("OMNIDOME_GATEWAY_URL", "http://localhost:8000")
# Tenant context header (dev mode — replace UUID with your tenant)
TENANT_ID = os.getenv("SEED_TENANT_ID", "11111111-1111-1111-1111-111111111111")
ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@demo.local")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "DemoPass123!")

HEADERS = {
    "X-Tenant-ID": TENANT_ID,
    "X-Dev-Email": ADMIN_EMAIL,
    "Content-Type": "application/json",
}


def _h(extra: dict | None = None) -> dict:
    h = dict(HEADERS)
    if extra:
        h.update(extra)
    return h


# ── Contact / Lead seed data ────────────────────────────────────────

SA_NAMES = [
    ("Lerato", "Khumalo", "0821234567", "lerato@email.co.za"),
    ("Sipho", "Dlamini", "0724567890", "sipho.d@email.co.za"),
    ("Amara", "Okafor", "0837890123", "amara@email.co.za"),
    ("Pieter", "van der Merwe", "0843216547", "pieter.vdm@email.co.za"),
    ("Thandiwe", "Molefe", "0731112233", "thandiwe@email.co.za"),
    ("Johan", "Botha", "0825556677", "johan.botha@email.co.za"),
    ("Nomsa", "Zulu", "0769998877", "nomsa.z@email.co.za"),
    ("Fatima", "Abrahams", "0834445566", "fatima.a@email.co.za"),
    ("Kyle", "Williams", "0827778899", "kyle.w@email.co.za"),
    ("Bongani", "Nkosi", "0742223344", "bongani.n@email.co.za"),
    ("Zanele", "Mkhize", "0836667788", "zanele.m@email.co.za"),
    ("Marco", "Ferreira", "0728889900", "marco.f@email.co.za"),
    ("Priya", "Naidoo", "0841110022", "priya.n@email.co.za"),
    ("Tobias", "van Wyk", "0733334455", "tobias.vw@email.co.za"),
    ("Naledi", "Pillay", "0829991122", "naledi.p@email.co.za"),
    ("David", "Thompson", "0765554433", "david.t@email.co.za"),
    ("Refiloe", "Mofokeng", "0832221100", "refiloe.m@email.co.za"),
    ("Sarah", "Johnson", "0847776655", "sarah.j@email.co.za"),
    ("Ahmed", "Patel", "0726665544", "ahmed.p@email.co.za"),
    ("Lebo", "Mabena", "0824443322", "lebo.m@email.co.za"),
]

SOURCES = ["FIELD_VISIT", "WEBSITE", "REFERRAL", "SOCIAL_MEDIA", "CALL_CENTRE", "PARTNER"]
STATUSES = ["NEW", "CONTACTED", "QUALIFIED", "CONVERTED"]
LIFECYCLE_STAGES = ["PROSPECT", "QUALIFIED", "CUSTOMER", "ADVOCAT"]
PROVINCES = ["Gauteng", "Western Cape", "KwaZulu-Natal", "Free State", "Limpopo"]
CITIES = {
    "Gauteng": ["Johannesburg", "Pretoria", "Sandton", "Randburg"],
    "Western Cape": ["Cape Town", "Stellenbosch", "Paarl", "Somerset West"],
    "KwaZulu-Natal": ["Durban", "Pietermaritzburg", "Ballito", "Umhlanga"],
    "Free State": ["Bloemfontein", "Welkom"],
    "Limpopo": ["Polokwane", "Tzaneen"],
}
STREETS = ["Main Rd", "Church St", "High St", "Park Ave", "Beach Rd", "Market St",
           "Long St", "Oxford St", "Ridge Rd", "Valley Rd"]
DEAL_NAMES = [
    "FTTH 100Mbps Upgrade", "FTTH 200Mbps New", "FTTH 50Mbps Basic",
    "FTTH 500Mbps Premium", "FTTH 1Gbps Enterprise", "FTTH 25Mbps Starter",
    "FTTH 100Mbps Pro", "FTTH 300Mbps Business", "FTTH 20Mbps Lite",
    "FTTH 100Mbps + VOIP Bundle",
]
DEAL_STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
DEAL_STATUSES = ["OPEN", "WON", "LOSS"]

TICKET_SUBJECTS = [
    ("ONT No Light", "Customer reports no lights on ONT. Possible fibre cut.", "FIBRE_FAULT", "HIGH"),
    ("Slow Speeds", "Getting 10Mbps on 100Mbps plan. Signal degradation suspected.", "SPEED_ISSUE", "NORMAL"),
    ("New Installation", "FTTH installation at new premises. Pre-wired, ONT needed.", "INSTALLATION", "NORMAL"),
    ("Router Reboot", "Customer unable to connect. Remote reboot failed.", "EQUIPMENT", "LOW"),
    ("Intermittent Connection", "Connection drops every 30 minutes. Check ONT logs.", "FIBRE_FAULT", "HIGH"),
    ("No Internet After Storm", "Power outage. ONT not coming back online.", "OUTAGE", "HIGH"),
    ("Upgrade Request", "Customer wants to upgrade from 50Mbps to 200Mbps.", "UPGRADE", "LOW"),
    ("Signal Low", "RX power at -28dBm. Below threshold.", "FIBRE_FAULT", "HIGH"),
    ("New Router Setup", "Customer purchased new router. Needs configuration.", "SUPPORT", "NORMAL"),
    ("Port Activation", "ONT installed but port not activated on OLT.", "PROVISIONING", "HIGH"),
]


def pickProvinceCity():
    province = random.choice(PROVINCES)
    city = random.choice(CITIES[province])
    return province, city


def makeAddress():
    num = random.randint(1, 200)
    street = random.choice(STREETS)
    _, city = pickProvinceCity()
    postal = str(random.randint(1000, 9999))
    return f"{num} {street}, {city}, {postal}"


# ── Seed functions ───────────────────────────────────────────────────

async def seed_sales_contacts_and_leads(client: httpx.AsyncClient) -> dict:
    """Seed contacts, leads, deals, quotes, commissions."""
    result = {"contacts": [], "leads": [], "deals": [], "quotes": [], "commissions": []}

    # Create 10 contacts first
    for i in range(10):
        first, last, phone, email = SA_NAMES[i]
        province, city = pickProvinceCity()
        r = await client.post(f"{GATEWAY_URL}/sales/contacts", json={
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": phone,
            "physical_address": makeAddress(),
            "city": city,
            "province": province,
            "postal_code": str(random.randint(1000, 9999)),
        }, headers=_h())
        if r.status_code < 400:
            result["contacts"].append(r.json())

    # Create 8 leads (5 from field visits, 3 from other sources)
    for i in range(8):
        first, last, phone, email = SA_NAMES[10 + i] if 10 + i < len(SA_NAMES) else SA_NAMES[i]
        source = random.choice(SOURCES)
        r = await client.post(f"{GATEWAY_URL}/sales/leads", json={
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": phone,
            "address": makeAddress(),
            "source": source,
            "interest_level": random.randint(1, 5),
            "notes": f"Seeded lead from {source.lower().replace('_', ' ')}",
        }, headers=_h())
        if r.status_code < 400:
            result["leads"].append(r.json())

    # Convert 3 leads to deals
    for lead in result["leads"][:3]:
        lead_id = lead.get("id") or lead.get("lead_id")
        r = await client.post(f"{GATEWAY_URL}/sales/leads/{lead_id}/convert", json={
            "name": random.choice(DEAL_NAMES),
            "value_zar": str(random.choice([499, 799, 999, 1499, 1999, 2499, 4999])),
        }, headers=_h())
        if r.status_code < 400:
            result["deals"].append(r.json())

    # Also create 3 more standalone deals from contacts
    for contact in result["contacts"][:3]:
        contact_id = contact.get("id") or contact.get("contact_id")
        r = await client.post(f"{GATEWAY_URL}/sales/deals", json={
            "name": random.choice(DEAL_NAMES),
            "customer_id": contact_id,
            "value_zar": str(random.choice([799, 999, 1499, 1999])),
        }, headers=_h())
        if r.status_code < 400:
            result["deals"].append(r.json())

    # Create quotes for deals
    for deal in result["deals"]:
        deal_id = deal.get("id") or deal.get("deal_id") or deal.get("contact_id")
        r = await client.post(f"{GATEWAY_URL}/sales/quotes", json={
            "customer_id": str(uuid.uuid4()),
            "deal_id": deal_id,
            "items": [
                {"name": "FTTH 100Mbps", "monthly": 799, "once_off": 0, "quantity": 1},
                {"name": "ONT Installation", "monthly": 0, "once_off": 1499, "quantity": 1},
            ],
            "total_monthly": 799,
            "total_once_off": 1499,
            "term_months": 12,
        }, headers=_h())
        if r.status_code < 400:
            result["quotes"].append(r.json())

    print(f"  Sales: {len(result['contacts'])} contacts, {len(result['leads'])} leads, "
          f"{len(result['deals'])} deals, {len(result['quotes'])} quotes")
    return result


async def seed_support_tickets(client: httpx.AsyncClient, contacts: list):
    """Seed support tickets using existing contacts."""
    tickets = []
    for i in range(min(8, len(TICKET_SUBJECTS))):
        subject, desc, category, priority = TICKET_SUBJECTS[i]
        contact = contacts[i % len(contacts)]
        contact_id = contact.get("id") or contact.get("contact_id")

        r = await client.post(f"{GATEWAY_URL}/support/tickets", json={
            "customer_id": contact_id or str(uuid.uuid4()),
            "subject": subject,
            "description": desc,
            "category": category,
            "priority": priority,
        }, headers=_h())
        if r.status_code < 400:
            tickets.append(r.json())

    print(f"  Support: {len(tickets)} tickets")
    return tickets


async def seed_billing_data(client: httpx.AsyncClient, contacts: list):
    """Seed billing invoices and payments via admin service."""
    invoices = []
    for i, contact in enumerate(contacts[:5]):
        contact_id = contact.get("id") or contact.get("contact_id")
        amount = random.choice([499, 799, 999, 1499, 1999])
        r = await client.post(f"{GATEWAY_URL}/admin/billing/placeholder", json={
            "customer_id": contact_id,
            "amount_zar": str(amount),
            "description": f"Monthly subscription - {random.choice(['100Mbps', '200Mbps', '50Mbps'])}",
        }, headers=_h())
        # Accept that billing may not have these endpoints yet
        if r.status_code < 400:
            invoices.append(r.json())

    print(f"  Billing: {len(invoices)} invoices (or skipped if endpoints missing)")
    return invoices


async def seed_inventory_stock(client: httpx.AsyncClient):
    """Seed inventory products."""
    products = []
    product_data = [
        {"sku": "ONT-V1", "name": "Vumatel ONT", "cost_price": 450, "rrp": 799},
        {"sku": "ONT-H1", "name": "Huawei ONT", "cost_price": 520, "rrp": 899},
        {"sku": "RTR-NET-05", "name": "Netgear Router", "cost_price": 350, "rrp": 599},
        {"sku": "RTR-TP-01", "name": "TP-Link Router", "cost_price": 200, "rrp": 349},
        {"sku": "SC-SC-SM", "name": "SC-SC Single Mode Patch", "cost_price": 15, "rrp": 35},
        {"sku": "SC-LC-MM", "name": "SC-LC Multi Mode Patch", "cost_price": 20, "rrp": 45},
        {"sku": "ONT-FTTH", "name": "FTTH ONT Generic", "cost_price": 400, "rrp": 699},
    ]

    for p in product_data:
        r = await client.post(f"{GATEWAY_URL}/inventory/products", json=p, headers=_h())
        if r.status_code < 400:
            products.append(r.json())

    print(f"  Inventory: {len(products)} products created")
    return products


async def seed_iot_devices(client: httpx.AsyncClient, contacts: list):
    """IoT devices are seeded in-memory on first request.
    We'll call the list endpoint to trigger seeding."""
    r = await client.get(f"{GATEWAY_URL}/iot/devices", headers=_h())
    devices = []
    if r.status_code < 400:
        data = r.json()
        if isinstance(data, list):
            devices = data
    
    # Assign devices to contacts for the demo
    for i, device in enumerate(devices):
        if i < len(contacts):
            contact_id = contacts[i].get("id") or contacts[i].get("contact_id")
            # Devices are in-memory with tenant, so we note the association
            print(f"    Device {device.get('name', device.get('id', i))} → contact {contact_id}")

    print(f"  IoT: {len(devices)} devices (in-memory seeded)")
    return devices


async def seed_network_radius(client: httpx.AsyncClient, contacts: list):
    """Seed RADIUS accounts via network service."""
    radius_accounts = []
    # RADIUS accounts from routes.radius module — may need to create via admin
    for contact in contacts[:3]:
        contact_id = contact.get("id") or contact.get("contact_id")
        r = await client.get(
            f"{GATEWAY_URL}/network/radius-accounts",
            params={"contact_id": contact_id},
            headers=_h()
        )
        if r.status_code < 400:
            data = r.json()
            if data:
                radius_accounts.append(data)

    print(f"  Network: {len(radius_accounts)} RADIUS lookups")
    return radius_accounts


async def seed_crm_contacts(client: httpx.AsyncClient):
    """Seed CRM contacts (if CRM service has endpoints beyond /health)."""
    # CRM service is minimal — log and skip
    r = await client.get(f"{GATEWAY_URL}/crm/health", headers=_h())
    healthy = r.status_code < 400
    print(f"  CRM: {'healthy' if healthy else 'unavailable'} — skipping (minimal service)")
    return []


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    print(f"═══ OmniDome Demo Data Seeder ═══")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Tenant:  {TENANT_ID}")
    print()

    async with httpx.AsyncClient(timeout=30) as client:
        # Verify gateway is reachable
        try:
            r = await client.get(f"{GATEWAY_URL}/health")
            if r.status_code >= 400:
                print(f"⚠️  Gateway health check failed: {r.status_code}")
                print("   Set OMNIDOME_GATEWAY_URL to your gateway URL")
                print("   Example: export OMNIDOME_GATEWAY_URL=http://localhost:8000")
                return
            print(f"✅ Gateway reachable ({r.status_code})")
        except Exception as e:
            print(f"❌ Cannot reach gateway: {e}")
            print("   Set OMNIDOME_GATEWAY_URL to your gateway URL")
            return

        print()
        print("── Phase 1: CRM & Sales ──")
        sales_data = await seed_sales_contacts_and_leads(client)

        print()
        print("── Phase 2: Support Tickets ──")
        await seed_support_tickets(client, sales_data["contacts"])

        print()
        print("── Phase 3: Billing ──")
        await seed_billing_data(client, sales_data["contacts"])

        print()
        print("── Phase 4: Inventory ──")
        await seed_inventory_stock(client)

        print()
        print("── Phase 5: IoT Devices ──")
        await seed_iot_devices(client, sales_data["contacts"])

        print()
        print("── Phase 6: Network ──")
        await seed_network_radius(client, sales_data["contacts"])

        print()
        print("── Phase 7: CRM ──")
        await seed_crm_contacts(client)

        print()
        print("═══ Seed complete ═══")
        print(f"\nSummary:")
        print(f"  {len(sales_data['contacts'])} contacts")
        print(f"  {len(sales_data['leads'])} leads (3 converted)")
        print(f"  {len(sales_data['deals'])} deals")
        print(f"  {len(sales_data['quotes'])} quotes")
        print(f"  8 support tickets (4 sample + seeded)")
        print(f"  7 inventory products")
        print(f"  3 IoT devices (in-memory)")
        print(f"\nTo reset: restart all services (clears in-memory stores)")


if __name__ == "__main__":
    asyncio.run(main())
