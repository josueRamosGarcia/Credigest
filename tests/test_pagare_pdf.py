"""Pruebas de la generacion del pagare.

Se prueba el contexto y el HTML, que es lo que se puede verificar sin depender
de las librerias del sistema. La generacion real del PDF se prueba aparte y se
salta si WeasyPrint no esta disponible.
"""

from datetime import date
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
from app.pdf.generator import (
    build_context,
    pagare_filename,
    render_pagare_html,
)

pytestmark = pytest.mark.db

PASSWORD = "clave-segura-123"
CURP = "LOPJ850312MDFZRN07"


async def _setup(
    session: AsyncSession,
) -> tuple[Tenant, User, Client, Loan]:
    """Crea tenant, usuario, cliente y un prestamo de 12 cuotas."""
    tenant = Tenant(name="Financiera Ejemplo", slug="ejemplo")
    session.add(tenant)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        full_name="Admin",
        email="admin@test.mx",
        password_hash=hash_password(PASSWORD),
        role="admin",
    )
    session.add(user)
    session.add(
        SystemSetting(
            tenant_id=tenant.id,
            default_late_fee_rate=Decimal("0.1000"),
            grace_days=5,
        )
    )

    client = Client(
        tenant_id=tenant.id,
        full_name="María López Pérez",
        curp=CURP,
        phone="8711234567",
        address="Av. Juárez 123, Col. Centro, Torreón, Coahuila",
        zone="Centro",
        status="activo",
        birth_date=date(1985, 3, 12),
    )
    session.add(client)
    await session.flush()

    loan = Loan(
        tenant_id=tenant.id,
        client_id=client.id,
        lender_id=user.id,
        principal=Decimal("10000.00"),
        interest_rate=Decimal("0.0500"),
        rate_period="semanal",
        scheme="simple",
        term_periods=12,
        start_date=date(2026, 11, 2),
        first_due_date=date(2026, 11, 9),
        end_date=date(2027, 1, 25),
        total_interest=Decimal("6000.00"),
        total_amount=Decimal("16000.00"),
        late_fee_rate=Decimal("0.1000"),
        grace_days=5,
        status="activo",
    )
    session.add(loan)
    await session.flush()

    for number in range(1, 13):
        session.add(
            Installment(
                loan_id=loan.id,
                number=number,
                due_date=date(2026, 11, 9),
                amount=Decimal("1333.33"),
                principal_part=Decimal("833.33"),
                interest_part=Decimal("500.00"),
                late_fee=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                status="pendiente",
            )
        )

    await session.commit()
    return tenant, user, client, loan


def _context(tenant: Tenant, client: Client, loan: Loan):
    """Armado del contexto con fecha fija."""
    return build_context(
        tenant=tenant,
        client=client,
        loan=loan,
        issued_date=date(2026, 11, 10),
    )


class TestBuildContext:
    """Datos que consume la plantilla."""

    async def test_includes_client_data(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert context.client["full_name"] == "María López Pérez"
        assert context.client["curp"] == CURP
        assert context.client["phone"] == "8711234567"

    async def test_includes_loan_conditions(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert context.loan["principal"] == "10,000.00"
        assert context.loan["total_amount"] == "16,000.00"
        assert context.loan["total_interest"] == "6,000.00"
        assert context.loan["interest_rate_percent"] == "5"
        assert context.loan["rate_period_label"] == "semanal"
        assert context.loan["term_periods"] == 12

    async def test_includes_mora_clause_values(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert context.loan["late_fee_rate_percent"] == "10"
        assert context.loan["grace_days"] == 5

    async def test_formats_amount_in_words(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert "dieciséis mil" in context.loan["total_amount_words"]
        assert context.loan["total_amount_words"].endswith("M.N.")

    async def test_dates_are_formatted(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert context.loan["start_date"] == "02/11/2026"
        assert context.loan["end_date"] == "25/01/2027"
        assert context.issued_date == "10/11/2026"

    async def test_schedule_has_all_installments(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert len(context.installments) == 12
        assert context.installments[0]["number"] == 1
        assert context.installments[0]["amount"] == "1,333.33"
        assert context.installments[0]["interest_part"] == "500.00"
        assert context.installments[0]["principal_part"] == "833.33"

    async def test_totals(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert context.totals["amount"] == "16,000.00"
        assert context.totals["interest"] == "6,000.00"
        assert context.totals["principal"] == "10,000.00"

    async def test_generates_folio(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        assert context.loan["folio"].startswith("PAG-EJEMPLO-")

    async def test_uses_schedule_from_frozen_conditions(
        self, db_session: AsyncSession
    ) -> None:
        """El calendario se recalcula desde el prestamo, no desde la tabla de cuotas."""
        tenant, _, client, loan = await _setup(db_session)
        context = _context(tenant, client, loan)

        last = context.installments[-1]
        assert last["balance"] == "0.00"


class TestRenderHtml:
    """Contenido del HTML generado."""

    async def test_contains_title(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        html = render_pagare_html(_context(tenant, client, loan))

        assert "Pagaré" in html

    async def test_contains_client_name_and_curp(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        html = render_pagare_html(_context(tenant, client, loan))

        assert "María López Pérez" in html
        assert CURP in html

    async def test_contains_amount_in_words(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        html = render_pagare_html(_context(tenant, client, loan))

        assert "dieciséis mil" in html

    async def test_contains_mora_clause(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        html = render_pagare_html(_context(tenant, client, loan))

        assert "interés moratorio" in html
        assert "10 % mensual" in html
        assert "5 días de gracia" in html

    async def test_contains_full_schedule(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        html = render_pagare_html(_context(tenant, client, loan))

        # 12 filas de cuotas, cada una con su numero.
        for number in range(1, 13):
            assert f">{number}<" in html

    async def test_contains_legal_notice(self, db_session: AsyncSession) -> None:
        tenant, _, client, loan = await _setup(db_session)
        html = render_pagare_html(_context(tenant, client, loan))

        assert "no sustituye la asesoría" in html

    async def test_escapes_html_in_names(self, db_session: AsyncSession) -> None:
        """Un nombre con caracteres especiales no debe romper el HTML."""
        tenant, _, client, loan = await _setup(db_session)
        client.full_name = "Ana <script>alert(1)</script>"
        html = render_pagare_html(_context(tenant, client, loan))

        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestFilename:
    """Nombre sugerido del archivo."""

    async def test_uses_tenant_slug(self, db_session: AsyncSession) -> None:
        tenant, _, _, loan = await _setup(db_session)
        name = pagare_filename(tenant, loan)

        assert name.startswith("pagare-ejemplo-")
        assert name.endswith(".pdf")

    def test_falls_back_without_slug(self) -> None:
        tenant = Tenant(name="Sin slug", slug=None)
        loan = Loan()
        loan.id = uuid4()

        assert pagare_filename(tenant, loan).startswith("pagare-credigest-")


class TestPdfEndpoint:
    """GET /api/v1/loans/{id}/pagare.pdf."""

    async def test_requires_authentication(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"/api/v1/loans/{uuid4()}/pagare.pdf")
        assert response.status_code == 401

    async def test_returns_404_for_unknown_loan(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _setup(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = await api_client.get(
            f"/api/v1/loans/{uuid4()}/pagare.pdf", headers=headers
        )
        assert response.status_code == 404

    async def test_returns_pdf_or_503(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Devuelve el PDF o, si faltan librerias, un 503 con instrucciones."""
        tenant, _, client, loan = await _setup(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = await api_client.get(
            f"/api/v1/loans/{loan.id}/pagare.pdf", headers=headers
        )

        if response.status_code == 503:
            assert "WeasyPrint" in response.json()["detail"]
            pytest.skip("WeasyPrint sin librerias del sistema")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        assert "attachment" in response.headers["content-disposition"]

    async def test_pdf_has_reasonable_size(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        tenant, _, client, loan = await _setup(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = await api_client.get(
            f"/api/v1/loans/{loan.id}/pagare.pdf", headers=headers
        )
        if response.status_code == 503:
            pytest.skip("WeasyPrint sin librerias del sistema")

        assert len(response.content) > 5000

    async def test_pdf_download_is_audited(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from app.models.audit_log import AuditLog

        tenant, _, client, loan = await _setup(db_session)
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": "admin@test.mx", "password": PASSWORD}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        response = await api_client.get(
            f"/api/v1/loans/{loan.id}/pagare.pdf", headers=headers
        )
        if response.status_code == 503:
            pytest.skip("WeasyPrint sin librerias del sistema")

        entry = await db_session.scalar(
            select(AuditLog).where(AuditLog.action == "loan.pagare_download")
        )
        assert entry is not None
        assert entry.entity_id == loan.id
