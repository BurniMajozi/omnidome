"""baseline plus billing_account soft delete

Revision ID: 419d8e0ef0d0
Revises:
Create Date: 2026-06-29 18:53:36.483834

First Alembic revision for the billing service. The live tables already
existed (created ad hoc before this service had migration tooling), so this
revision is scoped to ONLY the one genuinely new, additive change. Autogenerate
also detected pre-existing drift unrelated to this work — column comments,
index renames, and notably `op.drop_column('invoices', 'line_items')` /
`op.drop_column('subscriptions', 'plan')`, both legacy columns the model
moved away from at some prior point but which still hold live data. Dropping
those is a deliberate decision for someone who can confirm the legacy data
is safe to discard, not something to fold silently into a migrations-tooling
change — left alone here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '419d8e0ef0d0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'billing_accounts',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('billing_accounts', 'deleted_at')
