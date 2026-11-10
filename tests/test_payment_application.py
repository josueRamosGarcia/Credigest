"""Pruebas del motor de aplicacion de pagos (RN-29 a RN-35)."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.domain.money import MoneyError
from app.domain.payment_application import (
    Concept,
    InstallmentState,
    allocate_payment,
    breakdown_by_concept,
    late_fee_covered,
    total_pending,
)


def make_installment(
    number: int,
    principal: str,
    interest: str,
    late_fee: str = "0.00",
    paid_late_fee: str = "0.00",
    paid_interest: str = "0.00",
    paid_principal: str = "0.00",
) -> InstallmentState:
    """Construye una cuota coherente para las pruebas."""
    principal_part = Decimal(principal)
    interest_part = Decimal(interest)
    return InstallmentState(
        number=number,
        amount=principal_part + interest_part,
        principal_part=principal_part,
        interest_part=interest_part,
        late_fee=Decimal(late_fee),
        paid_late_fee=Decimal(paid_late_fee),
        paid_interest=Decimal(paid_interest),
        paid_principal=Decimal(paid_principal),
    )


#: Escenario base: cuota de 1,000 con 250 de interes y 750 de capital.
def simple_installment(number: int = 1, late_fee: str = "0.00") -> InstallmentState:
    """Cuota estandar de las pruebas."""
    return make_installment(number, principal="750.00", interest="250.00", late_fee=late_fee)


class TestTotalPending:
    """Suma de lo pendiente del prestamo (RN-24)."""

    def test_empty_loan(self) -> None:
        assert total_pending([]) == Decimal("0.00")

    def test_single_installment(self) -> None:
        assert total_pending([simple_installment()]) == Decimal("1000.00")

    def test_includes_late_fee(self) -> None:
        assert total_pending([simple_installment(late_fee="50.00")]) == Decimal("1050.00")

    def test_sums_several(self) -> None:
        rows = [simple_installment(1), simple_installment(2), simple_installment(3)]
        assert total_pending(rows) == Decimal("3000.00")


class TestPaymentOrder:
    """RN-29: mora, luego interes, luego capital."""

    def test_first_goes_to_late_fee(self) -> None:
        row = simple_installment(late_fee="100.00")
        result = allocate_payment([row], "50.00")

        assert result.applications == [
            result.applications[0]
        ], "debe haber una sola aplicacion"
        assert result.applications[0].concept is Concept.MORA
        assert result.applications[0].amount == Decimal("50.00")

    def test_late_fee_before_interest(self) -> None:
        row = simple_installment(late_fee="100.00")
        result = allocate_payment([row], "150.00")

        assert len(result.applications) == 2
        assert result.applications[0].concept is Concept.MORA
        assert result.applications[1].concept is Concept.INTERES
        assert result.applications[0].amount == Decimal("100.00")
        assert result.applications[1].amount == Decimal("50.00")

    def test_interest_before_principal(self) -> None:
        row = simple_installment()
        result = allocate_payment([row], "400.00")

        assert result.applications[0].concept is Concept.INTERES
        assert result.applications[0].amount == Decimal("250.00")
        assert result.applications[1].concept is Concept.CAPITAL
        assert result.applications[1].amount == Decimal("150.00")

    def test_full_waterfall(self) -> None:
        row = simple_installment(late_fee="100.00")
        result = allocate_payment([row], "1100.00")

        concepts = [application.concept for application in result.applications]
        assert concepts == [Concept.MORA, Concept.INTERES, Concept.CAPITAL]
        assert result.applied == Decimal("1100.00")
        assert result.unapplied == Decimal("0.00")


class TestOldestFirst:
    """La cuota mas antigua se cubre primero."""

    def test_covers_first_installment_fully(self) -> None:
        rows = [
            make_installment(1, principal="750.00", interest="250.00"),
            make_installment(2, principal="750.00", interest="250.00"),
        ]
        result = allocate_payment(rows, "1000.00")

        numbers = {application.installment_number for application in result.applications}
        assert numbers == {1}

    def test_spills_into_second_installment(self) -> None:
        rows = [
            make_installment(1, principal="750.00", interest="250.00"),
            make_installment(2, principal="750.00", interest="250.00"),
        ]
        result = allocate_payment(rows, "1200.00")

        assert result.covers_multiple_installments is True
        assert result.new_states[1].is_paid is True
        assert result.new_states[2].paid_interest == Decimal("200.00")

    def test_ignores_input_order(self) -> None:
        rows = [
            make_installment(2, principal="750.00", interest="250.00"),
            make_installment(1, principal="750.00", interest="250.00"),
        ]
        result = allocate_payment(rows, "1000.00")

        assert result.new_states[1].is_paid is True
        assert result.new_states[2].paid_amount == Decimal("0.00")


class TestPartialPayments:
    """Pagos parciales (RN-31)."""

    def test_partial_leaves_installment_partial(self) -> None:
        row = simple_installment()
        result = allocate_payment([row], "400.00")

        state = result.new_states[1]
        assert state.status_after_payment == "parcial"
        assert state.pending_total == Decimal("600.00")

    def test_partial_of_late_fee_only(self) -> None:
        row = simple_installment(late_fee="100.00")
        result = allocate_payment([row], "30.00")

        state = result.new_states[1]
        assert state.pending_late_fee == Decimal("70.00")
        assert state.pending_interest == Decimal("250.00")
        assert state.status_after_payment == "parcial"

    def test_exact_payment_closes_installment(self) -> None:
        row = simple_installment(late_fee="50.00")
        result = allocate_payment([row], "1050.00")

        state = result.new_states[1]
        assert state.is_paid is True
        assert state.status_after_payment == "pagada"
        assert state.pending_total == Decimal("0.00")


class TestAdvancePayments:
    """Pagos adelantados: cubren cuotas futuras sin cambiar fechas (RN-35)."""

    def test_pays_three_installments_in_advance(self) -> None:
        rows = [
            make_installment(number, principal="750.00", interest="250.00")
            for number in range(1, 4)
        ]
        result = allocate_payment(rows, "3000.00")

        assert all(result.new_states[number].is_paid for number in (1, 2, 3))
        assert result.unapplied == Decimal("0.00")

    def test_advance_stops_when_money_runs_out(self) -> None:
        rows = [
            make_installment(number, principal="750.00", interest="250.00")
            for number in range(1, 4)
        ]
        result = allocate_payment(rows, "2500.00")

        assert result.new_states[1].is_paid is True
        assert result.new_states[2].is_paid is True
        assert result.new_states[3].paid_amount == Decimal("500.00")

    def test_skips_installments_already_paid(self) -> None:
        rows = [
            make_installment(
                1,
                principal="750.00",
                interest="250.00",
                paid_principal="750.00",
                paid_interest="250.00",
            ),
            make_installment(2, principal="750.00", interest="250.00"),
        ]
        result = allocate_payment(rows, "1000.00")

        assert result.applications[0].installment_number == 2


class TestValidation:
    """Errores que deben rechazarse antes de tocar la base."""

    def test_rejects_zero(self) -> None:
        with pytest.raises(MoneyError, match="mayor que cero"):
            allocate_payment([simple_installment()], "0")

    def test_rejects_negative(self) -> None:
        with pytest.raises(MoneyError, match="mayor que cero"):
            allocate_payment([simple_installment()], "-100")

    def test_rejects_float(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            allocate_payment([simple_installment()], 100.0)  # type: ignore[arg-type]

    def test_rejects_more_than_pending(self) -> None:
        """RN-24: no se acepta un pago mayor al saldo total."""
        with pytest.raises(MoneyError, match="excede"):
            allocate_payment([simple_installment()], "1000.01")

    def test_rejects_duplicate_installments(self) -> None:
        rows = [simple_installment(1), simple_installment(1)]
        with pytest.raises(MoneyError, match="repetida"):
            allocate_payment(rows, "100.00")

    def test_rejects_inconsistent_installment(self) -> None:
        broken = InstallmentState(
            number=1,
            amount=Decimal("1000.00"),
            principal_part=Decimal("600.00"),
            interest_part=Decimal("300.00"),
        )
        with pytest.raises(MoneyError, match="no cuadra"):
            allocate_payment([broken], "100.00")

    def test_rejects_negative_amount(self) -> None:
        broken = InstallmentState(
            number=1,
            amount=Decimal("0.00"),
            principal_part=Decimal("0.00"),
            interest_part=Decimal("0.00"),
            late_fee=Decimal("-5.00"),
        )
        with pytest.raises(MoneyError, match="negativo"):
            allocate_payment([broken], "10.00")

    def test_rejects_overpaid_late_fee(self) -> None:
        broken = make_installment(
            1, principal="750.00", interest="250.00", late_fee="10.00", paid_late_fee="20.00"
        )
        with pytest.raises(MoneyError, match="mas mora"):
            allocate_payment([broken], "10.00")

    def test_rejects_overpaid_interest(self) -> None:
        broken = make_installment(
            1, principal="750.00", interest="250.00", paid_interest="300.00"
        )
        with pytest.raises(MoneyError, match="mas interes"):
            allocate_payment([broken], "10.00")

    def test_rejects_overpaid_principal(self) -> None:
        broken = make_installment(
            1, principal="750.00", interest="250.00", paid_principal="800.00"
        )
        with pytest.raises(MoneyError, match="mas capital"):
            allocate_payment([broken], "10.00")

    def test_rejects_invalid_number(self) -> None:
        broken = make_installment(0, principal="750.00", interest="250.00")
        with pytest.raises(MoneyError, match="numero de cuota"):
            allocate_payment([broken], "10.00")


class TestBreakdown:
    """Desglose para el comprobante y el dashboard."""

    def test_breakdown_sums_each_concept(self) -> None:
        row = simple_installment(late_fee="100.00")
        result = allocate_payment([row], "1100.00")

        breakdown = breakdown_by_concept(result)
        assert breakdown[Concept.MORA] == Decimal("100.00")
        assert breakdown[Concept.INTERES] == Decimal("250.00")
        assert breakdown[Concept.CAPITAL] == Decimal("750.00")

    def test_breakdown_of_partial(self) -> None:
        result = allocate_payment([simple_installment()], "400.00")
        breakdown = breakdown_by_concept(result)

        assert breakdown[Concept.MORA] == Decimal("0.00")
        assert breakdown[Concept.INTERES] == Decimal("250.00")
        assert breakdown[Concept.CAPITAL] == Decimal("150.00")

    def test_late_fee_covered(self) -> None:
        row = simple_installment(late_fee="100.00")
        result = allocate_payment([row], "150.00")

        assert late_fee_covered(result) == Decimal("100.00")

    def test_late_fee_covered_when_none(self) -> None:
        result = allocate_payment([simple_installment()], "400.00")
        assert late_fee_covered(result) == Decimal("0.00")

    def test_applied_plus_unapplied_equals_amount(self) -> None:
        """El dinero nunca se pierde ni se crea."""
        rows = [simple_installment(1), simple_installment(2)]
        result = allocate_payment(rows, "1500.00")

        assert result.applied + result.unapplied == Decimal("1500.00")

    def test_applications_sum_to_applied(self) -> None:
        rows = [simple_installment(1, late_fee="20.00"), simple_installment(2)]
        result = allocate_payment(rows, "1200.00")

        total = sum((application.amount for application in result.applications), Decimal("0"))
        assert total == result.applied


class TestRounding:
    """Centavos: el reparto debe cuadrar al centavo."""

    def test_odd_amount_splits_cleanly(self) -> None:
        rows = [make_installment(1, principal="333.33", interest="0.01")]
        result = allocate_payment(rows, "333.34")

        assert result.new_states[1].is_paid is True
        assert result.applied == Decimal("333.34")

    def test_repeated_partial_payments_reach_zero(self) -> None:
        """Diez pagos de 100 deben liquidar una cuota de 1000."""
        row = simple_installment()
        state = row

        for _ in range(10):
            result = allocate_payment([state], "100.00")
            state = result.new_states[1]

        assert state.is_paid is True
        assert state.pending_total == Decimal("0.00")

    def test_status_after_first_penny(self) -> None:
        result = allocate_payment([simple_installment()], "0.01")
        assert result.new_states[1].status_after_payment == "parcial"


class TestAllocationDataclass:
    """Propiedades del resultado."""

    def test_single_installment_flag(self) -> None:
        result = allocate_payment([simple_installment()], "100.00")
        assert result.covers_multiple_installments is False

    def test_empty_applications_for_zero_pending(self) -> None:
        """Un prestamo ya pagado no genera aplicaciones."""
        row = make_installment(
            1,
            principal="750.00",
            interest="250.00",
            paid_principal="750.00",
            paid_interest="250.00",
        )
        with pytest.raises(MoneyError):
            allocate_payment([row], "100.00")

    def test_allocation_is_immutable(self) -> None:
        result = allocate_payment([simple_installment()], "100.00")
        with pytest.raises(FrozenInstanceError):
            result.applied = Decimal("0")  # type: ignore[misc]

    def test_new_states_cover_every_installment(self) -> None:
        rows = [simple_installment(1), simple_installment(2), simple_installment(3)]
        result = allocate_payment(rows, "500.00")

        assert set(result.new_states) == {1, 2, 3}
