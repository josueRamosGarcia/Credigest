"""Pruebas de integracion del comparador bancario (RF-45 a RF-47, RN-52 a RN-54)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token
from app.core.security import hash_password
from app.domain.comparator import DISCLAIMER_TEXT
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"


async def _make_user(
    session: AsyncSession,
    *,
    role: str = "admin",
    plan: str = "empresarial",
) -> tuple[Tenant, User, dict[str, str]]:
    """Crea tenant y usuario con el rol indicado."""
    unique = uuid4().hex[:8]
    tenant = Tenant(name=f"Financiera {unique}", slug=f"fin-{unique}", plan=plan)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario Comparador",
        email=f"{role}-{unique}@demo.mx",
        password_hash=hash_password(PASSWORD),
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.commit()

    token, _, _ = create_access_token(user.id, tenant.id, user.role)
    return tenant, user, {"Authorization": f"Bearer {token}"}


class TestComparatorApi:
    """GET /api/v1/banks, POST /api/v1/banks, PATCH /api/v1/banks/{id} y POST /api/v1/compare."""

    async def test_seeds_default_catalog_and_compares_offers(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, headers = await _make_user(db_session, role="prestamista")

        banks_res = await api_client.get("/api/v1/banks", headers=headers)
        assert banks_res.status_code == 200
        banks = banks_res.json()
        assert len(banks) == 5

        compare_res = await api_client.post(
            "/api/v1/compare",
            headers=headers,
            json={
                "principal": "10000.00",
                "interest_rate": "0.0300",
                "rate_period": "mensual",
                "scheme": "cuota_fija",
                "term_periods": 12,
                "opening_fee": "0.00",
            },
        )
        assert compare_res.status_code == 200
        body = compare_res.json()
        assert body["disclaimer"] == DISCLAIMER_TEXT
        assert body["own_offer"]["is_own_offer"] is True
        assert body["own_offer"]["installment_amount"] == "1004.62"
        assert body["own_offer"]["estimated_cat"] == "42.58"
        assert len(body["bank_offers"]) == 5

    async def test_admin_can_create_and_update_bank_but_lender_cannot(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-54: solo el Administrador configura el catalogo."""
        tenant, _, admin_headers = await _make_user(db_session, role="admin")
        lender = User(
            tenant_id=tenant.id,
            full_name="Prestamista",
            email=f"lender-{uuid4().hex[:6]}@demo.mx",
            password_hash=hash_password(PASSWORD),
            role="prestamista",
        )
        db_session.add(lender)
        await db_session.commit()
        lender_token, _, _ = create_access_token(lender.id, tenant.id, lender.role)
        lender_headers = {"Authorization": f"Bearer {lender_token}"}

        # Prestamista no puede dar de alta bancos -> 403
        forbidden = await api_client.post(
            "/api/v1/banks",
            headers=lender_headers,
            json={"name": "Banco X", "annual_rate": "0.4500"},
        )
        assert forbidden.status_code == 403

        # Admin crea y actualiza un banco
        created = await api_client.post(
            "/api/v1/banks",
            headers=admin_headers,
            json={
                "name": "Banco Regional",
                "annual_rate": "0.3600",
                "cat": "0.4258",
                "opening_fee": "300.00",
                "is_active": True,
            },
        )
        assert created.status_code == 201
        bank_id = created.json()["id"]

        updated = await api_client.patch(
            f"/api/v1/banks/{bank_id}",
            headers=admin_headers,
            json={"opening_fee": "500.00", "is_active": False},
        )
        assert updated.status_code == 200
        assert updated.json()["opening_fee"] == "500.00"
        assert updated.json()["is_active"] is False

    async def test_cobrador_cannot_access_comparator(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, cobrador_headers = await _make_user(db_session, role="cobrador")

        res_banks = await api_client.get("/api/v1/banks", headers=cobrador_headers)
        assert res_banks.status_code == 403

        res_compare = await api_client.post(
            "/api/v1/compare",
            headers=cobrador_headers,
            json={
                "principal": "10000.00",
                "interest_rate": "0.0300",
                "rate_period": "mensual",
                "scheme": "simple",
                "term_periods": 12,
            },
        )
        assert res_compare.status_code == 403

