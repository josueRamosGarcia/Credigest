"""Modelos de pagos y su distribucion.

Un pago nunca se borra: se anula con un registro de anulacion para conservar la
trazabilidad (RN-36). La distribucion por concepto vive en
`payment_application`, lo que permite auditar a donde fue cada centavo.

Reglas que aplican:
- RN-30: cada aplicacion se guarda por separado (mora, interes, capital).
- RN-36: anular revierte las aplicaciones y recalcula estados.
- RN-39: cada pago tiene un folio legible.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.loan import Installment


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Un pago recibido de un cliente."""

    __tablename__ = "payment"
    __table_args__ = (
        # RN-39: el folio es unico dentro de la financiera.
        UniqueConstraint("tenant_id", "folio", name="uq_payment_tenant_id_folio"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    loan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("loan.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    #: Folio legible: PAGO-{tenant}-{anio}-{consecutivo} (RN-39).
    folio: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    #: Monto recibido del cliente.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    method: Mapped[str] = mapped_column(
        Enum("efectivo", "spei", name="payment_method"),
        nullable=False,
    )

    #: Referencia de la transferencia. Obligatoria si el metodo es SPEI (RN-25).
    spei_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    #: Etiqueta descriptiva: la aplicacion siempre sigue RN-29.
    payment_type: Mapped[str] = mapped_column(
        Enum(
            "parcial",
            "completo",
            "adelantado",
            "moratorio",
            name="payment_type",
        ),
        nullable=False,
        default="parcial",
    )

    status: Mapped[str] = mapped_column(
        Enum("aplicado", "anulado", name="payment_status"),
        nullable=False,
        default="aplicado",
        server_default="aplicado",
        index=True,
    )

    registered_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    #: Datos de la anulacion (RN-36). Nunca se borra el pago.
    cancelled_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    applications: Mapped[list["PaymentApplication"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Representacion de depuracion sin montos."""
        return f"<Payment {self.folio} status={self.status}>"


class PaymentApplication(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Porcion de un pago aplicada a un concepto de una cuota (RN-30)."""

    __tablename__ = "payment_application"

    payment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("payment.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    installment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("installment.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    concept: Mapped[str] = mapped_column(
        Enum("mora", "interes", "capital", name="payment_concept"),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    payment: Mapped[Payment] = relationship(back_populates="applications")

    installment: Mapped["Installment"] = relationship(back_populates="applications")

    def __repr__(self) -> str:
        """Representacion de depuracion."""
        return f"<PaymentApplication {self.concept}>"
