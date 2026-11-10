"""Pruebas de integracion de autenticacion."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"


async def _create_user(
    session: AsyncSession,
    *,
    email: str = "admin@test.mx",
    role: str = "admin",
    password: str = PASSWORD,
    is_active: bool = True,
    slug: str = "test",
) -> User:
    """Crea un tenant y un usuario para la prueba."""
    tenant = Tenant(name="Financiera Test", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario Test",
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    return user


class TestLogin:
    """POST /api/v1/auth/login."""

    async def test_returns_token_pair(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)

        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["expires_in"] == 15 * 60

    async def test_stores_hashed_refresh_token(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)

        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        refresh = response.json()["refresh_token"]

        stored = await db_session.scalar(select(RefreshToken))
        assert stored is not None
        assert stored.token_hash != refresh
        assert len(stored.token_hash) == 64

    async def test_updates_last_login(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        assert user.last_login_at is None

        await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        await db_session.refresh(user)

        assert user.last_login_at is not None

    async def test_rejects_wrong_password(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)

        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": "equivocada-123"}
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Correo o contrasena incorrectos."

    async def test_rejects_unknown_email_silently(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """No debe revelar si el correo existe."""
        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "nadie@test.mx", "password": PASSWORD}
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Correo o contrasena incorrectos."

    async def test_rejects_inactive_user(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session, is_active=False)

        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )

        assert response.status_code == 401
        assert "desactivada" in response.json()["detail"]

    async def test_email_is_case_insensitive(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session, email="admin@test.mx")

        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "ADMIN@TEST.MX", "password": PASSWORD}
        )

        assert response.status_code == 200

    async def test_rejects_invalid_email_format(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "no-es-correo", "password": PASSWORD}
        )
        assert response.status_code == 422

    async def test_rejects_empty_password(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/auth/login", json={"email": "a@b.mx", "password": ""}
        )
        assert response.status_code == 422


class TestMe:
    """GET /api/v1/auth/me."""

    async def test_returns_profile(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        await _create_user(db_session, role="prestamista")
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        token = login.json()["access_token"]

        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "admin@test.mx"
        assert body["role"] == "prestamista"
        assert body["tenant_name"] == "Financiera Test"
        assert body["tenant_slug"] == "test"

    async def test_requires_token(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_rejects_refresh_token_as_access(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        refresh = login.json()["refresh_token"]

        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"}
        )

        assert response.status_code == 401

    async def test_rejects_deactivated_user_after_login(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        token = login.json()["access_token"]

        user.is_active = False
        await db_session.commit()

        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403


class TestRefresh:
    """POST /api/v1/auth/refresh."""

    async def test_returns_new_pair(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        old_refresh = login.json()["refresh_token"]

        response = await api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )

        assert response.status_code == 200
        assert response.json()["refresh_token"] != old_refresh

    async def test_revokes_used_token(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """La rotacion debe impedir reutilizar el refresh anterior."""
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        old_refresh = login.json()["refresh_token"]

        await api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        second = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

        assert second.status_code == 401

    async def test_reuse_revokes_all_sessions(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Reutilizar un token revocado puede indicar robo: se cierran todas."""
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        old_refresh = login.json()["refresh_token"]

        rotated = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        new_refresh = rotated.json()["refresh_token"]

        # Reutilizar el viejo dispara la revocacion masiva.
        await api_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

        response = await api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": new_refresh}
        )
        assert response.status_code == 401

    async def test_rejects_garbage(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "no-es-un-token"}
        )
        assert response.status_code == 401

    async def test_rejects_access_token(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        access = login.json()["access_token"]

        response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": access})
        assert response.status_code == 401


class TestLogout:
    """POST /api/v1/auth/logout."""

    async def test_revokes_refresh_token(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        refresh = login.json()["refresh_token"]

        logout = await api_client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
        assert logout.status_code == 204

        attempt = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert attempt.status_code == 401

    async def test_is_idempotent(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        await _create_user(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        refresh = login.json()["refresh_token"]

        first = await api_client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
        second = await api_client.post("/api/v1/auth/logout", json={"refresh_token": refresh})

        assert first.status_code == 204
        assert second.status_code == 204


class TestOpenApi:
    """Los endpoints deben estar documentados."""

    async def test_auth_endpoints_are_documented(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/openapi.json")
        paths = response.json()["paths"]

        assert "/api/v1/auth/login" in paths
        assert "/api/v1/auth/refresh" in paths
        assert "/api/v1/auth/logout" in paths
        assert "/api/v1/auth/me" in paths


class TestSimulateStillPublic:
    """La simulacion sigue abierta: es una calculadora, no expone datos."""

    async def test_simulate_without_token(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/loans/simulate",
            json={
                "principal": 10000,
                "interest_rate": 0.05,
                "rate_period": "semanal",
                "scheme": "simple",
                "term_periods": 12,
                "start_date": "2026-11-02",
            },
        )

        assert response.status_code == 200
