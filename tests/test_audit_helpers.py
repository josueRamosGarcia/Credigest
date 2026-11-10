"""Utilidades compartidas por las pruebas de auditoria."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "clave-segura-123"


async def make_tenant_and_user(
    session: AsyncSession,
    *,
    email: str = "audit@test.mx",
    slug: str = "audit",
    role: str = "admin",
) -> tuple[Tenant, User]:
    """Crea un tenant y un usuario para las pruebas de auditoria."""
    tenant = Tenant(name=f"Financiera {slug}", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario Auditoria",
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    session.add(user)
    await session.commit()
    return tenant, user


def unused_date() -> date:
    """Fecha fija para pruebas que la necesiten."""
    return date(2026, 11, 10)


def unused_decimal() -> Decimal:
    """Monto fijo para pruebas que lo necesiten."""
    return Decimal("100.00")
