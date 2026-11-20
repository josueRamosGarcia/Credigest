"""Endpoints de auditoria.

Solo lectura: no existen rutas para modificar ni borrar registros, porque la
bitacora es append-only (RN-66). El acceso esta limitado al Administrador.
"""

import csv
import io
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditEntry, AuditListResponse
from app.services import audit_service
from app.services.payment_service import business_today

router = APIRouter(prefix="/audit", tags=["auditoria"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminDep = Annotated[AuthContext, Depends(require_role("admin"))]

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_csv_cell(value: Any) -> Any:
    """Neutraliza inyeccion de formulas al abrir el CSV en hojas de calculo."""
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


@router.get(
    "",
    response_model=AuditListResponse,
    summary="Consultar la bitacora",
    description=(
        "Devuelve los movimientos registrados, del mas reciente al mas antiguo. "
        "Se puede filtrar por fecha, usuario, accion y entidad. Solo Administrador."
    ),
)
async def list_audit(
    context: AdminDep,
    session: SessionDep,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    entity: Annotated[str | None, Query(max_length=80)] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditListResponse:
    """Consulta la bitacora con filtros."""
    entries, total = await audit_service.list_entries(
        session,
        context.tenant_id,
        from_date=from_date,
        to_date=to_date,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )

    return AuditListResponse(
        items=[AuditEntry.model_validate(audit_service.entry_to_dict(entry)) for entry in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/export.csv",
    summary="Exportar la bitacora a CSV",
    description="Descarga los registros filtrados como archivo CSV. Solo Administrador.",
    response_class=StreamingResponse,
)
async def export_audit(
    context: AdminDep,
    session: SessionDep,
    request: Request,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    entity: Annotated[str | None, Query(max_length=80)] = None,
) -> StreamingResponse:
    """Exporta la bitacora filtrada a CSV.

    Se exportan como maximo 10,000 registros mediante paginacion por cursor
    para evitar consultas COUNT redundantes y desplazamientos por inserciones.
    """
    max_rows = 10_000
    batch_size = 200
    collected: list[AuditLog] = []
    cursor_id: int | None = None

    while len(collected) < max_rows:
        remaining = max_rows - len(collected)
        batch = await audit_service.list_entries_after_cursor(
            session,
            context.tenant_id,
            from_date=from_date,
            to_date=to_date,
            user_id=user_id,
            action=action,
            entity=entity,
            before_id=cursor_id,
            limit=min(batch_size, remaining),
        )
        if not batch:
            break
        collected.extend(batch)
        cursor_id = batch[-1].id
        if len(batch) < min(batch_size, remaining):
            break

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "fecha",
            "usuario",
            "accion",
            "entidad",
            "entidad_id",
            "antes",
            "despues",
            "ip",
            "user_agent",
        ]
    )

    for entry in collected:
        data = audit_service.entry_to_dict(entry)
        writer.writerow(
            [
                data["id"],
                data["created_at"],
                data["user_id"],
                _safe_csv_cell(data["action"]),
                _safe_csv_cell(data["entity"]),
                data["entity_id"],
                _safe_csv_cell(str(data["before"]) if data["before"] is not None else ""),
                _safe_csv_cell(str(data["after"]) if data["after"] is not None else ""),
                data["ip_address"],
                _safe_csv_cell(data["user_agent"]),
            ]
        )

    meta = request_meta(request)
    await audit_service.record(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user.id,
        action="audit.export",
        entity="audit_log",
        after={"exported_rows": len(collected)},
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
        commit=True,
    )

    buffer.seek(0)
    filename = f"auditoria-{context.tenant.slug or 'credigest'}-{business_today().isoformat()}.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
