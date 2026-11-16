"""Endpoints del comparador bancario (RF-45 a RF-47, RN-52 a RN-54)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.domain.comparator import ComparisonRow
from app.schemas.comparator import (
    BankCreate,
    BankRead,
    BankUpdate,
    CompareRequest,
    CompareResponse,
    CompareRowRead,
)
from app.services import comparator_service

banks_router = APIRouter(prefix="/banks", tags=["comparador bancario"])
compare_router = APIRouter(prefix="/compare", tags=["comparador bancario"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LenderDep = Annotated[AuthContext, Depends(require_role("prestamista"))]
AdminDep = Annotated[AuthContext, Depends(require_role("admin"))]


def _to_row_read(row: ComparisonRow) -> CompareRowRead:
    """Convierte una fila del dominio al esquema de respuesta."""
    return CompareRowRead(
        institution=row.institution,
        is_own_offer=row.is_own_offer,
        periodic_rate=row.periodic_rate,
        annual_rate=row.annual_rate,
        estimated_cat=row.estimated_cat,
        installment_amount=row.installment_amount,
        total_interest=row.total_interest,
        opening_fee=row.opening_fee,
        total_cost=row.total_cost,
    )


@banks_router.get(
    "",
    response_model=list[BankRead],
    summary="Listar catalogo de bancos",
    description=(
        "Devuelve el catalogo de instituciones bancarias de la financiera. "
        "Si aun no se ha configurado, inicializa el catalogo estatico de "
        "referencia (RF-45)."
    ),
)
async def list_banks(
    context: LenderDep,
    session: SessionDep,
    only_active: Annotated[bool, Query()] = False,
) -> list[BankRead]:
    """Lista los bancos del catalogo de la financiera."""
    banks = await comparator_service.list_banks(
        session, context.tenant_id, only_active=only_active
    )
    return [BankRead.model_validate(bank) for bank in banks]


@banks_router.post(
    "",
    response_model=BankRead,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar institucion al catalogo bancario",
    description="Permite al Administrador agregar una institucion al catalogo (RN-54).",
)
async def create_bank(
    payload: BankCreate,
    context: AdminDep,
    session: SessionDep,
    request: Request,
) -> BankRead:
    """Agrega un banco nuevo al catalogo."""
    meta = request_meta(request)
    bank = await comparator_service.create_bank(
        session,
        context.tenant_id,
        context.user.id,
        payload,
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
    )
    return BankRead.model_validate(bank)


@banks_router.patch(
    "/{bank_id}",
    response_model=BankRead,
    summary="Editar institucion del catalogo bancario",
    description="Permite al Administrador modificar tasas, comisiones o estado (RN-54).",
)
async def update_bank(
    bank_id: UUID,
    payload: BankUpdate,
    context: AdminDep,
    session: SessionDep,
    request: Request,
) -> BankRead:
    """Actualiza los datos de un banco del catalogo."""
    meta = request_meta(request)
    try:
        bank = await comparator_service.update_bank(
            session,
            context.tenant_id,
            bank_id,
            context.user.id,
            payload,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except comparator_service.BankNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return BankRead.model_validate(bank)


@compare_router.post(
    "",
    response_model=CompareResponse,
    summary="Comparar condiciones contra el catalogo bancario",
    description=(
        "Calcula tasa, CAT estimado, cuota periodica, comisiones y costo total "
        "de la oferta propia frente a las instituciones bancarias seleccionadas, "
        "incluyendo la leyenda informativa obligatoria (RF-45 a RF-47, RN-52, RN-53)."
    ),
)
async def compare(
    payload: CompareRequest,
    context: LenderDep,
    session: SessionDep,
) -> CompareResponse:
    """Ejecuta la comparacion contra el catalogo bancario."""
    disclaimer, own_row, bank_rows = await comparator_service.compare_offers(
        session,
        context.tenant_id,
        context.tenant.name,
        payload,
    )

    return CompareResponse(
        disclaimer=disclaimer,
        own_offer=_to_row_read(own_row),
        bank_offers=[_to_row_read(row) for row in bank_rows],
    )

