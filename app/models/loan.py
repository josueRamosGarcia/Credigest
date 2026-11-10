"""Modelos de prestamos y su calendario de cuotas.

Un prestamo guarda las condiciones **congeladas** al aprobarse (RN-06, RN-14):
si manana cambia la tasa moratoria global, los prestamos ya firmados no se
alteran.

Estados (docs/03-reglas-de-negocio.md, seccion 16)::

    activo --(todas las cuotas pagadas)--> pagado
       |
       +--(cuota vencida)--> vencido --(se regulariza)--> activo
       |
       +--(cancelacion admin)--> cancelado
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Loan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Un prestamo aprobado y firmado."""

    __tablename__ = "loan"

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    client_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("client.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    #: Prestamista que coloco el credito.
    lender_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    #: Monto prestado, sin intereses.
    principal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    #: Tasa por periodo, como fraccion (0.05 = 5 %). Nunca se guarda como
    #: porcentaje para no dividir en cada calculo (RN-04).
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)

    rate_period: Mapped[str] = mapped_column(
        Enum("semanal", "quincenal", "mensual", name="loan_frequency"),
        nullable=False,
    )

    scheme: Mapped[str] = mapped_column(
        Enum("simple", "saldo_insoluto", "cuota_fija", name="loan_scheme"),
        nullable=False,
    )

    term_periods: Mapped[int] = mapped_column(Integer, nullable=False)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    first_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    #: Totales congelados al aprobar el prestamo.
    total_interest: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    #: Tasa moratoria mensual aplicable a este prestamo (RN-22).
    late_fee_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    grace_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        Enum("activo", "pagado", "vencido", "cancelado", name="loan_status"),
        nullable=False,
        default="activo",
        server_default="activo",
        index=True,
    )

    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    installments: Mapped[list["Installment"]] = relationship(
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="Installment.number",
    )

    def __repr__(self) -> str:
        """Representacion de depuracion sin montos ni datos del cliente."""
        return f"<Loan {self.id} status={self.status}>"


class Installment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una cuota del calendario de pagos."""

    __tablename__ = "installment"
    __table_args__ = (
        UniqueConstraint("loan_id", "number", name="uq_installment_loan_id_number"),
        # Indice para la consulta diaria de cuotas vencidas.
        Index("ix_installment_due_status", "due_date", "status"),
    )

    loan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("loan.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: Numero de cuota, empezando en 1.
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    #: Monto esperado de la cuota (capital + interes), sin mora.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    principal_part: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interest_part: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    #: Mora devengada consolidada por el cierre diario (RN-20).
    late_fee: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    #: Suma de lo ya aplicado (mora + interes + capital).
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )

    status: Mapped[str] = mapped_column(
        Enum("pendiente", "parcial", "pagada", "vencida", name="installment_status"),
        nullable=False,
        default="pendiente",
        server_default="pendiente",
        index=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Ultima fecha en que el cierre diario consolido la mora de esta cuota.
    late_fee_calculated_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    loan: Mapped[Loan] = relationship(back_populates="installments")

    @property
    def pending_amount(self) -> Decimal:
        """Lo que falta por pagar de esta cuota, incluida la mora."""
        return self.amount + self.late_fee - self.paid_amount

    def __repr__(self) -> str:
        """Representacion de depuracion."""
        return f"<Installment {self.number} status={self.status}>"
