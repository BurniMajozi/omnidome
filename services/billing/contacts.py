"""Customer contact lookup (email) shared by Paystack initialization and dunning."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from services.common.http_client import service_get
from services.billing import finance_posting as fp
from services.billing.database import get_session
from services.billing.models import BillingAccount

logger = logging.getLogger("billing.contacts")


async def resolve_customer_email(tenant_id: uuid.UUID, customer_id: uuid.UUID,
                                 billing_account_id: Optional[uuid.UUID] = None) -> Optional[str]:
    """The customer's email from billing's account, else from the CRM record. Never from a client."""
    if billing_account_id:
        with get_session() as session:
            acct = session.query(BillingAccount).filter(
                BillingAccount.id == billing_account_id, BillingAccount.tenant_id == tenant_id).first()
            if acct is not None and acct.billing_email:
                return acct.billing_email
    try:
        data = await service_get("crm", f"/customers/{customer_id}", tenant_id=tenant_id,
                                 user_id=uuid.UUID(fp.service_user_id()), timeout=5.0)
        email = data.get("email") if isinstance(data, dict) else None
        return email if isinstance(email, str) and "@" in email else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("customer email lookup failed for %s: %s", customer_id, type(exc).__name__)
        return None
