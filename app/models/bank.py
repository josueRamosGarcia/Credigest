"""Modelo del catalogo de instituciones bancarias para el comparador (RN-54).

Cada financiera mantiene su propio catalogo estatico de referencia, configurable
por el Administrador (RF-45).
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Bank(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Institucion bancaria de referencia para comparar ofertas."""

    __tablename__ = "bank"

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    #: Tasa de interes anual de referencia como fraccion (ej. 0.3600 = 36 %).
    annual_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)

    #: CAT estimado de referencia como fraccion (ej. 0.4500 = 45 %).
    cat: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0.0000"),
        server_default="0.0000",
    )

    #: Comision de apertura en pesos MXN.
    opening_fee: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    def __repr__(self) -> str:
        """Representacion legible para depuracion."""
        return f"<Bank {self.name} ({self.id})>"

