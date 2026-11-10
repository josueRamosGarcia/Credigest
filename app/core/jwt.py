"""Emision y validacion de tokens JWT.

Se usan dos tokens (RNF-07):

- **Access token**: dura pocos minutos y viaja en cada peticion. Si se filtra,
  el dano es limitado en el tiempo.
- **Refresh token**: dura dias y solo sirve para pedir un access nuevo. Se
  guarda hasheado en la base para poder revocarlo (cerrar sesion).

El token solo contiene identificadores, nunca datos personales: ni nombre, ni
correo, ni CURP.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt

from app.core.config import get_settings

#: Tipo de token, para impedir que un refresh se use como access.
TokenType = Literal["access", "refresh"]


class TokenError(ValueError):
    """Error al emitir o validar un token."""


@dataclass(frozen=True)
class TokenPayload:
    """Contenido validado de un token."""

    subject: UUID
    tenant_id: UUID
    role: str
    token_type: TokenType
    jti: UUID
    issued_at: datetime
    expires_at: datetime


def _now() -> datetime:
    """Fecha actual en UTC."""
    return datetime.now(UTC)


def create_token(
    *,
    subject: UUID,
    tenant_id: UUID,
    role: str,
    token_type: TokenType,
    expires_delta: timedelta,
    token_id: UUID | None = None,
) -> tuple[str, UUID, datetime]:
    """Crea un token firmado.

    Args:
        subject: Id del usuario.
        tenant_id: Financiera a la que pertenece.
        role: Rol del usuario, para autorizacion rapida.
        token_type: "access" o "refresh".
        expires_delta: Cuanto dura el token.
        token_id: Identificador unico; se genera si no se entrega.

    Returns:
        Una tupla con (token firmado, jti, fecha de expiracion).
    """
    settings = get_settings()
    issued_at = _now()
    expires_at = issued_at + expires_delta
    jti = token_id or uuid4()

    # Los claims `iat` y `exp` son segundos enteros. Se trunca aqui para que la
    # fecha devuelta coincida exactamente con la que viaja en el token.
    issued_at = issued_at.replace(microsecond=0)
    expires_at = expires_at.replace(microsecond=0)

    claims: dict[str, Any] = {
        "sub": str(subject),
        "tid": str(tenant_id),
        "role": role,
        "type": token_type,
        "jti": str(jti),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def create_access_token(subject: UUID, tenant_id: UUID, role: str) -> tuple[str, UUID, datetime]:
    """Crea un token de acceso con la duracion configurada."""
    settings = get_settings()
    return create_token(
        subject=subject,
        tenant_id=tenant_id,
        role=role,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(
    subject: UUID,
    tenant_id: UUID,
    role: str,
    token_id: UUID | None = None,
) -> tuple[str, UUID, datetime]:
    """Crea un token de refresco con la duracion configurada."""
    settings = get_settings()
    return create_token(
        subject=subject,
        tenant_id=tenant_id,
        role=role,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_days),
        token_id=token_id,
    )


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    """Valida la firma, la expiracion y el tipo de un token.

    Args:
        token: Token recibido en la cabecera Authorization.
        expected_type: Tipo que se espera ("access" o "refresh").

    Returns:
        El contenido validado del token.

    Raises:
        TokenError: Si el token es invalido, expiro o es de otro tipo.
    """
    settings = get_settings()

    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "tid", "role", "type", "jti", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("El token expiro.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("El token no es valido.") from exc

    if claims.get("type") != expected_type:
        raise TokenError(f"Se esperaba un token de tipo '{expected_type}'.")

    try:
        return TokenPayload(
            subject=UUID(claims["sub"]),
            tenant_id=UUID(claims["tid"]),
            role=claims["role"],
            token_type=claims["type"],
            jti=UUID(claims["jti"]),
            issued_at=datetime.fromtimestamp(claims["iat"], UTC),
            expires_at=datetime.fromtimestamp(claims["exp"], UTC),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TokenError("El token tiene un formato inesperado.") from exc
