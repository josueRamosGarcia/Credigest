"""Pruebas del comprobante de pago y del enlace de WhatsApp."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.loan import Loan
from app.models.payment import Payment
from app.models.tenant import Tenant
from app.models.user import User
from app.pdf.receipt import (
    build_receipt_context,
    receipt_filename,
    render_receipt_html,
    render_receipt_pdf,
    whatsapp_link,
)


def _entities() -> tuple[Tenant, Client, Loan, Payment, User]:
    """Construye las entidades en memoria, sin base de datos."""
    tenant = Tenant(id=uuid4(), name="Financiera Ejemplo", slug="ejemplo")
    client = Client(
        id=uuid4(),
        full_name="María López Pérez",
        curp="LOPJ850312MDFZRN07",
        phone="8711234567",
        address="Av. Juárez 123",
    )
    loan = Loan(
        id=uuid4(),
        principal=Decimal("10000.00"),
        status="activo",
    )
    payment = Payment(
        id=uuid4(),
        folio="PAGO-EJEMPLO-2026-00001",
        amount=Decimal("1333.33"),
        method="efectivo",
        status="aplicado",
        created_at=datetime(2026, 11, 10, 15, 30),
    )
    user = User(full_name="Admin Demo")
    return tenant, client, loan, payment, user


class TestReceiptContext:
    """Datos del comprobante."""

    def test_includes_folio_and_date(self) -> None:
        tenant, client, loan, payment, user = _entities()

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("interes", Decimal("500.00")), ("capital", Decimal("833.33"))],
            remaining_total=Decimal("8666.67"),
            registered_by=user,
        )

        assert context.payment["folio"] == "PAGO-EJEMPLO-2026-00001"
        assert context.payment["date"] == "10/11/2026"

    def test_formats_amount_and_words(self) -> None:
        tenant, client, loan, payment, user = _entities()

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("1333.33"))],
            remaining_total=Decimal("8666.67"),
            registered_by=user,
        )

        assert context.payment["amount"] == "1,333.33"
        assert "mil trescientos" in context.payment["amount_words"]

    def test_groups_applications_by_concept(self) -> None:
        tenant, client, loan, payment, user = _entities()

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[
                ("interes", Decimal("200.00")),
                ("interes", Decimal("100.00")),
                ("capital", Decimal("500.00")),
            ],
            remaining_total=Decimal("8000.00"),
            registered_by=user,
        )

        by_label = {row["label"]: row["amount"] for row in context.concepts}
        assert by_label["Interés"] == "300.00"
        assert by_label["Capital"] == "500.00"

    def test_includes_remaining_balance(self) -> None:
        tenant, client, loan, payment, user = _entities()

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("1000.00"))],
            remaining_total=Decimal("9000.00"),
            registered_by=user,
        )

        assert context.loan["remaining_total"] == "9,000.00"

    def test_labels_payment_method(self) -> None:
        tenant, client, loan, payment, user = _entities()
        payment.method = "spei"
        payment.spei_reference = "REF123456"

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("1000.00"))],
            remaining_total=Decimal("9000.00"),
            registered_by=user,
        )

        assert context.payment["method_label"] == "Transferencia SPEI"
        assert context.payment["spei_reference"] == "REF123456"

    def test_falls_back_without_registered_by(self) -> None:
        tenant, client, loan, payment, _ = _entities()

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("1000.00"))],
            remaining_total=Decimal("9000.00"),
            registered_by=None,
        )

        assert context.payment["registered_by"] == "Sistema"

    def test_uses_loan_status_label(self) -> None:
        tenant, client, loan, payment, user = _entities()
        loan.status = "pagado"

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("1000.00"))],
            remaining_total=Decimal("0.00"),
            registered_by=user,
        )

        assert context.loan["status_label"] == "Pagado"


class TestReceiptHtml:
    """Contenido del HTML."""

    def _html(self) -> str:
        tenant, client, loan, payment, user = _entities()
        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("interes", Decimal("500.00")), ("capital", Decimal("833.33"))],
            remaining_total=Decimal("8666.67"),
            registered_by=user,
        )
        return render_receipt_html(context)

    def test_contains_tenant_and_folio(self) -> None:
        html = self._html()
        assert "Financiera Ejemplo" in html
        assert "PAGO-EJEMPLO-2026-00001" in html

    def test_contains_client_name(self) -> None:
        assert "María López Pérez" in self._html()

    def test_contains_concepts(self) -> None:
        html = self._html()
        assert "Interés" in html
        assert "Capital" in html

    def test_contains_amount(self) -> None:
        assert "1,333.33" in self._html()

    def test_contains_balance(self) -> None:
        assert "8,666.67" in self._html()

    def test_escapes_html(self) -> None:
        tenant, client, loan, payment, user = _entities()
        client.full_name = "Ana <script>alert(1)</script>"

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("100.00"))],
            remaining_total=Decimal("900.00"),
            registered_by=user,
        )
        html = render_receipt_html(context)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_marks_cancelled_payment(self) -> None:
        tenant, client, loan, payment, user = _entities()
        payment.status = "anulado"
        payment.cancel_reason = "Registrado por error"

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("100.00"))],
            remaining_total=Decimal("900.00"),
            registered_by=user,
        )
        html = render_receipt_html(context)

        assert "PAGO ANULADO" in html
        assert "Registrado por error" in html


class TestReceiptPdf:
    """Generacion del PDF."""

    def test_generates_valid_pdf(self) -> None:
        tenant, client, loan, payment, user = _entities()
        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("1000.00"))],
            remaining_total=Decimal("9000.00"),
            registered_by=user,
        )

        try:
            pdf = render_receipt_pdf(context)
        except Exception as exc:  # pragma: no cover - depende del sistema
            pytest.skip(f"WeasyPrint no disponible: {exc}")

        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 2000

    def test_filename_uses_folio(self) -> None:
        _, _, _, payment, _ = _entities()
        assert receipt_filename(payment) == "pago-ejemplo-2026-00001.pdf"


class TestWhatsappLink:
    """Enlace de WhatsApp."""

    def _payment(self) -> Payment:
        _, _, _, payment, _ = _entities()
        return payment

    def test_builds_wa_me_url(self) -> None:
        link = whatsapp_link("8711234567", tenant_name="Financiera", payment=self._payment())

        assert link.startswith("https://wa.me/528711234567?text=")

    def test_keeps_country_code_when_present(self) -> None:
        link = whatsapp_link("528711234567", tenant_name="F", payment=self._payment())
        assert "wa.me/528711234567" in link

    def test_strips_formatting_characters(self) -> None:
        link = whatsapp_link("871-123-4567", tenant_name="F", payment=self._payment())
        assert "wa.me/528711234567" in link

    def test_message_contains_folio_and_amount(self) -> None:
        from urllib.parse import unquote

        link = whatsapp_link("8711234567", tenant_name="Mi Financiera", payment=self._payment())
        message = unquote(link.split("text=")[1])

        assert "PAGO-EJEMPLO-2026-00001" in message
        assert "1,333.33" in message
        assert "Mi Financiera" in message


class TestReceiptEndpoint:
    """GET /api/v1/payments/{id}/receipt.pdf y /whatsapp."""

    async def _payment_id(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> str:
        from tests.test_payments_api import _create_loan, _setup
        from tests.test_payments_api import _headers as payment_headers

        _, _, client = await _setup(db_session)
        headers = await payment_headers(api_client, "admin@test.mx")
        loan = await _create_loan(api_client, headers, client.id)

        payment = await api_client.post(
            "/api/v1/payments",
            json={"loan_id": loan["id"], "amount": 400, "method": "efectivo"},
            headers=headers,
        )
        return payment.json()["payment"]["id"]

    async def test_receipt_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"/api/v1/payments/{uuid4()}/receipt.pdf")
        assert response.status_code == 401

    async def test_receipt_404_for_unknown(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from app.core.security import hash_password
        from app.models.system_setting import SystemSetting

        tenant = Tenant(name="T", slug="t")
        db_session.add(tenant)
        await db_session.flush()
        db_session.add(
            User(
                tenant_id=tenant.id,
                full_name="Admin",
                email="admin@test.mx",
                password_hash=hash_password("clave-segura-123"),
                role="admin",
            )
        )
        db_session.add(SystemSetting(tenant_id=tenant.id))
        await db_session.commit()

        login = await api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.mx", "password": "clave-segura-123"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = await api_client.get(
            f"/api/v1/payments/{uuid4()}/receipt.pdf", headers=headers
        )
        assert response.status_code == 404

    async def test_receipt_returns_pdf(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from tests.test_payments_api import _headers as payment_headers

        payment_id = await self._payment_id(api_client, db_session)
        headers = await payment_headers(api_client, "admin@test.mx")

        response = await api_client.get(
            f"/api/v1/payments/{payment_id}/receipt.pdf", headers=headers
        )

        if response.status_code == 503:
            pytest.skip("WeasyPrint no disponible")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    async def test_whatsapp_endpoint(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from tests.test_payments_api import _headers as payment_headers

        payment_id = await self._payment_id(api_client, db_session)
        headers = await payment_headers(api_client, "admin@test.mx")

        response = await api_client.get(
            f"/api/v1/payments/{payment_id}/whatsapp", headers=headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["url"].startswith("https://wa.me/")
        assert body["phone"] == "8711234567"

    async def test_whatsapp_404_for_unknown(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from tests.test_payments_api import _headers as payment_headers

        await self._payment_id(api_client, db_session)
        headers = await payment_headers(api_client, "admin@test.mx")

        response = await api_client.get(
            f"/api/v1/payments/{uuid4()}/whatsapp", headers=headers
        )
        assert response.status_code == 404


class TestLocalDate:
    """La fecha del comprobante debe ser la del negocio, no UTC."""

    def test_converts_utc_to_local(self) -> None:
        """Un pago a las 22:00 hora de Mexico no debe mostrar el dia siguiente.

        Se crea un pago a las 04:00 UTC del dia 11, que en Mexico (UTC-6) es
        todavia el dia 10 a las 22:00.
        """
        from app.pdf.receipt import local_date_of

        _, _, _, payment, _ = _entities()
        payment.created_at = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)

        assert local_date_of(payment) == date(2026, 11, 10)

    def test_context_uses_local_date(self) -> None:
        tenant, client, loan, payment, user = _entities()
        payment.created_at = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)

        context = build_receipt_context(
            tenant=tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=[("capital", Decimal("100.00"))],
            remaining_total=Decimal("900.00"),
            registered_by=user,
        )

        assert context.payment["date"] == "10/11/2026"

    def test_whatsapp_uses_local_date(self) -> None:
        from urllib.parse import unquote

        _, _, _, payment, _ = _entities()
        payment.created_at = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)

        link = whatsapp_link("8711234567", tenant_name="F", payment=payment)
        message = unquote(link.split("text=")[1])

        assert "10/11/2026" in message
