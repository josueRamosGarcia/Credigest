"""Dependencias compartidas de la API.

La dependencia `get_current_user` es el punto unico donde se valida el token y
se carga el usuario. A partir de ahi, toda consulta filtra por su `tenant_id`,
lo que garantiza el aislamiento entre financieras (RNF-08).
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import TokenError, decode_token
from app.db.session import get_session
from app.models.tenant import Tenant
from app.models.user import User

#: Extrae el token de la cabecera `Authorization: Bearer <token>`.
_bearer = HTTPBearer(auto_error=False)


class AuthContext:
    """Usuario autenticado junto con su financiera.

    Se pasa a los endpoints como una sola dependencia para que no puedan
    olvidar el filtro por tenant.
    """

    def __init__(self, user: User, tenant: Tenant) -> None:
        self.user = user
        self.tenant = tenant

    @property
    def tenant_id(self) -> Any:
        """Id de la financiera del usuario."""
        return self.user.tenant_id

    @property
    def role(self) -> str:
        """Rol del usuario."""
        return self.user.role

    def has_permission(self, permission: str) -> bool:
        """Comprueba un permiso granular.

        El Administrador siempre tiene todo (RN-61). Para los demas roles, el
        permiso debe estar concedido de forma explicita en `permissions`.
        """
        if self.role == "admin":
            return True
        return bool(self.user.permissions.get(permission, False))


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthContext:
    """Valida el token y carga al usuario y su financiera.

    Args:
        credentials: Credenciales extraidas de la cabecera.
        session: Sesion de base de datos.

    Returns:
        El contexto de autenticacion.

    Raises:
        HTTPException: 401 si falta el token o no es valido; 403 si el usuario
            o la financiera estan desactivados.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de acceso.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await session.scalar(select(User).where(User.id == payload.subject))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario ya no existe.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta esta desactivada.",
        )

    # El token no manda sobre la base: si el rol cambio, prevalece el actual.
    if user.tenant_id != payload.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token no corresponde a este usuario.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant = await session.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La financiera esta desactivada.",
        )

    return AuthContext(user=user, tenant=tenant)


#: Alias para usar en las firmas de los endpoints.
CurrentUserDep = Annotated[AuthContext, Depends(get_current_user)]


def require_role(
    *roles: str,
) -> Callable[[AuthContext], Coroutine[Any, Any, AuthContext]]:
    """Crea una dependencia que exige uno de los roles indicados.

    El Administrador siempre pasa, porque tiene acceso total (RN-61).

    Args:
        *roles: Roles permitidos, ademas de `admin`.

    Returns:
        Una dependencia lista para usar en un endpoint.
    """

    async def _checker(context: CurrentUserDep) -> AuthContext:
        if context.role == "admin" or context.role in roles:
            return context
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu rol no tiene acceso a esta operacion.",
        )

    return _checker
