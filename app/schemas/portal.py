"""Esquemas del portal de consulta para el cliente acreditado."""

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.validation import CurpError, parse_curp
from app.schemas.loan import Money


class PortalLoginRequest(BaseModel):
    """Credenciales de acceso al portal del cliente (CURP + PIN de 6 digitos)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    curp: Annotated[str, Field(max_length=30)]
    pin: Annotated[str, Field(pattern=r"^\d{6}$")]
    tenant_slug: Annotated[str | None, Field(default=None, max_length=50)] = None

    @field_validator("curp")
    @classmethod
    def _validate_curp(cls, value: str) -> str:
        try:
            return parse_curp(value).curp
        except CurpError as exc:
            raise ValueError(str(exc)) from exc


class PortalTokenResponse(BaseModel):
    """Token de sesion exclusivo para el portal del cliente."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    client_name: str
    tenant_name: str


class PortalInstallmentRead(BaseModel):
    """Cuota visible para el cliente en su calendario de pagos."""

    number: int
    due_date: date
    amount: Money
    late_fee: Money
    paid_amount: Money
    pending_amount: Money
    status: str
    paid_at: datetime | None


class PortalPaymentRead(BaseModel):
    """Abono aplicado visible para el cliente."""

    id: UUID
    folio: str
    amount: Money
    method: str
    created_at: datetime


class PortalNextInstallment(BaseModel):
    """Informacion destacada del proximo pago del prestamo."""

    number: int
    due_date: date
    pending_amount: Money
    is_overdue: bool


class PortalLoanSummary(BaseModel):
    """Estado de cuenta y avance de un prestamo del cliente."""

    id: UUID
    folio: str
    principal: Money
    total_amount: Money
    rate_period: str
    scheme: str
    term_periods: int
    start_date: date
    end_date: date
    status: str
    paid_total: Money
    remaining_total: Money
    progress_percent: Money
    paid_installments_count: int
    next_installment: PortalNextInstallment | None
    installments: list[PortalInstallmentRead]
    payments: list[PortalPaymentRead]


class PortalOverviewResponse(BaseModel):
    """Resumen general de todos los prestamos del cliente."""

    client_name: str
    tenant_name: str
    active_loans_count: int
    total_paid: Money
    total_remaining: Money
    loans: list[PortalLoanSummary]
