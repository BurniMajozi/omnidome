"""baseline plus soft delete and numbering

Revision ID: 5c4b7a2e5acd
Revises:
Create Date: 2026-06-29 18:47:51.802703

This is the first Alembic revision for the finance service. journal_entries,
journal_entry_lines, financial_records and budget_scenarios already exist in
the live database (created ad hoc via Base.metadata.create_all() before this
service had migration tooling), so this revision is scoped to ONLY the two
genuinely new, additive changes — it deliberately does NOT carry the
NOT NULL / index-rename / FK-drop noise autogenerate also detected against
the live schema. That drift (e.g. the journal_entries_tenant_id_fkey -> tenants
constraint, which is real and should stay) predates Alembic and is left alone
here; reconcile it later as its own deliberate migration if desired.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5c4b7a2e5acd'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'journal_entry_sequences',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('last_number', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_journal_entry_sequences_tenant_id'),
        'journal_entry_sequences', ['tenant_id'], unique=True,
    )
    op.add_column(
        'journal_entries',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('journal_entries', 'deleted_at')
    op.drop_index(op.f('ix_journal_entry_sequences_tenant_id'), table_name='journal_entry_sequences')
    op.drop_table('journal_entry_sequences')
