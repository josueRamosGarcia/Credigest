"""Endpoints de usuarios y configuracion global del sistema.

Reservados al Administrador de la financiera (RF-03 a RF-12, RN-61).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.schemas.user import (
    SystemSettingRead,
    SystemSettingUpdate,
    UserCreate,
    UserCreatedResponse,
    UserListResponse,
    UserPasswordResetRequest,
    UserPasswordResetResponse,
    UserRead,
    UserStatusChange,
    UserUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/users", tags=["usuarios"])
settings_router = APIRouter(prefix="/settings", tags=["configuracion"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminDep = Annotated[AuthContext, Depends(require_role("admin"))]


def _not_found(message: str) -> HTTPException:
    """Error uniforme de recurso inexistente."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _conflict(message: str) -> HTTPException:
    """Error uniforme de conflicto o regla de negocio."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


@router.get(
    "",
    response_model=UserListResponse,
    summary="Listar usuarios",
    description="Devuelve los usuarios de la financiera con filtros opcionales.",
)
async def list_users(
    context: AdminDep,
    session: SessionDep,
    role: Annotated[
        str | None, Query(pattern="^(admin|prestamista|cobrador)$")
    ] = None,
    is_active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserListResponse:
    """Lista los usuarios de la financiera."""
    items, total = await user_service.list_users(
        session,
        context.tenant_id,
        role=role,
        is_active=is_active,
        search=search,
        page=page,
        page_size=page_size,
    )

    return UserListResponse(
        items=[UserRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=UserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario",
    description=(
        "Crea un usuario dentro de la financiera con el rol y permisos indicados. "
        "Si no se envia contrasena, genera una contrasena temporal (RF-06)."
    ),
)
async def create_user(
    payload: UserCreate,
    context: AdminDep,
    session: SessionDep,
    request: Request,
) -> UserCreatedResponse:
    """Crea un usuario nuevo."""
    meta = request_meta(request)
    try:
        user, temporary_password = await user_service.create_user(
            session,
            context.tenant,
            context.user.id,
            payload,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except user_service.DuplicateEmailError as exc:
        raise _conflict(str(exc)) from exc
    except user_service.PlanLimitExceededError as exc:
        raise _conflict(str(exc)) from exc

    data = UserRead.model_validate(user).model_dump()
    return UserCreatedResponse(**data, temporary_password=temporary_password)


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Consultar un usuario",
)
async def get_user(
    user_id: UUID,
    context: AdminDep,
    session: SessionDep,
) -> UserRead:
    """Devuelve el detalle de un usuario de la financiera."""
    try:
        user = await user_service.get_user(session, context.tenant_id, user_id)
    except user_service.UserNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    return UserRead.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Editar un usuario",
    description="Modifica nombre, telefono, rol o permisos granulares (RF-03, RF-05).",
)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    context: AdminDep,
    session: SessionDep,
    request: Request,
) -> UserRead:
    """Actualiza los datos de un usuario."""
    meta = request_meta(request)
    try:
        user = await user_service.update_user(
            session,
            context.tenant_id,
            user_id,
            context.user.id,
            payload,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except user_service.UserNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except user_service.AdminProtectionError as exc:
        raise _conflict(str(exc)) from exc

    return UserRead.model_validate(user)


@router.patch(
    "/{user_id}/status",
    response_model=UserRead,
    summary="Activar o desactivar un usuario",
    description=(
        "Activa o desactiva la cuenta. Impide que el administrador se desactive "
        "a si mismo o deje a la financiera sin administradores activos (RN-62)."
    ),
)
async def change_user_status(
    user_id: UUID,
    payload: UserStatusChange,
    context: AdminDep,
    session: SessionDep,
    request: Request,
) -> UserRead:
    """Cambia el estado de un usuario."""
    meta = request_meta(request)
    try:
        user = await user_service.change_status(
            session,
            context.tenant,
            user_id,
            context.user.id,
            payload.is_active,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except user_service.UserNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except user_service.AdminProtectionError as exc:
        raise _conflict(str(exc)) from exc
    except user_service.PlanLimitExceededError as exc:
        raise _conflict(str(exc)) from exc

    return UserRead.model_validate(user)


@router.post(
    "/{user_id}/reset-password",
    response_model=UserPasswordResetResponse,
    summary="Restablecer contrasena de un usuario",
    description=(
        "Genera o asigna una contrasena temporal y cierra las sesiones activas "
        "del usuario (RF-06, RN-63)."
    ),
)
async def reset_user_password(
    user_id: UUID,
    context: AdminDep,
    session: SessionDep,
    request: Request,
    payload: UserPasswordResetRequest | None = None,
) -> UserPasswordResetResponse:
    """Restablece la contrasena de un usuario."""
    meta = request_meta(request)
    desired_password = payload.password if payload is not None else None
    try:
        temporary = await user_service.reset_password(
            session,
            context.tenant_id,
            user_id,
            context.user.id,
            new_password=desired_password,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except user_service.UserNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    return UserPasswordResetResponse(
        user_id=user_id,
        temporary_password=temporary,
    )


@settings_router.get(
    "",
    response_model=SystemSettingRead,
    summary="Consultar parametros globales",
    description=(
        "Devuelve la tasa moratoria por defecto, el esquema predeterminado y "
        "los dias de gracia de la financiera (RF-09 a RF-11)."
    ),
)
async def get_settings(
    context: AdminDep,
    session: SessionDep,
) -> SystemSettingRead:
    """Devuelve la configuracion global de la financiera."""
    setting = await user_service.get_or_create_settings(session, context.tenant_id)
    return SystemSettingRead.model_validate(setting)


@settings_router.put(
    "",
    response_model=SystemSettingRead,
    summary="Actualizar parametros globales",
    description=(
        "Actualiza los parametros por defecto para futuros prestamos sin "
        "modificar los ya aprobados (RF-12, RN-06)."
    ),
)
async def update_settings(
    payload: SystemSettingUpdate,
    context: AdminDep,
    session: SessionDep,
    request: Request,
) -> SystemSettingRead:
    """Actualiza la configuracion global de la financiera."""
    meta = request_meta(request)
    setting = await user_service.update_settings(
        session,
        context.tenant_id,
        context.user.id,
        payload,
        ip_address=meta.ip_address,
        user_agent=meta.user_agent,
    )
    return SystemSettingRead.model_validate(setting)

