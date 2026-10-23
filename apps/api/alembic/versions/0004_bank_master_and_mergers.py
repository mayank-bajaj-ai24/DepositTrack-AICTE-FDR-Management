"""bank master and bank mergers

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'bank',
        sa.Column('code', sa.String(length=4), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('bank_type', sa.String(length=20), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('code', name=op.f('pk_bank')),
    )
    op.create_table(
        'bank_merger',
        sa.Column('old_bank', sa.String(length=4), nullable=False),
        sa.Column('canonical_bank', sa.String(length=4), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('source', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('old_bank', name=op.f('pk_bank_merger')),
    )


def downgrade() -> None:
    op.drop_table('bank_merger')
    op.drop_table('bank')
