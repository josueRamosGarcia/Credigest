"""Modelo de parametros globales por tenant.

Los cambios aqui solo afectan prestamos nuevos. Los prestamos ya aprobados
conservan sus condiciones congeladas (RN-06, RN-12).
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SystemSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Configuracion global de una financiera."""

    __tablename__ = "system_setting"

    #: Un tenant tiene una sola configuracion.
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    #: Tasa moratoria mensual como fraccion (0.10 = 10 %).
    default_late_fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0.1000"),
        server_default="0.1000",
    )

    default_scheme: Mapped[str] = mapped_column(
        Enum("simple", "saldo_insoluto", "cuota_fija", name="loan_scheme"),
        nullable=False,
        default="simple",
        server_default="simple",
    )

    #: Dias de tolerancia antes de cobrar mora (RN-19).
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="America/Mexico_City",
        server_default="America/Mexico_City",
    )

    def __repr__(self) -> str:
        """Representacion legible para depuracion."""
        return f"<SystemSetting tenant={self.tenant_id} grace={self.grace_days}>"
