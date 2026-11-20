"""Pruebas de integracion del portal del cliente (CURP + PIN de 6 digitos)."""

from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt import create_access_token
from app.core.security import hash_password
from app.models.client import Client
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
CURP = "LOPJ850312MDFZRN00"


async def _setup_scenario(
    session: AsyncSession,
) -> tuple[Tenant, User, Client, dict[str, str]]:
    """Crea financiera, administrador y cliente."""
    unique = uuid4().hex[:8]
    tenant = Tenant(name=f"Financiera {unique}", slug=f"fin-{unique}")
    session.add(tenant)
    await session.flush()

    admin = User(
        tenant_id=tenant.id,
        full_name="Admin Portal",
        email=f"admin-{unique}@demo.mx",
        password_hash=hash_password(PASSWORD),
        role="admin",
    )
    session.add(admin)

    client = Client(
        tenant_id=tenant.id,
        full_name="Maria Lopez",
        curp=CURP,
        phone="8711234567",
        address="Calle 1, Centro",
        status="activo",
        birth_date=date(1985, 3, 12),
    )
    session.add(client)
    await session.commit()

    token, _, _ = create_access_token(admin.id, tenant.id, admin.role)
    return tenant, admin, client, {"Authorization": f"Bearer {token}"}


class TestClientPortalFlow:
    """Flujo completo: generar PIN -> login del cliente -> consultar avance."""

    async def test_generate_pin_login_and_view_progress(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client, admin_headers = await _setup_scenario(db_session)

        # 1. Crear un prestamo de 10,000 a 10 semanas al 5% simple (total 15,000)
        loan_res = await api_client.post(
            "/api/v1/loans",
            headers=admin_headers,
            json={
                "client_id": str(client.id),
                "principal": 10000,
                "interest_rate": 0.05,
                "rate_period": "semanal",
                "scheme": "simple",
                "term_periods": 10,
                "start_date": "2026-11-02",
            },
        )
        assert loan_res.status_code == 201
        loan_id = loan_res.json()["id"]

        # 2. Registrar un abono de 1,500 (10 % del total de 15,000)
        pay_res = await api_client.post(
            "/api/v1/payments",
            headers=admin_headers,
            json={"loan_id": loan_id, "amount": 1500, "method": "efectivo"},
        )
        assert pay_res.status_code == 201

        # 3. Generar PIN de 6 digitos para el cliente
        pin_res = await api_client.post(
            f"/api/v1/clients/{client.id}/portal-pin",
            headers=admin_headers,
        )
        assert pin_res.status_code == 200
        pin = pin_res.json()["pin"]
        assert len(pin) == 6
        assert pin.isdigit()
        assert "wa.me/" in pin_res.json()["whatsapp_url"]

        # 4. Cliente inicia sesion en /api/v1/portal/login con CURP + PIN
        portal_login = await api_client.post(
            "/api/v1/portal/login",
            json={"curp": CURP, "pin": pin},
        )
        assert portal_login.status_code == 200
        portal_token = portal_login.json()["access_token"]
        portal_headers = {"Authorization": f"Bearer {portal_token}"}

        # 5. Cliente consulta su progreso en /api/v1/portal/me
        me_res = await api_client.get("/api/v1/portal/me", headers=portal_headers)
        assert me_res.status_code == 200
        overview = me_res.json()
        assert overview["client_name"] == "Maria Lopez"
        assert overview["active_loans_count"] == 1
        assert overview["total_paid"] == "1500.00"
        assert overview["total_remaining"] == "13500.00"

        loan_summary = overview["loans"][0]
        assert loan_summary["progress_percent"] == "10.00"
        assert loan_summary["paid_installments_count"] == 1
        assert loan_summary["next_installment"]["number"] == 2
        assert len(loan_summary["payments"]) == 1

        # 6. El token del portal NUNCA puede usarse en endpoints de empleados
        forbidden_staff = await api_client.get(
            "/api/v1/clients", headers=portal_headers
        )
        assert forbidden_staff.status_code == 401

    async def test_rejects_wrong_pin(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client, admin_headers = await _setup_scenario(db_session)
        await api_client.post(
            f"/api/v1/clients/{client.id}/portal-pin",
            headers=admin_headers,
            json={"pin": "123456"},
        )

        wrong = await api_client.post(
            "/api/v1/portal/login",
            json={"curp": CURP, "pin": "999999"},
        )
        assert wrong.status_code == 401
