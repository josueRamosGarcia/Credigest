"""Esquemas de la bitacora de auditoria."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEntry(BaseModel):
    """Un movimiento de la bitacora."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None
    user_id: UUID | None
    action: str
    entity: str
    entity_id: UUID | None

    #: Solo los campos que cambiaron, ya sin datos sensibles.
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    ip_address: str | None = None
    user_agent: str | None = None


class AuditListResponse(BaseModel):
    """Pagina de movimientos."""

    items: list[AuditEntry]
    total: int
    page: int
    page_size: int
