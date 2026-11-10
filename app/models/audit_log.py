"""Modelo de la bitacora de auditoria.

Es append-only: la aplicacion solo inserta y lee. No existen endpoints de
actualizacion ni de borrado, y el rol de base de datos no debe tener permisos de
modificacion (RN-66).

Reglas que aplican:
- RN-64: se auditan las operaciones sensibles del sistema.
- RN-65: se guarda `before` y `after` solo con los campos que cambiaron.
- RN-66: inmutable desde la aplicacion.
- RN-67: retencion minima de 5 anios.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Un registro de la bitacora.

    No hereda de `UUIDPrimaryKeyMixin` porque usa una llave numerica: es mas
    eficiente para una tabla que solo crece y el orden natural refleja la
    secuencia de los hechos.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_log_entity", "entity", "entity_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=False,
    )

    #: Usuario que realizo la accion. Nulo cuando la hizo el sistema.
    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    #: Accion en formato `recurso.verbo`, por ejemplo `loan.create`.
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    #: Entidad afectada, por ejemplo `loan` o `client`.
    entity: Mapped[str] = mapped_column(String(80), nullable=False)

    entity_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    #: Estado previo. Solo los campos que cambiaron (RN-65).
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    #: Estado nuevo. Solo los campos que cambiaron (RN-65).
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        """Representacion de depuracion sin valores del cambio."""
        return f"<AuditLog {self.action} entity={self.entity}>"
