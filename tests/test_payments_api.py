"""Pruebas de integracion de pagos.

Cubren el flujo completo: registrar, ver el desglose, acumular pagos parciales,
adelantar cuotas y anular. Los montos se verifican al centavo.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.domain.payment_application import InstallmentState
from app.models.client import Client
from app.models.loan import Installment, Loan
from app.models.payment import Payment
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
CURP = "LOPJ850312MDFZRN07"
START = "2026-11-02"

LOAN = {
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
    role: str = "admin",
    permissions: dict[str, bool] | None = None,
) -> tuple[Tenant, User, Client]:
    """Crea tenant, usuario, configuracion y cliente."""
    tenant = Tenant(name="Financiera Test", slug=slug)
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Usuario Test",
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        permissions=permissions or {},
    )
    session.add(user)
    session.add(
        SystemSetting(
            tenant_id=tenant.id,
            default_late_fee_rate=Decimal("0.1000"),
            grace_days=0,
        )
    )

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
    return tenant, user, client


async def _headers(client: AsyncClient, email: str = "admin@test.mx") -> dict[str, str]:
    """Inicia sesion y devuelve la cabecera."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_loan(client: AsyncClient, headers: dict[str, str], client_id: UUID) -> dict:
    """Crea un prestamo de 10,000 a 12 semanas al 5 % simple."""
    response = await client.post(
        "/api/v1/loans",
        json={**LOAN, "client_id": str(client_id)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestRegisterPayment:
    """POST /api/v1/payments."""

    async def test_registers_partial_payment(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 400, "method": "efectivo"},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["payment"]["status"] == "aplicado"
        assert body["covered_interest"] == "400.00"
        assert body["covered_principal"] == "0.00"
        assert body["covered_late_fee"] == "0.00"
        assert body["remaining_total"] == "15600.00"

    async def test_generates_folio(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-39: folio legible y unico por financiera."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        first = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )
        second = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        folio_one = first.json()["payment"]["folio"]
        folio_two = second.json()["payment"]["folio"]

        assert folio_one.startswith("PAGO-TEST-")
        assert folio_one != folio_two

    async def test_pays_full_installment(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 1333.33, "method": "efectivo"},
            headers=headers,
        )

        body = response.json()
        assert body["covered_interest"] == "500.00"
        assert body["covered_principal"] == "833.33"
        assert body["remaining_total"] == "14666.67"

    async def test_first_installment_becomes_paid(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 1333.33, "method": "efectivo"},
            headers=headers,
        )

        detail = await api_client.get(f"/api/v1/loans/{loan['id']}", headers=headers)
        installments = detail.json()["installments"]

        assert installments[0]["status"] == "pagada"
        assert installments[0]["paid_at"] is not None
        assert installments[1]["status"] == "pendiente"

    async def test_advance_payment_covers_several_installments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-31: un pago puede cubrir varias cuotas."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 2666.66, "method": "efectivo"},
            headers=headers,
        )

        detail = await api_client.get(f"/api/v1/loans/{loan['id']}", headers=headers)
        statuses = [row["status"] for row in detail.json()["installments"][:3]]

        assert statuses[0] == "pagada"
        assert statuses[1] == "pagada"
        assert response.json()["remaining_total"] == "13333.34"

    async def test_spei_requires_reference(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-25: la transferencia necesita referencia."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "spei"},
            headers=headers,
        )

        assert response.status_code == 422
        assert "referencia SPEI" in response.text

    async def test_spei_with_reference_is_accepted(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={
                "loan_id": loan["id"],
                "amount": 500,
                "method": "spei",
                "spei_reference": "REF123456",
            },
            headers=headers,
        )

        assert response.status_code == 201
        assert response.json()["payment"]["spei_reference"] == "REF123456"

    async def test_rejects_payment_over_balance(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-24: no se acepta mas de lo que se debe."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 16000.01, "method": "efectivo"},
            headers=headers,
        )

        assert response.status_code == 409
        assert "excede" in response.json()["detail"]

    async def test_exact_balance_closes_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 16000, "method": "efectivo"},
            headers=headers,
        )

        assert response.status_code == 201
        assert response.json()["loan_status"] == "pagado"
        assert response.json()["remaining_total"] == "0.00"

    async def test_rejects_payment_on_paid_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-27: un prestamo pagado no admite mas pagos."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 16000, "method": "efectivo"},
            headers=headers,
        )
        second = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        assert second.status_code == 409

    async def test_rejects_payment_on_cancelled_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        await api_client.post(
            f"/api/v1/loans/{loan['id']}/cancel",
            json={"reason": "Cancelado por prueba."},
            headers=headers,
        )
        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        assert response.status_code == 409

    async def test_rejects_unknown_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": str(uuid4()), "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        assert response.status_code == 404

    async def test_rejects_zero_amount(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 0, "method": "efectivo"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": str(uuid4()), "amount": 100, "method": "efectivo"},
        )
        assert response.status_code == 401

    async def test_does_not_leak_other_tenant_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RNF-08: no se cobra un prestamo de otra financiera."""
        _, _, client_a = await _setup(db_session, email="a@test.mx", slug="a")
        headers_a = await _headers(api_client, "a@test.mx")
        loan_a = await _create_loan(api_client, headers_a, client_a.id)

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

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan_a["id"], "amount": 100, "method": "efectivo"},
            headers=headers_b,
        )

        assert response.status_code == 404


class TestPaymentWithLateFee:
    """El pago cubre primero la mora (RN-29)."""

    async def test_late_fee_is_paid_first(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        # Se simula mora acumulada por el cierre diario.
        installment = await db_session.scalar(
            select(Installment)
            .join(Loan, Loan.id == Installment.loan_id)
            .where(Loan.id == UUID(loan["id"]), Installment.number == 1)
        )
        assert installment is not None
        installment.late_fee = Decimal("100.00")
        await db_session.commit()

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 1200, "method": "efectivo"},
            headers=headers,
        )

        body = response.json()
        assert body["covered_late_fee"] == "100.00"
        assert body["covered_interest"] == "500.00"
        assert body["covered_principal"] == "600.00"


class TestListPayments:
    """GET /api/v1/payments."""

    async def test_lists_payments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        response = await api_client.get("/api/v1/payments", headers=headers)

        assert response.json()["total"] == 1

    async def test_filters_by_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        matching = await api_client.get(
            f"/api/v1/payments?loan_id={loan['id']}", headers=headers
        )
        other = await api_client.get(f"/api/v1/payments?loan_id={uuid4()}", headers=headers)

        assert matching.json()["total"] == 1
        assert other.json()["total"] == 0

    async def test_returns_detail_with_applications(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        created = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 1000, "method": "efectivo"},
            headers=headers,
        )
        payment_id = created.json()["payment"]["id"]

        response = await api_client.get(f"/api/v1/payments/{payment_id}", headers=headers)

        assert response.status_code == 200
        applications = response.json()["applications"]
        assert len(applications) == 2
        assert {row["concept"] for row in applications} == {"interes", "capital"}


class TestCancelPayment:
    """POST /api/v1/payments/{id}/cancel (RN-36)."""

    async def test_cancels_and_restores_balance(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        created = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 1333.33, "method": "efectivo"},
            headers=headers,
        )
        payment_id = created.json()["payment"]["id"]

        response = await api_client.post(
            f"/api/v1/payments/{payment_id}/cancel",
            json={"reason": "Se registro por error en el monto."},
            headers=headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["payment"]["status"] == "anulado"
        assert body["remaining_total"] == "16000.00"

    async def test_cancel_restores_installment_status(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        created = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 1333.33, "method": "efectivo"},
            headers=headers,
        )

        await api_client.post(
            f"/api/v1/payments/{created.json()['payment']['id']}/cancel",
            json={"reason": "Error de captura del cobrador."},
            headers=headers,
        )
        detail = await api_client.get(f"/api/v1/loans/{loan['id']}", headers=headers)

        first = detail.json()["installments"][0]
        assert first["status"] in {"pendiente", "vencida"}
        assert first["paid_amount"] == "0.00"
        assert first["paid_at"] is None

    async def test_cannot_cancel_twice(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        created = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 500, "method": "efectivo"},
            headers=headers,
        )
        payment_id = created.json()["payment"]["id"]

        await api_client.post(
            f"/api/v1/payments/{payment_id}/cancel",
            json={"reason": "Primera anulacion valida."},
            headers=headers,
        )
        second = await api_client.post(
            f"/api/v1/payments/{payment_id}/cancel",
            json={"reason": "Segunda anulacion intentada."},
            headers=headers,
        )

        assert second.status_code == 409

    async def test_cannot_cancel_when_later_payments_exist(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        first = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )
        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 200, "method": "efectivo"},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/payments/{first.json()['payment']['id']}/cancel",
            json={"reason": "Intento de anular el pago viejo."},
            headers=headers,
        )

        assert response.status_code == 409
        assert "posteriores" in response.json()["detail"]

    async def test_requires_permission(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """RN-37: un cobrador no puede anular."""
        await _setup(db_session, role="cobrador")
        headers = await _headers(api_client)

        response = await api_client.post(
            f"/api/v1/payments/{uuid4()}/cancel",
            json={"reason": "Intento sin permiso."},
            headers=headers,
        )

        assert response.status_code == 403

    async def test_prestamista_with_permission_can_cancel(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(
            db_session,
            email="prest@test.mx",
            role="prestamista",
            permissions={"cancel_payment": True},
        )
        headers = await _headers(api_client, "prest@test.mx")
        loan = await _create_loan(api_client, headers, client.id)
        created = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 300, "method": "efectivo"},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/payments/{created.json()['payment']['id']}/cancel",
            json={"reason": "Anulacion con permiso explicito."},
            headers=headers,
        )

        assert response.status_code == 200

    async def test_rejects_short_reason(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        created = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 300, "method": "efectivo"},
            headers=headers,
        )

        response = await api_client.post(
            f"/api/v1/payments/{created.json()['payment']['id']}/cancel",
            json={"reason": "corto"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_cancel_unknown_payment(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            f"/api/v1/payments/{uuid4()}/cancel",
            json={"reason": "Pago que no existe en la base."},
            headers=headers,
        )
        assert response.status_code == 404


class TestPaymentServiceRules:
    """Reglas verificadas directamente en el servicio."""

    async def test_multiple_partials_sum_exactly(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Diez pagos de 1,333.33 deben liquidar diez cuotas."""
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        last: dict = {}
        for _ in range(10):
            response = await api_client.post(
                "/api/v1/payments",
                json={"loan_id": loan["id"], "amount": 1333.33, "method": "efectivo"},
                headers=headers,
            )
            last = response.json()

        detail = await api_client.get(f"/api/v1/loans/{loan['id']}", headers=headers)
        paid = [row for row in detail.json()["installments"] if row["status"] == "pagada"]

        assert len(paid) == 10
        assert last["loan_status"] == "activo"

    async def test_loan_becomes_paid_after_all_installments(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 16000, "method": "efectivo"},
            headers=headers,
        )

        assert response.json()["loan_status"] == "pagado"

    async def test_payment_repr_hides_amount(self) -> None:
        payment = Payment(folio="PAGO-TEST-2026-00001", amount=Decimal("5000.00"))
        text = repr(payment)

        assert "5000" not in text
        assert "PAGO-TEST" in text

    async def test_application_repr(self) -> None:
        from app.models.payment import PaymentApplication

        application = PaymentApplication(concept="interes", amount=Decimal("100.00"))
        assert "interes" in repr(application)


class TestMissingBranches:
    """Ramas de error y validacion que faltaban cubrir."""

    async def test_get_unknown_payment(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.get(f"/api/v1/payments/{uuid4()}", headers=headers)
        assert response.status_code == 404

    async def test_spei_reference_too_short(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)

        response = await api_client.post(
            "/api/v1/payments",
            json={
                "loan_id": loan["id"],
                "amount": 100,
                "method": "spei",
                "spei_reference": "AB1",
            },
            headers=headers,
        )

        assert response.status_code == 422
        assert "al menos 6" in response.text

    async def test_cancel_unknown_loan_branch(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        headers = await _headers(api_client)

        response = await api_client.post(
            f"/api/v1/payments/{uuid4()}/cancel",
            json={"reason": "Pago inexistente en esta financiera."},
            headers=headers,
        )
        assert response.status_code == 404


class TestDomainEdgeCases:
    """Casos del dominio sin cobertura."""

    def test_status_when_nothing_paid(self) -> None:
        row = InstallmentState(
            number=1,
            amount=Decimal("1000.00"),
            principal_part=Decimal("750.00"),
            interest_part=Decimal("250.00"),
        )
        assert row.status_after_payment == "pendiente"

    def test_skip_zero_take(self) -> None:
        """Una cuota con pendiente cero no genera aplicaciones."""
        from app.domain.payment_application import allocate_payment

        paid = InstallmentState(
            number=1,
            amount=Decimal("1000.00"),
            principal_part=Decimal("750.00"),
            interest_part=Decimal("250.00"),
            paid_principal=Decimal("750.00"),
            paid_interest=Decimal("250.00"),
        )
        pending = InstallmentState(
            number=2,
            amount=Decimal("1000.00"),
            principal_part=Decimal("750.00"),
            interest_part=Decimal("250.00"),
        )

        result = allocate_payment([paid, pending], "100.00")

        assert result.applications[0].installment_number == 2

    async def test_filters_by_date_range(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        _, _, client = await _setup(db_session)
        headers = await _headers(api_client)
        loan = await _create_loan(api_client, headers, client.id)
        await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 100, "method": "efectivo"},
            headers=headers,
        )

        today = date.today().isoformat()
        inside = await api_client.get(
            f"/api/v1/payments?from_date={today}&to_date={today}", headers=headers
        )
        past = await api_client.get(
            "/api/v1/payments?from_date=2020-01-01&to_date=2020-01-31", headers=headers
        )

        assert inside.json()["total"] == 1
        assert past.json()["total"] == 0
