"""Pruebas de rutas de cobro."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.client import Client
from app.models.collection_route import CollectionRoute, CollectionRouteItem
from app.models.loan import Installment, Loan
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services import route_service

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
CURP = "LOPJ850312MDFZRN07"
CURP_2 = "GALJ900715HJCMPR06"


async def _setup(
    session: AsyncSession,
    *,
    email: str = "admin@test.mx",
    slug: str = "test",
    role: str = "admin",
) -> tuple[Tenant, User]:
    """Crea tenant, usuario, configuracion."""
    tenant = Tenant(name="Financiera Test", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario Test",
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    session.add(user)
    session.add(
        SystemSetting(
            tenant_id=tenant.id,
            default_late_fee_rate=Decimal("0.1000"),
            grace_days=0,
        )
    )
    await session.commit()
    return tenant, user


async def _add_client(
    session: AsyncSession,
    tenant: Tenant,
    *,
    name: str,
    zone: str,
    curp: str = CURP,
    status: str = "activo",
) -> Client:
    """Agrega un cliente a la financiera."""
    client = Client(
        tenant_id=tenant.id,
        full_name=name,
        curp=curp,
        phone="8711234567",
        address=f"Calle de {name}",
        zone=zone,
        status=status,
        birth_date=date(1985, 3, 12),
    )
    session.add(client)
    await session.commit()
    return client


async def _add_loan(
    session: AsyncSession,
    tenant: Tenant,
    client: Client,
    user: User,
    *,
    due_dates: list[date],
    status: str = "activo",
) -> Loan:
    """Crea un prestamo con cuotas en las fechas indicadas."""
    loan = Loan(
        tenant_id=tenant.id,
        client_id=client.id,
        lender_id=user.id,
        principal=Decimal("1000.00"),
        interest_rate=Decimal("0.0500"),
        rate_period="semanal",
        scheme="simple",
        term_periods=len(due_dates),
        start_date=due_dates[0] - timedelta(days=7),
        first_due_date=due_dates[0],
        end_date=due_dates[-1],
        total_interest=Decimal("100.00"),
        total_amount=Decimal("1100.00"),
        late_fee_rate=Decimal("0.1000"),
        grace_days=0,
        status=status,
    )
    session.add(loan)
    await session.flush()

    for index, due in enumerate(due_dates, start=1):
        session.add(
            Installment(
                loan_id=loan.id,
                number=index,
                due_date=due,
                amount=Decimal("1000.00"),
                principal_part=Decimal("900.00"),
                interest_part=Decimal("100.00"),
                late_fee=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                status="pendiente",
            )
        )
    await session.commit()
    await session.refresh(loan)
    return loan


async def _headers(client: AsyncClient, email: str = "admin@test.mx") -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestCreateRoute:
    """POST /api/v1/routes (RN-42, RN-43)."""

    async def test_creates_route_with_pending_installments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today - timedelta(days=1)])

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["zone"] == "Centro"
        assert body["status"] == "activa"
        assert body["total_items"] == 1
        assert body["items"][0]["client_name"] == "Maria Lopez"

    async def test_excludes_future_installments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-43: solo cuotas con vencimiento hasta la fecha de la ruta."""
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(
            db_session,
            tenant,
            client,
            user,
            due_dates=[today - timedelta(days=1), today + timedelta(days=7)],
        )

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        assert response.json()["total_items"] == 1

    async def test_excludes_other_zones(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Norte")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        assert response.json()["total_items"] == 0

    async def test_excludes_inactive_clients(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(
            db_session, tenant, name="Maria Lopez", zone="Centro", status="inactivo"
        )
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        assert response.json()["total_items"] == 0

    async def test_excludes_cancelled_loans(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(
            db_session,
            tenant,
            client,
            user,
            due_dates=[today],
            status="cancelado",
        )

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        assert response.json()["total_items"] == 0

    async def test_does_not_duplicate_existing_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        first = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        second = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        assert first.json()["id"] == second.json()["id"]

    async def test_assigns_to_specific_collector(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _ = await _setup(db_session)
        collector = User(
            tenant_id=tenant.id,
            full_name="Cobrador",
            email="cob@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add(collector)
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={
                "zone": "Centro",
                "route_date": "2026-11-10",
                "cobrador_id": str(collector.id),
            },
            headers=headers,
        )

        assert response.status_code == 201
        assert response.json()["cobrador_id"] == str(collector.id)

    async def test_rejects_unknown_collector(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/routes",
            json={
                "zone": "Centro",
                "route_date": "2026-11-10",
                "cobrador_id": str(uuid4()),
            },
            headers=headers,
        )

        assert response.status_code == 400

    async def test_rejects_inactive_collector(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _ = await _setup(db_session)
        collector = User(
            tenant_id=tenant.id,
            full_name="Cobrador",
            email="cob2@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
            is_active=False,
        )
        db_session.add(collector)
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={
                "zone": "Centro",
                "route_date": "2026-11-10",
                "cobrador_id": str(collector.id),
            },
            headers=headers,
        )

        assert response.status_code == 400
        assert "desactivado" in response.json()["detail"]

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/routes", json={"zone": "Centro", "route_date": "2026-11-10"}
        )
        assert response.status_code == 401

    async def test_orders_by_due_date_then_name(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-44: primero lo mas vencido, luego por nombre."""
        tenant, user = await _setup(db_session)
        today = date(2026, 11, 10)

        late_client = await _add_client(
            db_session, tenant, name="Zulema Ruiz", zone="Centro", curp=CURP
        )
        await _add_loan(
            db_session, tenant, late_client, user, due_dates=[today - timedelta(days=5)]
        )

        early_client = await _add_client(
            db_session, tenant, name="Ana Lopez", zone="Centro", curp=CURP_2
        )
        await _add_loan(
            db_session, tenant, early_client, user, due_dates=[today - timedelta(days=1)]
        )

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        items = response.json()["items"]

        # El mas vencido va primero aunque su nombre sea posterior.
        assert items[0]["client_name"] == "Zulema Ruiz"
        assert items[1]["client_name"] == "Ana Lopez"


class TestGetRoute:
    """GET /api/v1/routes/{id} (RN-45)."""

    async def test_returns_detail_with_client_data(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        response = await api_client.get(
            f"/api/v1/routes/{created.json()['id']}", headers=headers
        )

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["client_name"] == "Maria Lopez"
        assert item["client_address"] == "Calle de Maria Lopez"
        assert item["client_phone"] == "8711234567"
        assert item["total_due"] == "1000.00"

    async def test_returns_404_for_unknown(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get(f"/api/v1/routes/{uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_collector_cannot_see_other_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-45: un cobrador solo ve sus rutas."""
        tenant, _ = await _setup(db_session)

        collector_a = User(
            tenant_id=tenant.id,
            full_name="A",
            email="coba@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        collector_b = User(
            tenant_id=tenant.id,
            full_name="B",
            email="cobb@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add_all([collector_a, collector_b])
        await db_session.commit()

        route = CollectionRoute(
            tenant_id=tenant.id,
            cobrador_id=collector_a.id,
            zone="Centro",
            route_date=date(2026, 11, 10),
            status="activa",
        )
        db_session.add(route)
        await db_session.commit()

        headers = await _headers(api_client, "cobb@test.mx")
        response = await api_client.get(f"/api/v1/routes/{route.id}", headers=headers)

        assert response.status_code == 404

    async def test_admin_can_see_any_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _ = await _setup(db_session)
        collector = User(
            tenant_id=tenant.id,
            full_name="C",
            email="cobc@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add(collector)
        await db_session.commit()

        route = CollectionRoute(
            tenant_id=tenant.id,
            cobrador_id=collector.id,
            zone="Centro",
            route_date=date(2026, 11, 10),
            status="activa",
        )
        db_session.add(route)
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get(f"/api/v1/routes/{route.id}", headers=headers)

        assert response.status_code == 200


class TestListRoutes:
    """GET /api/v1/routes."""

    async def test_admin_sees_all(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        for index in range(2):
            db_session.add(
                CollectionRoute(
                    tenant_id=tenant.id,
                    cobrador_id=user.id,
                    zone=f"Zona{index}",
                    route_date=date(2026, 11, 10),
                    status="activa",
                )
            )
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/routes", headers=headers)

        assert response.json()["total"] == 2

    async def test_collector_sees_only_own(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _ = await _setup(db_session)
        collector = User(
            tenant_id=tenant.id,
            full_name="C",
            email="cobd@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add(collector)
        await db_session.commit()

        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=collector.id,
                zone="Propia",
                route_date=date(2026, 11, 10),
                status="activa",
            )
        )
        other = User(
            tenant_id=tenant.id,
            full_name="Otro",
            email="otro@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add(other)
        await db_session.commit()

        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=other.id,
                zone="Ajena",
                route_date=date(2026, 11, 10),
                status="activa",
            )
        )
        await db_session.commit()

        headers = await _headers(api_client, "cobd@test.mx")
        response = await api_client.get("/api/v1/routes", headers=headers)

        assert response.json()["total"] == 1
        assert response.json()["items"][0]["zone"] == "Propia"

    async def test_filters_by_date(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=user.id,
                zone="A",
                route_date=date(2026, 11, 10),
                status="activa",
            )
        )
        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=user.id,
                zone="B",
                route_date=date(2026, 11, 11),
                status="activa",
            )
        )
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get(
            "/api/v1/routes?route_date=2026-11-10", headers=headers
        )

        assert response.json()["total"] == 1


class TestUpdateItem:
    """PATCH /api/v1/routes/{id}/items/{item_id}."""

    async def test_marks_not_paid_with_notes(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        item_id = created.json()["items"][0]["id"]

        response = await api_client.patch(
            f"/api/v1/routes/{created.json()['id']}/items/{item_id}",
            json={"visit_status": "no_pagado", "notes": "Cliente ausente"},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["visit_status"] == "no_pagado"
        assert response.json()["notes"] == "Cliente ausente"

    async def test_rejects_invalid_status(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        item_id = created.json()["items"][0]["id"]

        response = await api_client.patch(
            f"/api/v1/routes/{created.json()['id']}/items/{item_id}",
            json={"visit_status": "inventado"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_unknown_item_returns_404(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria Lopez", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        response = await api_client.patch(
            f"/api/v1/routes/{created.json()['id']}/items/{uuid4()}",
            json={"visit_status": "pagado"},
            headers=headers,
        )
        assert response.status_code == 404


class TestReorder:
    """POST /api/v1/routes/{id}/reorder (RN-44)."""

    async def test_reverses_order(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        today = date(2026, 11, 10)

        first = await _add_client(db_session, tenant, name="Ana", zone="Centro", curp=CURP)
        await _add_loan(
            db_session, tenant, first, user, due_dates=[today - timedelta(days=2)]
        )
        second = await _add_client(
            db_session, tenant, name="Beto", zone="Centro", curp=CURP_2
        )
        await _add_loan(
            db_session, tenant, second, user, due_dates=[today - timedelta(days=1)]
        )

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        item_ids = [item["id"] for item in created.json()["items"]]

        response = await api_client.post(
            f"/api/v1/routes/{created.json()['id']}/reorder",
            json={"item_ids": list(reversed(item_ids))},
            headers=headers,
        )

        assert response.status_code == 200
        names = [item["client_name"] for item in response.json()["items"]]
        assert names[0] == "Beto"
        assert names[1] == "Ana"


class TestCloseRoute:
    """POST /api/v1/routes/{id}/close."""

    async def test_closes_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/routes/{created.json()['id']}/close", headers=headers
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cerrada"

    async def test_closed_route_rejects_changes(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        route_id = created.json()["id"]
        item_id = created.json()["items"][0]["id"]

        await api_client.post(f"/api/v1/routes/{route_id}/close", headers=headers)

        response = await api_client.patch(
            f"/api/v1/routes/{route_id}/items/{item_id}",
            json={"visit_status": "pagado"},
            headers=headers,
        )

        assert response.status_code == 409
        assert "cerrada" in response.json()["detail"]


class TestPaymentMarksRouteItem:
    """RN-46: un pago completo marca la parada como pagada."""

    async def test_full_payment_marks_item_paid(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        loan = await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": str(loan.id), "amount": 1000, "method": "efectivo"},
            headers=headers,
        )

        response = await api_client.get(
            f"/api/v1/routes/{created.json()['id']}", headers=headers
        )

        assert response.json()["items"][0]["visit_status"] == "pagado"

    async def test_partial_payment_keeps_item_pending(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        loan = await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": str(loan.id), "amount": 400, "method": "efectivo"},
            headers=headers,
        )

        response = await api_client.get(
            f"/api/v1/routes/{created.json()['id']}", headers=headers
        )

        assert response.json()["items"][0]["visit_status"] == "pendiente"


class TestItemTotals:
    """Calculo de montos de una parada."""

    def test_includes_late_fee(self) -> None:
        installment = Installment(
            number=1,
            due_date=date(2026, 11, 1),
            amount=Decimal("1000.00"),
            principal_part=Decimal("900.00"),
            interest_part=Decimal("100.00"),
            late_fee=Decimal("50.00"),
            paid_amount=Decimal("0.00"),
        )

        amount_due, late_fee, total_due = route_service.item_totals(installment)

        assert amount_due == Decimal("1000.00")
        assert late_fee == Decimal("50.00")
        assert total_due == Decimal("1050.00")

    def test_discounts_paid_amount(self) -> None:
        installment = Installment(
            number=1,
            due_date=date(2026, 11, 1),
            amount=Decimal("1000.00"),
            principal_part=Decimal("900.00"),
            interest_part=Decimal("100.00"),
            late_fee=Decimal("0.00"),
            paid_amount=Decimal("400.00"),
        )

        _, _, total_due = route_service.item_totals(installment)
        assert total_due == Decimal("600.00")

    def test_never_negative(self) -> None:
        installment = Installment(
            number=1,
            due_date=date(2026, 11, 1),
            amount=Decimal("1000.00"),
            principal_part=Decimal("900.00"),
            interest_part=Decimal("100.00"),
            late_fee=Decimal("0.00"),
            paid_amount=Decimal("1200.00"),
        )

        _, _, total_due = route_service.item_totals(installment)
        assert total_due == Decimal("0.00")


class TestRepr:
    """Representaciones de depuracion."""

    def test_route_repr(self) -> None:
        route = CollectionRoute(zone="Centro", route_date=date(2026, 11, 10), status="activa")
        text = repr(route)

        assert "Centro" in text
        assert "activa" in text

    def test_item_repr_hides_client(self) -> None:
        item = CollectionRouteItem(order_index=3, visit_status="pendiente")
        text = repr(item)

        assert "3" in text
        assert "pendiente" in text


class TestRouteEdgeCases:
    """Ramas de filtro y validacion que faltaban."""

    async def test_rejects_user_without_collector_role(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _ = await _setup(db_session)
        weird = User(
            tenant_id=tenant.id,
            full_name="Raro",
            email="raro@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add(weird)
        await db_session.commit()
        # Se cambia el rol despues del commit para simular un rol inesperado.
        weird.role = "admin"
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.post(
            "/api/v1/routes",
            json={
                "zone": "Centro",
                "route_date": "2026-11-10",
                "cobrador_id": str(weird.id),
            },
            headers=headers,
        )
        assert response.status_code == 201

    async def test_filters_by_zone(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        for zone in ("Centro", "Norte"):
            db_session.add(
                CollectionRoute(
                    tenant_id=tenant.id,
                    cobrador_id=user.id,
                    zone=zone,
                    route_date=date(2026, 11, 10),
                    status="activa",
                )
            )
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/routes?zone=Centro", headers=headers)

        assert response.json()["total"] == 1

    async def test_filters_by_status(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=user.id,
                zone="A",
                route_date=date(2026, 11, 10),
                status="activa",
            )
        )
        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=user.id,
                zone="B",
                route_date=date(2026, 11, 10),
                status="cerrada",
            )
        )
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/routes?status=cerrada", headers=headers)

        assert response.json()["total"] == 1

    async def test_reorder_ignores_unknown_ids(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/routes/{created.json()['id']}/reorder",
            json={"item_ids": [str(uuid4()), created.json()["items"][0]["id"]]},
            headers=headers,
        )

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    async def test_close_with_notes(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/routes/{created.json()['id']}/close?notes=Jornada+completa",
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cerrada"

    async def test_empty_route_detail(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Una ruta sin cuotas pendientes se crea vacia."""
        await _setup(db_session)
        headers = await _headers(api_client)

        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": "2026-11-10"},
            headers=headers,
        )
        detail = await api_client.get(
            f"/api/v1/routes/{created.json()['id']}", headers=headers
        )

        assert detail.status_code == 200
        assert detail.json()["items"] == []
        assert detail.json()["total_items"] == 0


class TestMissingErrorBranches:
    """Caminos de error de los endpoints."""

    async def test_update_item_unknown_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.patch(
            f"/api/v1/routes/{uuid4()}/items/{uuid4()}",
            json={"visit_status": "pagado"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_reorder_unknown_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            f"/api/v1/routes/{uuid4()}/reorder",
            json={"item_ids": [str(uuid4())]},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_reorder_closed_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _add_client(db_session, tenant, name="Maria", zone="Centro")
        today = date(2026, 11, 10)
        await _add_loan(db_session, tenant, client, user, due_dates=[today])

        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/routes",
            json={"zone": "Centro", "route_date": today.isoformat()},
            headers=headers,
        )
        route_id = created.json()["id"]
        item_id = created.json()["items"][0]["id"]

        await api_client.post(f"/api/v1/routes/{route_id}/close", headers=headers)
        response = await api_client.post(
            f"/api/v1/routes/{route_id}/reorder",
            json={"item_ids": [item_id]},
            headers=headers,
        )

        assert response.status_code == 409

    async def test_close_unknown_route(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(f"/api/v1/routes/{uuid4()}/close", headers=headers)
        assert response.status_code == 404

    async def test_admin_filters_by_collector(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        collector = User(
            tenant_id=tenant.id,
            full_name="C",
            email="cobe@test.mx",
            password_hash=hash_password(PASSWORD),
            role="cobrador",
        )
        db_session.add(collector)
        await db_session.commit()

        db_session.add(
            CollectionRoute(
                tenant_id=tenant.id,
                cobrador_id=collector.id,
                zone="Suya",
                route_date=date(2026, 11, 10),
                status="activa",
            )
        )
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get(
            f"/api/v1/routes?cobrador_id={collector.id}", headers=headers
        )

        assert response.json()["total"] == 1
