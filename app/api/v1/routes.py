"""Endpoints de rutas de cobro.

El cobrador solo ve sus rutas (RN-45); el Administrador ve todas y puede
generarlas para cualquier cobrador.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, CurrentUserDep, require_role
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.models.client import Client
from app.models.collection_route import CollectionRoute
from app.models.loan import Installment, Loan
from app.models.user import User
from app.schemas.collection_route import (
    CollectorOption,
    RouteCreate,
    RouteDetail,
    RouteItemRead,
    RouteItemUpdate,
    RouteListResponse,
    RouteRead,
    RouteReorder,
    ZoneOption,
)
from app.services import audit_service, route_service
from app.services.payment_service import business_today

router = APIRouter(prefix="/routes", tags=["rutas de cobro"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LenderDep = Annotated[AuthContext, Depends(require_role("prestamista"))]


def _not_found(message: str) -> HTTPException:
    """Error uniforme de recurso inexistente."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _conflict(message: str) -> HTTPException:
    """Error de regla de negocio."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


async def _collector_names(session: AsyncSession, collector_ids: set[UUID]) -> dict[UUID, str]:
    """Resuelve los nombres de los cobradores en una sola consulta."""
    if not collector_ids:
        return {}
    rows = await session.execute(
        select(User.id, User.full_name).where(User.id.in_(collector_ids))
    )
    return {user_id: full_name for user_id, full_name in rows.all()}


async def _build_detail(
    session: AsyncSession, route: CollectionRoute, *, include_items: bool = True
) -> RouteDetail:
    """Arma la respuesta con los datos del cliente y la cuota de cada parada.

    Se resuelven en una sola consulta para evitar el problema N+1.
    """
    pending_items = sum(1 for item in route.items if item.visit_status == "pendiente")
    paid_items = sum(1 for item in route.items if item.visit_status == "pagado")
    names = await _collector_names(session, {route.cobrador_id})
    cobrador_name = names.get(route.cobrador_id)

    if not include_items or not route.items:
        return RouteDetail(
            id=route.id,
            cobrador_id=route.cobrador_id,
            cobrador_name=cobrador_name,
            zone=route.zone,
            route_date=route.route_date,
            status=route.status,
            notes=route.notes,
            total_items=len(route.items),
            pending_items=pending_items,
            paid_items=paid_items,
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
                client_neighborhood=client.neighborhood,
                client_latitude=client.latitude,
                client_longitude=client.longitude,
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
        cobrador_name=cobrador_name,
        zone=route.zone,
        route_date=route.route_date,
        status=route.status,
        notes=route.notes,
        total_items=len(items),
        pending_items=pending_items,
        paid_items=paid_items,
        items=items,
    )


@router.get(
    "/zones",
    response_model=list[ZoneOption],
    summary="Listar zonas disponibles para rutas",
    description=(
        "Devuelve las zonas de clientes activos de la financiera junto con el "
        "numero de cuotas pendientes hasta la fecha indicada."
    ),
)
async def list_route_zones(
    context: LenderDep,
    session: SessionDep,
    route_date: Annotated[date | None, Query()] = None,
) -> list[ZoneOption]:
    """Lista zonas seleccionables para generar una ruta sin escribirla a mano."""
    effective_date = route_date or business_today()
    rows = await route_service.list_zones(session, context.tenant_id, effective_date)
    return [
        ZoneOption(
            zone=zone,
            active_clients=active_clients,
            pending_installments=pending_installments,
        )
        for zone, active_clients, pending_installments in rows
    ]


@router.get(
    "/collectors",
    response_model=list[CollectorOption],
    summary="Listar cobradores disponibles",
    description=(
        "Devuelve los usuarios activos de la financiera a los que se les puede "
        "asignar una ruta de cobro."
    ),
)
async def list_collectors(
    context: LenderDep,
    session: SessionDep,
) -> list[CollectorOption]:
    """Lista los usuarios activos asignables a una ruta, priorizando cobradores."""
    users = (
        await session.scalars(
            select(User)
            .where(
                User.tenant_id == context.tenant_id,
                User.is_active.is_(True),
                User.role.in_(["cobrador", "prestamista", "admin"]),
            )
            .order_by(User.full_name)
        )
    ).all()
    role_priority = {"cobrador": 0, "prestamista": 1, "admin": 2}
    ordered = sorted(users, key=lambda u: (role_priority.get(u.role, 9), u.full_name.lower()))
    return [CollectorOption.model_validate(user) for user in ordered]


@router.get(
    "",
    response_model=RouteListResponse,
    summary="Listar rutas",
    description=(
        "El Administrador y Prestamista ven todas las rutas; el cobrador solo las suyas (RN-45)."
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
    is_manager = context.role in {"admin", "prestamista"}
    effective_collector = None
    if not is_manager:
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
    names = await _collector_names(session, {route.cobrador_id for route in items})

    return RouteListResponse(
        items=[
            RouteRead(
                id=route.id,
                cobrador_id=route.cobrador_id,
                cobrador_name=names.get(route.cobrador_id),
                zone=route.zone,
                route_date=route.route_date,
                status=route.status,
                notes=route.notes,
                total_items=len(route.items),
                pending_items=sum(
                    1 for item in route.items if item.visit_status == "pendiente"
                ),
                paid_items=sum(
                    1 for item in route.items if item.visit_status == "pagado"
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
        "fecha indicada. Si la ruta ya existe, devuelve la existente. "
        "Solo el Administrador o Prestamista pueden crear y asignar rutas."
    ),
)
async def create_route(
    payload: RouteCreate,
    context: LenderDep,
    session: SessionDep,
    request: Request,
) -> RouteDetail:
    """Genera una ruta de cobro.

    Raises:
        HTTPException: 400 si el cobrador no es valido; 403 si es cobrador.
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

    meta = request_meta(request)
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
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
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
            is_admin=context.role in {"admin", "prestamista"},
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
            is_admin=context.role in {"admin", "prestamista"},
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
        client_neighborhood=client.neighborhood,
        client_latitude=client.latitude,
        client_longitude=client.longitude,
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
            is_admin=context.role in {"admin", "prestamista"},
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
            is_admin=context.role in {"admin", "prestamista"},
        )
    except route_service.RouteNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    names = await _collector_names(session, {route.cobrador_id})
    return RouteRead(
        id=route.id,
        cobrador_id=route.cobrador_id,
        cobrador_name=names.get(route.cobrador_id),
        zone=route.zone,
        route_date=route.route_date,
        status=route.status,
        notes=route.notes,
        total_items=len(route.items),
        pending_items=sum(1 for item in route.items if item.visit_status == "pendiente"),
        paid_items=sum(1 for item in route.items if item.visit_status == "pagado"),
    )
