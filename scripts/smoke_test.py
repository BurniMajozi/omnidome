"""OmniDome Integration Smoke Tests.

Tests cross-service workflows end-to-end through the gateway:
1. Create contact → verify CRM
2. Create lead → convert to deal → verify lifecycle
3. Create ticket → accept → start → resolve
4. Check parts → checkout → verify stock movement
5. Create employee → performance review → attrition check
6. Create RICA session → check status
7. Create finance record → verify overview

Usage: python -m scripts.smoke_test
"""

import asyncio
import os
import sys
import uuid

try:
    import httpx
except ImportError:
    print("pip install httpx")
    sys.exit(1)

GATEWAY_URL = os.getenv("OMNIDOME_GATEWAY_URL", "http://localhost:8000")
TENANT_ID = os.getenv("SMOKE_TENANT_ID", "11111111-1111-1111-1111-111111111111")

HEADERS = {
    "X-Tenant-ID": TENANT_ID,
    "X-Dev-Email": "smoke@demo.local",
    "Content-Type": "application/json",
}

PASSED = 0
FAILED = 0


def report(name: str, ok: bool, detail: str = ""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED += 1
        print(f"  ❌ {name}: {detail}")


async def test_contact_crud(client: httpx.AsyncClient):
    """Test 1: Create contact → verify."""
    print("\n── Test 1: Contact CRUD ──")
    contact_id = str(uuid.uuid4())
    r = await client.post(f"{GATEWAY_URL}/api/sales/contacts", json={
        "id": contact_id,
        "first_name": "Smoke",
        "last_name": "Test",
        "email": f"smoke-{contact_id[:8]}@test.local",
        "phone": "0820000001",
        "physical_address": "123 Test St, Johannesburg",
        "city": "Johannesburg",
        "province": "Gauteng",
        "postal_code": "2000",
    }, headers=HEADERS)
    report("Create contact", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        r = await client.get(f"{GATEWAY_URL}/api/sales/contacts/{contact_id}", headers=HEADERS)
        report("Get contact", r.status_code < 400 and r.json().get("first_name") == "Smoke")

    return contact_id


async def test_lead_to_deal(client: httpx.AsyncClient):
    """Test 2: Create lead → convert to deal."""
    print("\n── Test 2: Lead → Deal ──")
    r = await client.post(f"{GATEWAY_URL}/api/sales/leads", json={
        "first_name": "Lead",
        "last_name": "Test",
        "email": f"lead-{uuid.uuid4().hex[:8]}@test.local",
        "phone": "0820000002",
        "source": "SMOKE_TEST",
        "interest_level": 4,
    }, headers=HEADERS)
    report("Create lead", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        lead_id = r.json().get("id")
        r = await client.post(f"{GATEWAY_URL}/api/sales/leads/{lead_id}/convert", json={
            "name": "Smoke Test Deal",
            "value_zar": "999",
        }, headers=HEADERS)
        report("Convert lead to deal", r.status_code < 400, f"status={r.status_code}")
    else:
        report("Convert lead to deal", False, "skipped (lead creation failed)")


async def test_ticket_lifecycle(client: httpx.AsyncClient, contact_id: str):
    """Test 3: Create ticket → accept → start → resolve."""
    print("\n── Test 3: Ticket Lifecycle ──")
    r = await client.post(f"{GATEWAY_URL}/api/support/tickets", json={
        "customer_id": contact_id,
        "subject": "Smoke Test Ticket",
        "description": "Integration test ticket",
        "category": "SMOKE_TEST",
        "priority": "NORMAL",
    }, headers=HEADERS)
    report("Create ticket", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        ticket_id = r.json().get("id")

        r = await client.post(f"{GATEWAY_URL}/api/support/tickets/{ticket_id}/accept", headers=HEADERS)
        report("Accept ticket", r.status_code < 400, f"status={r.status_code}")

        r = await client.post(f"{GATEWAY_URL}/api/support/tickets/{ticket_id}/start", headers=HEADERS)
        report("Start ticket", r.status_code < 400, f"status={r.status_code}")

        r = await client.post(f"{GATEWAY_URL}/api/support/tickets/{ticket_id}/resolve", json={
            "resolution_notes": "Smoke test resolution",
            "fcr": True,
        }, headers=HEADERS)
        report("Resolve ticket", r.status_code < 400, f"status={r.status_code}")
    else:
        report("Accept ticket", False, "skipped")
        report("Start ticket", False, "skipped")
        report("Resolve ticket", False, "skipped")


async def test_inventory_checkout(client: httpx.AsyncClient):
    """Test 4: Check parts → checkout."""
    print("\n── Test 4: Inventory Checkout ──")
    r = await client.get(f"{GATEWAY_URL}/api/inventory/stock?sku=ONT-V1", headers=HEADERS)
    report("Check stock", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        items = r.json()
        if items:
            product_id = items[0].get("id") or items[0].get("product_id")
            r = await client.post(f"{GATEWAY_URL}/api/inventory/stock/checkout", json={
                "job_id": str(uuid.uuid4()),
                "items": [{"product_id": product_id, "quantity": 1}],
            }, headers=HEADERS)
            report("Checkout stock", r.status_code < 400, f"status={r.status_code}")
        else:
            report("Checkout stock", False, "no stock items found")
    else:
        report("Checkout stock", False, "skipped")


async def test_hr_employee(client: httpx.AsyncClient):
    """Test 5: Create employee → performance review."""
    print("\n── Test 5: HR Employee ──")
    r = await client.post(f"{GATEWAY_URL}/api/hr/employees", json={
        "employee_id": f"SMK-{uuid.uuid4().hex[:4].upper()}",
        "full_name": "Smoke Test Employee",
        "job_title": "QA Engineer",
        "department": "Engineering",
        "email": f"smoke-{uuid.uuid4().hex[:8]}@test.local",
        "phone": "0820000003",
    }, headers=HEADERS)
    report("Create employee", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        emp_id = r.json().get("id")
        r = await client.post(f"{GATEWAY_URL}/api/hr/employees/{emp_id}/performance", json={
            "review_period": "2026-Q2",
            "tickets_resolved": 42,
            "avg_resolution_time": 35,
            "fcr_rate": 85.0,
            "kpi_score": 8.5,
            "sentiment_score": 0.82,
            "attrition_risk": "LOW",
        }, headers=HEADERS)
        report("Create performance review", r.status_code < 400, f"status={r.status_code}")
    else:
        report("Create performance review", False, "skipped")


async def test_rica_session(client: httpx.AsyncClient, contact_id: str):
    """Test 6: Create RICA session → check status."""
    print("\n── Test 6: RICA Session ──")
    r = await client.post(f"{GATEWAY_URL}/api/rica/sessions", json={
        "contact_id": contact_id,
        "verification_type": "DOCUMENT_VERIFICATION",
    }, headers=HEADERS)
    report("Create RICA session", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        job_id = r.json().get("job_id")
        r = await client.get(f"{GATEWAY_URL}/api/rica/status/{job_id}", headers=HEADERS)
        report("Check RICA status", r.status_code < 400, f"status={r.status_code}")
    else:
        report("Check RICA status", False, "skipped")


async def test_finance_gl(client: httpx.AsyncClient):
    """Test 7: GL Journal Entries → Trial Balance → Cash Flow."""
    print("\n── Test 7: Finance GL ──")

    # Create a balanced journal entry
    r = await client.post(f"{GATEWAY_URL}/api/finance/journal-entries", json={
        "entry_date": "2026-06-01",
        "reference": "SMOKE-001",
        "description": "Smoke test revenue entry",
        "source": "MANUAL",
        "lines": [
            {"account_code": "1100", "account_name": "Accounts Receivable",
             "debit": 50000, "credit": 0, "description": "Test AR"},
            {"account_code": "4000", "account_name": "Revenue - FTTH Subscriptions",
             "debit": 0, "credit": 50000, "description": "Test revenue"},
        ],
    }, headers=HEADERS)
    report("Create journal entry", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        entry_id = r.json().get("id")
        r = await client.post(
            f"{GATEWAY_URL}/api/finance/journal-entries/{entry_id}/post",
            headers=HEADERS,
        )
        report("Post journal entry", r.status_code < 400, f"status={r.status_code}")

    # List journal entries
    r = await client.get(f"{GATEWAY_URL}/api/finance/journal-entries", headers=HEADERS)
    report("List journal entries", r.status_code < 400, f"status={r.status_code}")

    # Trial balance
    r = await client.get(f"{GATEWAY_URL}/api/finance/trial-balance", headers=HEADERS)
    report("Trial balance", r.status_code < 400, f"status={r.status_code}")
    if r.status_code < 400:
        tb = r.json()
        report(
            "Trial balance balanced",
            tb.get("is_balanced", False),
            f"debits={tb.get('total_debits')}, credits={tb.get('total_credits')}",
        )

    # Cash flow statement
    r = await client.get(f"{GATEWAY_URL}/api/finance/cash-flow", headers=HEADERS)
    report("Cash flow statement", r.status_code < 400, f"status={r.status_code}")

    # Financial statements
    r = await client.get(f"{GATEWAY_URL}/api/finance/statements", headers=HEADERS)
    report("Financial statements", r.status_code < 400, f"status={r.status_code}")

    # Overview
    r = await client.get(f"{GATEWAY_URL}/api/finance/overview", headers=HEADERS)
    report("Finance overview", r.status_code < 400, f"status={r.status_code}")


async def test_gateway_health(client: httpx.AsyncClient):
    """Test 8: Gateway health check aggregation."""
    print("\n── Test 8: Gateway Health ──")
    r = await client.get(f"{GATEWAY_URL}/health", headers=HEADERS)
    report("Gateway health", r.status_code < 400, f"status={r.status_code}")

    if r.status_code < 400:
        data = r.json()
        services = data.get("services", {})
        up_count = sum(1 for s in services.values() if s.get("status") == "up")
        print(f"  ℹ️  {up_count}/{len(services)} services up")


async def main():
    global PASSED, FAILED
    print(f"═══ OmniDome Integration Smoke Tests ═══")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Tenant:  {TENANT_ID}")

    async with httpx.AsyncClient(timeout=15) as client:
        # Verify gateway is reachable
        try:
            r = await client.get(f"{GATEWAY_URL}/health")
            if r.status_code >= 400:
                print(f"❌ Gateway health check failed: {r.status_code}")
                sys.exit(1)
            print(f"✅ Gateway reachable")
        except Exception as e:
            print(f"❌ Cannot reach gateway: {e}")
            sys.exit(1)

        contact_id = await test_contact_crud(client)
        await test_lead_to_deal(client)
        await test_ticket_lifecycle(client, contact_id)
        await test_inventory_checkout(client)
        await test_hr_employee(client)
        await test_rica_session(client, contact_id)
        await test_finance_gl(client)
        await test_gateway_health(client)

    print(f"\n═══ Results: {PASSED} passed, {FAILED} failed ═══")
    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
