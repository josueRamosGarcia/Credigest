"""agregar catalogo de bancos

Revision ID: c7a4f189d201
Revises: 99888f586b89
Create Date: 2026-11-16 01:58:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# Identificadores de la revision.
revision: str = 'c7a4f189d201'
down_revision: str | None = '99888f586b89'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'bank',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('annual_rate', sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column('cat', sa.Numeric(precision=8, scale=4), server_default='0.0000', nullable=False),
        sa.Column('opening_fee', sa.Numeric(precision=14, scale=2), server_default='0.00', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_bank_tenant_id_tenant'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_bank')),
    )
    op.create_index(op.f('ix_bank_tenant_id'), 'bank', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bank_tenant_id'), table_name='bank')
    op.drop_table('bank')

