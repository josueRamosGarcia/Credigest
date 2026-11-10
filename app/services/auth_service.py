"""Servicio de autenticacion.

Concentra la logica de sesiones: emitir tokens, rotarlos y revocarlos. La API
solo valida la forma de la peticion y llama a este servicio.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.jwt import TokenError, create_access_token, create_refresh_token, decode_token
from app.core.security import verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User


class AuthenticationError(Exception):
    """Credenciales incorrectas o sesion no valida."""


class SessionExpiredError(AuthenticationError):
    """El refresh token ya no es utilizable."""


@dataclass(frozen=True)
class IssuedTokens:
    """Par de tokens emitido, con la duracion del access en segundos."""

    access_token: str
    refresh_token: str
    expires_in: int


def _hash_token(token: str) -> str:
    """Hash sha256 del token. Se guarda esto, nunca el token en claro."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    """Fecha actual en UTC."""
    return datetime.now(UTC)


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    """Valida correo y contrasena.

    Args:
        session: Sesion de base de datos.
        email: Correo del usuario.
        password: Contrasena en claro.

    Returns:
        El usuario autenticado.

    Raises:
        AuthenticationError: Si las credenciales no son validas. El mensaje es
            siempre el mismo para no revelar si el correo existe.
    """
    user = await session.scalar(select(User).where(User.email == email.lower().strip()))

    # Se verifica siempre el hash, incluso si el usuario no existe, para que el
    # tiempo de respuesta no delate correos validos.
    if user is None:
        verify_password(password, "$2b$12$" + "x" * 53)
        raise AuthenticationError("Correo o contrasena incorrectos.")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Correo o contrasena incorrectos.")

    if not user.is_active:
        raise AuthenticationError("La cuenta esta desactivada.")

    return user


async def issue_tokens(session: AsyncSession, user: User) -> IssuedTokens:
    """Emite un par nuevo de tokens y guarda el refresh hasheado.

    Args:
        session: Sesion de base de datos.
        user: Usuario que inicia sesion.

    Returns:
        Los tokens emitidos.
    """
    settings = get_settings()

    access_token, _, _ = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token, _, expires_at = create_refresh_token(user.id, user.tenant_id, user.role)

    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh_token),
            expires_at=expires_at,
        )
    )
    user.last_login_at = _now()
    await session.commit()

    return IssuedTokens(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
    )


async def rotate_tokens(session: AsyncSession, raw_refresh_token: str) -> IssuedTokens:
    """Canjea un refresh token por un par nuevo y revoca el anterior.

    La rotacion limita el dano de un token robado: al usarlo, el original deja
    de servir y quien lo robo se queda con un token ya revocado.

    Args:
        session: Sesion de base de datos.
        raw_refresh_token: Token recibido del cliente.

    Returns:
        El par de tokens nuevo.

    Raises:
        SessionExpiredError: Si el token es invalido, expiro o ya fue revocado.
    """
    try:
        payload = decode_token(raw_refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise SessionExpiredError(str(exc)) from exc

    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token(raw_refresh_token))
    )

    if stored is None:
        raise SessionExpiredError("La sesion no existe.")

    if stored.revoked_at is not None:
        # Un refresh revocado en uso puede indicar robo: se revocan todos los
        # tokens del usuario para obligarlo a iniciar sesion de nuevo.
        await revoke_all_for_user(session, stored.user_id)
        raise SessionExpiredError("La sesion fue revocada. Inicia sesion de nuevo.")

    if stored.expires_at <= _now():
        raise SessionExpiredError("La sesion expiro. Inicia sesion de nuevo.")

    # El registro esta ligado al usuario por llave foranea, asi que no hace
    # falta comparar `stored.user_id` con el `sub` del token: la base lo impide.
    user = await session.scalar(select(User).where(User.id == payload.subject))
    if user is None or not user.is_active:
        raise SessionExpiredError("La cuenta ya no esta disponible.")

    # Rotacion: el token usado se marca como revocado antes de emitir otro.
    stored.revoked_at = _now()
    await session.commit()

    return await issue_tokens(session, user)


async def logout(session: AsyncSession, raw_refresh_token: str) -> None:
    """Revoca el refresh token indicado.

    Es idempotente: si el token no existe o ya estaba revocado, no falla.

    Args:
        session: Sesion de base de datos.
        raw_refresh_token: Token que se quiere invalidar.
    """
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == _hash_token(raw_refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    await session.commit()


async def revoke_all_for_user(session: AsyncSession, user_id: UUID) -> None:
    """Revoca todas las sesiones de un usuario."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await session.commit()


async def cleanup_expired(session: AsyncSession, older_than_days: int = 30) -> int:
    """Elimina tokens caducados hace mas de `older_than_days`.

    Returns:
        La cantidad de registros eliminados.
    """
    threshold = _now() - timedelta(days=older_than_days)
    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < threshold)
    )
    await session.commit()
    deleted = getattr(result, "rowcount", 0) or 0
    return int(deleted)
