"""Servicio de rutas de cobro.

Arma la lista diaria del cobrador a partir de las cuotas pendientes de una zona.

Reglas cubiertas:
- RN-42: agrupa cuotas pendientes o vencidas de una zona y fecha.
- RN-43: solo incluye cuotas con vencimiento hasta la fecha de la ruta.
- RN-44: orden por fecha de vencimiento y nombre, editable despues.
- RN-45: el cobrador solo ve sus propias rutas.
- RN-46: el estado de la parada refleja pagos y visitas.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.money import round_money
from app.models.client import Client
from app.models.collection_route import CollectionRoute, CollectionRouteItem
from app.models.loan import Installment, Loan
from app.models.user import User

#: Tamano maximo de pagina.
MAX_PAGE_SIZE = 100


class RouteError(Exception):
    """Error de negocio relacionado con rutas."""


class RouteNotFoundError(RouteError):
    """La ruta no existe o no pertenece al usuario."""


class RouteClosedError(RouteError):
    """La ruta ya esta cerrada y no admite cambios."""


class ItemNotFoundError(RouteError):
    """La parada no existe en la ruta."""


class InvalidCollectorError(RouteError):
    """El usuario indicado no puede ser cobrador."""


async def _validate_collector(
    session: AsyncSession, tenant_id: UUID, cobrador_id: UUID
) -> User:
    """Comprueba que el usuario exista, sea del tenant y pueda cobrar.

    Un Administrador tambien puede tener ruta asignada: en la practica cobra
    ocasionalmente.

    Raises:
        InvalidCollectorError: Si el usuario no cumple las condiciones.
    """
    user = await session.scalar(
        select(User).where(User.id == cobrador_id, User.tenant_id == tenant_id)
    )
    if user is None:
        raise InvalidCollectorError("El cobrador no existe en esta financiera.")
    if not user.is_active:
        raise InvalidCollectorError("El cobrador esta desactivado.")
    if user.role not in {"cobrador", "admin", "prestamista"}:
        raise InvalidCollectorError("El usuario no puede tener rutas asignadas.")
    return user


async def _pending_installments(
    session: AsyncSession,
    tenant_id: UUID,
    zone: str,
    route_date: date,
) -> Sequence[tuple[Installment, Loan, Client]]:
    """Cuotas pendientes de una zona con vencimiento hasta la fecha (RN-43).

    Solo considera prestamos activos o vencidos: uno cancelado o pagado no se
    cobra.
    """
    result = await session.execute(
        select(Installment, Loan, Client)
        .join(Loan, Loan.id == Installment.loan_id)
        .join(Client, Client.id == Loan.client_id)
        .where(
            Loan.tenant_id == tenant_id,
            Loan.status.in_(["activo", "vencido"]),
            Client.zone == zone,
            Client.status == "activo",
            Installment.due_date <= route_date,
            Installment.status.in_(["pendiente", "parcial", "vencida"]),
        )
        .order_by(Installment.due_date, Client.full_name)
    )
    return result.all()


async def create_route(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    zone: str,
    route_date: date,
    cobrador_id: UUID,
    created_by: UUID | None = None,
) -> CollectionRoute:
    """Genera una ruta con las cuotas pendientes de la zona.

    Si ya existe una ruta para el mismo cobrador, zona y fecha, se devuelve la
    existente en lugar de duplicarla.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera.
        zone: Zona de cobro.
        route_date: Dia de la visita.
        cobrador_id: Usuario que hara la ruta.
        created_by: Usuario que la genera, si es distinto del cobrador.

    Returns:
        La ruta generada o la existente.

    Raises:
        InvalidCollectorError: Si el cobrador no es valido.
    """
    await _validate_collector(session, tenant_id, cobrador_id)

    existing = await session.scalar(
        select(CollectionRoute)
        .options(selectinload(CollectionRoute.items))
        .where(
            CollectionRoute.tenant_id == tenant_id,
            CollectionRoute.cobrador_id == cobrador_id,
            CollectionRoute.zone == zone,
            CollectionRoute.route_date == route_date,
        )
    )
    if existing is not None:
        return existing

    route = CollectionRoute(
        tenant_id=tenant_id,
        cobrador_id=cobrador_id,
        zone=zone,
        route_date=route_date,
        status="activa",
    )
    session.add(route)
    await session.flush()

    pending = await _pending_installments(session, tenant_id, zone, route_date)

    for index, (installment, loan, client) in enumerate(pending, start=1):
        session.add(
            CollectionRouteItem(
                route_id=route.id,
                client_id=client.id,
                loan_id=loan.id,
                installment_id=installment.id,
                order_index=index,
                visit_status="pendiente",
            )
        )

    await session.commit()
    return await get_route(session, tenant_id, route.id, cobrador_id=None, is_admin=True)


async def get_route(
    session: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
    *,
    cobrador_id: UUID | None,
    is_admin: bool,
    refresh: bool = False,
) -> CollectionRoute:
    """Obtiene una ruta con sus paradas.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera.
        route_id: Ruta solicitada.
        cobrador_id: Usuario actual; se usa para validar la pertenencia.
        is_admin: Si el usuario es Administrador, puede ver cualquier ruta.
        refresh: Si es `True`, descarta el estado en cache de la sesion. Se usa
            despues de reordenar para reflejar el nuevo orden.

    Returns:
        La ruta con sus paradas.

    Raises:
        RouteNotFoundError: Si no existe, es de otro tenant o de otro cobrador
            (RN-45).
    """
    conditions = [CollectionRoute.id == route_id, CollectionRoute.tenant_id == tenant_id]
    if not is_admin and cobrador_id is not None:
        conditions.append(CollectionRoute.cobrador_id == cobrador_id)

    statement = (
        select(CollectionRoute)
        .options(selectinload(CollectionRoute.items))
        .where(*conditions)
    )
    if refresh:
        statement = statement.execution_options(populate_existing=True)

    route = await session.scalar(statement)
    if route is None:
        raise RouteNotFoundError("La ruta no existe.")
    return route


async def list_routes(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    cobrador_id: UUID | None = None,
    zone: str | None = None,
    route_date: date | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[CollectionRoute], int]:
    """Lista las rutas con filtros y paginacion."""
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    conditions = [CollectionRoute.tenant_id == tenant_id]
    if cobrador_id:
        conditions.append(CollectionRoute.cobrador_id == cobrador_id)
    if zone:
        conditions.append(CollectionRoute.zone == zone)
    if route_date:
        conditions.append(CollectionRoute.route_date == route_date)
    if status:
        conditions.append(CollectionRoute.status == status)

    total = await session.scalar(
        select(func.count()).select_from(CollectionRoute).where(*conditions)
    )

    result = await session.scalars(
        select(CollectionRoute)
        .options(selectinload(CollectionRoute.items))
        .where(*conditions)
        .order_by(CollectionRoute.route_date.desc(), CollectionRoute.zone)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return result.all(), int(total or 0)


async def update_item(
    session: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
    item_id: UUID,
    *,
    visit_status: str | None = None,
    notes: str | None = None,
    cobrador_id: UUID | None = None,
    is_admin: bool = False,
) -> CollectionRouteItem:
    """Actualiza el estado de una parada.

    Raises:
        RouteNotFoundError: Si la ruta no existe o no es del cobrador.
        RouteClosedError: Si la ruta ya se cerro.
        ItemNotFoundError: Si la parada no pertenece a la ruta.
    """
    route = await get_route(
        session, tenant_id, route_id, cobrador_id=cobrador_id, is_admin=is_admin
    )

    if route.status == "cerrada":
        raise RouteClosedError("La ruta esta cerrada y no admite cambios.")

    item = await session.scalar(
        select(CollectionRouteItem).where(
            CollectionRouteItem.id == item_id,
            CollectionRouteItem.route_id == route.id,
        )
    )
    if item is None:
        raise ItemNotFoundError("La parada no existe en esta ruta.")

    if visit_status is not None:
        item.visit_status = visit_status
    if notes is not None:
        item.notes = notes

    await session.commit()
    await session.refresh(item)
    return item


async def reorder_items(
    session: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
    item_ids: list[UUID],
    *,
    cobrador_id: UUID | None = None,
    is_admin: bool = False,
) -> CollectionRoute:
    """Cambia el orden de visita (RN-44).

    El orden debe incluir todas las paradas de la ruta; si falta alguna, se
    conserva al final en su orden actual.

    Raises:
        RouteNotFoundError: Si la ruta no existe o no es del cobrador.
        RouteClosedError: Si la ruta ya se cerro.
    """
    route = await get_route(
        session, tenant_id, route_id, cobrador_id=cobrador_id, is_admin=is_admin
    )

    if route.status == "cerrada":
        raise RouteClosedError("La ruta esta cerrada y no admite cambios.")

    by_id = {item.id: item for item in route.items}
    position = 0

    for item_id in item_ids:
        item = by_id.pop(item_id, None)
        if item is None:
            continue
        position += 1
        item.order_index = position

    for item in by_id.values():
        position += 1
        item.order_index = position

    await session.commit()

    return await get_route(
        session, tenant_id, route.id, cobrador_id=None, is_admin=True, refresh=True
    )


async def close_route(
    session: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
    *,
    notes: str | None = None,
    cobrador_id: UUID | None = None,
    is_admin: bool = False,
) -> CollectionRoute:
    """Cierra la ruta al terminar la jornada.

    Una ruta cerrada ya no admite cambios, lo que evita alterar el historico.
    """
    route = await get_route(
        session, tenant_id, route_id, cobrador_id=cobrador_id, is_admin=is_admin
    )

    route.status = "cerrada"
    if notes is not None:
        route.notes = notes

    await session.commit()
    await session.refresh(route)
    return route


def item_totals(installment: Installment) -> tuple[Decimal, Decimal, Decimal]:
    """Montos de una parada: lo esperado, la mora y el total a cobrar.

    Returns:
        Una tupla con (monto esperado de la cuota, mora, total pendiente).
    """
    amount_due = round_money(installment.amount)
    late_fee = round_money(installment.late_fee)
    total_due = round_money(
        max(Decimal("0.00"), installment.amount + installment.late_fee - installment.paid_amount)
    )

    return (amount_due, late_fee, total_due)
