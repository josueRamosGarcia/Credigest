"""Pruebas de las utilidades de dinero."""

from decimal import Decimal

import pytest

from app.domain.money import (
    MoneyError,
    money,
    rate,
    require_non_negative_rate,
    require_positive_amount,
    round_money,
    round_rate,
    to_decimal,
)


def test_to_decimal_accepts_decimal() -> None:
    value = Decimal("10.50")
    assert to_decimal(value) == value


def test_to_decimal_accepts_int() -> None:
    assert to_decimal(10) == Decimal("10")


def test_to_decimal_accepts_string() -> None:
    assert to_decimal("10.50") == Decimal("10.50")


def test_to_decimal_rejects_float() -> None:
    with pytest.raises(MoneyError, match="float"):
        to_decimal(10.5)


def test_to_decimal_rejects_bool() -> None:
    with pytest.raises(MoneyError, match="booleano"):
        to_decimal(True)


def test_to_decimal_rejects_invalid_string() -> None:
    with pytest.raises(MoneyError, match="no es un numero valido"):
        to_decimal("mucho")


def test_round_money_half_up() -> None:
    """0.005 debe redondear hacia arriba, no al par mas cercano (RN-02)."""
    assert round_money(Decimal("0.005")) == Decimal("0.01")


def test_round_money_half_up_negative() -> None:
    assert round_money(Decimal("-0.005")) == Decimal("-0.01")


def test_round_money_rounds_1333_333() -> None:
    assert round_money(Decimal("1333.333333")) == Decimal("1333.33")


def test_round_money_rounds_1333_335() -> None:
    assert round_money(Decimal("1333.335")) == Decimal("1333.34")


def test_round_money_keeps_two_decimals() -> None:
    assert round_money(Decimal("100")) == Decimal("100.00")


def test_round_rate_keeps_four_decimals() -> None:
    assert round_rate(Decimal("0.0525")) == Decimal("0.0525")
    assert round_rate(Decimal("0.05255")) == Decimal("0.0526")


def test_money_converts_and_rounds() -> None:
    assert money("1000.005") == Decimal("1000.01")


def test_rate_converts_and_rounds() -> None:
    assert rate("0.05") == Decimal("0.0500")


def test_require_positive_amount_rejects_zero() -> None:
    with pytest.raises(MoneyError, match="mayor que cero"):
        require_positive_amount(Decimal("0"))


def test_require_positive_amount_rejects_negative() -> None:
    with pytest.raises(MoneyError, match="mayor que cero"):
        require_positive_amount(Decimal("-10"))


def test_require_non_negative_rate_rejects_negative() -> None:
    with pytest.raises(MoneyError, match="negativo"):
        require_non_negative_rate(Decimal("-0.01"))


def test_require_non_negative_rate_allows_zero() -> None:
    assert require_non_negative_rate(Decimal("0")) == Decimal("0")
