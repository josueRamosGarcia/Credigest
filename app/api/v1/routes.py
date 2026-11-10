"""Endpoints de rutas de cobro.

El cobrador solo ve sus rutas (RN-45); el Administrador ve todas y puede
generarlas para cualquier cobrador.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.db.session import get_session
from app.models.client import Client
from app.models.collection_route import CollectionRoute
from app.models.loan import Installment, Loan
from app.schemas.collection_route import (
    RouteCreate,
    RouteDetail,
    RouteItemRead,
    RouteItemUpdate,
    RouteListResponse,
    RouteRead,
    RouteReorder,
)
from app.services import audit_service, route_service

router = APIRouter(prefix="/routes", tags=["rutas de cobro"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _not_found(message: str) -> HTTPException:
    """Error uniforme de recurso inexistente."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _conflict(message: str) -> HTTPException:
    """Error de regla de negocio."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


async def _build_detail(
    session: AsyncSession, route: CollectionRoute, *, include_items: bool = True
) -> RouteDetail:
    """Arma la respuesta con los datos del cliente y la cuota de cada parada.

    Se resuelven en una sola consulta para evitar el problema N+1.
    """
    pending_items = sum(1 for item in route.items if item.visit_status == "pendiente")

    if not include_items or not route.items:
        return RouteDetail(
            id=route.id,
            cobrador_id=route.cobrador_id,
            zone=route.zone,
            route_date=route.route_date,
            status=route.status,
            notes=route.notes,
            total_items=len(route.items),
            pending_items=pending_items,
            items=[],
        )

    installment_ids = [item.installment_id for item in route.items]

    rows = await session.execute(
        select(Installment, Client)
        .join(Loan, Loan.id == Installment.loan_id)
        .join(Client, Client.id == Loan.client_id)
        .where(Installment.id.in_(installment_ids))
    )
    by_installment: dict[UUID, tuple[Installment, Client]] = {}
    for installment, client in rows.all():
        by_installment[installment.id] = (installment, client)

    items: list[RouteItemRead] = []
    for item in route.items:
        pair = by_installment.get(item.installment_id)
        if pair is None:
            continue

        installment, client = pair
        amount_due, late_fee, total_due = route_service.item_totals(installment)

        items.append(
            RouteItemRead(
                id=item.id,
                client_id=item.client_id,
                loan_id=item.loan_id,
                installment_id=item.installment_id,
                order_index=item.order_index,
                visit_status=item.visit_status,
                notes=item.notes,
                client_name=client.full_name,
                client_address=client.address,
                client_phone=client.phone,
                installment_number=installment.number,
                due_date=installment.due_date,
                amount_due=amount_due,
                late_fee=late_fee,
                total_due=total_due,
            )
        )

    return RouteDetail(
        id=route.id,
        cobrador_id=route.cobrador_id,
        zone=route.zone,
        route_date=route.route_date,
        status=route.status,
        notes=route.notes,
        total_items=len(items),
        pending_items=pending_items,
        items=items,
    )


@router.get(
    "",
    response_model=RouteListResponse,
    summary="Listar rutas",
    description=(
        "El Administrador ve todas las rutas; el cobrador solo las suyas (RN-45)."
    ),
)
async def list_routes(
    context: CurrentUserDep,
    session: SessionDep,
    zone: Annotated[str | None, Query(max_length=80)] = None,
    route_date: Annotated[date | None, Query()] = None,
    route_status: Annotated[
        str | None, Query(alias="status", pattern="^(borrador|activa|cerrada)$")
    ] = None,
    cobrador_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RouteListResponse:
    """Lista las rutas visibles para el usuario."""
    effective_collector = None
    if context.role != "admin":
        effective_collector = context.user.id
    elif cobrador_id is not None:
        effective_collector = cobrador_id

    items, total = await route_service.list_routes(
        session,
        context.tenant_id,
        cobrador_id=effective_collector,
        zone=zone,
        route_date=route_date,
        status=route_status,
        page=page,
        page_size=page_size,
    )

    return RouteListResponse(
        items=[
            RouteRead(
                id=route.id,
                cobrador_id=route.cobrador_id,
                zone=route.zone,
                route_date=route.route_date,
                status=route.status,
                notes=route.notes,
                total_items=len(route.items),
                pending_items=sum(
                    1 for item in route.items if item.visit_status == "pendiente"
                ),
            )
            for route in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=RouteDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Generar una ruta",
    description=(
        "Arma la lista de cuotas pendientes de una zona con vencimiento hasta la "
        "fecha indicada. Si la ruta ya existe, devuelve la existente."
    ),
)
async def create_route(
    payload: RouteCreate,
    context: CurrentUserDep,
    session: SessionDep,
) -> RouteDetail:
    """Genera una ruta de cobro.

    Raises:
        HTTPException: 400 si el cobrador no es valido.
    """
    target = payload.cobrador_id or context.user.id

    try:
        route = await route_service.create_route(
            session,
            context.tenant_id,
            zone=payload.zone,
            route_date=payload.route_date,
            cobrador_id=target,
            created_by=context.user.id,
        )
    except route_service.InvalidCollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    await audit_service.record(
        session,
        tenant_id=context.tenant_id,
        user_id=context.user.id,
        action="route.create",
        entity="collection_route",
        entity_id=route.id,
        after={
            "zone": route.zone,
            "route_date": str(route.route_date),
            "cobrador_id": str(route.cobrador_id),
            "items": len(route.items),
        },
        commit=True,
    )

    return await _build_detail(session, route)


@router.get(
    "/{route_id}",
    response_model=RouteDetail,
    summary="Consultar una ruta",
)
async def get_route(
    route_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> RouteDetail:
    """Devuelve la ruta con todas sus paradas.

    Raises:
        HTTPException: 404 si no existe o no es del cobrador (RN-45).
    """
    try:
        route = await route_service.get_route(
            session,
            context.tenant_id,
            route_id,
            cobrador_id=context.user.id,
            is_admin=context.role == "admin",
        )
    except route_service.RouteNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    return await _build_detail(session, route)


@router.patch(
    "/{route_id}/items/{item_id}",
    response_model=RouteItemRead,
    summary="Actualizar una parada",
    description="El cobrador marca la visita como pagada o no pagada y deja notas.",
)
async def update_item(
    route_id: UUID,
    item_id: UUID,
    payload: RouteItemUpdate,
    context: CurrentUserDep,
    session: SessionDep,
) -> RouteItemRead:
    """Actualiza el estado de una parada.

    Raises:
        HTTPException: 404 si no existe; 409 si la ruta esta cerrada.
    """
    try:
        item = await route_service.update_item(
            session,
            context.tenant_id,
            route_id,
            item_id,
            visit_status=payload.visit_status,
            notes=payload.notes,
            cobrador_id=context.user.id,
            is_admin=context.role == "admin",
        )
    except route_service.RouteNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except route_service.ItemNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except route_service.RouteClosedError as exc:
        raise _conflict(str(exc)) from exc

    installment = await session.get(Installment, item.installment_id)
    client = await session.get(Client, item.client_id)
    assert installment is not None and client is not None

    amount_due, late_fee, total_due = route_service.item_totals(installment)

    return RouteItemRead(
        id=item.id,
        client_id=item.client_id,
        loan_id=item.loan_id,
        installment_id=item.installment_id,
        order_index=item.order_index,
        visit_status=item.visit_status,
        notes=item.notes,
        client_name=client.full_name,
        client_address=client.address,
        client_phone=client.phone,
        installment_number=installment.number,
        due_date=installment.due_date,
        amount_due=amount_due,
        late_fee=late_fee,
        total_due=total_due,
    )


@router.post(
    "/{route_id}/reorder",
    response_model=RouteDetail,
    summary="Reordenar la ruta",
    description="Cambia el orden de visita segun la lista de identificadores.",
)
async def reorder_route(
    route_id: UUID,
    payload: RouteReorder,
    context: CurrentUserDep,
    session: SessionDep,
) -> RouteDetail:
    """Reordena las paradas de la ruta (RN-44)."""
    try:
        route = await route_service.reorder_items(
            session,
            context.tenant_id,
            route_id,
            payload.item_ids,
            cobrador_id=context.user.id,
            is_admin=context.role == "admin",
        )
    except route_service.RouteNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except route_service.RouteClosedError as exc:
        raise _conflict(str(exc)) from exc

    return await _build_detail(session, route)


@router.post(
    "/{route_id}/close",
    response_model=RouteRead,
    summary="Cerrar la ruta",
    description="Marca la jornada como terminada; ya no admite cambios.",
)
async def close_route(
    route_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> RouteRead:
    """Cierra la ruta del dia."""
    try:
        route = await route_service.close_route(
            session,
            context.tenant_id,
            route_id,
            cobrador_id=context.user.id,
            is_admin=context.role == "admin",
        )
    except route_service.RouteNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    return RouteRead(
        id=route.id,
        cobrador_id=route.cobrador_id,
        zone=route.zone,
        route_date=route.route_date,
        status=route.status,
        notes=route.notes,
    )
