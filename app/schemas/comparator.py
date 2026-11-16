"""Esquemas del comparador bancario (RF-45 a RF-47, RN-52 a RN-54)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.loan import Money, Rate

RatePeriodLiteral = Literal["semanal", "quincenal", "mensual"]
LoanSchemeLiteral = Literal["simple", "saldo_insoluto", "cuota_fija"]


class BankCreate(BaseModel):
    """Alta de una institucion bancaria en el catalogo de la financiera (RN-54)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=2, max_length=150)]
    annual_rate: Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("5"))]
    cat: Annotated[Decimal, Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("10"))] = (
        Decimal("0")
    )
    opening_fee: Annotated[Decimal, Field(default=Decimal("0"), ge=Decimal("0"))] = (
        Decimal("0")
    )
    is_active: bool = True


class BankUpdate(BaseModel):
    """Actualizacion de una institucion del catalogo bancario."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Annotated[str | None, Field(default=None, min_length=2, max_length=150)] = (
        None
    )
    annual_rate: Annotated[
        Decimal | None, Field(default=None, ge=Decimal("0"), le=Decimal("5"))
    ] = None
    cat: Annotated[
        Decimal | None, Field(default=None, ge=Decimal("0"), le=Decimal("10"))
    ] = None
    opening_fee: Annotated[
        Decimal | None, Field(default=None, ge=Decimal("0"))
    ] = None
    is_active: bool | None = None


class BankRead(BaseModel):
    """Institucion bancaria del catalogo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    annual_rate: Rate
    cat: Rate
    opening_fee: Money
    is_active: bool
    updated_at: datetime


class CompareRequest(BaseModel):
    """Condiciones propias a comparar contra el catalogo bancario (CU-09)."""

    principal: Money = Field(gt=0, description="Monto del prestamo.")
    interest_rate: Rate = Field(ge=0, description="Tasa propia por periodo.")
    rate_period: RatePeriodLiteral
    scheme: LoanSchemeLiteral = "simple"
    term_periods: Annotated[int, Field(ge=1, le=520)]
    opening_fee: Money = Field(default=Decimal("0.00"), ge=0)
    bank_ids: list[UUID] | None = Field(
        default=None,
        description="Bancos del catalogo a incluir. Si se omite, compara contra todos los activos.",
    )


class CompareRowRead(BaseModel):
    """Resultado comparativo de una institucion o de la oferta propia (RF-46)."""

    institution: str
    is_own_offer: bool
    periodic_rate: Rate
    annual_rate: Rate
    estimated_cat: Money
    installment_amount: Money
    total_interest: Money
    opening_fee: Money
    total_cost: Money


class CompareResponse(BaseModel):
    """Respuesta completa del comparador bancario con leyenda informativa (RN-53)."""

    disclaimer: str
    own_offer: CompareRowRead
    bank_offers: list[CompareRowRead]

