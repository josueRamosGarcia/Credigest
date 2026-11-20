"""Endpoints de clientes.

Todos los endpoints filtran por el tenant del usuario autenticado. El
aislamiento no se delega al cliente de la API: se aplica en el servicio.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, CurrentUserDep, require_role
from app.core.request_meta import request_meta
from app.core.storage import get_storage
from app.db.session import get_session
from app.schemas.client import (
    ClientCreate,
    ClientDetail,
    ClientListResponse,
    ClientRead,
    ClientReferenceCreate,
    ClientReferenceRead,
    ClientStatusChange,
    ClientUpdate,
    DocumentRead,
    PortalPinResponse,
    PortalPinSetRequest,
)
from app.services import client_service

router = APIRouter(prefix="/clients", tags=["clientes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LenderDep = Annotated[AuthContext, Depends(require_role("prestamista"))]


def _not_found() -> HTTPException:
    """Error uniforme para cliente inexistente o de otro tenant."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="El cliente no existe.",
    )


@router.get(
    "",
    response_model=ClientListResponse,
    summary="Listar clientes",
    description=(
        "Devuelve los clientes de la financiera del usuario. "
        "Permite buscar por nombre, CURP o telefono, y filtrar por zona y estado."
    ),
)
async def list_clients(
    context: LenderDep,
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    zone: Annotated[str | None, Query(max_length=80)] = None,
    client_status: Annotated[
        str | None, Query(alias="status", pattern="^(activo|inactivo)$")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ClientListResponse:
    """Lista los clientes con paginacion."""
    items, total = await client_service.list_clients(
        session,
        context.tenant_id,
        search=search,
        zone=zone,
        status=client_status,
        page=page,
        page_size=page_size,
    )

    return ClientListResponse(
        items=[ClientRead.model_validate(client) for client in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ClientDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un cliente",
    description=(
        "Valida la CURP (estructura y digito verificador) y evita duplicados "
        "dentro de la misma financiera."
    ),
)
async def create_client(
    payload: ClientCreate,
    context: LenderDep,
    session: SessionDep,
    request: Request,
) -> ClientDetail:
    """Registra un cliente nuevo con sus referencias.

    Raises:
        HTTPException: 409 si la CURP ya existe en la financiera.
    """
    try:
        meta = request_meta(request)
        client = await client_service.create_client(
            session,
            context.tenant_id,
            context.user.id,
            payload,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except client_service.DuplicateCurpError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except client_service.ClientPlanLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ClientDetail.model_validate(client)


@router.get(
    "/zones",
    response_model=list[str],
    summary="Listar zonas registradas",
    description="Devuelve las zonas de cobro existentes en los clientes de la financiera.",
)
async def list_client_zones(
    context: LenderDep,
    session: SessionDep,
) -> list[str]:
    """Lista las zonas distintas en uso dentro del tenant."""
    return await client_service.list_zones(session, context.tenant_id)


@router.get(
    "/{client_id}",
    response_model=ClientDetail,
    summary="Consultar un cliente",
)
async def get_client(
    client_id: UUID,
    context: LenderDep,
    session: SessionDep,
) -> ClientDetail:
    """Devuelve un cliente con sus referencias.

    Raises:
        HTTPException: 404 si no existe o es de otra financiera.
    """
    try:
        client = await client_service.get_client_detail(session, context.tenant_id, client_id)
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc

    return ClientDetail.model_validate(client)


@router.patch(
    "/{client_id}",
    response_model=ClientDetail,
    summary="Editar un cliente",
    description="Solo modifica los campos enviados. La CURP no es editable.",
)
async def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    context: LenderDep,
    session: SessionDep,
    request: Request,
) -> ClientDetail:
    """Actualiza los datos de un cliente.

    Raises:
        HTTPException: 404 si no existe o es de otra financiera.
    """
    try:
        meta = request_meta(request)
        client = await client_service.update_client(
            session,
            context.tenant_id,
            client_id,
            payload,
            actor_id=context.user.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc

    return ClientDetail.model_validate(client)


@router.patch(
    "/{client_id}/status",
    response_model=ClientRead,
    summary="Activar o desactivar un cliente",
    description=(
        "Desactivar impide crear prestamos nuevos pero conserva todo el "
        "historial. Nunca se elimina un cliente con prestamos (RN-57)."
    ),
)
async def change_status(
    client_id: UUID,
    payload: ClientStatusChange,
    context: LenderDep,
    session: SessionDep,
    request: Request,
) -> ClientRead:
    """Cambia el estado de un cliente."""
    try:
        meta = request_meta(request)
        client = await client_service.change_status(
            session,
            context.tenant_id,
            client_id,
            payload.status,
            actor_id=context.user.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc
    except client_service.ClientPlanLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return ClientRead.model_validate(client)


@router.post(
    "/{client_id}/anonymize",
    response_model=ClientDetail,
    summary="Anonimizar datos personales del cliente",
    description=(
        "Reemplaza los datos personales por valores seudonimos y elimina "
        "referencias y documentos a solicitud del titular (RNF-25, RN-70). "
        "Reservado al Administrador."
    ),
)
async def anonymize_client(
    client_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
    request: Request,
) -> ClientDetail:
    """Anonimiza un cliente y borra sus documentos fisicos."""
    if context.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el Administrador puede anonimizar datos personales.",
        )

    try:
        meta = request_meta(request)
        client, file_keys = await client_service.anonymize_client(
            session,
            context.tenant_id,
            client_id,
            actor_id=context.user.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc

    storage = get_storage()
    for key in file_keys:
        storage.delete(key)

    return ClientDetail.model_validate(client)


@router.post(
    "/{client_id}/references",
    response_model=ClientReferenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar una referencia personal",
)
async def add_reference(
    client_id: UUID,
    payload: ClientReferenceCreate,
    context: LenderDep,
    session: SessionDep,
) -> ClientReferenceRead:
    """Agrega una referencia a un cliente existente."""
    try:
        reference = await client_service.add_reference(
            session,
            context.tenant_id,
            client_id,
            name=payload.name,
            relationship=payload.relationship,
            phone=payload.phone,
            address=payload.address,
        )
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc

    return ClientReferenceRead.model_validate(reference)


@router.get(
    "/{client_id}/documents",
    response_model=list[DocumentRead],
    summary="Listar documentos",
    description="Solo devuelve metadatos; la descarga usa una URL firmada aparte.",
)
async def list_documents(
    client_id: UUID,
    context: LenderDep,
    session: SessionDep,
) -> list[DocumentRead]:
    """Lista los documentos del cliente."""
    try:
        documents = await client_service.list_documents(session, context.tenant_id, client_id)
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc

    return [DocumentRead.model_validate(document) for document in documents]


@router.post(
    "/{client_id}/portal-pin",
    response_model=PortalPinResponse,
    summary="Generar o actualizar PIN del portal del cliente",
    description=(
        "Genera o asigna un PIN de 6 digitos para que el cliente consulte "
        "sus prestamos en el portal y devuelve un enlace de WhatsApp listo "
        "para compartirselo."
    ),
)
async def set_client_portal_pin(
    client_id: UUID,
    context: LenderDep,
    session: SessionDep,
    request: Request,
    payload: PortalPinSetRequest | None = None,
) -> PortalPinResponse:
    """Genera o asigna el PIN de 6 digitos del portal del cliente."""
    desired_pin = payload.pin if payload is not None else None
    try:
        meta = request_meta(request)
        client, raw_pin = await client_service.set_portal_pin(
            session,
            context.tenant_id,
            client_id,
            pin=desired_pin,
            actor_id=context.user.id,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except client_service.ClientNotFoundError as exc:
        raise _not_found() from exc

    whatsapp_url = client_service.build_portal_whatsapp_url(
        client.phone,
        context.tenant.name,
        client.curp,
        raw_pin,
    )

    return PortalPinResponse(
        client_id=client.id,
        pin=raw_pin,
        whatsapp_url=whatsapp_url,
    )
