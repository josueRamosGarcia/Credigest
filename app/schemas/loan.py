"""Esquemas de la simulacion y creacion de prestamos.

Los esquemas definen el contrato de la API: que recibe y que devuelve cada
endpoint. Separarlos de los modelos de base de datos permite que la API cambie
sin alterar la persistencia y viceversa.

Reglas que se reflejan aqui:
- RN-01: los importes viajan como Decimal, nunca como float.
- RN-04: la tasa es por periodo; se devuelve su equivalente anual solo como dato.
- RN-12: la simulacion no persiste nada.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

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
