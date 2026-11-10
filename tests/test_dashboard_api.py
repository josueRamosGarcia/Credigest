"""Pruebas del dashboard financiero.

Cada prueba arma un escenario pequeno y verifica los indicadores a mano.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.client import Client
from app.models.loan import Installment, Loan
from app.models.payment import Payment, PaymentApplication
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User
from app.services import dashboard_service

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
TODAY = date(2026, 11, 15)


async def _setup(
    session: AsyncSession,
    *,
    email: str = "admin@test.mx",
    slug: str = "test",
    role: str = "admin",
) -> tuple[Tenant, User]:
    """Crea tenant, usuario y configuracion."""
    tenant = Tenant(name="Financiera Test", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario",
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


async def _client(session: AsyncSession, tenant: Tenant, name: str = "Cliente") -> Client:
    """Crea un cliente."""
    client = Client(
        tenant_id=tenant.id,
        full_name=name,
        curp="LOPJ850312MDFZRN07",
        phone="8711234567",
        address="Calle 1",
        zone="Centro",
        status="activo",
        birth_date=date(1985, 3, 12),
    )
    session.add(client)
    await session.commit()
    return client


async def _loan(
    session: AsyncSession,
    tenant: Tenant,
    client: Client,
    user: User,
    *,
    principal: str,
    start_date: date,
    status: str = "activo",
    installments: list[tuple[date, str, str, str]] | None = None,
) -> Loan:
    """Crea un prestamo con sus cuotas.

    Args:
        installments: Lista de (vencimiento, monto, capital, interes).
    """
    rows = installments or []
    loan = Loan(
        tenant_id=tenant.id,
        client_id=client.id,
        lender_id=user.id,
        principal=Decimal(principal),
        interest_rate=Decimal("0.0500"),
        rate_period="mensual",
        scheme="simple",
        term_periods=max(1, len(rows)),
        start_date=start_date,
        first_due_date=rows[0][0] if rows else start_date,
        end_date=rows[-1][0] if rows else start_date,
        total_interest=Decimal("0.00"),
        total_amount=Decimal(principal),
        late_fee_rate=Decimal("0.1000"),
        grace_days=0,
        status=status,
    )
    session.add(loan)
    await session.flush()

    for index, (due, amount, capital, interest) in enumerate(rows, start=1):
        session.add(
            Installment(
                loan_id=loan.id,
                number=index,
                due_date=due,
                amount=Decimal(amount),
                principal_part=Decimal(capital),
                interest_part=Decimal(interest),
                late_fee=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                status="pendiente",
            )
        )
    await session.commit()
    await session.refresh(loan)
    return loan


async def _payment(
    session: AsyncSession,
    tenant: Tenant,
    loan: Loan,
    user: User,
    *,
    amount: str,
    applications: list[tuple[str, str]],
    status: str = "aplicado",
    created_at: Any = None,
) -> Payment:
    """Crea un pago con sus aplicaciones."""
    payment = Payment(
        tenant_id=tenant.id,
        loan_id=loan.id,
        folio=f"PAGO-TEST-{amount}",
        amount=Decimal(amount),
        method="efectivo",
        payment_type="completo",
        status=status,
        registered_by=user.id,
    )
    if created_at is not None:
        payment.created_at = created_at

    session.add(payment)
    await session.flush()

    installment = await session.scalar(
        select(Installment).where(Installment.loan_id == loan.id).limit(1)
    )
    assert installment is not None

    for concept, value in applications:
        session.add(
            PaymentApplication(
                payment_id=payment.id,
                installment_id=installment.id,
                concept=concept,
                amount=Decimal(value),
            )
        )
    await session.commit()
    return payment


async def _headers(client: AsyncClient, email: str = "admin@test.mx") -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestSummaryBasic:
    """Indicadores con un escenario simple."""

    async def test_empty_dashboard(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["capital_prestado"] == "0.00"
        assert body["indice_morosidad"] == "0.00"

    async def test_capital_prestado_sums_principal(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        await _loan(
            db_session, tenant, client, user,
            principal="10000", start_date=TODAY - timedelta(days=10),
        )
        await _loan(
            db_session, tenant, client, user,
            principal="5000", start_date=TODAY - timedelta(days=5),
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.json()["capital_prestado"] == "15000.00"

    async def test_excludes_cancelled_loans(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        await _loan(
            db_session, tenant, client, user,
            principal="10000", start_date=TODAY, status="cancelado",
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.json()["capital_prestado"] == "0.00"

    async def test_capital_recuperado_sums_capital_concept(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Solo cuenta la porcion de capital de los pagos (RN-47)."""
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        loan = await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=TODAY,
            installments=[(TODAY, "1100.00", "1000.00", "100.00")],
        )
        await _payment(
            db_session, tenant, loan, user,
            amount="1100.00",
            applications=[("interes", "100.00"), ("capital", "1000.00")],
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.json()["capital_recuperado"] == "1000.00"
        assert response.json()["intereses_generados"] == "100.00"

    async def test_mora_cobrada(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        loan = await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=TODAY,
            installments=[(TODAY, "1100.00", "1000.00", "100.00")],
        )
        await _payment(
            db_session, tenant, loan, user,
            amount="1116.67",
            applications=[("mora", "16.67"), ("interes", "100.00"), ("capital", "1000.00")],
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        body = response.json()
        assert body["mora_cobrada"] == "16.67"
        assert body["utilidad_generada"] == "116.67"

    async def test_excludes_cancelled_payments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-49: los pagos anulados no cuentan."""
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        loan = await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=TODAY,
            installments=[(TODAY, "1100.00", "1000.00", "100.00")],
        )
        await _payment(
            db_session, tenant, loan, user,
            amount="1100.00",
            applications=[("capital", "1000.00")],
            status="anulado",
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.json()["capital_recuperado"] == "0.00"


class TestMorosity:
    """Indice de morosidad (RN-47, RN-50)."""

    async def test_zero_when_nothing_overdue(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=TODAY,
            installments=[(date.today() + timedelta(days=30), "1100.00", "1000.00", "100.00")],
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.json()["indice_morosidad"] == "0.00"

    async def test_percentage_with_two_decimals(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Una cuota vencida de 1,000 sobre 3,000 de cartera es 33.33 %."""
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)

        overdue = date.today() - timedelta(days=10)
        future = date.today() + timedelta(days=30)

        await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=overdue,
            installments=[(overdue, "1000.00", "900.00", "100.00")],
        )
        await _loan(
            db_session, tenant, client, user,
            principal="2000", start_date=future,
            installments=[(future, "2000.00", "1800.00", "200.00")],
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)

        assert response.json()["indice_morosidad"] == "33.33"


class TestAging:
    """Reporte de antiguedad (RN-51)."""

    async def test_buckets_by_installment(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        today = date.today()

        await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=today,
            installments=[
                (today - timedelta(days=10), "1000.00", "900.00", "100.00"),
                (today - timedelta(days=45), "2000.00", "1800.00", "200.00"),
                (today - timedelta(days=100), "3000.00", "2700.00", "300.00"),
                (today + timedelta(days=10), "4000.00", "3600.00", "400.00"),
            ],
        )

        headers = await _headers(api_client)
        response = await api_client.get(f"/api/v1/dashboard/aging?today={today}", headers=headers)

        assert response.status_code == 200
        buckets = {row["label"]: row for row in response.json()["buckets"]}

        assert buckets["al_dia"]["amount"] == "4000.00"
        assert buckets["dias_1_30"]["amount"] == "1000.00"
        assert buckets["dias_31_60"]["amount"] == "2000.00"
        assert buckets["mas_90"]["amount"] == "3000.00"
        assert response.json()["total_vencido"] == "6000.00"

    async def test_all_buckets_present_when_empty(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get("/api/v1/dashboard/aging", headers=headers)
        labels = [row["label"] for row in response.json()["buckets"]]

        assert labels == ["al_dia", "dias_1_30", "dias_31_60", "dias_61_90", "mas_90"]

    async def test_excludes_paid_installments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        today = date.today()

        loan = await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=today,
            installments=[(today - timedelta(days=10), "1000.00", "900.00", "100.00")],
        )

        installment = await db_session.scalar(
            select(Installment).where(Installment.loan_id == loan.id).limit(1)
        )
        assert installment is not None
        installment.status = "pagada"
        installment.paid_amount = Decimal("1000.00")
        await db_session.commit()

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/aging", headers=headers)

        assert response.json()["total_vencido"] == "0.00"


class TestDateFilters:
    """RN-48: las fechas filtran distinto segun el concepto."""

    async def test_placed_filters_by_start_date(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=date(2026, 1, 10),
        )
        await _loan(
            db_session, tenant, client, user,
            principal="2000", start_date=date(2026, 6, 10),
        )

        headers = await _headers(api_client)
        response = await api_client.get(
            "/api/v1/dashboard/summary?from_date=2026-05-01&to_date=2026-12-31",
            headers=headers,
        )

        assert response.json()["capital_prestado"] == "2000.00"

    async def test_collections_filter_by_payment_date(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        loan = await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=date(2026, 1, 1),
            installments=[(date(2026, 1, 10), "1000.00", "900.00", "100.00")],
        )
        await _payment(
            db_session, tenant, loan, user,
            amount="100.00", applications=[("capital", "100.00")],
        )

        headers = await _headers(api_client)
        inside = await api_client.get(
            f"/api/v1/dashboard/summary?from_date={date.today()}&to_date={date.today()}",
            headers=headers,
        )
        outside = await api_client.get(
            "/api/v1/dashboard/summary?from_date=2020-01-01&to_date=2020-01-31",
            headers=headers,
        )

        assert inside.json()["capital_recuperado"] == "100.00"
        assert outside.json()["capital_recuperado"] == "0.00"


class TestCollectionsSeries:
    """Serie diaria de cobranza."""

    async def test_returns_daily_totals(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        loan = await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=date.today(),
            installments=[(date.today(), "1000.00", "900.00", "100.00")],
        )
        await _payment(
            db_session, tenant, loan, user,
            amount="500.00", applications=[("capital", "500.00")],
        )

        headers = await _headers(api_client)
        response = await api_client.get("/api/v1/dashboard/collections", headers=headers)

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["amount"] == "500.00"

    async def test_empty_series(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get("/api/v1/dashboard/collections", headers=headers)

        assert response.json() == []


class TestAuthorization:
    """Solo el Administrador ve el dashboard."""

    @pytest.mark.parametrize("role", ["prestamista", "cobrador"])
    async def test_rejects_non_admin(
        self, api_client: AsyncClient, db_session: AsyncSession, role: str
    ) -> None:
        await _setup(db_session, email=f"{role}@test.mx", role=role)
        headers = await _headers(api_client, f"{role}@test.mx")

        response = await api_client.get("/api/v1/dashboard/summary", headers=headers)
        assert response.status_code == 403

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.get("/api/v1/dashboard/summary")
        assert response.status_code == 401

    async def test_does_not_leak_other_tenants(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant_a, user_a = await _setup(db_session, email="a@test.mx", slug="a")
        client = await _client(db_session, tenant_a)
        await _loan(
            db_session, tenant_a, client, user_a,
            principal="5000", start_date=date.today(),
        )

        await _setup(db_session, email="b@test.mx", slug="b")
        headers_b = await _headers(api_client, "b@test.mx")

        response = await api_client.get("/api/v1/dashboard/summary", headers=headers_b)

        assert response.json()["capital_prestado"] == "0.00"


class TestBucketFunction:
    """Clasificacion de dias de atraso."""

    @pytest.mark.parametrize(
        ("days", "expected"),
        [
            (-5, "al_dia"),
            (0, "al_dia"),
            (1, "dias_1_30"),
            (30, "dias_1_30"),
            (31, "dias_31_60"),
            (60, "dias_31_60"),
            (61, "dias_61_90"),
            (90, "dias_61_90"),
            (91, "mas_90"),
            (365, "mas_90"),
        ],
    )
    def test_bucket_boundaries(self, days: int, expected: str) -> None:
        assert dashboard_service._bucket_for(days) == expected


class TestSummaryService:
    """Reglas verificadas en el servicio."""

    async def test_projected_equals_total_portfolio(
        self, db_session: AsyncSession
    ) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        await _loan(
            db_session, tenant, client, user,
            principal="1000", start_date=date.today(),
            installments=[(date.today() + timedelta(days=30), "1100.00", "1000.00", "100.00")],
        )

        result = await dashboard_service.summary(db_session, tenant.id)

        assert result.capital_proyectado == result.cartera_total == Decimal("1100.00")

    async def test_counts_loans_by_status(self, db_session: AsyncSession) -> None:
        tenant, user = await _setup(db_session)
        client = await _client(db_session, tenant)
        for status in ("activo", "pagado", "vencido"):
            await _loan(
                db_session, tenant, client, user,
                principal="1000", start_date=date.today(), status=status,
            )

        result = await dashboard_service.summary(db_session, tenant.id)

        assert result.prestamos_activos == 1
        assert result.prestamos_pagados == 1
        assert result.prestamos_vencidos == 1


class TestInternalHelpers:
    """Funciones auxiliares del servicio."""

    def test_to_decimal_handles_none(self) -> None:
        assert dashboard_service._to_decimal(None) == Decimal("0.00")

    def test_to_decimal_handles_decimal(self) -> None:
        assert dashboard_service._to_decimal(Decimal("123.456")) == Decimal("123.46")

    def test_to_decimal_handles_int(self) -> None:
        assert dashboard_service._to_decimal(100) == Decimal("100.00")

    def test_bucket_fallback(self) -> None:
        """Un atraso fuera de las franjas cae en mas_90."""
        assert dashboard_service._bucket_for(9999) == "mas_90"
