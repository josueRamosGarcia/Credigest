"""Pruebas unitarias del motor puro del comparador bancario (RN-52, RN-53)."""

from decimal import Decimal

import pytest

from app.domain.comparator import (
    DISCLAIMER_TEXT,
    BankOfferInput,
    estimate_cat,
    evaluate_bank_offer,
    evaluate_own_offer,
)
from app.domain.interest import Frequency, LoanTerms, Scheme
from app.domain.money import MoneyError


class TestEstimateCat:
    """Verificacion matematica de la formula de CAT estimado (RN-52)."""

    def test_cat_without_opening_fee_matches_hand_calculation(self) -> None:
        """Tasa mensual 3 % (0.03), sin comision: ((1.03)^12 - 1) * 100 = 42.58 %."""
        cat = estimate_cat(
            monthly_rate=Decimal("0.0300"),
            principal=Decimal("10000.00"),
            opening_fee=Decimal("0.00"),
            term_months=Decimal("12"),
        )
        assert cat == Decimal("42.58")

    def test_cat_with_opening_fee_adds_annualized_percentage(self) -> None:
        """Tasa mensual 3 %, comision $500 sobre $10,000 a 6 meses -> +10 % anualizado = 52.58 %."""
        cat = estimate_cat(
            monthly_rate=Decimal("0.0300"),
            principal=Decimal("10000.00"),
            opening_fee=Decimal("500.00"),
            term_months=Decimal("6"),
        )
        assert cat == Decimal("52.58")

    def test_rejects_negative_fee_or_non_positive_months(self) -> None:
        with pytest.raises(MoneyError):
            estimate_cat("0.03", "10000", opening_fee="-10", term_months=12)

        with pytest.raises(MoneyError):
            estimate_cat("0.03", "10000", opening_fee="0", term_months=0)


class TestOffersComparison:
    """Evaluacion de oferta propia frente a una institucion bancaria (RF-45 a RF-47)."""

    def test_evaluates_own_and_bank_offer(self) -> None:
        terms = LoanTerms.create(
            principal=Decimal("10000.00"),
            rate=Decimal("0.0300"),
            periods=12,
            frequency=Frequency.MENSUAL,
            scheme=Scheme.CUOTA_FIJA,
        )
        own = evaluate_own_offer(terms, institution_name="Mi Financiera")
        assert own.is_own_offer is True
        assert own.installment_amount == Decimal("1004.62")
        assert own.total_interest == Decimal("2055.44")
        assert own.total_cost == Decimal("12055.44")
        assert own.estimated_cat == Decimal("42.58")

        bank = BankOfferInput(
            name="Banco Referencia",
            annual_rate=Decimal("0.3600"),
            opening_fee=Decimal("300.00"),
        )
        bank_row = evaluate_bank_offer(
            bank,
            principal=Decimal("10000.00"),
            periods=12,
            frequency=Frequency.MENSUAL,
        )
        assert bank_row.is_own_offer is False
        assert bank_row.periodic_rate == Decimal("0.0300")
        assert bank_row.installment_amount == Decimal("1004.62")
        assert bank_row.opening_fee == Decimal("300.00")
        assert bank_row.total_cost == Decimal("12355.44")
        assert bank_row.estimated_cat == Decimal("45.58")

    def test_disclaimer_matches_rn53(self) -> None:
        assert (
            DISCLAIMER_TEXT
            == "Resultados estimados con fines informativos; no constituyen una oferta de crédito."
        )

