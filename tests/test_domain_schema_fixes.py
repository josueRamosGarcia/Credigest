"""Pruebas unitarias para correcciones de dominio financiero y esquemas."""

from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.domain.amortization import build_schedule, schedule_totals
from app.domain.interest import Frequency, LoanTerms, Scheme, last_installment
from app.domain.money import MoneyError, to_decimal
from app.domain.payment_application import InstallmentState, allocate_payment
from app.main import app
from app.schemas.client import ClientUpdate
from app.schemas.loan import LoanCreate
from app.schemas.user import SystemSettingUpdate


class TestMoneyFiniteness:
    """NaN e Infinity deben rechazarse como MoneyError."""

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", Decimal("NaN")])
    def test_rejects_non_finite_values(self, bad: str | Decimal) -> None:
        with pytest.raises(MoneyError, match="finito"):
            to_decimal(bad)


class TestDecliningLastInstallment:
    """last_installment debe coincidir exactamente con el ajuste de centavos del calendario."""

    def test_matches_schedule_last_amount(self) -> None:
        terms = LoanTerms.create("1000", "0.05", 3, Frequency.MENSUAL, Scheme.SALDO_INSOLUTO)
        schedule = build_schedule(terms, date(2026, 1, 1))

        assert last_installment(terms) == schedule[-1].amount == Decimal("350.01")


class TestFixedPaymentNonNegativeInterest:
    """cuota_fija nunca debe producir interes negativo ni saldo negativo."""

    @pytest.mark.parametrize(
        ("principal", "rate", "periods"),
        [
            ("100", "0.05", 60),
            ("50", "0.001", 120),
            ("100", "0.01", 100),
            ("10000", "0.03", 12),
        ],
    )
    def test_schedule_is_non_negative_and_payable(
        self, principal: str, rate: str, periods: int
    ) -> None:
        terms = LoanTerms.create(principal, rate, periods, Frequency.MENSUAL, Scheme.CUOTA_FIJA)
        schedule = build_schedule(terms, date(2026, 1, 1))

        assert all(row.interest_part >= Decimal("0.00") for row in schedule)
        assert all(row.principal_part >= Decimal("0.00") for row in schedule)
        assert all(row.balance >= Decimal("0.00") for row in schedule)
        assert schedule[-1].balance == Decimal("0.00")

        total_amount, _, total_principal = schedule_totals(schedule)
        assert total_principal == terms.principal

        # El calendario generado debe ser aceptado por el motor de pagos.
        states = [
            InstallmentState(
                number=row.number,
                amount=row.amount,
                principal_part=row.principal_part,
                interest_part=row.interest_part,
            )
            for row in schedule
        ]
        allocation = allocate_payment(states, total_amount)
        assert allocation.applied == total_amount
        assert all(state.is_paid for state in allocation.new_states.values())


class TestSchemaValidations:
    """Validaciones que antes provocaban HTTP 500."""

    async def test_simulate_high_weekly_rate_does_not_overflow_response(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/loans/simulate",
                json={
                    "principal": 10000,
                    "interest_rate": "0.2000",
                    "rate_period": "semanal",
                    "scheme": "simple",
                    "term_periods": 12,
                    "start_date": "2026-11-02",
                },
            )
        assert response.status_code == 200
        assert response.json()["annual_equivalent_rate"] == "13103.6309"

    def test_loan_create_rejects_invalid_scheme_and_frequency(self) -> None:
        with pytest.raises(ValidationError):
            LoanCreate(
                client_id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
                principal=Decimal("1000.00"),
                interest_rate=Decimal("0.0500"),
                rate_period="diaria",  # type: ignore[arg-type]
                scheme="simple",
                term_periods=12,
                start_date=date(2026, 11, 2),
            )

        with pytest.raises(ValidationError):
            LoanCreate(
                client_id="00000000-0000-0000-0000-000000000001",  # type: ignore[arg-type]
                principal=Decimal("1000.00"),
                interest_rate=Decimal("0.0500"),
                rate_period="semanal",
                scheme="inventado",  # type: ignore[arg-type]
                term_periods=12,
                start_date=date(2026, 11, 2),
            )

    def test_client_update_rejects_explicit_null_and_whitespace(self) -> None:
        with pytest.raises(ValidationError):
            ClientUpdate(full_name=None)
        with pytest.raises(ValidationError):
            ClientUpdate(full_name="   ")
        # Campos opcionales sin enviar siguen funcionando.
        valid = ClientUpdate(zone="Norte")
        assert valid.zone == "Norte"

    def test_system_setting_rejects_invalid_timezone(self) -> None:
        with pytest.raises(ValidationError, match="Zona horaria"):
            SystemSettingUpdate(
                default_late_fee_rate=Decimal("0.1000"),
                default_scheme="simple",
                grace_days=0,
                timezone="Mars/Olympus_Mons",
            )
