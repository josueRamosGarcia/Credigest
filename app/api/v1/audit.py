"""Endpoints de auditoria.

Solo lectura: no existen rutas para modificar ni borrar registros, porque la
bitacora es append-only (RN-66). El acceso esta limitado al Administrador.
"""

import csv
import io
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.db.session import get_session
from app.schemas.audit import AuditEntry, AuditListResponse
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["auditoria"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "",
    response_model=AuditListResponse,
    summary="Consultar la bitacora",
    description=(
        "Devuelve los movimientos registrados, del mas reciente al mas antiguo. "
        "Se puede filtrar por fecha, usuario, accion y entidad."
    ),
)
async def list_audit(
    context: CurrentUserDep,
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
    description="Descarga los registros filtrados como archivo CSV.",
    response_class=StreamingResponse,
)
async def export_audit(
    context: CurrentUserDep,
    session: SessionDep,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    entity: Annotated[str | None, Query(max_length=80)] = None,
) -> StreamingResponse:
    """Exporta la bitacora filtrada a CSV.

    Se exportan como maximo 10,000 registros para no agotar la memoria del
    servidor. Si se necesita mas, conviene filtrar por fecha.
    """
    entries, _ = await audit_service.list_entries(
        session,
        context.tenant_id,
        from_date=from_date,
        to_date=to_date,
        user_id=user_id,
        action=action,
        entity=entity,
        page=1,
        page_size=200,
    )

    # Se pagina internamente hasta juntar 10,000 registros como maximo.
    collected = list(entries)
    current_page = 1
    while len(collected) < 10_000:
        current_page += 1
        batch, _ = await audit_service.list_entries(
            session,
            context.tenant_id,
            from_date=from_date,
            to_date=to_date,
            user_id=user_id,
            action=action,
            entity=entity,
            page=current_page,
            page_size=200,
        )
        if not batch:
            break
        collected.extend(batch)

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
                data["action"],
                data["entity"],
                data["entity_id"],
                data["before"],
                data["after"],
                data["ip_address"],
                data["user_agent"],
            ]
        )

    buffer.seek(0)
    filename = f"auditoria-{context.tenant.slug or 'credigest'}-{date.today().isoformat()}.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
