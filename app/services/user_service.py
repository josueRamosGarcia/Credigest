"""Servicio de usuarios y configuracion global del sistema.

Reglas de negocio cubiertas:
- RF-03 a RF-06: alta, edicion, cambio de estado y contrasena temporal.
- RF-08 / RN-64: auditoria en cada creacion, edicion, cambio de estado o parametros.
- RF-09 a RF-12: parametros globales de mora, esquema y dias de gracia.
- RN-61: el rol define el alcance y los permisos granulares se validan.
- RN-62: un usuario no puede desactivarse a si mismo ni dejar al tenant sin admin activo.
- RN-63: al cambiar rol, permisos, contrasena o desactivar se revocan sus tokens.
- RN-68 / RN-69: limites de usuarios activos segun el plan contratado.
"""

import secrets
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.user import SystemSettingUpdate, UserCreate, UserUpdate
from app.services import audit_service, auth_service

#: Limite de usuarios activos por plan (RN-68).
USER_PLAN_LIMITS: dict[str, int] = {
    "basico": 5,
    "profesional": 12,
    "empresarial": 30,
}

#: Tamano maximo de pagina al listar usuarios.
MAX_PAGE_SIZE = 100


class UserServiceError(Exception):
    """Error base de negocio para usuarios y configuracion."""


class UserNotFoundError(UserServiceError):
    """El usuario no existe dentro de esta financiera."""


class DuplicateEmailError(UserServiceError):
    """El correo ya esta registrado en el sistema (RF-01)."""


class PlanLimitExceededError(UserServiceError):
    """Se alcanzo el limite de usuarios activos del plan (RN-68)."""


class AdminProtectionError(UserServiceError):
    """Operacion bloqueada por proteccion de cuenta de administrador (RN-62)."""


def generate_temporary_password() -> str:
    """Genera una contrasena temporal segura de al menos 12 caracteres (RF-06)."""
    return secrets.token_urlsafe(12)


async def _count_active_users(session: AsyncSession, tenant_id: UUID) -> int:
    """Cuenta los usuarios activos del tenant."""
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.is_active.is_(True))
    )
    return int(count or 0)


async def _count_active_admins(session: AsyncSession, tenant_id: UUID) -> int:
    """Cuenta los administradores activos del tenant."""
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.tenant_id == tenant_id,
            User.role == "admin",
            User.is_active.is_(True),
        )
    )
    return int(count or 0)


async def _enforce_user_plan_limit(session: AsyncSession, tenant: Tenant) -> None:
    """Verifica que el tenant no supere el limite de usuarios de su plan (RN-68)."""
    limit = USER_PLAN_LIMITS.get(tenant.plan, USER_PLAN_LIMITS["basico"])
    active_count = await _count_active_users(session, tenant.id)
    if active_count >= limit:
        raise PlanLimitExceededError(
            f"Tu plan '{tenant.plan}' permite hasta {limit} usuarios activos. "
            "Sube de plan para agregar mas usuarios."
        )


async def get_user(session: AsyncSession, tenant_id: UUID, user_id: UUID) -> User:
    """Obtiene un usuario perteneciente al tenant.

    Raises:
        UserNotFoundError: Si no existe o pertenece a otra financiera.
    """
    user = await session.scalar(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    if user is None:
        raise UserNotFoundError("El usuario no existe.")
    return user


async def list_users(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    role: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[User], int]:
    """Lista los usuarios de la financiera con filtros y paginacion."""
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    conditions = [User.tenant_id == tenant_id]
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(
            User.full_name.ilike(pattern) | User.email.ilike(pattern)
        )

    total = await session.scalar(
        select(func.count()).select_from(User).where(*conditions)
    )

    result = await session.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return result.all(), int(total or 0)


async def create_user(
    session: AsyncSession,
    tenant: Tenant,
    actor_id: UUID,
    payload: UserCreate,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, str | None]:
    """Crea un usuario nuevo en la financiera (RF-03, RF-04, RF-05, RF-06).

    Returns:
        Tupla `(usuario, temporary_password)`. `temporary_password` solo se
        devuelve cuando el sistema genero una contrasena temporal o se definio
        al dar de alta.

    Raises:
        PlanLimitExceededError: Si se alcanzo el limite del plan (RN-68).
        DuplicateEmailError: Si el correo ya existe en cualquier financiera.
    """
    await _enforce_user_plan_limit(session, tenant)

    normalized_email = payload.email.lower().strip()
    existing = await session.scalar(
        select(User).where(User.email == normalized_email)
    )
    if existing is not None:
        raise DuplicateEmailError("Ya existe un usuario con ese correo electronico.")

    raw_password = payload.password or generate_temporary_password()
    temporary_password = raw_password if payload.password is None else None

    user = User(
        tenant_id=tenant.id,
        full_name=payload.full_name,
        email=normalized_email,
        phone=payload.phone,
        password_hash=hash_password(raw_password),
        role=payload.role,
        permissions=dict(payload.permissions),
        is_active=True,
    )
    session.add(user)
    await session.flush()

    await audit_service.record(
        session,
        tenant_id=tenant.id,
        user_id=actor_id,
        action="user.create",
        entity="user",
        entity_id=user.id,
        after={
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "permissions": user.permissions,
            "is_active": user.is_active,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    await session.refresh(user)
    return user, temporary_password


async def update_user(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    actor_id: UUID,
    payload: UserUpdate,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    """Actualiza datos, rol o permisos de un usuario (RF-03, RF-05, RN-62, RN-63)."""
    user = await get_user(session, tenant_id, user_id)

    before = {
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "permissions": dict(user.permissions or {}),
    }

    role_changing_from_admin = (
        payload.role is not None
        and payload.role != "admin"
        and user.role == "admin"
    )
    if role_changing_from_admin and user.is_active:
        active_admins = await _count_active_admins(session, tenant_id)
        if active_admins <= 1:
            raise AdminProtectionError(
                "No se puede quitar el rol de administrador al ultimo administrador activo."
            )

    revoke_needed = False
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if "phone" in payload.model_fields_set:
        user.phone = payload.phone
    if payload.role is not None and payload.role != user.role:
        user.role = payload.role
        revoke_needed = True
    if payload.permissions is not None and payload.permissions != user.permissions:
        user.permissions = dict(payload.permissions)
        revoke_needed = True

    after = {
        "full_name": user.full_name,
        "phone": user.phone,
        "role": user.role,
        "permissions": dict(user.permissions or {}),
    }

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="user.update",
        entity="user",
        entity_id=user.id,
        before=before,
        after=after,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    if revoke_needed:
        await auth_service.revoke_all_for_user(session, user.id)
    await session.refresh(user)
    return user


async def change_status(
    session: AsyncSession,
    tenant: Tenant,
    user_id: UUID,
    actor_id: UUID,
    is_active: bool,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    """Activa o desactiva un usuario respetando RN-62 y RN-68."""
    user = await get_user(session, tenant.id, user_id)

    if not is_active and user.id == actor_id:
        raise AdminProtectionError("No puedes desactivar tu propia cuenta.")

    if not is_active and user.is_active and user.role == "admin":
        active_admins = await _count_active_admins(session, tenant.id)
        if active_admins <= 1:
            raise AdminProtectionError(
                "No se puede desactivar al ultimo administrador activo de la financiera."
            )

    if is_active and not user.is_active:
        await _enforce_user_plan_limit(session, tenant)

    previous = user.is_active
    user.is_active = is_active

    await audit_service.record(
        session,
        tenant_id=tenant.id,
        user_id=actor_id,
        action="user.status_change",
        entity="user",
        entity_id=user.id,
        before={"is_active": previous},
        after={"is_active": is_active},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    if not is_active:
        await auth_service.revoke_all_for_user(session, user.id)
    await session.refresh(user)
    return user


async def reset_password(
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    actor_id: UUID,
    new_password: str | None = None,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Asigna o genera una contrasena temporal y revoca las sesiones (RF-06, RN-63)."""
    user = await get_user(session, tenant_id, user_id)
    temporary = new_password or generate_temporary_password()
    user.password_hash = hash_password(temporary)

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="user.password_reset",
        entity="user",
        entity_id=user.id,
        after={"password_reset": True},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    await auth_service.revoke_all_for_user(session, user.id)
    return temporary


async def get_or_create_settings(
    session: AsyncSession, tenant_id: UUID
) -> SystemSetting:
    """Obtiene la configuracion del tenant o la inicializa con valores por defecto."""
    setting = await session.scalar(
        select(SystemSetting).where(SystemSetting.tenant_id == tenant_id)
    )
    if setting is not None:
        return setting

    setting = SystemSetting(
        tenant_id=tenant_id,
        default_late_fee_rate=Decimal("0.1000"),
        default_scheme="simple",
        grace_days=0,
        timezone="America/Mexico_City",
    )
    session.add(setting)
    await session.commit()
    await session.refresh(setting)
    return setting


async def update_settings(
    session: AsyncSession,
    tenant_id: UUID,
    actor_id: UUID,
    payload: SystemSettingUpdate,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SystemSetting:
    """Actualiza los parametros globales de la financiera (RF-09 a RF-12)."""
    setting = await get_or_create_settings(session, tenant_id)

    before = {
        "default_late_fee_rate": str(setting.default_late_fee_rate),
        "default_scheme": setting.default_scheme,
        "grace_days": setting.grace_days,
        "timezone": setting.timezone,
    }

    setting.default_late_fee_rate = payload.default_late_fee_rate
    setting.default_scheme = payload.default_scheme
    setting.grace_days = payload.grace_days
    setting.timezone = payload.timezone

    after = {
        "default_late_fee_rate": str(setting.default_late_fee_rate),
        "default_scheme": setting.default_scheme,
        "grace_days": setting.grace_days,
        "timezone": setting.timezone,
    }

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="settings.update",
        entity="system_setting",
        entity_id=setting.id,
        before=before,
        after=after,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    await session.refresh(setting)
    return setting
