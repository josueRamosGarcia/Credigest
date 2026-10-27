"""Modelo de usuario del sistema.

Reglas que aplican:
- RNF-06: la contrasena se guarda solo como hash, nunca en claro.
- RN-01 de modelos: el correo es unico global, no por tenant.
- RN-61: el Administrador siempre tiene todas las acciones.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una cuenta de acceso a Credigest."""

    __tablename__ = "users"

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    #: Unico global: el login no necesita conocer el tenant.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    #: Hash bcrypt. Nunca se expone en la API ni se escribe en logs.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(
        Enum("admin", "prestamista", "cobrador", name="user_role"),
        nullable=False,
    )

    #: Permisos granulares. Solo restringen; nunca amplian el rol (RN-61).
    permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Representacion legible para depuracion, sin datos sensibles."""
        return f"<User {self.id} ({self.role})>"
