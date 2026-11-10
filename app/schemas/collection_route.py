"""Esquemas de rutas de cobro."""

from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.loan import Money


class RouteItemRead(BaseModel):
    """Una parada de la ruta con los datos que necesita el cobrador.

    Incluye el nombre, direccion y telefono del cliente porque el cobrador los
    necesita en campo; son datos que ya ve por su rol (RN-38).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    loan_id: UUID
    installment_id: UUID
    order_index: int
    visit_status: str
    notes: str | None

    #: Datos del cliente y la cuota, resueltos por el servicio.
    client_name: str
    client_address: str
    client_phone: str
    installment_number: int
    due_date: date
    amount_due: Money
    late_fee: Money
    total_due: Money


class RouteRead(BaseModel):
    """Ruta sin sus paradas, para listados."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cobrador_id: UUID
    zone: str
    route_date: date
    status: str
    notes: str | None
    total_items: int = 0
    pending_items: int = 0


class RouteDetail(RouteRead):
    """Ruta con todas sus paradas."""

    items: list[RouteItemRead] = Field(default_factory=list)


class RouteCreate(BaseModel):
    """Datos para generar una ruta.

    Si no se indica `cobrador_id`, se usa el usuario autenticado cuando su rol
    es cobrador.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "zone": "Centro",
                "route_date": "2026-11-11",
                "cobrador_id": None,
            }
        }
    )

    zone: Annotated[str, Field(min_length=1, max_length=80)]
    route_date: date
    cobrador_id: UUID | None = None


class RouteItemUpdate(BaseModel):
    """Cambios que el cobrador puede hacer sobre una parada."""

    visit_status: Annotated[str | None, Field(pattern="^(pendiente|pagado|no_pagado)$")] = None
    notes: Annotated[str | None, Field(max_length=500)] = None


class RouteReorder(BaseModel):
    """Nuevo orden de visita."""

    item_ids: Annotated[list[UUID], Field(min_length=1, max_length=500)]


class RouteListResponse(BaseModel):
    """Pagina de rutas."""

    items: list[RouteRead]
    total: int
    page: int
    page_size: int
