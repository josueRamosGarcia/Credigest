"""Script de migracion base."""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401

from alembic import op  # noqa: F401

# Identificadores de la revision.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las extensiones necesarias.

    Aun no existen tablas de negocio; esta migracion solo prepara la base.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    """Revierte la migracion base."""
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
