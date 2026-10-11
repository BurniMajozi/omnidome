"""Freeze real billing parties; incomplete documents are explicitly pro forma."""
import os
from decimal import Decimal
from sqlalchemy import text

DDL = ["CREATE SEQUENCE IF NOT EXISTS platform_invoice_number_seq",
       """CREATE TABLE IF NOT EXISTS platform_invoice_supplier (
         singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), profile jsonb NOT NULL,
         actor_id uuid, updated_at timestamptz NOT NULL DEFAULT now())""",
       "ALTER TABLE platform_invoice_supplier ALTER COLUMN actor_id DROP NOT NULL"]

async def tax_policy(db):
    from services.common.platform_pricing import catalog
    profile = (await db.execute(text("SELECT profile FROM platform_invoice_supplier WHERE singleton=true"))).scalar_one_or_none() or catalog()["supplier"]
    return {"vat_registered":profile.get("vat_registered",False),"prices_include_vat":profile.get("prices_include_vat",True),"rate":catalog()["tax_policy"]["rate"]}

async def snapshot(db, tenant, priced):
    supplier = (await db.execute(text("SELECT profile FROM platform_invoice_supplier WHERE singleton=true"))).scalar_one_or_none()
    supplier = supplier or {"name":os.getenv("PLATFORM_SUPPLIER_NAME", ""),"address":os.getenv("PLATFORM_SUPPLIER_ADDRESS", ""),"vat_number":os.getenv("PLATFORM_SUPPLIER_VAT_NUMBER", "")}
    customer = dict((tenant.get("settings") or {}).get("platform_billing") or {})
    customer.setdefault("name", tenant.get("name", ""))
    complete = bool(supplier.get("name") and supplier.get("address") and
                    (Decimal(priced["vat_zar"]) == 0 or supplier.get("vat_number")))
    if priced.get("vat_registered") and Decimal(priced["total_zar"]) > 5000:
        complete = complete and bool(customer.get("name") and customer.get("address") and
                                     (not customer.get("vat_registered") or customer.get("vat_number")))
    return {"supplier":supplier,"customer":customer,"document_type":("Tax invoice" if priced.get("vat_registered") else "Invoice") if complete else "Pro forma invoice",
            "complete":complete}
