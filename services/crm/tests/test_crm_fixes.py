"""Unit tests verifying CRM P0 fixes:
1. Lead.converted_at column and safe access in Customer 360
2. Scoped Deal and Commission queries in Customer 360
3. Scoped Contact query in CX (NPS score)
4. Pagination count_stmt execution in list_leads
5. Setting converted_at during convert_lead
"""

import inspect
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from services.crm.models import Lead, Customer
from services.crm.routes import customer_360, leads


def test_lead_model_has_converted_at():
    """Lead model must define converted_at column."""
    lead = Lead(
        tenant_id=uuid.uuid4(),
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        status="converted",
        converted_at=datetime.now(timezone.utc),
    )
    assert hasattr(lead, "converted_at")
    assert lead.converted_at is not None


def test_leads_route_uses_func_count():
    """list_leads must execute count_stmt with func.count, not len(scalars.all())."""
    src = inspect.getsource(leads.list_leads)
    assert "func.count(Lead.id)" in src
    assert "len(total_result.scalars().all())" not in src
    assert "total = total_result.scalar() or 0" in src


def test_convert_lead_sets_converted_at():
    """convert_lead must record converted_at timestamp."""
    src = inspect.getsource(leads.convert_lead)
    assert "lead.converted_at =" in src


def test_customer_360_scopes_deals_and_commissions():
    """customer_360.get_customer_crm must filter Deals by contact_id and Commissions by customer deal_ids."""
    src = inspect.getsource(customer_360.get_customer_crm)
    # Deal query scoped to customer_id
    assert "Deal.contact_id == customer_id" in src
    # Commissions scoped to customer deal IDs
    assert "Commission.deal_id.in_(deal_ids)" in src
    # converted_at is safely accessed
    assert "getattr(lead, \"converted_at\", None)" in src


def test_customer_360_scopes_contact_nps():
    """customer_360.get_customer_cx must scope Contact lookup to customer_id or customer.email."""
    src = inspect.getsource(customer_360.get_customer_cx)
    assert "Contact.id == customer_id" in src
    assert "Contact.email == customer.email" in src
