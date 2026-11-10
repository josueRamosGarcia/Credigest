"""Modelo de refresh tokens.

Guardar el token hasheado en la base permite revocarlo al cerrar sesion o al
detectar un robo. Nunca se guarda el token en claro: si la base se filtra, los
tokens no se pueden reutilizar.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RefreshToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Un token de refresco emitido a un usuario."""

    __tablename__ = "refresh_token"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    #: sha256 del token. No se usa bcrypt porque el token es aleatorio y largo:
    #: no necesita un hash lento, solo uno que no permita recuperarlo.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Fecha en que se revoco (logout, rotacion o deteccion de robo).
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Representacion de depuracion sin exponer el token."""
        return f"<RefreshToken user={self.user_id} revoked={self.revoked_at is not None}>"
