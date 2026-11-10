"""Endpoints de autenticacion."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep
from app.db.session import get_session
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    TokenPair,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["autenticacion"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Iniciar sesion",
    description=(
        "Valida correo y contrasena y devuelve un par de tokens. "
        "El correo es unico global, asi que no hace falta indicar la financiera."
    ),
)
async def login(payload: LoginRequest, session: SessionDep) -> TokenPair:
    """Inicia sesion y devuelve los tokens.

    Raises:
        HTTPException: 401 si las credenciales no son validas.
    """
    try:
        user = await auth_service.authenticate(session, payload.email, payload.password)
    except auth_service.AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    tokens = await auth_service.issue_tokens(session, user)

    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Renovar el token de acceso",
    description=(
        "Canjea un refresh token por un par nuevo. El token usado queda revocado "
        "(rotacion): si alguien intenta reutilizarlo, se cierran todas las sesiones."
    ),
)
async def refresh(payload: RefreshRequest, session: SessionDep) -> TokenPair:
    """Renueva los tokens.

    Raises:
        HTTPException: 401 si el refresh token no es utilizable.
    """
    try:
        tokens = await auth_service.rotate_tokens(session, payload.refresh_token)
    except auth_service.SessionExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesion",
    description="Revoca el refresh token indicado. Es idempotente.",
)
async def logout(payload: RefreshRequest, session: SessionDep) -> None:
    """Cierra la sesion revocando el refresh token."""
    await auth_service.logout(session, payload.refresh_token)


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Datos del usuario autenticado",
    description="Devuelve el usuario, su rol, sus permisos y los datos de su financiera.",
)
async def me(context: CurrentUserDep) -> CurrentUser:
    """Devuelve el perfil del usuario autenticado."""
    return CurrentUser(
        id=context.user.id,
        tenant_id=context.user.tenant_id,
        full_name=context.user.full_name,
        email=context.user.email,
        role=context.user.role,
        permissions=context.user.permissions,
        tenant_name=context.tenant.name,
        tenant_slug=context.tenant.slug,
        tenant_plan=context.tenant.plan,
    )
