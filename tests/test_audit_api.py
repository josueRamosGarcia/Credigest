"""Pruebas de los endpoints de auditoria y de su integracion.

Verifica que las operaciones reales dejen rastro: crear cliente, prestamo,
pago, cancelaciones y cambios de estado.
"""

from datetime import date
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services import audit_service
from tests.test_audit_helpers import PASSWORD, make_tenant_and_user
from tests.test_payments_api import _create_loan, _setup

pytestmark = pytest.mark.db


async def _headers(client: AsyncClient, email: str = "admin@test.mx") -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera."""
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestAuditEndpoints:
    """GET /api/v1/audit y su exportacion."""

    async def test_lists_entries(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        for action in ("client.create", "loan.create"):
            await audit_service.record(
                db_session,
                tenant_id=tenant.id,
                user_id=user.id,
                action=action,
                entity=action.split(".")[0],
            )
        await db_session.commit()

        headers = await _headers(api_client, "audit@test.mx")
        response = await api_client.get("/api/v1/audit", headers=headers)

        assert response.status_code == 200
        assert response.json()["total"] == 2

    async def test_returns_empty_for_new_tenant(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await make_tenant_and_user(db_session)
        headers = await _headers(api_client, "audit@test.mx")

        response = await api_client.get("/api/v1/audit", headers=headers)

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_filters_by_action(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.create",
            entity="client",
        )
        await audit_service.record(
            db_session, tenant_id=tenant.id, user_id=user.id, action="loan.create", entity="loan"
        )
        await db_session.commit()

        headers = await _headers(api_client, "audit@test.mx")
        response = await api_client.get("/api/v1/audit?action=loan.create", headers=headers)

        assert response.json()["total"] == 1
        assert response.json()["items"][0]["action"] == "loan.create"

    async def test_filters_by_entity(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.create",
            entity="client",
        )
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="payment.create",
            entity="payment",
        )
        await db_session.commit()

        headers = await _headers(api_client, "audit@test.mx")
        response = await api_client.get("/api/v1/audit?entity=payment", headers=headers)

        assert response.json()["total"] == 1

    async def test_filters_by_date_range(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.create",
            entity="client",
        )
        await db_session.commit()

        today = date.today().isoformat()
        headers = await _headers(api_client, "audit@test.mx")

        inside = await api_client.get(
            f"/api/v1/audit?from_date={today}&to_date={today}", headers=headers
        )
        outside = await api_client.get(
            "/api/v1/audit?from_date=2020-01-01&to_date=2020-01-02", headers=headers
        )

        assert inside.json()["total"] == 1
        assert outside.json()["total"] == 0

    async def test_paginates(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        for index in range(5):
            await audit_service.record(
                db_session,
                tenant_id=tenant.id,
                user_id=user.id,
                action=f"test.action{index}",
                entity="test",
            )
        await db_session.commit()

        headers = await _headers(api_client, "audit@test.mx")
        response = await api_client.get("/api/v1/audit?page=1&page_size=2", headers=headers)

        assert response.json()["total"] == 5
        assert len(response.json()["items"]) == 2

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/audit")
        assert response.status_code == 401

    async def test_does_not_leak_other_tenants(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant_a, user_a = await make_tenant_and_user(db_session, email="aa@test.mx", slug="aa")
        await make_tenant_and_user(db_session, email="bb@test.mx", slug="bb")

        await audit_service.record(
            db_session,
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            action="client.create",
            entity="client",
        )
        await db_session.commit()

        headers = await _headers(api_client, "bb@test.mx")
        response = await api_client.get("/api/v1/audit", headers=headers)

        assert response.json()["total"] == 0

    async def test_exports_csv(self, api_client: AsyncClient, db_session: AsyncSession) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="client.create",
            entity="client",
            after={"full_name": "Maria"},
        )
        await db_session.commit()

        headers = await _headers(api_client, "audit@test.mx")
        response = await api_client.get("/api/v1/audit/export.csv", headers=headers)

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        body = response.text
        assert "id,fecha,usuario,accion,entidad" in body
        assert "client.create" in body

    async def test_csv_redacts_sensitive_data(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await make_tenant_and_user(db_session)
        await audit_service.record(
            db_session,
            tenant_id=tenant.id,
            user_id=user.id,
            action="user.create",
            entity="user",
            after={"email": "a@b.mx", "password": "super-secreto"},
        )
        await db_session.commit()

        headers = await _headers(api_client, "audit@test.mx")
        response = await api_client.get("/api/v1/audit/export.csv", headers=headers)

        assert "super-secreto" not in response.text
        assert "***" in response.text


class TestAuditIntegration:
    """Las operaciones reales deben dejar rastro."""

    async def test_client_creation_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")

        created = await api_client.post(
            "/api/v1/clients",
            json={
                "full_name": "Juan Garcia Lopez",
                "curp": "GALJ900715HJCMPR06",
                "phone": "8711234567",
                "address": "Av. Juarez 123, Centro",
                "zone": "Centro",
            },
            headers=headers,
        )
        assert created.status_code == 201

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "client.create"))
        assert entry is not None
        assert entry.after is not None
        assert entry.after["full_name"] == "Juan Garcia Lopez"

    async def test_client_curp_is_redacted_in_audit(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """La CURP es dato sensible y no debe quedar en la bitacora."""
        await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")

        await api_client.post(
            "/api/v1/clients",
            json={
                "full_name": "Juan Garcia Lopez",
                "curp": "GALJ900715HJCMPR06",
                "phone": "8711234567",
                "address": "Av. Juarez 123, Centro",
            },
            headers=headers,
        )

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "client.create"))
        assert entry is not None
        assert entry.after is not None
        assert entry.after["curp"] == "***"

    async def test_client_update_audits_only_changes(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")
        created = await api_client.post(
            "/api/v1/clients",
            json={
                "full_name": "Juan Garcia Lopez",
                "curp": "GALJ900715HJCMPR06",
                "phone": "8711234567",
                "address": "Av. Juarez 123, Centro",
                "zone": "Centro",
            },
            headers=headers,
        )

        await api_client.patch(
            f"/api/v1/clients/{created.json()['id']}",
            json={"zone": "Norte"},
            headers=headers,
        )

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "client.update"))
        assert entry is not None
        assert entry.before == {"zone": "Centro"}
        assert entry.after == {"zone": "Norte"}

    async def test_status_change_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")
        created = await api_client.post(
            "/api/v1/clients",
            json={
                "full_name": "Juan Garcia Lopez",
                "curp": "GALJ900715HJCMPR06",
                "phone": "8711234567",
                "address": "Av. Juarez 123, Centro",
            },
            headers=headers,
        )

        await api_client.patch(
            f"/api/v1/clients/{created.json()['id']}/status",
            json={"status": "inactivo"},
            headers=headers,
        )

        entry = await db_session.scalar(
            select(AuditLog).where(AuditLog.action == "client.status_change")
        )
        assert entry is not None
        assert entry.before == {"status": "activo"}
        assert entry.after == {"status": "inactivo"}

    async def test_loan_creation_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")
        loan = await _create_loan(api_client, headers, client.id)

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "loan.create"))
        assert entry is not None
        assert entry.entity_id == UUID(loan["id"])
        assert entry.after is not None
        assert entry.after["principal"] == "10000.00"

    async def test_loan_cancellation_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")
        loan = await _create_loan(api_client, headers, client.id)

        await api_client.post(
            f"/api/v1/loans/{loan['id']}/cancel",
            json={"reason": "Cliente desistio del credito."},
            headers=headers,
        )

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "loan.cancel"))
        assert entry is not None
        assert entry.before == {"status": "activo"}
        assert entry.after is not None
        assert entry.after["status"] == "cancelado"

    async def test_payment_creation_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")
        loan = await _create_loan(api_client, headers, client.id)

        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 400, "method": "efectivo"},
            headers=headers,
        )

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "payment.create"))
        assert entry is not None
        assert entry.after is not None
        assert entry.after["covered_interest"] == "400.00"

    async def test_payment_cancellation_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")
        loan = await _create_loan(api_client, headers, client.id)
        payment = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 400, "method": "efectivo"},
            headers=headers,
        )

        await api_client.post(
            f"/api/v1/payments/{payment.json()['payment']['id']}/cancel",
            json={"reason": "Se registro con el monto equivocado."},
            headers=headers,
        )

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "payment.cancel"))
        assert entry is not None
        assert entry.after is not None
        assert entry.after["status"] == "anulado"

    async def test_audit_records_ip_and_user_agent(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client, "admin@test.mx")

        await api_client.post(
            "/api/v1/clients",
            json={
                "full_name": "Juan Garcia Lopez",
                "curp": "GALJ900715HJCMPR06",
                "phone": "8711234567",
                "address": "Av. Juarez 123, Centro",
            },
            headers=headers,
        )

        entry = await db_session.scalar(select(AuditLog).where(AuditLog.action == "client.create"))
        assert entry is not None
        assert entry.ip_address is not None
        assert entry.user_agent is not None
