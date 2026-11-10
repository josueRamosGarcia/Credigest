"""Servicio de clientes.

Concentra las reglas de negocio: unicidad de CURP por tenant, borrado logico y
filtro obligatorio por tenant.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.validation import parse_curp
from app.models.client import Client, ClientDocument, ClientReference
from app.schemas.client import ClientCreate, ClientUpdate
from app.services import audit_service

#: Tamano maximo de pagina para evitar consultas gigantes.
MAX_PAGE_SIZE = 100


class ClientError(Exception):
    """Error de negocio relacionado con clientes."""


class DuplicateCurpError(ClientError):
    """La CURP ya existe en esta financiera (RN-56)."""


class ClientNotFoundError(ClientError):
    """El cliente no existe o pertenece a otra financiera."""


class ClientHasHistoryError(ClientError):
    """El cliente tiene historial y no puede eliminarse (RN-57)."""


async def get_client(session: AsyncSession, tenant_id: UUID, client_id: UUID) -> Client:
    """Obtiene un cliente del tenant indicado.

    El filtro por `tenant_id` es obligatorio: sin el, un usuario podria leer
    datos de otra financiera (RNF-08).

    Raises:
        ClientNotFoundError: Si no existe o es de otro tenant.
    """
    client = await session.scalar(
        select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
    )
    if client is None:
        raise ClientNotFoundError("El cliente no existe.")
    return client


async def get_client_detail(
    session: AsyncSession, tenant_id: UUID, client_id: UUID
) -> Client:
    """Obtiene un cliente con sus referencias precargadas."""
    client = await session.scalar(
        select(Client)
        .options(selectinload(Client.references))
        .where(Client.id == client_id, Client.tenant_id == tenant_id)
    )
    if client is None:
        raise ClientNotFoundError("El cliente no existe.")
    return client


async def list_clients(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    search: str | None = None,
    zone: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[Client], int]:
    """Lista los clientes de un tenant con filtros y paginacion.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera cuyos clientes se consultan.
        search: Texto a buscar en nombre o CURP.
        zone: Zona de cobro.
        status: "activo" o "inactivo".
        page: Pagina, empezando en 1.
        page_size: Resultados por pagina (maximo 100).

    Returns:
        La pagina de clientes y el total de coincidencias.
    """
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    conditions = [Client.tenant_id == tenant_id]

    if search:
        term = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Client.full_name).like(term),
                func.lower(Client.curp).like(term),
                Client.phone.like(f"%{search.strip()}%"),
            )
        )

    if zone:
        conditions.append(Client.zone == zone)

    if status:
        conditions.append(Client.status == status)

    total = await session.scalar(select(func.count()).select_from(Client).where(*conditions))

    result = await session.scalars(
        select(Client)
        .where(*conditions)
        .order_by(Client.full_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return result.all(), int(total or 0)


async def create_client(
    session: AsyncSession,
    tenant_id: UUID,
    created_by: UUID,
    payload: ClientCreate,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Client:
    """Registra un cliente nuevo.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera a la que pertenece.
        created_by: Usuario que lo registra.
        payload: Datos ya validados por Pydantic.

    Returns:
        El cliente creado con sus referencias.

    Raises:
        DuplicateCurpError: Si la CURP ya existe en el tenant (RN-56).
    """
    existing = await session.scalar(
        select(Client.id).where(Client.tenant_id == tenant_id, Client.curp == payload.curp)
    )
    if existing is not None:
        raise DuplicateCurpError("Ya existe un cliente con esa CURP en esta financiera.")

    client = Client(
        tenant_id=tenant_id,
        full_name=payload.full_name,
        curp=payload.curp,
        phone=payload.phone,
        address=payload.address,
        zone=payload.zone,
        notes=payload.notes,
        birth_date=parse_curp(payload.curp).birth_date,
        created_by=created_by,
    )
    session.add(client)
    await session.flush()

    for reference in payload.references:
        session.add(
            ClientReference(
                client_id=client.id,
                name=reference.name,
                relation=reference.relationship,
                phone=reference.phone,
                address=reference.address,
            )
        )

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=created_by,
        action="client.create",
        entity="client",
        entity_id=client.id,
        after={
            "full_name": client.full_name,
            "curp": client.curp,
            "phone": client.phone,
            "zone": client.zone,
            "status": client.status,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    return await get_client_detail(session, tenant_id, client.id)


async def update_client(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    payload: ClientUpdate,
    *,
    actor_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Client:
    """Actualiza los campos editables de un cliente.

    Solo se aplican los campos presentes en la peticion.

    Raises:
        ClientNotFoundError: Si el cliente no existe en el tenant.
    """
    client = await get_client(session, tenant_id, client_id)

    changes = payload.model_dump(exclude_unset=True)
    before = {field: getattr(client, field) for field in changes}

    for field, value in changes.items():
        setattr(client, field, value)

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="client.update",
        entity="client",
        entity_id=client.id,
        before=before,
        after=changes,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    return await get_client_detail(session, tenant_id, client_id)


async def change_status(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    status: str,
    *,
    actor_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Client:
    """Activa o desactiva un cliente (RN-58).

    Desactivar impide crear prestamos nuevos, pero conserva el historial.
    """
    client = await get_client(session, tenant_id, client_id)
    previous = client.status
    client.status = status

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="client.status_change",
        entity="client",
        entity_id=client.id,
        before={"status": previous},
        after={"status": status},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    return client


async def add_reference(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    *,
    name: str,
    relationship: str,
    phone: str,
    address: str,
) -> ClientReference:
    """Agrega una referencia personal a un cliente existente."""
    await get_client(session, tenant_id, client_id)

    reference = ClientReference(
        client_id=client_id,
        name=name,
        relation=relationship,
        phone=phone,
        address=address,
    )
    session.add(reference)
    await session.commit()
    await session.refresh(reference)
    return reference


async def list_documents(
    session: AsyncSession, tenant_id: UUID, client_id: UUID
) -> Sequence[ClientDocument]:
    """Lista los documentos de un cliente."""
    await get_client(session, tenant_id, client_id)

    result = await session.scalars(
        select(ClientDocument)
        .where(ClientDocument.client_id == client_id)
        .order_by(ClientDocument.created_at)
    )
    return result.all()


async def add_document(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    *,
    doc_type: str,
    file_key: str,
    mime_type: str,
    size_bytes: int,
    uploaded_by: UUID,
) -> ClientDocument:
    """Registra un documento ya subido al almacenamiento.

    El archivo se sube antes y aqui solo se guarda la referencia (RN-60).
    """
    await get_client(session, tenant_id, client_id)

    document = ClientDocument(
        client_id=client_id,
        doc_type=doc_type,
        file_key=file_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        uploaded_by=uploaded_by,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document
