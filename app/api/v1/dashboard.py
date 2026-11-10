"""Endpoints del dashboard financiero.

Solo el Administrador accede a estas cifras: son la vista global del negocio.
"""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.db.session import get_session
from app.schemas.dashboard import (
    AgingBucketRead,
    AgingRead,
    CollectionDayRead,
    DashboardSummaryRead,
)
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _require_admin(role: str) -> None:
    """Restringe el acceso al Administrador.

    Raises:
        HTTPException: 403 si el rol no es administrador.
    """
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El dashboard esta disponible solo para administradores.",
        )


@router.get(
    "/summary",
    response_model=DashboardSummaryRead,
    summary="Indicadores principales",
    description=(
        "Capital prestado, recuperado y proyectado; intereses, mora y utilidad; "
        "ademas del indice de morosidad. Las fechas filtran la colocacion por "
        "inicio del prestamo y la cobranza por fecha del pago (RN-48)."
    ),
)
async def get_summary(
    context: CurrentUserDep,
    session: SessionDep,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> DashboardSummaryRead:
    """Devuelve los indicadores principales del negocio."""
    _require_admin(context.role)

    result = await dashboard_service.summary(
        session,
        context.tenant_id,
        from_date=from_date,
        to_date=to_date,
    )

    return DashboardSummaryRead(
        capital_prestado=result.capital_prestado,
        capital_recuperado=result.capital_recuperado,
        capital_proyectado=result.capital_proyectado,
        intereses_generados=result.intereses_generados,
        mora_cobrada=result.mora_cobrada,
        utilidad_generada=result.utilidad_generada,
        cartera_total=result.cartera_total,
        cartera_vencida=result.cartera_vencida,
        indice_morosidad=result.indice_morosidad,
        prestamos_activos=result.prestamos_activos,
        prestamos_pagados=result.prestamos_pagados,
        prestamos_vencidos=result.prestamos_vencidos,
    )


@router.get(
    "/aging",
    response_model=AgingRead,
    summary="Antiguedad de la cartera",
    description=(
        "Agrupa el saldo pendiente por dias de atraso, calculado por cuota y no "
        "por prestamo (RN-51)."
    ),
)
async def get_aging(
    context: CurrentUserDep,
    session: SessionDep,
    today: Annotated[date | None, Query()] = None,
) -> AgingRead:
    """Devuelve el reporte de antiguedad de saldos."""
    _require_admin(context.role)

    report = await dashboard_service.aging(session, context.tenant_id, today=today)

    return AgingRead(
        buckets=[
            AgingBucketRead(
                label=bucket.label,
                min_days=bucket.min_days,
                max_days=bucket.max_days,
                amount=bucket.amount,
                installments=bucket.installments,
            )
            for bucket in report.buckets
        ],
        total_vencido=report.total_vencido,
    )


@router.get(
    "/collections",
    response_model=list[CollectionDayRead],
    summary="Cobranza por dia",
    description="Serie diaria de lo cobrado, para la grafica de flujo de caja.",
)
async def get_collections(
    context: CurrentUserDep,
    session: SessionDep,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> list[CollectionDayRead]:
    """Devuelve la serie de cobranza diaria.

    Si no se indica rango, se usan los ultimos 30 dias.
    """
    _require_admin(context.role)

    end = to_date or date.today()
    start = from_date or (end - timedelta(days=30))

    series = await dashboard_service.collections_by_day(
        session, context.tenant_id, from_date=start, to_date=end
    )

    return [CollectionDayRead(day=day, amount=amount) for day, amount in series]
