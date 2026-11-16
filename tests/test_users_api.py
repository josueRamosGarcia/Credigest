"""Pruebas de integracion para los endpoints de usuarios y configuracion."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"


async def _setup_admin(
    session: AsyncSession,
    *,
    plan: str = "basico",
    slug: str | None = None,
) -> tuple[Tenant, User, dict[str, str]]:
    """Crea una financiera con su administrador y devuelve las cabeceras auth."""
    unique = uuid4().hex[:8]
    tenant = Tenant(
        name=f"Financiera {unique}",
        slug=slug or f"fin-{unique}",
        plan=plan,
    )
    session.add(tenant)
    await session.flush()

    admin = User(
        tenant_id=tenant.id,
        full_name="Admin Principal",
        email=f"admin-{unique}@demo.mx",
        password_hash=hash_password(PASSWORD),
        role="admin",
        permissions={},
        is_active=True,
    )
    session.add(admin)
    await session.commit()

    token, _, _ = create_access_token(admin.id, tenant.id, admin.role)
    return tenant, admin, {"Authorization": f"Bearer {token}"}


class TestUsersCrudAndRules:
    """RF-03 a RF-08, RN-61 a RN-63, RN-68: gestion de usuarios."""

    async def test_create_user_generates_temp_password_and_audits(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _, headers = await _setup_admin(db_session)

        response = await api_client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "full_name": "Laura Prestamista",
                "email": "laura@demo.mx",
                "phone": "8711234567",
                "role": "prestamista",
                "permissions": {"cancel_payment": True},
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "laura@demo.mx"
        assert body["role"] == "prestamista"
        assert body["permissions"] == {"cancel_payment": True}
        assert body["temporary_password"] is not None
        assert len(body["temporary_password"]) >= 10

        # La contrasena temporal permite iniciar sesion de inmediato.
        login = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "laura@demo.mx", "password": body["temporary_password"]},
        )
        assert login.status_code == 200

        # Quedo auditado.
        audit = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.action == "user.create",
            )
        )
        assert audit is not None

    async def test_duplicate_email_returns_409(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, admin, headers = await _setup_admin(db_session)

        response = await api_client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "full_name": "Otro",
                "email": admin.email,
                "role": "cobrador",
            },
        )
        assert response.status_code == 409

    async def test_non_admin_cannot_manage_users(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _, _ = await _setup_admin(db_session)
        lender = User(
            tenant_id=tenant.id,
            full_name="Prestamista",
            email=f"lender-{uuid4().hex[:6]}@demo.mx",
            password_hash=hash_password(PASSWORD),
            role="prestamista",
        )
        db_session.add(lender)
        await db_session.commit()

        token, _, _ = create_access_token(lender.id, tenant.id, lender.role)
        headers = {"Authorization": f"Bearer {token}"}

        res_list = await api_client.get("/api/v1/users", headers=headers)
        assert res_list.status_code == 403

        res_settings = await api_client.get("/api/v1/settings", headers=headers)
        assert res_settings.status_code == 403

    async def test_plan_limit_blocks_6th_user_on_basico(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-68: el plan basico permite hasta 5 usuarios activos."""
        _, _, headers = await _setup_admin(db_session, plan="basico")

        # Ya existe 1 admin; creamos 4 usuarios mas (total 5).
        for idx in range(4):
            res = await api_client.post(
                "/api/v1/users",
                headers=headers,
                json={
                    "full_name": f"Cobrador {idx}",
                    "email": f"cobrador-{idx}-{uuid4().hex[:6]}@demo.mx",
                    "role": "cobrador",
                },
            )
            assert res.status_code == 201

        # El 6to se bloquea con 409.
        blocked = await api_client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "full_name": "Cobrador Extra",
                "email": f"extra-{uuid4().hex[:6]}@demo.mx",
                "role": "cobrador",
            },
        )
        assert blocked.status_code == 409
        assert "plan" in blocked.json()["detail"].lower()

    async def test_cannot_deactivate_self_or_last_admin(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-62: proteccion del propio admin y del ultimo admin activo."""
        _, admin, headers = await _setup_admin(db_session)

        # Desactivarse a si mismo -> 409
        self_deactivate = await api_client.patch(
            f"/api/v1/users/{admin.id}/status",
            headers=headers,
            json={"is_active": False},
        )
        assert self_deactivate.status_code == 409

        # Quitarse el rol admin siendo el unico -> 409
        demote_last = await api_client.patch(
            f"/api/v1/users/{admin.id}",
            headers=headers,
            json={"role": "prestamista"},
        )
        assert demote_last.status_code == 409

    async def test_update_reset_password_and_tenant_isolation(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, headers_a = await _setup_admin(db_session)
        _, admin_b, _ = await _setup_admin(db_session)

        created = await api_client.post(
            "/api/v1/users",
            headers=headers_a,
            json={
                "full_name": "Carlos Cobrador",
                "email": f"carlos-{uuid4().hex[:6]}@demo.mx",
                "role": "cobrador",
            },
        )
        user_id = created.json()["id"]

        # Actualizar permisos y telefono.
        updated = await api_client.patch(
            f"/api/v1/users/{user_id}",
            headers=headers_a,
            json={
                "full_name": "Carlos Editado",
                "phone": "8710001122",
                "role": "prestamista",
                "permissions": {"edit_rate": True},
            },
        )
        assert updated.status_code == 200
        assert updated.json()["full_name"] == "Carlos Editado"
        assert updated.json()["role"] == "prestamista"
        assert updated.json()["permissions"] == {"edit_rate": True}

        # Reset password.
        reset_res = await api_client.post(
            f"/api/v1/users/{user_id}/reset-password",
            headers=headers_a,
            json={"password": "nueva-clave-segura-99"},
        )
        assert reset_res.status_code == 200
        assert reset_res.json()["temporary_password"] == "nueva-clave-segura-99"

        # Aislamiento entre tenants: no puede ver al admin_b.
        cross = await api_client.get(
            f"/api/v1/users/{admin_b.id}",
            headers=headers_a,
        )
        assert cross.status_code == 404


class TestSystemSettingsApi:
    """RF-09 a RF-12: parametros del sistema por financiera."""

    async def test_get_and_update_settings(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _, headers = await _setup_admin(db_session)

        # GET inicializa si no existia.
        initial = await api_client.get("/api/v1/settings", headers=headers)
        assert initial.status_code == 200
        assert initial.json()["default_scheme"] == "simple"

        # PUT actualiza y audita.
        updated = await api_client.put(
            "/api/v1/settings",
            headers=headers,
            json={
                "default_late_fee_rate": "0.1500",
                "default_scheme": "cuota_fija",
                "grace_days": 5,
                "timezone": "America/Mexico_City",
            },
        )
        assert updated.status_code == 200
        body = updated.json()
        assert body["default_late_fee_rate"] == "0.1500"
        assert body["default_scheme"] == "cuota_fija"
        assert body["grace_days"] == 5

        audit = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.action == "settings.update",
            )
        )
        assert audit is not None

