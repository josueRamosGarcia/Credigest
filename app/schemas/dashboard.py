"""Esquemas del dashboard financiero."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.loan import Money


class DashboardSummaryRead(BaseModel):
    """Indicadores principales."""

    capital_prestado: Money
    capital_recuperado: Money
    capital_proyectado: Money
    intereses_generados: Money
    mora_cobrada: Money
    utilidad_generada: Money
    cartera_total: Money
    cartera_vencida: Money

    #: Porcentaje con 2 decimales (RN-50).
    indice_morosidad: Money

    prestamos_activos: int
    prestamos_pagados: int
    prestamos_vencidos: int


class AgingBucketRead(BaseModel):
    """Una franja de antiguedad."""

    label: str
    min_days: int
    max_days: int | None
    amount: Money
    installments: int


class AgingRead(BaseModel):
    """Reporte de antiguedad de saldos."""

    buckets: list[AgingBucketRead]
    total_vencido: Money


class CollectionDayRead(BaseModel):
    """Cobranza de un dia."""

    day: date
    amount: Money


class DashboardFilters(BaseModel):
    """Filtros aplicados, para que el frontend muestre que se esta viendo.

    RN-48: la fecha de colocacion usa `loan.start_date` y la de cobranza usa
    `payment.created_at`. Se devuelven ambos criterios explicitos.
    """

    from_date: date | None = None
    to_date: date | None = None
    prestamista_id: UUID | None = None
    colocacion_por: str = Field(default="fecha de inicio del prestamo")
    cobranza_por: str = Field(default="fecha de registro del pago")
