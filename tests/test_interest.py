"""Pruebas de los esquemas de interes con ejemplos calculados a mano.

Los valores esperados se tomaron de docs/03-reglas-de-negocio.md, seccion 3.
Cada prueba documenta la operacion aritmetica para que se pueda verificar sin
ejecutar el codigo.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.interest import (
    Frequency,
    LoanTerms,
    Scheme,
    annual_equivalent_rate,
    annuity_payment,
    due_date,
    end_date,
    first_installment,
    last_installment,
    simple_installment,
    simple_interest_total,
    total_amount,
    total_interest,
)
from app.domain.money import MoneyError


class TestDueDate:
    """RN-07: las fechas se calculan desde el inicio, no desde la cuota previa."""

    def test_weekly(self) -> None:
        assert due_date(date(2026, 1, 5), Frequency.SEMANAL, 1) == date(2026, 1, 12)
        assert due_date(date(2026, 1, 5), Frequency.SEMANAL, 4) == date(2026, 2, 2)

    def test_fortnightly_are_exactly_fifteen_days(self) -> None:
        assert due_date(date(2026, 1, 1), Frequency.QUINCENAL, 1) == date(2026, 1, 16)
        assert due_date(date(2026, 1, 1), Frequency.QUINCENAL, 2) == date(2026, 1, 31)

    def test_monthly_does_not_drift(self) -> None:
        """31 de enero + 1 mes debe ser 28 de febrero, no 3 de marzo."""
        assert due_date(date(2026, 1, 31), Frequency.MENSUAL, 1) == date(2026, 2, 28)
        assert due_date(date(2026, 1, 31), Frequency.MENSUAL, 2) == date(2026, 3, 31)

    def test_rejects_zero_period(self) -> None:
        with pytest.raises(MoneyError):
            due_date(date(2026, 1, 1), Frequency.MENSUAL, 0)


class TestLoanTermsValidation:
    """RN-10 y RN-11: validaciones de entrada."""

    def test_rejects_zero_principal(self) -> None:
        with pytest.raises(MoneyError, match="principal"):
            LoanTerms.create(principal="0", rate="0.05", periods=12)

    def test_rejects_negative_principal(self) -> None:
        with pytest.raises(MoneyError):
            LoanTerms.create(principal="-100", rate="0.05", periods=12)

    def test_rejects_negative_rate(self) -> None:
        with pytest.raises(MoneyError, match="tasa"):
            LoanTerms.create(principal="10000", rate="-0.01", periods=12)

    def test_rejects_zero_periods(self) -> None:
        with pytest.raises(MoneyError, match="plazo"):
            LoanTerms.create(principal="10000", rate="0.05", periods=0)

    def test_rejects_non_integer_periods(self) -> None:
        with pytest.raises(MoneyError, match="entero"):
            LoanTerms.create(principal="10000", rate="0.05", periods=True)  # type: ignore[arg-type]

    def test_rejects_float_principal(self) -> None:
        with pytest.raises(MoneyError, match="float"):
            LoanTerms.create(principal=10000.0, rate="0.05", periods=12)

    def test_allows_zero_rate(self) -> None:
        terms = LoanTerms.create(principal="1200", rate="0", periods=12)
        assert terms.rate == Decimal("0.0000")

    def test_normalizes_values(self) -> None:
        terms = LoanTerms.create(principal="10000", rate="0.05", periods=12)
        assert terms.principal == Decimal("10000.00")
        assert terms.rate == Decimal("0.0500")


class TestSimpleScheme:
    """RN-12: interes simple sobre capital original.

    Ejemplo del documento: 10,000 a 12 semanas con 5% semanal.
        interes total = 10,000 * 0.05 * 12 = 6,000.00
        cuota         = (10,000 + 6,000) / 12 = 1,333.33
        total         = 16,000.00
    """

    terms = LoanTerms.create(
        principal="10000",
        rate="0.05",
        periods=12,
        frequency=Frequency.SEMANAL,
        scheme=Scheme.SIMPLE,
    )

    def test_total_interest(self) -> None:
        assert simple_interest_total(self.terms) == Decimal("6000.00")

    def test_installment(self) -> None:
        assert simple_installment(self.terms) == Decimal("1333.33")

    def test_first_and_last_are_equal(self) -> None:
        assert first_installment(self.terms) == last_installment(self.terms)

    def test_total_interest_method(self) -> None:
        assert total_interest(self.terms) == Decimal("6000.00")

    def test_total_amount(self) -> None:
        assert total_amount(self.terms) == Decimal("16000.00")

    def test_end_date(self) -> None:
        assert end_date(self.terms, date(2026, 11, 2)) == date(2027, 1, 25)


class TestDecliningScheme:
    """RN-13: interes sobre saldo insoluto.

    Ejemplo del documento: 10,000 a 4 meses con 3% mensual.
        cuota 1 = 2,500 capital + 300 interes = 2,800
        cuota 2 = 2,500 capital + 225 interes = 2,725
        cuota 3 = 2,500 capital + 150 interes = 2,650
        cuota 4 = 2,500 capital +  75 interes = 2,575
        interes total = 750
    """

    terms = LoanTerms.create(
        principal="10000",
        rate="0.03",
        periods=4,
        frequency=Frequency.MENSUAL,
        scheme=Scheme.SALDO_INSOLUTO,
    )

    def test_first_installment_is_highest(self) -> None:
        assert first_installment(self.terms) == Decimal("2800.00")

    def test_last_installment_is_lowest(self) -> None:
        assert last_installment(self.terms) == Decimal("2575.00")

    def test_total_interest(self) -> None:
        assert total_interest(self.terms) == Decimal("750.00")

    def test_total_amount(self) -> None:
        assert total_amount(self.terms) == Decimal("10750.00")

    def test_zero_rate_has_no_interest(self) -> None:
        terms = LoanTerms.create(
            principal="10000",
            rate="0",
            periods=4,
            frequency=Frequency.MENSUAL,
            scheme=Scheme.SALDO_INSOLUTO,
        )
        assert total_interest(terms) == Decimal("0.00")
        assert first_installment(terms) == Decimal("2500.00")


class TestFixedPaymentScheme:
    """RN-09: cuota fija precalculada.

    Ejemplo del documento: 10,000 a 12 meses con 3% mensual.
        A = 10,000 * 0.03 / (1 - 1.03^-12) ~= 1,004.62
        interes total = 1,004.62 * 12 - 10,000 = 2,055.44
    """

    terms = LoanTerms.create(
        principal="10000",
        rate="0.03",
        periods=12,
        frequency=Frequency.MENSUAL,
        scheme=Scheme.CUOTA_FIJA,
    )

    def test_annuity_payment(self) -> None:
        assert annuity_payment(self.terms) == Decimal("1004.62")

    def test_first_and_last_are_equal(self) -> None:
        assert first_installment(self.terms) == last_installment(self.terms)

    def test_total_interest(self) -> None:
        assert total_interest(self.terms) == Decimal("2055.44")

    def test_total_amount(self) -> None:
        assert total_amount(self.terms) == Decimal("12055.44")

    def test_zero_rate_divides_equally(self) -> None:
        terms = LoanTerms.create(
            principal="1200",
            rate="0",
            periods=12,
            frequency=Frequency.MENSUAL,
            scheme=Scheme.CUOTA_FIJA,
        )
        assert annuity_payment(terms) == Decimal("100.00")
        assert total_interest(terms) == Decimal("0.00")


class TestAnnualEquivalent:
    """RN-04: la equivalencia anual es informativa, no se usa para calcular."""

    def test_weekly_five_percent(self) -> None:
        # (1.05)^52 - 1 = 11.6428... expresado como fraccion, o 1164.28 %
        result = annual_equivalent_rate(Decimal("0.05"), Frequency.SEMANAL)
        assert result == Decimal("11.6428")

    def test_monthly_three_percent(self) -> None:
        # (1.03)^12 - 1 = 0.4258... -> 42.58%
        result = annual_equivalent_rate(Decimal("0.03"), Frequency.MENSUAL)
        assert result == Decimal("0.4258")

    def test_zero_rate(self) -> None:
        assert annual_equivalent_rate(Decimal("0"), Frequency.MENSUAL) == Decimal("0.0000")
