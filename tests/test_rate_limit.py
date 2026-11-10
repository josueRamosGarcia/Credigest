"""Pruebas del limite de intentos de login (RNF-10)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import RateLimiter, login_limiter
from app.core.security import hash_password
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "clave-segura-123"


@pytest.fixture(autouse=True)
def _clean_limiter() -> None:
    """Limpia el limitador global entre pruebas."""
    login_limiter.clear()
    yield
    login_limiter.clear()


class TestRateLimiter:
    """Comportamiento del limitador en aislamiento."""

    def test_allows_until_limit(self) -> None:
        limiter = RateLimiter(limit=3, window_seconds=60)

        for _ in range(3):
            allowed, _ = limiter.check("ip")
            assert allowed is True
            limiter.hit("ip")

        allowed, retry = limiter.check("ip")
        assert allowed is False
        assert retry >= 1

    def test_different_keys_are_independent(self) -> None:
        limiter = RateLimiter(limit=2, window_seconds=60)

        limiter.hit("a")
        limiter.hit("a")

        assert limiter.check("a")[0] is False
        assert limiter.check("b")[0] is True

    def test_window_expires(self) -> None:
        """Despues de la ventana el contador se reinicia."""
        limiter = RateLimiter(limit=2, window_seconds=10)

        limiter.hit("ip", now=0.0)
        limiter.hit("ip", now=1.0)
        assert limiter.check("ip", now=2.0)[0] is False

        assert limiter.check("ip", now=11.0)[0] is True

    def test_reset_clears_key(self) -> None:
        limiter = RateLimiter(limit=1, window_seconds=60)

        limiter.hit("ip")
        assert limiter.check("ip")[0] is False

        limiter.reset("ip")
        assert limiter.check("ip")[0] is True

    def test_check_does_not_count(self) -> None:
        """"check" solo consulta: no gasta intentos."""
        limiter = RateLimiter(limit=1, window_seconds=60)

        for _ in range(10):
            assert limiter.check("ip")[0] is True

    def test_retry_after_is_positive(self) -> None:
        limiter = RateLimiter(limit=1, window_seconds=60)
        limiter.hit("ip", now=0.0)

        _, retry = limiter.check("ip", now=1.0)
        assert 1 <= retry <= 60

    def test_rejects_invalid_limit(self) -> None:
        with pytest.raises(ValueError, match="al menos 1"):
            RateLimiter(limit=0)

    def test_rejects_invalid_window(self) -> None:
        with pytest.raises(ValueError, match="al menos 1 segundo"):
            RateLimiter(window_seconds=0)

    def test_exposes_configuration(self) -> None:
        limiter = RateLimiter(limit=7, window_seconds=120)
        assert limiter.limit == 7
        assert limiter.window_seconds == 120

    def test_clear_removes_everything(self) -> None:
        limiter = RateLimiter(limit=1, window_seconds=60)
        limiter.hit("a")
        limiter.hit("b")

        limiter.clear()

        assert limiter.check("a")[0] is True
        assert limiter.check("b")[0] is True


async def _setup(session: AsyncSession) -> None:
    """Crea un tenant con un administrador."""
    tenant = Tenant(name="Test", slug="test")
    session.add(tenant)
    await session.flush()

    session.add(
        SystemSetting(tenant_id=tenant.id, default_late_fee_rate="0.1000", grace_days=0)
    )
    session.add(
        User(
            tenant_id=tenant.id,
            full_name="Admin",
            email="admin@test.mx",
            password_hash=hash_password(PASSWORD),
            role="admin",
        )
    )
    await session.commit()


class TestLoginRateLimit:
    """Limite aplicado al endpoint de login."""

    async def test_blocks_after_five_failures(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)

        for _ in range(5):
            response = await api_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.mx", "password": "equivocada-123"},
            )
            assert response.status_code == 401

        blocked = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.mx", "password": "equivocada-123"},
        )

        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert "Demasiados intentos" in blocked.json()["detail"]

    async def test_blocks_correct_password_too(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Mientras dure el bloqueo, ni la contrasena correcta pasa."""
        await _setup(db_session)

        for _ in range(5):
            await api_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.mx", "password": "equivocada-123"},
            )

        response = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.mx", "password": PASSWORD},
        )

        assert response.status_code == 429

    async def test_successful_login_resets_counter(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)

        for _ in range(4):
            await api_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.mx", "password": "equivocada-123"},
            )

        success = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.mx", "password": PASSWORD},
        )
        assert success.status_code == 200

        # El contador se reinicio: caben cinco fallos mas.
        for _ in range(5):
            response = await api_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.mx", "password": "equivocada-123"},
            )
            assert response.status_code == 401

    async def test_unknown_email_counts_as_failure(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Un correo inexistente tambien gasta intentos: no revela si existe."""
        await _setup(db_session)

        for _ in range(5):
            response = await api_client.post(
                "/api/v1/auth/login",
                json={"email": "nadie@test.mx", "password": "intento-malo"},
            )
            assert response.status_code == 401

        blocked = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "nadie@test.mx", "password": "intento-malo"},
        )
        assert blocked.status_code == 429

    async def test_other_endpoints_are_not_limited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Solo el login tiene limite; el resto de la API sigue funcionando."""
        await _setup(db_session)

        for _ in range(5):
            await api_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.mx", "password": "equivocada-123"},
            )

        health = await api_client.get("/health")
        assert health.status_code == 200

    async def test_limit_is_configurable(self) -> None:
        """El valor sale de la configuracion del entorno."""
        from app.core.config import get_settings

        settings = get_settings()
        assert login_limiter.limit == settings.login_rate_limit
        assert login_limiter.window_seconds == settings.login_rate_window
