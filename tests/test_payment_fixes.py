"""Pruebas unitarias para correcciones criticas de pagos y mora.

No requieren PostgreSQL: prueban directamente la logica de reparto con pagos
anulados, estados de cuotas tras anulacion y devengo de mora no decreciente.
"""

from datetime import date
from decimal import Decimal

from app.domain.payment_application import Concept, allocate_payment
from app.models.loan import Installment, Loan
from app.models.payment import Payment, PaymentApplication
from app.scripts.accrue_late_fees import _base_overdue_balance, compute_accrued_late_fee
from app.services.payment_service import _paid_for, _status_for, _to_state


def _make_installment(
    *,
    number: int = 1,
    due_date: date = date(2026, 10, 1),
    amount: str = "1000.00",
    principal: str = "700.00",
    interest: str = "300.00",
    late_fee: str = "0.00",
    paid_amount: str = "0.00",
    late_fee_calculated_on: date | None = None,
    applications: list[PaymentApplication] | None = None,
) -> Installment:
    inst = Installment(
        number=number,
        due_date=due_date,
        amount=Decimal(amount),
        principal_part=Decimal(principal),
        interest_part=Decimal(interest),
        late_fee=Decimal(late_fee),
        paid_amount=Decimal(paid_amount),
        status="pendiente",
        late_fee_calculated_on=late_fee_calculated_on,
    )
    inst.applications = applications or []
    return inst


def _make_app(concept: str, amount: str, *, status: str = "aplicado") -> PaymentApplication:
    payment = Payment(folio="PAGO-TEST-2026-00001", amount=Decimal(amount), status=status)
    app = PaymentApplication(concept=concept, amount=Decimal(amount))
    app.payment = payment
    return app


class TestCancelledApplicationsIgnored:
    """Los pagos anulados nunca deben contar como saldo ya cubierto."""

    def test_paid_for_ignores_cancelled_payments(self) -> None:
        inst = _make_installment(
            applications=[
                _make_app("interes", "300.00", status="anulado"),
                _make_app("capital", "700.00", status="anulado"),
            ]
        )

        assert _paid_for(inst, Concept.INTERES) == Decimal("0.00")
        assert _paid_for(inst, Concept.CAPITAL) == Decimal("0.00")

        state = _to_state(inst)
        assert state.pending_total == Decimal("1000.00")

        # Debe permitir volver a cobrar la cuota completa tras anular el pago anterior.
        allocation = allocate_payment([state], "1000.00")
        assert allocation.applied == Decimal("1000.00")
        assert allocation.new_states[1].is_paid is True

    def test_paid_for_keeps_applied_and_ignores_cancelled(self) -> None:
        inst = _make_installment(
            paid_amount="300.00",
            applications=[
                _make_app("interes", "300.00", status="aplicado"),
                _make_app("capital", "700.00", status="anulado"),
            ],
        )

        assert _paid_for(inst, Concept.INTERES) == Decimal("300.00")
        assert _paid_for(inst, Concept.CAPITAL) == Decimal("0.00")
        assert _to_state(inst).pending_total == Decimal("700.00")

    def test_base_overdue_balance_ignores_cancelled_payments(self) -> None:
        inst = _make_installment(
            applications=[
                _make_app("interes", "300.00", status="anulado"),
                _make_app("capital", "400.00", status="anulado"),
            ]
        )

        assert _base_overdue_balance(inst) == Decimal("1000.00")


class TestCancelStatusTransition:
    """Al anular un segundo pago, una cuota con pago previo queda en parcial."""

    def test_partial_status_preserved_when_future_due_date(self) -> None:
        inst = _make_installment(due_date=date(2026, 12, 1), paid_amount="300.00")
        assert _status_for(inst, date(2026, 11, 20), is_paid=False, has_payment=True) == "parcial"

    def test_overdue_status_when_past_due_date(self) -> None:
        inst = _make_installment(due_date=date(2026, 10, 1), paid_amount="300.00")
        assert _status_for(inst, date(2026, 11, 20), is_paid=False, has_payment=True) == "vencida"


class TestAccruedLateFeeNonDecreasing:
    """La mora devengada nunca debe bajar por debajo de lo ya pagado."""

    def test_partial_payment_does_not_reduce_late_fee_below_paid(self) -> None:
        due = date(2026, 10, 1)
        loan = Loan(late_fee_rate=Decimal("0.1000"), grace_days=0)

        # Dia 30: mora acumulada = 1000 * 0.10 * 30/30 = 100.00.
        # El cliente paga 100 de mora + 800 de cuota (saldo vencido baja a 200).
        inst = _make_installment(
            due_date=due,
            amount="1000.00",
            late_fee="100.00",
            paid_amount="900.00",
            late_fee_calculated_on=date(2026, 10, 31),
            applications=[
                _make_app("mora", "100.00", status="aplicado"),
                _make_app("interes", "300.00", status="aplicado"),
                _make_app("capital", "500.00", status="aplicado"),
            ],
        )

        # Dia 31 (1 dia adicional sobre saldo vencido de 200): 200 * 0.10 / 30 = 0.67.
        new_fee = compute_accrued_late_fee(inst, loan, date(2026, 11, 1))
        assert new_fee == Decimal("100.67")
        assert new_fee >= Decimal("100.00")

        # Verificar que el estado resultante sigue siendo valido para recibir pagos.
        inst.late_fee = new_fee
        state = _to_state(inst)
        allocation = allocate_payment([state], "200.67")
        assert allocation.new_states[1].is_paid is True

    def test_idempotent_same_day_after_calculated(self) -> None:
        due = date(2026, 10, 1)
        loan = Loan(late_fee_rate=Decimal("0.1000"), grace_days=5)
        inst = _make_installment(
            due_date=due,
            amount="1000.00",
            late_fee="16.67",
            late_fee_calculated_on=date(2026, 10, 11),
        )

        assert compute_accrued_late_fee(inst, loan, date(2026, 10, 11)) == Decimal("16.67")
