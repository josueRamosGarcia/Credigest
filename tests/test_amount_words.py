"""Pruebas de conversion de importes a letras."""

from decimal import Decimal

import pytest

from app.pdf.amount_words import amount_to_words


class TestSmallAmounts:
    """Numeros de una y dos cifras."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("0", "cero pesos M.N."),
            ("1", "uno peso M.N."),
            ("2", "dos pesos M.N."),
            ("15", "quince pesos M.N."),
            ("16", "dieciséis pesos M.N."),
            ("20", "veinte pesos M.N."),
            ("21", "veintiuno pesos M.N."),
            ("29", "veintinueve pesos M.N."),
            ("30", "treinta pesos M.N."),
            ("31", "treinta y uno pesos M.N."),
            ("99", "noventa y nueve pesos M.N."),
        ],
    )
    def test_small(self, value: str, expected: str) -> None:
        assert amount_to_words(value) == expected


class TestHundreds:
    """Centenas y el caso especial de cien."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("100", "cien pesos M.N."),
            ("101", "ciento uno pesos M.N."),
            ("150", "ciento cincuenta pesos M.N."),
            ("200", "doscientos pesos M.N."),
            ("500", "quinientos pesos M.N."),
            ("700", "setecientos pesos M.N."),
            ("999", "novecientos noventa y nueve pesos M.N."),
        ],
    )
    def test_hundreds(self, value: str, expected: str) -> None:
        assert amount_to_words(value) == expected


class TestThousands:
    """Miles y millones."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1000", "mil pesos M.N."),
            ("1001", "mil uno pesos M.N."),
            ("2500", "dos mil quinientos pesos M.N."),
            ("10000", "diez mil pesos M.N."),
            ("16000", "dieciséis mil pesos M.N."),
            ("100000", "cien mil pesos M.N."),
        ],
    )
    def test_thousands(self, value: str, expected: str) -> None:
        assert amount_to_words(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1000000", "un millón pesos M.N."),
            ("2000000", "dos millones pesos M.N."),
            ("5500000", "cinco millones quinientos mil pesos M.N."),
        ],
    )
    def test_millions(self, value: str, expected: str) -> None:
        assert amount_to_words(value) == expected


class TestCents:
    """Centavos como fraccion."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("100.50", "cien pesos 50/100 M.N."),
            ("16000.05", "dieciséis mil pesos 05/100 M.N."),
            ("1000.99", "mil pesos 99/100 M.N."),
            ("100.01", "cien pesos 01/100 M.N."),
        ],
    )
    def test_cents(self, value: str, expected: str) -> None:
        assert amount_to_words(value) == expected

    def test_exact_amount_has_no_cents(self) -> None:
        assert "/100" not in amount_to_words("1000.00")


class TestEdgeCases:
    """Casos borde."""

    def test_accepts_decimal(self) -> None:
        assert amount_to_words(Decimal("1234.56")).startswith("mil doscientos")

    def test_accepts_int(self) -> None:
        assert amount_to_words(500) == "quinientos pesos M.N."

    def test_rounds_half_up(self) -> None:
        assert "51/100" in amount_to_words("100.505")

    def test_negative_amount(self) -> None:
        result = amount_to_words("-100")
        assert result.startswith("menos ")
        assert "cien pesos" in result

    def test_large_amount(self) -> None:
        result = amount_to_words("999999999.99")
        assert "novecientos noventa y nueve millones" in result
        assert "99/100" in result
