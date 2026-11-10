"""Pruebas del script de creacion de financieras."""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.scripts import seed_tenant as seed_module
from app.scripts.seed_tenant import SeedError, main, seed_tenant

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"


@pytest.fixture(autouse=True)
def _use_test_session(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """Hace que el seed use la sesion de prueba en lugar de la real."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session() -> Any:
        yield db_session

    monkeypatch.setattr(seed_module, "SessionLocal", _session)
    return db_session


class TestSeedTenant:
    """Creacion del tenant inicial."""

    async def test_creates_tenant_setting_and_admin(self, db_session: AsyncSession) -> None:
        tenant, admin = await seed_tenant(
            name="Financiera Nueva",
            slug="nueva",
            admin_name="Admin Nueva",
            admin_email="admin@nueva.mx",
            admin_password=PASSWORD,
        )

        assert tenant.name == "Financiera Nueva"
        assert tenant.slug == "nueva"
        assert tenant.plan == "empresarial"
        assert admin.role == "admin"
        assert admin.email == "admin@nueva.mx"
        assert admin.tenant_id == tenant.id

    async def test_password_is_hashed(self, db_session: AsyncSession) -> None:
        _, admin = await seed_tenant(
            name="F", slug="hash", admin_name="A", admin_email="a@h.mx", admin_password=PASSWORD
        )

        assert admin.password_hash != PASSWORD
        assert verify_password(PASSWORD, admin.password_hash)

    async def test_creates_default_settings(self, db_session: AsyncSession) -> None:
        tenant, _ = await seed_tenant(
            name="F", slug="config", admin_name="A", admin_email="a@c.mx", admin_password=PASSWORD
        )

        setting = await db_session.scalar(
            select(SystemSetting).where(SystemSetting.tenant_id == tenant.id)
        )
        assert setting is not None
        assert str(setting.default_late_fee_rate) == "0.1000"
        assert setting.default_scheme == "simple"
        assert setting.grace_days == 5
        assert setting.timezone == "America/Mexico_City"

    async def test_rejects_duplicate_slug(self, db_session: AsyncSession) -> None:
        await seed_tenant(
            name="Uno", slug="dup", admin_name="A", admin_email="uno@d.mx", admin_password=PASSWORD
        )

        with pytest.raises(SeedError, match="slug"):
            await seed_tenant(
                name="Dos",
                slug="dup",
                admin_name="B",
                admin_email="dos@d.mx",
                admin_password=PASSWORD,
            )

    async def test_rejects_duplicate_email(self, db_session: AsyncSession) -> None:
        await seed_tenant(
            name="Uno",
            slug="uno",
            admin_name="A",
            admin_email="mismo@d.mx",
            admin_password=PASSWORD,
        )

        with pytest.raises(SeedError, match="correo"):
            await seed_tenant(
                name="Dos",
                slug="dos",
                admin_name="B",
                admin_email="mismo@d.mx",
                admin_password=PASSWORD,
            )

    async def test_rejects_short_password(self, db_session: AsyncSession) -> None:
        with pytest.raises(SeedError, match="10 caracteres"):
            await seed_tenant(
                name="F",
                slug="corta",
                admin_name="A",
                admin_email="a@corta.mx",
                admin_password="corta",
            )

    async def test_rejects_invalid_email_format(self, db_session: AsyncSession) -> None:
        with pytest.raises(Exception, match="email|correo|valid"):  # noqa: B017
            await seed_tenant(
                name="F",
                slug="malcorreo",
                admin_name="A",
                admin_email="no-es-correo",
                admin_password=PASSWORD,
            )


class TestSeedCli:
    """Interfaz de linea de comandos, sin crear un event loop nuevo."""

    async def test_returns_zero_on_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = seed_module._build_parser().parse_args(
            [
                "--name",
                "CLI",
                "--slug",
                "cli",
                "--admin-name",
                "Admin",
                "--admin-email",
                "cli@test.mx",
                "--admin-password",
                PASSWORD,
            ]
        )

        assert await seed_module.run_cli(args, PASSWORD) == 0
        output = capsys.readouterr().out
        assert "Tenant creado" in output
        assert "Administrador creado" in output

    async def test_returns_one_on_duplicate(self, capsys: pytest.CaptureFixture[str]) -> None:
        first = seed_module._build_parser().parse_args(
            [
                "--name",
                "CLI",
                "--slug",
                "cli-dup",
                "--admin-name",
                "Admin",
                "--admin-email",
                "cli-dup@test.mx",
            ]
        )
        assert await seed_module.run_cli(first, PASSWORD) == 0

        second = seed_module._build_parser().parse_args(
            [
                "--name",
                "Otra",
                "--slug",
                "cli-dup",
                "--admin-name",
                "Admin",
                "--admin-email",
                "otro@test.mx",
            ]
        )
        assert await seed_module.run_cli(second, PASSWORD) == 1
        assert "Error" in capsys.readouterr().err

    def test_requires_password(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)

        code = main(
            [
                "--name",
                "F",
                "--slug",
                "sin-pass",
                "--admin-name",
                "A",
                "--admin-email",
                "a@sinpass.mx",
            ]
        )

        assert code == 2
        assert "contrasena" in capsys.readouterr().err


class TestSeedPersistence:
    """Verificacion directa contra la base."""

    async def test_all_records_exist(self, db_session: AsyncSession) -> None:
        await seed_tenant(
            name="Persistente",
            slug="persistente",
            admin_name="Admin",
            admin_email="p@test.mx",
            admin_password=PASSWORD,
        )

        tenants = (await db_session.scalars(select(Tenant))).all()
        users = (await db_session.scalars(select(User))).all()
        settings = (await db_session.scalars(select(SystemSetting))).all()

        assert len(tenants) == 1
        assert len(users) == 1
        assert len(settings) == 1
        assert users[0].tenant_id == tenants[0].id
        assert settings[0].tenant_id == tenants[0].id
