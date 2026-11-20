"""agregar direccion estructurada y coordenadas en client

Revision ID: f7b3c91a4e05
Revises: e3b91a04c812
Create Date: 2026-11-20 11:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Identificadores de la revision.
revision: str = "f7b3c91a4e05"
down_revision: str | None = "e3b91a04c812"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("client", sa.Column("street", sa.String(length=200), nullable=True))
    op.add_column("client", sa.Column("exterior_number", sa.String(length=30), nullable=True))
    op.add_column("client", sa.Column("neighborhood", sa.String(length=150), nullable=True))
    op.add_column("client", sa.Column("postal_code", sa.String(length=10), nullable=True))
    op.add_column("client", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("client", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("client", sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True))
    op.add_column("client", sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True))


def downgrade() -> None:
    op.drop_column("client", "longitude")
    op.drop_column("client", "latitude")
    op.drop_column("client", "state")
    op.drop_column("client", "city")
    op.drop_column("client", "postal_code")
    op.drop_column("client", "neighborhood")
    op.drop_column("client", "exterior_number")
    op.drop_column("client", "street")
