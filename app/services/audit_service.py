"""Servicio de auditoria.

Escribe la bitacora de lo que pasa en el sistema. Dos decisiones importantes:

1. **Nunca se registran datos sensibles**: contrasenas, tokens, CURP, ni el
   contenido de documentos (RN-65, RNF-09). Las claves se filtran por lista
   negra antes de guardar.
2. **Un fallo de auditoria no tumba la operacion**: si escribir la bitacora
   falla, se registra en el log de la aplicacion y la operacion continua. Es
   preferible perder una entrada de auditoria que perder un pago.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services.dashboard_service import local_date

logger = logging.getLogger(__name__)

#: Claves que nunca se guardan en la bitacora, ni en `before` ni en `after`.
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "current_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "token_hash",
        "secret",
        "jwt_secret",
        "curp",
        "file_key",
        "spei_reference",
        "ine",
        "comprobante",
    }
)

#: Valor con que se sustituye un campo sensible.
REDACTED = "***"

#: Tamano maximo de pagina al consultar la bitacora.
MAX_PAGE_SIZE = 200


def sanitize(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Quita los campos sensibles de un diccionario.

    Se aplica recursivamente porque algunos valores son diccionarios anidados,
    como los permisos de un usuario.

    Args:
        payload: Diccionario a limpiar, o `None`.

    Returns:
        Un diccionario nuevo sin campos sensibles, o `None`.
    """
    if payload is None:
        return None

    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in SENSITIVE_KEYS:
            clean[key] = REDACTED
        elif isinstance(value, Mapping):
            clean[key] = sanitize(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            clean[key] = [
                sanitize(item) if isinstance(item, Mapping) else item for item in value
            ]
        else:
            clean[key] = value

    return clean


def diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Devuelve solo los campos que cambiaron (RN-65).

    Args:
        before: Estado previo.
        after: Estado nuevo.

    Returns:
        Dos diccionarios: `before` y `after` limitados a las claves distintas.
    """
    before_map = dict(before or {})
    after_map = dict(after or {})

    changed = {
        key
        for key in set(before_map) | set(after_map)
        if before_map.get(key) != after_map.get(key)
    }

    return (
        {key: before_map[key] for key in changed if key in before_map},
        {key: after_map[key] for key in changed if key in after_map},
    )


async def record(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    action: str,
    entity: str,
    user_id: UUID | None = None,
    entity_id: UUID | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    commit: bool = False,
) -> AuditLog | None:
    """Escribe una entrada en la bitacora.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera a la que pertenece el hecho.
        action: Accion en formato `recurso.verbo`, por ejemplo `loan.create`.
        entity: Nombre de la entidad afectada.
        user_id: Usuario que la realizo; `None` si fue el sistema.
        entity_id: Identificador del registro afectado.
        before: Estado previo. Se guardan solo los campos que cambiaron.
        after: Estado nuevo. Se guardan solo los campos que cambiaron.
        ip_address: Direccion IP de la peticion.
        user_agent: Navegador o cliente que hizo la peticion.
        commit: Si es `True`, confirma la transaccion. Por defecto no lo hace
            para que la entrada se guarde junto con la operacion auditada.

    Returns:
        La entrada creada, o `None` si no se pudo escribir.
    """
    changed_before, changed_after = diff(before, after)

    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=sanitize(changed_before) or None,
        after=sanitize(changed_after) or None,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    try:
        session.add(entry)
        if commit:
            await session.commit()
            await session.refresh(entry)
    except Exception:  # pragma: no cover - depende de la base
        # Nunca se interrumpe la operacion de negocio por un fallo de auditoria.
        logger.exception("No se pudo registrar la auditoria: %s", action)
        return None

    return entry


async def list_entries(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    from_date: Any = None,
    to_date: Any = None,
    user_id: UUID | None = None,
    action: str | None = None,
    entity: str | None = None,
    entity_id: UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    """Consulta la bitacora con filtros y paginacion.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera cuyos registros se consultan.
        from_date: Fecha inicial (inclusive), como `date`.
        to_date: Fecha final (inclusive), como `date`.
        user_id: Filtra por usuario.
        action: Filtra por accion exacta.
        entity: Filtra por entidad.
        entity_id: Filtra por registro afectado.
        page: Pagina, empezando en 1.
        page_size: Resultados por pagina (maximo 200).

    Returns:
        Los registros de la pagina y el total de coincidencias.
    """
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    conditions = [AuditLog.tenant_id == tenant_id]
    # La bitacora guarda en UTC; se compara contra la fecha local del negocio
    # para no desfasar un dia despues de las 18:00 hora de Mexico.
    if from_date is not None:
        conditions.append(local_date(AuditLog.created_at) >= from_date)
    if to_date is not None:
        conditions.append(local_date(AuditLog.created_at) <= to_date)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action:
        conditions.append(AuditLog.action == action)
    if entity:
        conditions.append(AuditLog.entity == entity)
    if entity_id is not None:
        conditions.append(AuditLog.entity_id == entity_id)

    total = await session.scalar(
        select(func.count()).select_from(AuditLog).where(*conditions)
    )

    result = await session.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return list(result.all()), int(total or 0)


def entry_to_dict(entry: AuditLog) -> dict[str, Any]:
    """Convierte una entrada a un diccionario exportable.

    Se usa para la consulta por API y para la exportacion a CSV.
    """
    return {
        "id": entry.id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "user_id": str(entry.user_id) if entry.user_id else None,
        "action": entry.action,
        "entity": entry.entity,
        "entity_id": str(entry.entity_id) if entry.entity_id else None,
        "before": entry.before,
        "after": entry.after,
        "ip_address": str(entry.ip_address) if entry.ip_address else None,
        "user_agent": entry.user_agent,
    }
