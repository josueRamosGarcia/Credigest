"""Pruebas de permisos, roles y aislamiento por tenant."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, require_role
from app.core.jwt import create_access_token
from app.core.security import hash_password
from app.models.refresh_token import RefreshToken
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services import auth_service

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"


async def _make_user(
    session: AsyncSession,
    *,
    email: str,
    role: str,
    permissions: dict[str, Any] | None = None,
    tenant_active: bool = True,
    user_active: bool = True,
    slug: str | None = None,
) -> tuple[User, Tenant]:
    """Crea tenant y usuario con las condiciones pedidas."""
    tenant = Tenant(
        name=f"Tenant {email}", slug=slug or email.split("@")[0], is_active=tenant_active
    )
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario",
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        permissions=permissions or {},
        is_active=user_active,
    )
    session.add(user)
    await session.commit()
    return user, tenant


class TestAuthContextPermissions:
    """RN-61: el Administrador siempre tiene todo."""

    def test_admin_has_every_permission(self) -> None:
        user = User(role="admin", permissions={})
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        assert context.has_permission("cancel_payment") is True
        assert context.has_permission("cualquier_cosa") is True

    def test_other_roles_need_explicit_permission(self) -> None:
        user = User(role="prestamista", permissions={"cancel_payment": True})
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        assert context.has_permission("cancel_payment") is True
        assert context.has_permission("edit_settings") is False

    def test_cobrador_has_no_permissions_by_default(self) -> None:
        user = User(role="cobrador", permissions={})
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        assert context.has_permission("register_payment") is False

    def test_exposes_tenant_id_and_role(self) -> None:
        tenant_id = uuid4()
        user = User(tenant_id=tenant_id, role="cobrador")
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        assert context.tenant_id == tenant_id
        assert context.role == "cobrador"


class TestRequireRole:
    """La dependencia de rol debe dejar pasar solo a los autorizados."""

    async def test_allows_listed_role(self) -> None:
        user = User(role="prestamista")
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        checker = require_role("prestamista")
        assert await checker(context) is context

    async def test_admin_always_passes(self) -> None:
        user = User(role="admin")
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        checker = require_role("cobrador")
        assert await checker(context) is context

    async def test_rejects_other_roles(self) -> None:
        from fastapi import HTTPException

        user = User(role="cobrador")
        context = AuthContext(user=user, tenant=Tenant(name="T"))

        checker = require_role("prestamista")
        with pytest.raises(HTTPException) as exc_info:
            await checker(context)

        assert exc_info.value.status_code == 403


class TestTenantIsolation:
    """RNF-08: un usuario no puede acceder a otra financiera."""

    async def test_user_of_other_tenant_is_rejected(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, _ = await _make_user(db_session, email="a@test.mx", role="admin")

        # Token con un tenant que no es el del usuario.
        forged, _, _ = create_access_token(user.id, uuid4(), "admin")

        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
        )
        assert response.status_code == 401

    async def test_inactive_tenant_is_rejected(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _make_user(db_session, email="b@test.mx", role="admin", tenant_active=False)

        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "b@test.mx", "password": PASSWORD}
        )
        token = login.json()["access_token"]

        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403

    async def test_deleted_user_token_is_rejected(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, _ = await _make_user(db_session, email="c@test.mx", role="admin")
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "c@test.mx", "password": PASSWORD}
        )
        token = login.json()["access_token"]

        await db_session.delete(user)
        await db_session.commit()

        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestRefreshEdgeCases:
    """Casos limite del refresh token."""

    async def test_rejects_expired_stored_token(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, _ = await _make_user(db_session, email="d@test.mx", role="admin")
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "d@test.mx", "password": PASSWORD}
        )
        refresh = login.json()["refresh_token"]

        stored = await db_session.scalar(select_first(RefreshToken))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.commit()

        response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 401
        assert "expiro" in response.json()["detail"]

    async def test_rejects_refresh_of_deactivated_user(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user, _ = await _make_user(db_session, email="e@test.mx", role="admin")
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "e@test.mx", "password": PASSWORD}
        )
        refresh = login.json()["refresh_token"]

        user.is_active = False
        await db_session.commit()

        response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 401

    async def test_deleted_user_invalidates_refresh(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Al borrar al usuario, sus tokens se borran en cascada (FK)."""
        user, _ = await _make_user(db_session, email="f@test.mx", role="admin")
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "f@test.mx", "password": PASSWORD}
        )
        refresh = login.json()["refresh_token"]

        await db_session.delete(user)
        await db_session.commit()

        response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert response.status_code == 401


class TestCleanupExpired:
    """Limpieza de tokens caducados."""

    async def test_deletes_only_old_tokens(self, db_session: AsyncSession) -> None:
        user, _ = await _make_user(db_session, email="g@test.mx", role="admin")

        old = RefreshToken(
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) - timedelta(days=60),
        )
        recent = RefreshToken(
            user_id=user.id,
            token_hash="b" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db_session.add_all([old, recent])
        await db_session.commit()

        deleted = await auth_service.cleanup_expired(db_session, older_than_days=30)
        assert deleted == 1

        remaining = (await db_session.scalars(select_all(RefreshToken))).all()
        assert len(remaining) == 1
        assert remaining[0].token_hash == "b" * 64

    async def test_returns_zero_when_nothing_to_delete(self, db_session: AsyncSession) -> None:
        assert await auth_service.cleanup_expired(db_session) == 0


class TestRevokeAll:
    """Cierre de todas las sesiones de un usuario."""

    async def test_revokes_every_active_token(self, db_session: AsyncSession) -> None:
        user, _ = await _make_user(db_session, email="h@test.mx", role="admin")

        for index in range(3):
            db_session.add(
                RefreshToken(
                    user_id=user.id,
                    token_hash=str(index) * 64,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
        await db_session.commit()

        await auth_service.revoke_all_for_user(db_session, user.id)

        tokens = (await db_session.scalars(select_all(RefreshToken))).all()
        assert all(token.revoked_at is not None for token in tokens)


class TestSystemSettingPerTenant:
    """Cada financiera tiene su propia configuracion."""

    async def test_settings_are_independent(self, db_session: AsyncSession) -> None:
        _, tenant_a = await _make_user(db_session, email="i@test.mx", role="admin")
        _, tenant_b = await _make_user(db_session, email="j@test.mx", role="admin")

        db_session.add_all(
            [
                SystemSetting(tenant_id=tenant_a.id, grace_days=5),
                SystemSetting(tenant_id=tenant_b.id, grace_days=15),
            ]
        )
        await db_session.commit()

        settings = (await db_session.scalars(select_all(SystemSetting))).all()
        graces = sorted(setting.grace_days for setting in settings)
        assert graces == [5, 15]


# Helpers de consulta para no repetir imports en cada prueba.
def select_first(model: Any) -> Any:
    """Selecciona el primer registro de un modelo."""
    from sqlalchemy import select

    return select(model).limit(1)


def select_all(model: Any) -> Any:
    """Selecciona todos los registros de un modelo."""
    from sqlalchemy import select

    return select(model)
