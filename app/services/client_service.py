"""Servicio de clientes.

Concentra las reglas de negocio: unicidad de CURP por tenant, borrado logico y
filtro obligatorio por tenant.
"""

import secrets
from collections.abc import Sequence
from urllib.parse import quote
from uuid import UUID

import bcrypt
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import BCRYPT_ROUNDS
from app.domain.validation import parse_curp
from app.models.client import Client, ClientDocument, ClientReference
from app.models.tenant import Tenant
from app.schemas.client import ClientCreate, ClientUpdate, compose_address
from app.services import audit_service

_ADDRESS_PARTS = frozenset(
    {"street", "exterior_number", "neighborhood", "postal_code", "city", "state"}
)

#: Tamano maximo de pagina para evitar consultas gigantes.
MAX_PAGE_SIZE = 100

#: Limite de clientes activos por plan (RN-68).
CLIENT_PLAN_LIMITS: dict[str, int | None] = {
    "basico": 50,
    "profesional": 200,
    "empresarial": None,
}


class ClientError(Exception):
    """Error de negocio relacionado con clientes."""


class DuplicateCurpError(ClientError):
    """La CURP ya existe en esta financiera (RN-56)."""


class ClientNotFoundError(ClientError):
    """El cliente no existe o pertenece a otra financiera."""


class ClientHasHistoryError(ClientError):
    """El cliente tiene historial y no puede eliminarse (RN-57)."""


class ClientPlanLimitError(ClientError):
    """Se alcanzo el limite de clientes activos del plan (RN-68)."""


async def _enforce_client_plan_limit(
    session: AsyncSession, tenant_id: UUID
) -> None:
    """Verifica que el tenant no supere el limite de clientes activos (RN-68)."""
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        return

    limit = CLIENT_PLAN_LIMITS.get(tenant.plan)
    if limit is None:
        return

    active_count = await session.scalar(
        select(func.count())
        .select_from(Client)
        .where(Client.tenant_id == tenant_id, Client.status == "activo")
    )
    if int(active_count or 0) >= limit:
        raise ClientPlanLimitError(
            f"Tu plan '{tenant.plan}' permite hasta {limit} clientes activos. "
            "Sube de plan para registrar mas clientes."
        )


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


async def list_zones(session: AsyncSession, tenant_id: UUID) -> list[str]:
    """Devuelve las zonas distintas registradas en los clientes de la financiera."""
    rows = await session.scalars(
        select(Client.zone)
        .where(
            Client.tenant_id == tenant_id,
            Client.zone.is_not(None),
            Client.zone != "",
        )
        .distinct()
        .order_by(Client.zone)
    )
    return [zone for zone in rows.all() if zone]


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
        ClientPlanLimitError: Si se alcanzo el limite del plan (RN-68).
    """
    await _enforce_client_plan_limit(session, tenant_id)

    existing = await session.scalar(
        select(Client.id).where(Client.tenant_id == tenant_id, Client.curp == payload.curp)
    )
    if existing is not None:
        raise DuplicateCurpError("Ya existe un cliente con esa CURP en esta financiera.")

    assert payload.address is not None
    client = Client(
        tenant_id=tenant_id,
        full_name=payload.full_name,
        curp=payload.curp,
        phone=payload.phone,
        address=payload.address,
        street=payload.street,
        exterior_number=payload.exterior_number,
        neighborhood=payload.neighborhood,
        postal_code=payload.postal_code,
        city=payload.city,
        state=payload.state,
        latitude=payload.latitude,
        longitude=payload.longitude,
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

    # Si se editaron componentes estructurados de domicilio sin enviar `address`,
    # se recompone el texto completo para mantenerlo sincronizado en pagares y recibos.
    if "address" not in changes and (_ADDRESS_PARTS & changes.keys()):
        composed = compose_address(
            street=client.street,
            exterior_number=client.exterior_number,
            neighborhood=client.neighborhood,
            postal_code=client.postal_code,
            city=client.city,
            state=client.state,
        )
        if composed:
            before["address"] = client.address
            client.address = composed
            changes["address"] = composed

    def _audit_val(val: object) -> object:
        return str(val) if val is not None and not isinstance(val, (str, int, float, bool)) else val

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="client.update",
        entity="client",
        entity_id=client.id,
        before={k: _audit_val(v) for k, v in before.items()},
        after={k: _audit_val(v) for k, v in changes.items()},
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
    if status == "activo" and client.status != "activo":
        await _enforce_client_plan_limit(session, tenant_id)

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


async def remove_document(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    document_id: UUID,
) -> str:
    """Elimina un documento y devuelve su clave de almacenamiento.

    El borrado del archivo fisico lo hace quien llama: el servicio no conoce el
    almacenamiento.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera del usuario.
        client_id: Cliente dueno del documento.
        document_id: Documento a eliminar.

    Returns:
        La clave del archivo, para que el llamador lo borre del almacen.

    Raises:
        ClientNotFoundError: Si el cliente no existe o el documento no le
            pertenece.
    """
    await get_client(session, tenant_id, client_id)

    document = await session.scalar(
        select(ClientDocument).where(
            ClientDocument.id == document_id,
            ClientDocument.client_id == client_id,
        )
    )
    if document is None:
        raise ClientNotFoundError("El documento no existe.")

    file_key = document.file_key
    await session.delete(document)
    await session.commit()

    return file_key


async def anonymize_client(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    *,
    actor_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[Client, list[str]]:
    """Anonimiza los datos personales de un cliente a solicitud del titular (RN-70).

    Reemplaza nombre, CURP, telefono y direccion por valores seudonimos,
    desactiva el registro y elimina referencias y documentos. La bitacora
    conserva unicamente identificadores internos.

    Returns:
        Tupla `(cliente, file_keys)` para que el llamador elimine los archivos
        fisicos del almacenamiento.
    """
    client = await get_client(session, tenant_id, client_id)

    docs = await list_documents(session, tenant_id, client_id)
    file_keys = [doc.file_key for doc in docs]

    await session.execute(
        delete(ClientReference).where(ClientReference.client_id == client.id)
    )
    await session.execute(
        delete(ClientDocument).where(ClientDocument.client_id == client.id)
    )

    pseudonym_curp = f"ANON{client.id.hex[:14].upper()}"
    client.full_name = f"CLIENTE ANONIMIZADO {client.id.hex[:6].upper()}"
    client.curp = pseudonym_curp
    client.phone = "0000000000"
    client.address = "DATOS ANONIMIZADOS"
    client.street = None
    client.exterior_number = None
    client.neighborhood = None
    client.postal_code = None
    client.city = None
    client.state = None
    client.latitude = None
    client.longitude = None
    client.zone = None
    client.birth_date = None
    client.notes = None
    client.portal_pin_hash = None
    client.status = "inactivo"

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="client.anonymize",
        entity="client",
        entity_id=client.id,
        after={
            "anonymized": True,
            "removed_documents": len(file_keys),
            "status": "inactivo",
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    return await get_client_detail(session, tenant_id, client.id), file_keys


def _hash_pin(pin: str) -> str:
    """Genera el hash bcrypt de un PIN de 6 digitos (RNF-06)."""
    return bcrypt.hashpw(
        pin.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def generate_portal_pin() -> str:
    """Genera un PIN numerico aleatorio de 6 digitos."""
    return f"{secrets.randbelow(1_000_000):06d}"


def build_portal_whatsapp_url(
    phone: str, tenant_name: str, curp: str, pin: str
) -> str:
    """Arma el enlace de WhatsApp con las instrucciones de acceso al portal."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = f"52{digits}"
    message = (
        f"Hola, *{tenant_name}* te comparte tu acceso para consultar el "
        f"estado y avance de tus prestamos:\n"
        f"- CURP: {curp}\n"
        f"- PIN de 6 digitos: *{pin}*"
    )
    return f"https://wa.me/{digits}?text={quote(message)}"


async def set_portal_pin(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    *,
    pin: str | None = None,
    actor_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[Client, str]:
    """Asigna o genera un PIN de 6 digitos para el portal del cliente."""
    client = await get_client(session, tenant_id, client_id)
    chosen_pin = pin or generate_portal_pin()
    client.portal_pin_hash = _hash_pin(chosen_pin)

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="client.portal_pin_reset",
        entity="client",
        entity_id=client.id,
        after={"portal_pin_configured": True},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    await session.refresh(client)
    return client, chosen_pin


