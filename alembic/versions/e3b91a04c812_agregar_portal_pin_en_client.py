"""agregar portal_pin_hash en client

Revision ID: e3b91a04c812
Revises: c7a4f189d201
Create Date: 2026-11-17 00:03:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# Identificadores de la revision.
revision: str = 'e3b91a04c812'
down_revision: str | None = 'c7a4f189d201'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'client',
        sa.Column('portal_pin_hash', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('client', 'portal_pin_hash')
