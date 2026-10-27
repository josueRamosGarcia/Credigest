"""Esquemas de interes y frecuencia de pago.

Contiene las formulas puras que describen como crece la deuda. La construccion
de las tablas completas vive en `app.domain.amortization`.

Reglas de negocio cubiertas:
- RN-04: la tasa es por periodo; las equivalencias anuales solo son informativas.
- RN-07: las fechas de vencimiento se calculan desde la fecha de inicio.
- RN-09: con tasa cero, la cuota fija es capital entre numero de periodos.
- RN-10: el capital y el plazo deben ser mayores que cero.
- RN-11: la tasa no puede ser negativa.
- RN-13: en saldo insoluto se reporta la primera y la ultima cuota.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from dateutil.relativedelta import relativedelta

from app.domain.money import (
    MoneyError,
    require_non_negative_rate,
    require_positive_amount,
    round_money,
    round_rate,
    to_decimal,
)


class Frequency(StrEnum):
    """Frecuencia con la que el cliente paga sus cuotas."""

    SEMANAL = "semanal"
    QUINCENAL = "quincenal"
    MENSUAL = "mensual"

    @property
    def periods_per_year(self) -> int:
        """Numero de periodos en un ano. Solo informativo (RN-04)."""
        return {
            Frequency.SEMANAL: 52,
            Frequency.QUINCENAL: 24,
            Frequency.MENSUAL: 12,
        }[self]


class Scheme(StrEnum):
    """Esquema de calculo de intereses."""

    SIMPLE = "simple"
    SALDO_INSOLUTO = "saldo_insoluto"
    CUOTA_FIJA = "cuota_fija"


def due_date(start: date, frequency: Frequency, period_number: int) -> date:
    """Calcula la fecha de vencimiento del periodo indicado (RN-07).

    La fecha se calcula siempre a partir de la fecha de inicio, no de la cuota
    anterior. Asi se evita el arrastre cuando un mes tiene menos dias que otro.

    Args:
        start: Fecha en que inicia el prestamo.
        frequency: Frecuencia de pago.
        period_number: Numero de periodo, empezando en 1.

    Returns:
        La fecha de vencimiento correspondiente.
    """
    if period_number < 1:
        raise MoneyError("El numero de periodo debe ser mayor o igual a 1.")

    if frequency is Frequency.SEMANAL:
        return start + relativedelta(weeks=period_number)
    if frequency is Frequency.QUINCENAL:
        # Quincenal son 15 dias exactos (decision registrada en docs/03).
        return start + relativedelta(days=15 * period_number)
    return start + relativedelta(months=period_number)


def annual_equivalent_rate(rate_per_period: Decimal, frequency: Frequency) -> Decimal:
    """Tasa anual equivalente, solo para mostrar al usuario (RN-04).

    No se usa para calcular cuotas. Sirve para que el prestamista pueda
    comparar su oferta con la de un banco.
    """
    periods = frequency.periods_per_year
    factor = (Decimal(1) + rate_per_period) ** periods - Decimal(1)
    return round_rate(factor)


@dataclass(frozen=True)
class LoanTerms:
    """Condiciones validadas de un prestamo.

    Se construye con `LoanTerms.create` para garantizar que los valores
    cumplan las reglas de negocio antes de usarse en cualquier calculo.
    """

    principal: Decimal
    rate: Decimal
    periods: int
    frequency: Frequency
    scheme: Scheme

    @classmethod
    def create(
        cls,
        principal: Decimal | int | str,
        rate: Decimal | int | str,
        periods: int,
        frequency: Frequency = Frequency.MENSUAL,
        scheme: Scheme = Scheme.SIMPLE,
    ) -> "LoanTerms":
        """Valida y normaliza las condiciones de un prestamo."""
        if isinstance(periods, bool) or not isinstance(periods, int):
            raise MoneyError("El plazo debe ser un numero entero de periodos.")
        if periods <= 0:
            raise MoneyError("El plazo debe ser mayor que cero (RN-10).")

        normalized_principal = require_positive_amount(
            round_money(to_decimal(principal, "principal")), "principal"
        )
        normalized_rate = require_non_negative_rate(round_rate(to_decimal(rate, "tasa")), "tasa")

        return cls(
            principal=normalized_principal,
            rate=normalized_rate,
            periods=periods,
            frequency=Frequency(frequency),
            scheme=Scheme(scheme),
        )


def simple_interest_total(terms: LoanTerms) -> Decimal:
    """Interes total del esquema simple sobre capital original (RN-12).

    Formula: ``P * i * n``.
    """
    return round_money(terms.principal * terms.rate * terms.periods)


def simple_installment(terms: LoanTerms) -> Decimal:
    """Cuota constante del esquema simple.

    Formula: ``(P + P * i * n) / n``.
    """
    total = terms.principal + simple_interest_total(terms)
    return round_money(total / terms.periods)


def declining_principal_part(terms: LoanTerms) -> Decimal:
    """Parte de capital de cada cuota en el esquema de saldo insoluto.

    El capital se amortiza en partes iguales: ``P / n``.
    """
    return round_money(terms.principal / terms.periods)


def declining_interest(terms: LoanTerms, balance: Decimal) -> Decimal:
    """Interes del periodo calculado sobre el saldo insoluto pendiente."""
    return round_money(balance * terms.rate)


def annuity_payment(terms: LoanTerms) -> Decimal:
    """Cuota fija precalculada con la formula de anualidad (RN-09).

    Formula: ``A = P * i / (1 - (1 + i)^(-n))``.
    Si la tasa es cero, la cuota es simplemente ``P / n``.
    """
    if terms.rate == 0:
        return round_money(terms.principal / terms.periods)

    factor = (Decimal(1) + terms.rate) ** (-terms.periods)
    payment = terms.principal * terms.rate / (Decimal(1) - factor)
    return round_money(payment)


def first_installment(terms: LoanTerms) -> Decimal:
    """Cuota del primer periodo segun el esquema elegido.

    Para `saldo_insoluto` esta es la cuota mas alta del prestamo (RN-13).
    """
    if terms.scheme is Scheme.SIMPLE:
        return simple_installment(terms)
    if terms.scheme is Scheme.CUOTA_FIJA:
        return annuity_payment(terms)
    capital = declining_principal_part(terms)
    interest = declining_interest(terms, terms.principal)
    return capital + interest


def last_installment(terms: LoanTerms) -> Decimal:
    """Cuota del ultimo periodo.

    Solo difiere de la primera en el esquema de saldo insoluto (RN-13).
    """
    if terms.scheme is not Scheme.SALDO_INSOLUTO:
        return first_installment(terms)

    capital = declining_principal_part(terms)
    remaining = terms.principal - capital * (terms.periods - 1)
    return capital + declining_interest(terms, remaining)


def total_interest(terms: LoanTerms) -> Decimal:
    """Interes total del prestamo para el esquema elegido.

    En saldo insoluto no existe una cuota unica, asi que se calcula como la
    suma de los intereses de cada periodo.
    """
    if terms.scheme is Scheme.SIMPLE:
        return simple_interest_total(terms)

    if terms.scheme is Scheme.CUOTA_FIJA:
        payment = annuity_payment(terms)
        return round_money(payment * terms.periods - terms.principal)

    if terms.rate == 0:
        return Decimal("0.00")

    # Saldo insoluto: la suma de una progresion aritmetica.
    # Interes_k = (P - (k-1) * P/n) * i
    capital_part = terms.principal / terms.periods
    total = Decimal(0)
    for period in range(terms.periods):
        balance = terms.principal - capital_part * period
        total += balance * terms.rate
    return round_money(total)


def total_amount(terms: LoanTerms) -> Decimal:
    """Importe total a pagar: capital mas intereses."""
    return round_money(terms.principal + total_interest(terms))


def end_date(terms: LoanTerms, start: date) -> date:
    """Fecha en que vence la ultima cuota."""
    return due_date(start, terms.frequency, terms.periods)
