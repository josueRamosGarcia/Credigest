"""Pruebas de las tablas de amortizacion.

Los valores se verificaron a mano contra docs/03-reglas-de-negocio.md.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.amortization import build_schedule, schedule_totals
from app.domain.interest import Frequency, LoanTerms, Scheme

START = date(2026, 1, 5)


class TestScheduleInvariants:
    """Propiedades que debe cumplir toda tabla, sin importar el esquema."""

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_number_of_rows_matches_term(self, scheme: Scheme) -> None:
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        schedule = build_schedule(terms, START)
        assert len(schedule) == 12

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_numbering_is_sequential(self, scheme: Scheme) -> None:
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        schedule = build_schedule(terms, START)
        assert [row.number for row in schedule] == list(range(1, 13))

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_last_balance_is_zero(self, scheme: Scheme) -> None:
        """RN-03: el saldo final debe ser exactamente cero."""
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        schedule = build_schedule(terms, START)
        assert schedule[-1].balance == Decimal("0.00")

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_principal_sums_to_loan_amount(self, scheme: Scheme) -> None:
        """RN-03: la suma de capital debe ser igual al monto prestado."""
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        schedule = build_schedule(terms, START)
        _, _, total_principal = schedule_totals(schedule)
        assert total_principal == terms.principal

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_each_row_adds_up(self, scheme: Scheme) -> None:
        """Cuota = interes + capital en cada fila."""
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        for row in build_schedule(terms, START):
            assert row.amount == row.interest_part + row.principal_part

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_balance_is_monotonically_decreasing(self, scheme: Scheme) -> None:
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        schedule = build_schedule(terms, START)
        balances = [row.balance for row in schedule]
        assert balances == sorted(balances, reverse=True)
        assert len(set(balances)) == len(balances)

    def test_rejects_unknown_scheme(self) -> None:
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, Scheme.SIMPLE)
        # Se reemplaza el esquema por uno inexistente para cubrir la guarda.
        object.__setattr__(terms, "scheme", "inventado")
        with pytest.raises(ValueError, match="no soportado"):
            build_schedule(terms, START)

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_is_last_only_marks_the_final_installment(self, scheme: Scheme) -> None:
        terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, scheme)
        schedule = build_schedule(terms, START)

        assert schedule[-1].is_last is True
        assert all(row.is_last is False for row in schedule[:-1])


class TestSimpleSchedule:
    """RN-12: 10,000 a 12 semanas con 5% semanal."""

    terms = LoanTerms.create("10000", "0.05", 12, Frequency.SEMANAL, Scheme.SIMPLE)
    schedule = build_schedule(terms, START)

    def test_installment_is_constant(self) -> None:
        amounts = {row.amount for row in self.schedule[:-1]}
        assert amounts == {Decimal("1333.33")}

    def test_interest_is_constant(self) -> None:
        """En el esquema simple el interes siempre se cobra sobre el capital original."""
        interests = {row.interest_part for row in self.schedule[:-1]}
        assert interests == {Decimal("500.00")}

    def test_first_row_details(self) -> None:
        first = self.schedule[0]
        assert first.number == 1
        assert first.due_date == date(2026, 1, 12)
        assert first.amount == Decimal("1333.33")
        assert first.interest_part == Decimal("500.00")
        assert first.principal_part == Decimal("833.33")
        assert first.balance == Decimal("9166.67")

    def test_totals(self) -> None:
        total_amount, total_interest, total_principal = schedule_totals(self.schedule)
        assert total_principal == Decimal("10000.00")
        assert total_interest == Decimal("6000.00")
        assert total_amount == Decimal("16000.00")


class TestDecliningSchedule:
    """RN-13: 10,000 a 4 meses con 3% sobre saldo insoluto."""

    terms = LoanTerms.create("10000", "0.03", 4, Frequency.MENSUAL, Scheme.SALDO_INSOLUTO)
    schedule = build_schedule(terms, START)

    def test_matches_documented_table(self) -> None:
        expected = [
            (Decimal("2800.00"), Decimal("300.00"), Decimal("2500.00"), Decimal("7500.00")),
            (Decimal("2725.00"), Decimal("225.00"), Decimal("2500.00"), Decimal("5000.00")),
            (Decimal("2650.00"), Decimal("150.00"), Decimal("2500.00"), Decimal("2500.00")),
            (Decimal("2575.00"), Decimal("75.00"), Decimal("2500.00"), Decimal("0.00")),
        ]
        actual = [(r.amount, r.interest_part, r.principal_part, r.balance) for r in self.schedule]
        assert actual == expected

    def test_installment_decreases(self) -> None:
        amounts = [row.amount for row in self.schedule]
        assert amounts == sorted(amounts, reverse=True)

    def test_totals(self) -> None:
        total_amount, total_interest, total_principal = schedule_totals(self.schedule)
        assert total_principal == Decimal("10000.00")
        assert total_interest == Decimal("750.00")
        assert total_amount == Decimal("10750.00")


class TestFixedPaymentSchedule:
    """RN-09: 10,000 a 12 meses con 3% de cuota fija."""

    terms = LoanTerms.create("10000", "0.03", 12, Frequency.MENSUAL, Scheme.CUOTA_FIJA)
    schedule = build_schedule(terms, START)

    def test_installment_is_constant_except_last(self) -> None:
        amounts = {row.amount for row in self.schedule[:-1]}
        assert amounts == {Decimal("1004.62")}

    def test_first_row_details(self) -> None:
        first = self.schedule[0]
        assert first.interest_part == Decimal("300.00")
        assert first.principal_part == Decimal("704.62")
        assert first.balance == Decimal("9295.38")

    def test_interest_decreases(self) -> None:
        interests = [row.interest_part for row in self.schedule]
        assert interests == sorted(interests, reverse=True)

    def test_principal_increases(self) -> None:
        principals = [row.principal_part for row in self.schedule[:-1]]
        assert principals == sorted(principals)

    def test_totals(self) -> None:
        total_amount, total_interest, total_principal = schedule_totals(self.schedule)
        assert total_principal == Decimal("10000.00")
        assert total_interest == Decimal("2055.44")
        assert total_amount == Decimal("12055.44")


class TestRoundingAdjustment:
    """RN-03: el ultimo periodo absorbe la diferencia de centavos."""

    def test_odd_amount_splits_exactly(self) -> None:
        """Un monto que no se divide exacto entre 3 debe cuadrar al final."""
        terms = LoanTerms.create("1000", "0", 3, Frequency.MENSUAL, Scheme.SALDO_INSOLUTO)
        schedule = build_schedule(terms, START)

        assert schedule[-1].balance == Decimal("0.00")
        _, _, total_principal = schedule_totals(schedule)
        assert total_principal == Decimal("1000.00")

    def test_simple_with_odd_division(self) -> None:
        terms = LoanTerms.create("100", "0.10", 3, Frequency.SEMANAL, Scheme.SIMPLE)
        schedule = build_schedule(terms, START)

        assert schedule[-1].balance == Decimal("0.00")
        _, _, total_principal = schedule_totals(schedule)
        assert total_principal == Decimal("100.00")

    def test_fixed_payment_with_odd_division(self) -> None:
        terms = LoanTerms.create("100", "0.10", 3, Frequency.SEMANAL, Scheme.CUOTA_FIJA)
        schedule = build_schedule(terms, START)

        assert schedule[-1].balance == Decimal("0.00")
        _, _, total_principal = schedule_totals(schedule)
        assert total_principal == Decimal("100.00")


class TestSinglePeriod:
    """Casos limite: prestamos de un solo periodo."""

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_one_installment_pays_everything(self, scheme: Scheme) -> None:
        terms = LoanTerms.create("1000", "0.10", 1, Frequency.MENSUAL, scheme)
        schedule = build_schedule(terms, START)

        assert len(schedule) == 1
        assert schedule[0].principal_part == Decimal("1000.00")
        assert schedule[0].balance == Decimal("0.00")
        assert schedule[0].amount == Decimal("1100.00")


class TestZeroRate:
    """Con tasa cero el interes debe ser cero en todos los esquemas."""

    @pytest.mark.parametrize("scheme", list(Scheme))
    def test_no_interest(self, scheme: Scheme) -> None:
        terms = LoanTerms.create("1200", "0", 12, Frequency.MENSUAL, scheme)
        schedule = build_schedule(terms, START)

        assert all(row.interest_part == Decimal("0.00") for row in schedule)
        total_amount, total_interest, total_principal = schedule_totals(schedule)
        assert total_interest == Decimal("0.00")
        assert total_principal == Decimal("1200.00")
        assert total_amount == Decimal("1200.00")
