"""Endpoints del dashboard financiero.

Solo el Administrador accede a estas cifras: son la vista global del negocio.
"""

import csv
import io
from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.schemas.dashboard import (
    AgingBucketRead,
    AgingRead,
    CollectionDayRead,
    DashboardSummaryRead,
)
from app.scripts.accrue_late_fees import accrue_late_fees
from app.services import audit_service, dashboard_service

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
    prestamista_id: Annotated[UUID | None, Query()] = None,
    route_id: Annotated[UUID | None, Query()] = None,
) -> DashboardSummaryRead:
    """Devuelve los indicadores principales del negocio."""
    _require_admin(context.role)

    result = await dashboard_service.summary(
        session,
        context.tenant_id,
        from_date=from_date,
        to_date=to_date,
        prestamista_id=prestamista_id,
        route_id=route_id,
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


@router.get(
    "/export.csv",
    summary="Exportar el dashboard a CSV",
    description=(
        "Descarga los indicadores principales y la antiguedad de cartera en "
        "formato CSV (RF-44, RN-64)."
    ),
    response_class=StreamingResponse,
)
async def export_dashboard(
    context: CurrentUserDep,
    session: SessionDep,
    request: Request,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    prestamista_id: Annotated[UUID | None, Query()] = None,
    route_id: Annotated[UUID | None, Query()] = None,
) -> StreamingResponse:
    """Exporta los indicadores del dashboard a CSV."""
    _require_admin(context.role)

    summary_data = await dashboard_service.summary(
        session,
        context.tenant_id,
        from_date=from_date,
        to_date=to_date,
        prestamista_id=prestamista_id,
        route_id=route_id,
    )
    aging_data = await dashboard_service.aging(session, context.tenant_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["seccion", "concepto", "valor", "detalle"])

    indicators = [
        ("indicadores", "capital_prestado", f"{summary_data.capital_prestado:.2f}", ""),
        ("indicadores", "capital_recuperado", f"{summary_data.capital_recuperado:.2f}", ""),
        ("indicadores", "capital_proyectado", f"{summary_data.capital_proyectado:.2f}", ""),
        ("indicadores", "intereses_generados", f"{summary_data.intereses_generados:.2f}", ""),
        ("indicadores", "mora_cobrada", f"{summary_data.mora_cobrada:.2f}", ""),
        ("indicadores", "utilidad_generada", f"{summary_data.utilidad_generada:.2f}", ""),
        ("indicadores", "cartera_total", f"{summary_data.cartera_total:.2f}", ""),
        ("indicadores", "cartera_vencida", f"{summary_data.cartera_vencida:.2f}", ""),
        ("indicadores", "indice_morosidad", f"{summary_data.indice_morosidad:.2f}", "%"),
        ("indicadores", "prestamos_activos", str(summary_data.prestamos_activos), "prestamos"),
        ("indicadores", "prestamos_pagados", str(summary_data.prestamos_pagados), "prestamos"),
        ("indicadores", "prestamos_vencidos", str(summary_data.prestamos_vencidos), "prestamos"),
    ]
    writer.writerows(indicators)

    for bucket in aging_data.buckets:
        writer.writerow(
            [
                "aging",
                bucket.label,
                f"{bucket.amount:.2f}",
                f"{bucket.installments} cuotas",
            ]
        )

    meta = request_meta(request)
    await audit_service.record(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user.id,
        action="dashboard.export",
        entity="dashboard",
        after={
            "from_date": str(from_date) if from_date else None,
            "to_date": str(to_date) if to_date else None,
            "prestamista_id": str(prestamista_id) if prestamista_id else None,
            "route_id": str(route_id) if route_id else None,
        },
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        commit=True,
    )

    buffer.seek(0)
    slug = context.tenant.slug or "credigest"
    filename = f"dashboard-{slug}-{date.today().isoformat()}.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/accrue-late-fees",
    summary="Ejecutar cierre diario de mora",
    description=(
        "Recorre las cuotas vencidas de la financiera y consolida la mora "
        "devengada de forma idempotente (RN-20)."
    ),
)
async def run_daily_accrual(
    context: CurrentUserDep,
    session: SessionDep,
    request: Request,
    today: Annotated[date | None, Query()] = None,
) -> dict[str, int | str]:
    """Ejecuta el cierre diario de mora para la financiera actual."""
    _require_admin(context.role)

    result = await accrue_late_fees(
        session, today=today, tenant_id=context.tenant_id
    )
    meta = request_meta(request)
    await audit_service.record(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user.id,
        action="loan.accrue_late_fees",
        entity="loan",
        after={
            "evaluated_loans": result.evaluated_loans,
            "updated_installments": result.updated_installments,
            "overdue_loans": result.overdue_loans,
            "total_late_fee": f"{result.total_late_fee:.2f}",
        },
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        commit=True,
    )

    return {
        "evaluated_loans": result.evaluated_loans,
        "updated_installments": result.updated_installments,
        "overdue_loans": result.overdue_loans,
        "total_late_fee": f"{result.total_late_fee:.2f}",
    }

