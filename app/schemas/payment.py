"""Esquemas de pagos."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.loan import Money


class PaymentApplicationRead(BaseModel):
    """Porcion aplicada a un concepto."""

    model_config = ConfigDict(from_attributes=True)

    installment_id: UUID
    concept: str
    amount: Money


class PaymentCreate(BaseModel):
    """Datos para registrar un pago.

    El reparto entre cuotas y conceptos lo decide el servidor (RN-29); el
    cliente solo indica cuanto dinero recibio y como.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "loan_id": "00000000-0000-0000-0000-000000000000",
                "amount": 400.0,
                "method": "efectivo",
                "payment_type": "parcial",
            }
        }
    )

    loan_id: UUID = Field(description="Prestamo al que se abona.")
    amount: Money = Field(gt=0, description="Monto recibido del cliente.")
    method: Literal["efectivo", "spei"] = Field(description="Forma de pago.")
    spei_reference: Annotated[str | None, Field(max_length=100)] = Field(
        default=None, description="Referencia SPEI. Obligatoria si el metodo es spei."
    )
    payment_type: Literal["parcial", "completo", "adelantado", "moratorio"] = Field(
        default="parcial",
        description="Etiqueta descriptiva; el reparto siempre sigue RN-29.",
    )
    notes: Annotated[str | None, Field(max_length=500)] = None

    @model_validator(mode="after")
    def _require_spei_reference(self) -> "PaymentCreate":
        """RN-25: una transferencia necesita referencia."""
        if self.method == "spei" and not (self.spei_reference or "").strip():
            raise ValueError("La referencia SPEI es obligatoria para pagos por transferencia.")
        if self.method == "spei" and len((self.spei_reference or "").strip()) < 6:
            raise ValueError("La referencia SPEI debe tener al menos 6 caracteres.")
        return self


class PaymentRead(BaseModel):
    """Pago registrado con su desglose."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    loan_id: UUID
    folio: str
    amount: Money
    method: str
    spei_reference: str | None
    payment_type: str
    status: str
    registered_by: UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime


class PaymentDetail(PaymentRead):
    """Pago con las aplicaciones por concepto."""

    applications: list[PaymentApplicationRead] = Field(default_factory=list)


class PaymentResult(BaseModel):
    """Resultado de registrar un pago.

    Incluye el estado del prestamo despues del abono para que el cobrador sepa
    de inmediato cuanto queda.
    """

    payment: PaymentDetail
    loan_status: str
    remaining_total: Money
    covered_late_fee: Money
    covered_interest: Money
    covered_principal: Money


class PaymentListResponse(BaseModel):
    """Pagina de pagos."""

    items: list[PaymentRead]
    total: int
    page: int
    page_size: int


class PaymentCancelRequest(BaseModel):
    """Motivo de anulacion de un pago."""

    reason: Annotated[str, Field(min_length=10, max_length=500)]
