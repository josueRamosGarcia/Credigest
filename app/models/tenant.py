"""Modelo de tenant: cada financiera cliente del SaaS.

El tenant es la unidad de aislamiento. Toda consulta de negocio debe filtrarse
por `tenant_id`; ninguna puede cruzar datos entre financieras (RNF-08).
"""

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Una financiera cliente de Credigest."""

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    #: Identificador legible para URLs y folios. Opcional (RN-39).
    slug: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)

    #: Plan contratado. Define los limites de RN-68.
    plan: Mapped[str] = mapped_column(
        Enum("basico", "profesional", "empresarial", name="tenant_plan"),
        nullable=False,
        default="basico",
        server_default="basico",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    def __repr__(self) -> str:
        """Representacion legible para depuracion."""
        return f"<Tenant {self.slug or self.id} ({self.plan})>"
