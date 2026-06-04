"""Data migration: consolidate duplicate customer/contact tables.

Migrates:
1. Sales contacts → CRM customers (if not already in CRM)
2. Sales leads → CRM leads (deduplicate by email/phone)
3. Updates deals.contact_id → deals.customer_id
4. Updates tickets to reference subscriptions

Run once during deployment: python3 scripts/migrate_customer_data.py
"""

import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.common.db import get_engine
from services.crm.models import Customer as CRMCustomer, Lead as CRMLead
from services.sales.models import Contact as SalesContact, Lead as SalesLead, Deal
from services.support.database import Ticket
from services.billing.models import Subscription


def migrate_contacts_to_customers(tenant_id: str):
    """Migrate Sales contacts that don't exist in CRM."""
    engine = get_engine()
    tid = uuid.UUID(tenant_id)

    with Session(engine) as session:
        # Get all sales contacts
        contacts = session.query(SalesContact).filter(
            SalesContact.tenant_id == tid
        ).all()

        migrated = 0
        for contact in contacts:
            # Check if customer already exists in CRM
            existing = session.query(CRMCustomer).filter(
                CRMCustomer.tenant_id == tid,
                CRMCustomer.email == contact.email,
            ).first()

            if not existing and contact.email:
                # Create CRM customer from sales contact
                customer = CRMCustomer(
                    tenant_id=tid,
                    first_name=contact.first_name,
                    last_name=contact.last_name,
                    email=contact.email,
                    phone=contact.phone,
                    id_number=contact.rica_id_number,
                    address=contact.physical_address,
                    city=contact.city,
                    province=contact.province,
                    rica_verified=contact.rica_verified,
                    status="active",
                )
                session.add(customer)
                migrated += 1

        session.commit()
        print(f"Migrated {migrated} contacts → customers.")
        return migrated


def migrate_leads(tenant_id: str):
    """Deduplicate and migrate sales leads to CRM leads."""
    engine = get_engine()
    tid = uuid.UUID(tenant_id)

    with Session(engine) as session:
        sales_leads = session.query(SalesLead).filter(
            SalesLead.tenant_id == tid
        ).all()

        migrated = 0
        for sl in sales_leads:
            existing = session.query(CRMLead).filter(
                CRMLead.tenant_id == tid,
                CRMLead.email == sl.email,
            ).first()

            if not existing and sl.email:
                crm_lead = CRMLead(
                    tenant_id=tid,
                    source=sl.source or "field_visit",
                    first_name=sl.first_name,
                    last_name=sl.last_name,
                    email=sl.email,
                    phone=sl.phone,
                    address=sl.address,
                    status=sl.status if sl.status in ["new", "contacted", "qualified", "converted", "lost"] else "new",
                    assigned_to=sl.agent_id,
                    notes=sl.notes,
                )
                session.add(crm_lead)
                migrated += 1

        session.commit()
        print(f"Migrated {migrated} sales leads → CRM leads.")
        return migrated


def update_deals_references(tenant_id: str):
    """Update deals to reference CRM customers instead of sales contacts."""
    engine = get_engine()
    tid = uuid.UUID(tenant_id)

    with Session(engine) as session:
        deals = session.query(Deal).filter(
            Deal.tenant_id == tid
        ).all()

        updated = 0
        for deal in deals:
            if deal.contact_id:
                # Find matching CRM customer
                contact = session.query(SalesContact).filter(
                    SalesContact.id == deal.contact_id,
                    SalesContact.tenant_id == tid,
                ).first()

                if contact and contact.email:
                    customer = session.query(CRMCustomer).filter(
                        CRMCustomer.tenant_id == tid,
                        CRMCustomer.email == contact.email,
                    ).first()

                    if customer:
                        # Add customer_id column if it doesn't exist
                        try:
                            deal.customer_id = customer.id
                            updated += 1
                        except AttributeError:
                            # Column doesn't exist yet — skip
                            pass

        session.commit()
        print(f"Updated {updated} deals with customer references.")
        return updated


def link_tickets_to_subscriptions(tenant_id: str):
    """Link support tickets to subscriptions where possible."""
    engine = get_engine()
    tid = uuid.UUID(tenant_id)

    with Session(engine) as session:
        tickets = session.query(Ticket).filter(
            Ticket.tenant_id == tid
        ).all()

        linked = 0
        for ticket in tickets:
            if ticket.customer_id and not getattr(ticket, 'subscription_id', None):
                sub = session.query(Subscription).filter(
                    Subscription.customer_id == ticket.customer_id,
                    Subscription.tenant_id == tid,
                    Subscription.status == "active",
                ).first()

                if sub:
                    try:
                        ticket.subscription_id = sub.id
                        linked += 1
                    except AttributeError:
                        pass

        session.commit()
        print(f"Linked {linked} tickets to subscriptions.")
        return linked


def run_migration(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    """Run all migrations for a tenant."""
    print(f"Running customer data migration for tenant {tenant_id}...")
    print("=" * 60)

    contacts_migrated = migrate_contacts_to_customers(tenant_id)
    leads_migrated = migrate_leads(tenant_id)
    deals_updated = update_deals_references(tenant_id)
    tickets_linked = link_tickets_to_subscriptions(tenant_id)

    print("=" * 60)
    print("Migration complete:")
    print(f"  Contacts → Customers: {contacts_migrated}")
    print(f"  Sales Leads → CRM Leads: {leads_migrated}")
    print(f"  Deals Updated: {deals_updated}")
    print(f"  Tickets Linked: {tickets_linked}")


if __name__ == "__main__":
    run_migration()
