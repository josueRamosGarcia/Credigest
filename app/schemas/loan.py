"""Esquemas de la simulacion y creacion de prestamos.

Los esquemas definen el contrato de la API: que recibe y que devuelve cada
endpoint. Separarlos de los modelos de base de datos permite que la API cambie
sin alterar la persistencia y viceversa.

Reglas que se reflejan aqui:
- RN-01: los importes viajan como Decimal, nunca como float.
- RN-04: la tasa es por periodo; se devuelve su equivalente anual solo como dato.
- RN-12: la simulacion no persiste nada.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

#: Importe monetario con 2 decimales.
#: Se serializa como cadena ("1333.33") para no perder precision: JavaScript
#: usa numeros de coma flotante y convertir ahi reintroduciria el error que
#: RN-01 prohibe.
Money = Annotated[
    Decimal,
    Field(max_digits=14, decimal_places=2),
    PlainSerializer(lambda value: f"{value:.2f}", return_type=str, when_used="json"),
]

#: Tasa con 4 decimales por periodo.
Rate = Annotated[
    Decimal,
    Field(max_digits=8, decimal_places=4, ge=0),
    PlainSerializer(lambda value: f"{value:.4f}", return_type=str, when_used="json"),
]


class SimulateRequest(BaseModel):
    """Datos que envia el prestamista para simular un prestamo."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "principal": 10000,
                "interest_rate": 0.05,
                "rate_period": "semanal",
                "scheme": "simple",
                "term_periods": 12,
                "start_date": "2026-11-02",
            }
        }
    )

    principal: Money = Field(gt=0, description="Monto prestado.")
    interest_rate: Rate = Field(description="Tasa de interes por periodo, como fraccion.")
    rate_period: str = Field(description="Frecuencia: semanal, quincenal o mensual.")
    scheme: str = Field(description="Esquema: simple, saldo_insoluto o cuota_fija.")
    term_periods: int = Field(gt=0, le=520, description="Numero de cuotas.")
    start_date: date = Field(description="Fecha en que inicia el prestamo.")


class ScheduleRow(BaseModel):
    """Una fila de la tabla de amortizacion en la respuesta."""

    number: int
    due_date: date
    amount: Money
    interest_part: Money
    principal_part: Money
    balance: Money


class SimulateResponse(BaseModel):
    """Resultado de la simulacion.

    `installment_amount` es la primera cuota. En el esquema de saldo insoluto
    la cuota decrece, por eso se devuelve tambien `installment_amount_last`
    (RN-13).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "installment_amount": "1333.33",
                "installment_amount_last": "1333.33",
                "total_interest": "6000.00",
                "total_amount": "16000.00",
                "estimated_profit": "6000.00",
                "end_date": "2027-01-25",
                "annual_equivalent_rate": "11.6428",
                "schedule": [],
            }
        }
    )

    installment_amount: Money
    installment_amount_last: Money
    total_interest: Money
    total_amount: Money
    estimated_profit: Money
    end_date: date
    annual_equivalent_rate: Rate
    schedule: list[ScheduleRow]


class LoanCreate(BaseModel):
    """Datos para aprobar un prestamo a partir de una simulacion.

    Convierte una cotizacion en un prestamo real: persiste el prestamo y genera
    su calendario de cuotas (RN-14).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_id": "00000000-0000-0000-0000-000000000000",
                "principal": 10000,
                "interest_rate": 0.05,
                "rate_period": "semanal",
                "scheme": "simple",
                "term_periods": 12,
                "start_date": "2026-11-02",
                "late_fee_rate": 0.10,
                "grace_days": 5,
            }
        }
    )

    client_id: UUID = Field(description="Cliente que recibe el prestamo.")
    principal: Money = Field(gt=0, description="Monto prestado.")
    interest_rate: Rate = Field(description="Tasa de interes por periodo.")
    rate_period: str = Field(description="Frecuencia: semanal, quincenal o mensual.")
    scheme: str = Field(description="Esquema: simple, saldo_insoluto o cuota_fija.")
    term_periods: int = Field(gt=0, le=520, description="Numero de cuotas.")
    start_date: date = Field(description="Fecha en que inicia el prestamo.")

    #: Si se omiten, se toman de la configuracion global del tenant (RN-22).
    late_fee_rate: Rate | None = Field(default=None, description="Tasa moratoria mensual.")
    grace_days: int | None = Field(default=None, ge=0, le=90, description="Dias de gracia.")


class InstallmentRead(BaseModel):
    """Una cuota tal como se devuelve a la API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: int
    due_date: date
    amount: Money
    principal_part: Money
    interest_part: Money
    late_fee: Money
    paid_amount: Money
    status: str
    paid_at: datetime | None


class LoanRead(BaseModel):
    """Prestamo con sus totales y su estado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    principal: Money
    interest_rate: Rate
    rate_period: str
    scheme: str
    term_periods: int
    start_date: date
    first_due_date: date
    end_date: date
    total_interest: Money
    total_amount: Money
    late_fee_rate: Rate
    grace_days: int
    status: str


class LoanDetail(LoanRead):
    """Prestamo con su calendario de cuotas."""

    installments: list[InstallmentRead] = Field(default_factory=list)


class LoanListResponse(BaseModel):
    """Pagina de prestamos."""

    items: list[LoanRead]
    total: int
    page: int
    page_size: int


class LoanCancelRequest(BaseModel):
    """Motivo por el que se cancela un prestamo."""

    reason: Annotated[str, Field(min_length=5, max_length=500)]
