"""Pruebas de los modelos de identidad y del seed inicial."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.db


class TestTenantModel:
    """Tabla tenant: la financiera cliente."""

    async def test_creates_with_defaults(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Financiera Uno", slug="uno")
        db_session.add(tenant)
        await db_session.commit()

        assert tenant.id is not None
        assert tenant.plan == "basico"
        assert tenant.is_active is True
        assert tenant.created_at is not None

    async def test_slug_is_optional(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Sin Slug")
        db_session.add(tenant)
        await db_session.commit()

        assert tenant.slug is None

    async def test_slug_is_unique(self, db_session: AsyncSession) -> None:
        db_session.add(Tenant(name="Uno", slug="repetido"))
        await db_session.commit()

        db_session.add(Tenant(name="Dos", slug="repetido"))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_accepts_all_plans(self, db_session: AsyncSession) -> None:
        for index, plan in enumerate(["basico", "profesional", "empresarial"]):
            db_session.add(Tenant(name=f"Plan {plan}", slug=f"plan-{index}", plan=plan))
        await db_session.commit()

        plans = (await db_session.scalars(select(Tenant.plan).order_by(Tenant.slug))).all()
        assert set(plans) == {"basico", "profesional", "empresarial"}

    async def test_rejects_unknown_plan(self, db_session: AsyncSession) -> None:
        db_session.add(Tenant(name="Malo", slug="malo", plan="gratis"))
        with pytest.raises(Exception):  # noqa: B017 - el driver reporta un error de enum
            await db_session.commit()


class TestUserModel:
    """Tabla users: las cuentas de acceso."""

    async def _tenant(self, db_session: AsyncSession) -> Tenant:
        tenant = Tenant(name="Base", slug="base")
        db_session.add(tenant)
        await db_session.commit()
        return tenant

    async def test_creates_admin(self, db_session: AsyncSession) -> None:
        tenant = await self._tenant(db_session)
        user = User(
            tenant_id=tenant.id,
            full_name="Admin",
            email="admin@test.mx",
            password_hash=hash_password("clave-segura-123"),
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()

        assert user.id is not None
        assert user.permissions == {}
        assert user.is_active is True
        assert user.last_login_at is None

    async def test_stores_hash_not_password(self, db_session: AsyncSession) -> None:
        tenant = await self._tenant(db_session)
        plain = "clave-segura-123"
        user = User(
            tenant_id=tenant.id,
            full_name="Admin",
            email="hash@test.mx",
            password_hash=hash_password(plain),
            role="admin",
        )
        db_session.add(user)
        await db_session.commit()

        assert user.password_hash != plain
        assert plain not in user.password_hash
        assert verify_password(plain, user.password_hash)

    async def test_email_is_unique_globally(self, db_session: AsyncSession) -> None:
        """Dos tenants distintos no pueden compartir el mismo correo."""
        first = Tenant(name="A", slug="a")
        second = Tenant(name="B", slug="b")
        db_session.add_all([first, second])
        await db_session.commit()

        db_session.add(
            User(
                tenant_id=first.id,
                full_name="Uno",
                email="mismo@test.mx",
                password_hash=hash_password("clave-segura-123"),
                role="admin",
            )
        )
        await db_session.commit()

        db_session.add(
            User(
                tenant_id=second.id,
                full_name="Dos",
                email="mismo@test.mx",
                password_hash=hash_password("clave-segura-123"),
                role="admin",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_accepts_all_roles(self, db_session: AsyncSession) -> None:
        tenant = await self._tenant(db_session)
        for index, role in enumerate(["admin", "prestamista", "cobrador"]):
            db_session.add(
                User(
                    tenant_id=tenant.id,
                    full_name=f"Usuario {role}",
                    email=f"{index}@{role}.mx",
                    password_hash=hash_password("clave-segura-123"),
                    role=role,
                )
            )
        await db_session.commit()

        roles = (await db_session.scalars(select(User.role).order_by(User.email))).all()
        assert set(roles) == {"admin", "prestamista", "cobrador"}

    async def test_permissions_are_jsonb(self, db_session: AsyncSession) -> None:
        tenant = await self._tenant(db_session)
        user = User(
            tenant_id=tenant.id,
            full_name="Prestamista",
            email="perm@test.mx",
            password_hash=hash_password("clave-segura-123"),
            role="prestamista",
            permissions={"edit_rate": False, "cancel_payment": True},
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.permissions["edit_rate"] is False
        assert user.permissions["cancel_payment"] is True


class TestSystemSettingModel:
    """Tabla system_setting: parametros globales por tenant."""

    async def test_creates_with_defaults(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Config", slug="config")
        db_session.add(tenant)
        await db_session.commit()

        setting = SystemSetting(tenant_id=tenant.id)
        db_session.add(setting)
        await db_session.commit()

        assert setting.default_late_fee_rate == Decimal("0.1000")
        assert setting.default_scheme == "simple"
        assert setting.grace_days == 0
        assert setting.timezone == "America/Mexico_City"

    async def test_one_setting_per_tenant(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Unica", slug="unica")
        db_session.add(tenant)
        await db_session.commit()

        db_session.add(SystemSetting(tenant_id=tenant.id))
        await db_session.commit()

        db_session.add(SystemSetting(tenant_id=tenant.id))
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_stores_decimal_rate_exactly(self, db_session: AsyncSession) -> None:
        """RN-01: la tasa se guarda como numeric, sin perdida de precision."""
        tenant = Tenant(name="Precision", slug="precision")
        db_session.add(tenant)
        await db_session.commit()

        setting = SystemSetting(tenant_id=tenant.id, default_late_fee_rate=Decimal("0.0525"))
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        assert setting.default_late_fee_rate == Decimal("0.0525")
        assert str(setting.default_late_fee_rate) == "0.0525"


class TestCascade:
    """Borrar un tenant debe borrar su configuracion y sus usuarios."""

    async def test_deleting_tenant_removes_children(self, db_session: AsyncSession) -> None:
        tenant = Tenant(name="Borrar", slug="borrar")
        db_session.add(tenant)
        await db_session.commit()

        db_session.add(SystemSetting(tenant_id=tenant.id))
        db_session.add(
            User(
                tenant_id=tenant.id,
                full_name="Admin",
                email="borrar@test.mx",
                password_hash=hash_password("clave-segura-123"),
                role="admin",
            )
        )
        await db_session.commit()

        await db_session.delete(tenant)
        await db_session.commit()

        assert (await db_session.scalars(select(User))).all() == []
        assert (await db_session.scalars(select(SystemSetting))).all() == []


class TestRepr:
    """Las representaciones de depuracion no deben exponer datos sensibles."""

    def test_tenant_repr_shows_slug_and_plan(self) -> None:
        tenant = Tenant(name="Visible", slug="visible", plan="profesional")
        text = repr(tenant)

        assert "visible" in text
        assert "profesional" in text

    def test_user_repr_hides_email_and_hash(self) -> None:
        user = User(
            full_name="Admin",
            email="secreto@test.mx",
            password_hash="$2b$12$hash",
            role="admin",
        )
        text = repr(user)

        assert "admin" in text
        assert "secreto@test.mx" not in text
        assert "hash" not in text

    def test_system_setting_repr_shows_grace(self) -> None:
        setting = SystemSetting(grace_days=7)
        assert "grace=7" in repr(setting)
