"""Pruebas de integracion de prestamos."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.client import Client
from app.models.loan import Installment, Loan
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services import loan_service

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
CURP = "LOPJ850312MDFZRN07"
START = "2026-11-02"

VALID_LOAN = {
    "principal": 10000,
    "interest_rate": 0.05,
    "rate_period": "semanal",
    "scheme": "simple",
    "term_periods": 12,
    "start_date": START,
}


async def _setup(
    session: AsyncSession,
    *,
    email: str = "admin@test.mx",
    slug: str = "test",
    client_status: str = "activo",
    grace_days: int = 5,
    late_fee_rate: str = "0.1000",
) -> tuple[Tenant, User, Client]:
    """Crea tenant, usuario, configuracion y un cliente."""
    tenant = Tenant(name="Financiera Test", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Admin",
        email=email,
        password_hash=hash_password(PASSWORD),
        role="admin",
    )
    session.add(user)

    session.add(
        SystemSetting(
            tenant_id=tenant.id,
            default_late_fee_rate=Decimal(late_fee_rate),
            default_scheme="simple",
            grace_days=grace_days,
        )
    )

    client = Client(
        tenant_id=tenant.id,
        full_name="Maria Lopez",
        curp=CURP,
        phone="8711234567",
        address="Calle 1, Centro",
        zone="Centro",
        status=client_status,
        birth_date=date(1985, 3, 12),
    )
    session.add(client)
    await session.commit()
    return tenant, user, client


async def _headers(client: AsyncClient, email: str = "admin@test.mx") -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestCreateLoan:
    """POST /api/v1/loans."""

    async def test_creates_loan_with_schedule(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "activo"
        assert body["principal"] == "10000.00"
        assert body["total_interest"] == "6000.00"
        assert body["total_amount"] == "16000.00"
        assert len(body["installments"]) == 12
        assert body["installments"][0]["status"] == "pendiente"

    async def test_freezes_totals(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)

        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )
        loan_id = created.json()["id"]

        # Cambiar la configuracion global no altera el prestamo (RN-06).
        setting = await db_session.scalar(select(SystemSetting))
        assert setting is not None
        setting.default_late_fee_rate = Decimal("0.5000")
        setting.grace_days = 30
        await db_session.commit()

        detail = await api_client.get(f"/api/v1/loans/{loan_id}", headers=headers)

        assert detail.json()["total_interest"] == "6000.00"
        assert detail.json()["late_fee_rate"] == "0.1000"
        assert detail.json()["grace_days"] == 5

    async def test_uses_tenant_settings_as_defaults(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-22: si no se envia tasa, se toma la global."""
        await _setup(db_session, grace_days=7, late_fee_rate="0.1500")
        client = await db_session.scalar(select(Client))
        assert client is not None
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        assert response.json()["late_fee_rate"] == "0.1500"
        assert response.json()["grace_days"] == 7

    async def test_explicit_settings_win(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session, grace_days=5, late_fee_rate="0.1000")
        client = await db_session.scalar(select(Client))
        assert client is not None
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={
                **VALID_LOAN,
                "client_id": str(client.id),
                "late_fee_rate": 0.20,
                "grace_days": 15,
            },
            headers=headers,
        )

        assert response.json()["late_fee_rate"] == "0.2000"
        assert response.json()["grace_days"] == 15

    async def test_generates_correct_due_dates(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )
        body = response.json()

        assert body["first_due_date"] == "2026-11-09"
        assert body["end_date"] == "2027-01-25"
        assert body["installments"][0]["due_date"] == "2026-11-09"

    async def test_rejects_inactive_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-15: no se presta a un cliente desactivado."""
        _, _, client = await _setup(db_session, client_status="inactivo")
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        assert response.status_code == 409
        assert "desactivado" in response.json()["detail"]

    async def test_rejects_unknown_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(uuid4())},
            headers=headers,
        )

        assert response.status_code == 404

    async def test_rejects_client_of_other_tenant(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RNF-08: no se puede prestar a un cliente de otra financiera."""
        _, _, foreign_client = await _setup(db_session, email="a@test.mx", slug="a")

        tenant_b = Tenant(name="B", slug="b")
        db_session.add(tenant_b)
        await db_session.flush()
        db_session.add(
            User(
                tenant_id=tenant_b.id,
                full_name="B",
                email="b@test.mx",
                password_hash=hash_password(PASSWORD),
                role="admin",
            )
        )
        await db_session.commit()
        headers = await _headers(api_client, "b@test.mx")

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(foreign_client.id)},
            headers=headers,
        )

        assert response.status_code == 404

    async def test_blocks_client_with_severe_overdue(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-16: bloquea si hay cuotas vencidas de mas de 90 dias."""
        tenant, user, client = await _setup(db_session)

        old_loan = Loan(
            tenant_id=tenant.id,
            client_id=client.id,
            lender_id=user.id,
            principal=Decimal("1000.00"),
            interest_rate=Decimal("0.0500"),
            rate_period="semanal",
            scheme="simple",
            term_periods=4,
            start_date=date.today() - timedelta(days=200),
            first_due_date=date.today() - timedelta(days=193),
            end_date=date.today() - timedelta(days=172),
            total_interest=Decimal("200.00"),
            total_amount=Decimal("1200.00"),
            late_fee_rate=Decimal("0.1000"),
            grace_days=0,
            status="vencido",
        )
        db_session.add(old_loan)
        await db_session.flush()
        db_session.add(
            Installment(
                loan_id=old_loan.id,
                number=1,
                due_date=date.today() - timedelta(days=193),
                amount=Decimal("300.00"),
                principal_part=Decimal("250.00"),
                interest_part=Decimal("50.00"),
                status="vencida",
            )
        )
        await db_session.commit()
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        assert response.status_code == 409
        assert "90 dias" in response.json()["detail"]

    async def test_allows_client_with_recent_overdue(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Un atraso menor a 90 dias no bloquea."""
        tenant, user, client = await _setup(db_session)

        recent_loan = Loan(
            tenant_id=tenant.id,
            client_id=client.id,
            lender_id=user.id,
            principal=Decimal("1000.00"),
            interest_rate=Decimal("0.0500"),
            rate_period="semanal",
            scheme="simple",
            term_periods=4,
            start_date=date.today() - timedelta(days=20),
            first_due_date=date.today() - timedelta(days=13),
            end_date=date.today() + timedelta(days=8),
            total_interest=Decimal("200.00"),
            total_amount=Decimal("1200.00"),
            late_fee_rate=Decimal("0.1000"),
            grace_days=0,
            status="vencido",
        )
        db_session.add(recent_loan)
        await db_session.flush()
        db_session.add(
            Installment(
                loan_id=recent_loan.id,
                number=1,
                due_date=date.today() - timedelta(days=13),
                amount=Decimal("300.00"),
                principal_part=Decimal("250.00"),
                interest_part=Decimal("50.00"),
                status="vencida",
            )
        )
        await db_session.commit()
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        assert response.status_code == 201

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/loans", json={**VALID_LOAN, "client_id": str(uuid4())}
        )
        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("scheme", "expected_interest", "expected_count"),
        [
            ("simple", "6000.00", 12),
            ("saldo_insoluto", "3250.00", 12),
            ("cuota_fija", "3539.00", 12),
        ],
    )
    async def test_all_schemes(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        scheme: str,
        expected_interest: str,
        expected_count: int,
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/loans",
            json={
                "principal": 10000,
                "interest_rate": 0.05,
                "rate_period": "semanal",
                "scheme": scheme,
                "term_periods": 12,
                "start_date": START,
                "client_id": str(client.id),
            },
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["total_interest"] == expected_interest
        assert len(body["installments"]) == expected_count

    async def test_principal_sums_to_total(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """La suma de capital de las cuotas debe ser el monto prestado (RN-03)."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)

        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )
        installments = created.json()["installments"]

        total = sum(Decimal(row["principal_part"]) for row in installments)
        assert total == Decimal("10000.00")


class TestListLoans:
    """GET /api/v1/loans."""

    async def test_empty_list(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get("/api/v1/loans", headers=headers)

        assert response.status_code == 200
        assert response.json()["total"] == 0

    async def test_lists_created_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        response = await api_client.get("/api/v1/loans", headers=headers)

        assert response.json()["total"] == 1

    async def test_filters_by_status(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        activos = await api_client.get("/api/v1/loans?status=activo", headers=headers)
        pagados = await api_client.get("/api/v1/loans?status=pagado", headers=headers)

        assert activos.json()["total"] == 1
        assert pagados.json()["total"] == 0

    async def test_filters_by_client(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        matching = await api_client.get(
            f"/api/v1/loans?client_id={client.id}", headers=headers
        )
        other = await api_client.get(f"/api/v1/loans?client_id={uuid4()}", headers=headers)

        assert matching.json()["total"] == 1
        assert other.json()["total"] == 0

    async def test_does_not_leak_other_tenants(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client_a = await _setup(db_session, email="a@test.mx", slug="a")
        headers_a = await _headers(api_client, "a@test.mx")
        await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client_a.id)},
            headers=headers_a,
        )

        tenant_b = Tenant(name="B", slug="b")
        db_session.add(tenant_b)
        await db_session.flush()
        db_session.add(
            User(
                tenant_id=tenant_b.id,
                full_name="B",
                email="b@test.mx",
                password_hash=hash_password(PASSWORD),
                role="admin",
            )
        )
        await db_session.commit()
        headers_b = await _headers(api_client, "b@test.mx")

        response = await api_client.get("/api/v1/loans", headers=headers_b)
        assert response.json()["total"] == 0


class TestGetLoan:
    """GET /api/v1/loans/{id} y /schedule."""

    async def test_returns_detail(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        response = await api_client.get(f"/api/v1/loans/{created.json()['id']}", headers=headers)

        assert response.status_code == 200
        assert len(response.json()["installments"]) == 12

    async def test_returns_404_for_unknown(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get(f"/api/v1/loans/{uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_schedule_recalculates_balances(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        response = await api_client.get(
            f"/api/v1/loans/{created.json()['id']}/schedule", headers=headers
        )

        assert response.status_code == 200
        schedule = response.json()
        assert len(schedule) == 12
        assert schedule[0]["balance"] == "9166.67"
        assert schedule[-1]["balance"] == "0.00"

    async def test_schedule_404_for_unknown(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get(f"/api/v1/loans/{uuid4()}/schedule", headers=headers)
        assert response.status_code == 404


class TestCancelLoan:
    """POST /api/v1/loans/{id}/cancel."""

    async def test_cancels_active_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/loans/{created.json()['id']}/cancel",
            json={"reason": "El cliente desistio del credito."},
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelado"

    async def test_cannot_cancel_twice(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )
        loan_id = created.json()["id"]

        await api_client.post(
            f"/api/v1/loans/{loan_id}/cancel",
            json={"reason": "Primera cancelacion."},
            headers=headers,
        )
        second = await api_client.post(
            f"/api/v1/loans/{loan_id}/cancel",
            json={"reason": "Segunda cancelacion."},
            headers=headers,
        )

        assert second.status_code == 409

    async def test_requires_reason(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        created = await api_client.post(
            "/api/v1/loans",
            json={**VALID_LOAN, "client_id": str(client.id)},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/loans/{created.json()['id']}/cancel",
            json={"reason": "mal"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_cancel_unknown_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            f"/api/v1/loans/{uuid4()}/cancel",
            json={"reason": "Motivo suficientemente largo."},
            headers=headers,
        )
        assert response.status_code == 404


class TestLoanServiceRules:
    """Reglas verificadas directamente en el servicio."""

    async def test_pending_amount_includes_late_fee(self, db_session: AsyncSession) -> None:
        _, _, client = await _setup(db_session)

        installment = Installment(
            loan_id=uuid4(),
            number=1,
            due_date=date(2026, 11, 9),
            amount=Decimal("1333.33"),
            principal_part=Decimal("833.33"),
            interest_part=Decimal("500.00"),
            late_fee=Decimal("16.67"),
            paid_amount=Decimal("400.00"),
        )

        assert installment.pending_amount == Decimal("950.00")

    async def test_first_installment_amount_matches_schedule(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user, client = await _setup(db_session)
        loan = await loan_service.create_loan(
            db_session,
            tenant.id,
            user.id,
            __import__("app.schemas.loan", fromlist=["LoanCreate"]).LoanCreate(
                client_id=client.id,
                principal=10000,
                interest_rate=0.05,
                rate_period="semanal",
                scheme="simple",
                term_periods=12,
                start_date=date(2026, 11, 2),
            ),
        )

        amount = await loan_service.first_installment_amount(loan)

        assert amount == Decimal("1333.33")
        assert loan.installments[0].amount == amount

    async def test_loan_repr_hides_amounts(self) -> None:
        loan = Loan(principal=Decimal("50000.00"), status="activo")
        text = repr(loan)

        assert "50000" not in text
        assert "activo" in text

    async def test_installment_repr(self) -> None:
        installment = Installment(number=3, status="pendiente")
        text = repr(installment)

        assert "3" in text
        assert "pendiente" in text
