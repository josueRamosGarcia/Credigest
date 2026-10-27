"""Pruebas del calculo de mora.

Los valores esperados siguen el ejemplo de docs/03-reglas-de-negocio.md:
cuota de $1,000 con 10 dias de atraso, 5 dias de gracia y 10 % mensual:

    dias_efectivos = 10 - 5 = 5
    mora = 1,000 * 0.10 * (5 / 30) = 16.67
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.late_fee import (
    LateFee,
    calculate_late_fee,
    chargeable_days,
    days_late,
    is_overdue,
    resolve_late_fee_rate,
    total_pending_with_late_fee,
)
from app.domain.money import MoneyError

DUE = date(2026, 10, 1)


class TestDaysLate:
    """RN-18: dias transcurridos desde el vencimiento."""

    def test_zero_before_due_date(self) -> None:
        assert days_late(DUE, date(2026, 9, 25)) == 0

    def test_zero_on_due_date(self) -> None:
        assert days_late(DUE, DUE) == 0

    def test_one_day_after(self) -> None:
        assert days_late(DUE, date(2026, 10, 2)) == 1

    def test_ten_days_after(self) -> None:
        assert days_late(DUE, date(2026, 10, 11)) == 10

    def test_across_month_boundary(self) -> None:
        assert days_late(date(2026, 10, 31), date(2026, 11, 2)) == 2

    def test_across_year_boundary(self) -> None:
        assert days_late(date(2026, 12, 30), date(2027, 1, 2)) == 3

    def test_document_due_date_ten_days_apart(self) -> None:
        assert days_late(DUE, DUE + timedelta(days=10)) == 10


class TestChargeableDays:
    """RN-19: la gracia se descuenta de los dias de atraso."""

    def test_no_grace_subtracts_nothing(self) -> None:
        assert chargeable_days(DUE, date(2026, 10, 11), 0) == 10

    def test_grace_five_of_ten_leaves_five(self) -> None:
        assert chargeable_days(DUE, date(2026, 10, 11), 5) == 5

    def test_grace_covers_all_lateness(self) -> None:
        assert chargeable_days(DUE, date(2026, 10, 4), 10) == 0

    def test_grace_exactly_equal_to_lateness(self) -> None:
        assert chargeable_days(DUE, date(2026, 10, 6), 5) == 0

    def test_not_overdue_yet(self) -> None:
        assert chargeable_days(DUE, date(2026, 9, 20), 0) == 0

    def test_rejects_negative_grace(self) -> None:
        with pytest.raises(MoneyError, match="negativos"):
            chargeable_days(DUE, date(2026, 10, 11), -1)

    def test_rejects_bool_grace(self) -> None:
        with pytest.raises(MoneyError, match="entero"):
            chargeable_days(DUE, date(2026, 10, 11), True)  # type: ignore[arg-type]


class TestIsOverdue:
    """RN-17: una cuota vencida tiene la fecha pasada y no esta pagada."""

    def test_before_due_date(self) -> None:
        assert is_overdue(DUE, date(2026, 9, 30)) is False

    def test_on_due_date(self) -> None:
        assert is_overdue(DUE, DUE) is False

    def test_after_due_date(self) -> None:
        assert is_overdue(DUE, date(2026, 10, 2)) is True

    def test_paid_is_never_overdue(self) -> None:
        assert is_overdue(DUE, date(2026, 12, 1), is_paid=True) is False


class TestCalculateLateFee:
    """RN-19: formula del recargo."""

    def test_document_example(self) -> None:
        """Cuota de 1,000 con 10 dias de atraso, 5 de gracia y 10 % mensual."""
        result = calculate_late_fee(
            balance="1000",
            rate="0.10",
            due_date=DUE,
            today=date(2026, 10, 11),
            grace_days=5,
        )

        assert result.days_late == 10
        assert result.chargeable_days == 5
        assert result.balance == Decimal("1000.00")
        assert result.rate == Decimal("0.1000")
        assert result.amount == Decimal("16.67")
        assert result.is_chargeable is True

    def test_without_grace(self) -> None:
        """10 dias completos: 1,000 * 0.10 * 10/30 = 33.33."""
        result = calculate_late_fee("1000", "0.10", DUE, date(2026, 10, 11))
        assert result.amount == Decimal("33.33")

    def test_thirty_days_equals_full_month(self) -> None:
        """30 dias de atraso sin gracia equivalen a un mes completo."""
        result = calculate_late_fee("1000", "0.10", DUE, date(2026, 10, 31))
        assert result.amount == Decimal("100.00")

    def test_sixty_days_is_two_months(self) -> None:
        result = calculate_late_fee("1000", "0.10", DUE, date(2026, 11, 30))
        assert result.amount == Decimal("200.00")

    def test_not_overdue_yet_returns_zero(self) -> None:
        result = calculate_late_fee("1000", "0.10", DUE, date(2026, 9, 20))
        assert result.amount == Decimal("0.00")
        assert result.is_chargeable is False

    def test_grace_not_exhausted_returns_zero(self) -> None:
        result = calculate_late_fee("1000", "0.10", DUE, date(2026, 10, 4), grace_days=5)
        assert result.amount == Decimal("0.00")
        assert result.days_late == 3
        assert result.chargeable_days == 0

    def test_zero_rate_returns_zero(self) -> None:
        result = calculate_late_fee("1000", "0", DUE, date(2026, 11, 15))
        assert result.amount == Decimal("0.00")

    def test_zero_balance_returns_zero(self) -> None:
        result = calculate_late_fee("0", "0.10", DUE, date(2026, 11, 15))
        assert result.amount == Decimal("0.00")

    def test_paid_installment_has_no_late_fee(self) -> None:
        result = calculate_late_fee("1000", "0.10", DUE, date(2026, 12, 1), is_paid=True)
        assert result.amount == Decimal("0.00")
        assert result.chargeable_days == 0

    def test_partial_balance(self) -> None:
        """Solo se cobra mora sobre lo que sigue pendiente."""
        result = calculate_late_fee("400", "0.10", DUE, date(2026, 10, 31))
        assert result.amount == Decimal("40.00")

    def test_small_balance_rounds_correctly(self) -> None:
        """50 * 0.10 * 5/30 = 0.8333 -> 0.83."""
        result = calculate_late_fee("50", "0.10", DUE, date(2026, 10, 6), grace_days=0)
        assert result.amount == Decimal("0.83")

    def test_rounds_half_up(self) -> None:
        """El redondeo comercial debe subir en el medio centavo."""
        result = calculate_late_fee("15", "0.10", DUE, date(2026, 10, 6))
        # 15 * 0.10 * 5 / 30 = 0.25 exacto
        assert result.amount == Decimal("0.25")

    def test_is_not_compound(self) -> None:
        """RN-21: la mora no se calcula sobre mora anterior."""
        first = calculate_late_fee("1000", "0.10", DUE, date(2026, 11, 30))
        second = calculate_late_fee("1000", "0.10", DUE, date(2026, 11, 30))

        assert first.amount == second.amount == Decimal("200.00")

    def test_rejects_negative_balance(self) -> None:
        with pytest.raises(MoneyError, match="negativo"):
            calculate_late_fee("-100", "0.10", DUE, date(2026, 11, 1))

    def test_rejects_negative_rate(self) -> None:
        with pytest.raises(MoneyError, match="negativo"):
            calculate_late_fee("1000", "-0.10", DUE, date(2026, 11, 1))

    def test_rejects_float_balance(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            calculate_late_fee(1000.0, "0.10", DUE, date(2026, 11, 1))  # type: ignore[arg-type]

    def test_rejects_float_rate(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            calculate_late_fee("1000", 0.10, DUE, date(2026, 11, 1))  # type: ignore[arg-type]


class TestResolveRate:
    """RN-22: la tasa del prestamo prevalece sobre la global."""

    def test_uses_loan_rate_when_defined(self) -> None:
        assert resolve_late_fee_rate("0.15", "0.10") == Decimal("0.1500")

    def test_falls_back_to_global(self) -> None:
        assert resolve_late_fee_rate(None, "0.10") == Decimal("0.1000")

    def test_zero_loan_rate_is_respected(self) -> None:
        """Cero es un valor valido: significa que el prestamo no cobra mora."""
        assert resolve_late_fee_rate("0", "0.10") == Decimal("0.0000")

    def test_rejects_negative_loan_rate(self) -> None:
        with pytest.raises(MoneyError, match="negativo"):
            resolve_late_fee_rate("-0.05", "0.10")

    def test_rejects_negative_global_rate(self) -> None:
        with pytest.raises(MoneyError, match="negativo"):
            resolve_late_fee_rate(None, "-0.10")


class TestTotalPending:
    """Monto que el cobrador debe recibir para cerrar la cuota hoy."""

    def test_adds_late_fee_to_pending(self) -> None:
        fee = calculate_late_fee("1000", "0.10", DUE, date(2026, 10, 11), grace_days=5)
        total = total_pending_with_late_fee(Decimal("1000.00"), fee)
        assert total == Decimal("1016.67")

    def test_zero_fee_keeps_pending(self) -> None:
        fee = LateFee(
            days_late=0,
            chargeable_days=0,
            balance=Decimal("500.00"),
            rate=Decimal("0.1000"),
            amount=Decimal("0.00"),
        )
        assert total_pending_with_late_fee(Decimal("500.00"), fee) == Decimal("500.00")

    def test_rejects_negative_pending(self) -> None:
        fee = calculate_late_fee("1000", "0.10", DUE, date(2026, 10, 11))
        with pytest.raises(MoneyError, match="negativo"):
            total_pending_with_late_fee(Decimal("-1"), fee)


class TestGracePeriodBoundaries:
    """Casos limite de la ventana de gracia."""

    @pytest.mark.parametrize(
        ("day_offset", "grace", "expected"),
        [
            (0, 0, 0),
            (0, 5, 0),
            (1, 0, 1),
            (4, 5, 0),
            (5, 5, 0),
            (6, 5, 1),
            (30, 0, 30),
            (30, 30, 0),
            (31, 30, 1),
        ],
    )
    def test_chargeable_days_table(self, day_offset: int, grace: int, expected: int) -> None:
        today = DUE + timedelta(days=day_offset)
        assert chargeable_days(DUE, today, grace) == expected
