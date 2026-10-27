"""Construccion de tablas de amortizacion.

Genera el calendario de cuotas de un prestamo. Es la base del pagare y del
calendario que consulta el cobrador.

Reglas de negocio cubiertas:
- RN-03: el ultimo periodo absorbe el ajuste de centavos para que la suma de
  capital sea exactamente el monto prestado.
- RN-07: las fechas se calculan desde la fecha de inicio.
- RN-12: esquema simple sobre capital original.
- RN-13: en saldo insoluto se conoce la primera y la ultima cuota.
- RN-14: el resultado es la base para crear las cuotas al aprobar el prestamo.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.interest import (
    LoanTerms,
    Scheme,
    annuity_payment,
    declining_interest,
    declining_principal_part,
    due_date,
    total_interest,
)
from app.domain.money import round_money


@dataclass(frozen=True)
class Installment:
    """Una cuota del calendario de pagos."""

    number: int
    due_date: date
    amount: Decimal
    interest_part: Decimal
    principal_part: Decimal
    balance: Decimal

    @property
    def is_last(self) -> bool:
        """Indica si es la ultima cuota del calendario."""
        return self.balance == Decimal("0.00")


def _build_simple(terms: LoanTerms, start: date) -> list[Installment]:
    """Tabla del esquema simple sobre capital original.

    El interes de cada cuota es constante y el capital se reparte por igual.
    La ultima cuota cuadra el capital y el interes exactos (RN-03).
    """
    interest_per_period = round_money(terms.principal * terms.rate)
    capital_per_period = round_money(terms.principal / terms.periods)

    rows: list[Installment] = []
    balance = terms.principal

    for number in range(1, terms.periods + 1):
        if number == terms.periods:
            # RN-03: absorber la diferencia de redondeo en el ultimo periodo
            # para que la suma de capital y de interes cuadre con las formulas.
            principal_part = balance
            interest_part = round_money(total_interest(terms) - _sum_interest(rows))
            amount = round_money(principal_part + interest_part)
        else:
            principal_part = capital_per_period
            interest_part = interest_per_period
            amount = round_money(principal_part + interest_part)

        balance = round_money(balance - principal_part)
        rows.append(
            Installment(
                number=number,
                due_date=due_date(start, terms.frequency, number),
                amount=amount,
                interest_part=interest_part,
                principal_part=principal_part,
                balance=balance,
            )
        )

    return rows


def _sum_interest(rows: list[Installment]) -> Decimal:
    """Suma de los intereses ya generados."""
    return sum((row.interest_part for row in rows), Decimal("0.00"))


def _build_declining(terms: LoanTerms, start: date) -> list[Installment]:
    """Tabla del esquema de interes sobre saldo insoluto.

    El capital se amortiza en partes iguales y el interes se calcula sobre el
    saldo pendiente, asi que la cuota decrece con el tiempo.
    """
    capital_per_period = declining_principal_part(terms)

    rows: list[Installment] = []
    balance = terms.principal

    for number in range(1, terms.periods + 1):
        interest_part = declining_interest(terms, balance)
        # RN-03: la ultima cuota amortiza el saldo exacto.
        principal_part = balance if number == terms.periods else capital_per_period
        amount = round_money(principal_part + interest_part)

        balance = round_money(balance - principal_part)
        rows.append(
            Installment(
                number=number,
                due_date=due_date(start, terms.frequency, number),
                amount=amount,
                interest_part=interest_part,
                principal_part=principal_part,
                balance=balance,
            )
        )

    return rows


def _build_fixed_payment(terms: LoanTerms, start: date) -> list[Installment]:
    """Tabla del esquema de cuota fija precalculada.

    La cuota es constante. El interes se calcula sobre el saldo y el capital es
    la diferencia entre la cuota y el interes.
    """
    payment = annuity_payment(terms)

    rows: list[Installment] = []
    balance = terms.principal

    for number in range(1, terms.periods + 1):
        if number == terms.periods:
            # RN-03: la ultima cuota cierra el saldo exactamente y ajusta el
            # interes para que el total coincida con la formula.
            principal_part = balance
            interest_part = round_money(total_interest(terms) - _sum_interest(rows))
            amount = round_money(principal_part + interest_part)
        else:
            interest_part = declining_interest(terms, balance)
            principal_part = round_money(payment - interest_part)
            amount = payment

        balance = round_money(balance - principal_part)
        rows.append(
            Installment(
                number=number,
                due_date=due_date(start, terms.frequency, number),
                amount=amount,
                interest_part=interest_part,
                principal_part=principal_part,
                balance=balance,
            )
        )

    return rows


#: Constructores disponibles por esquema de calculo.
_BUILDERS = {
    Scheme.SIMPLE: _build_simple,
    Scheme.SALDO_INSOLUTO: _build_declining,
    Scheme.CUOTA_FIJA: _build_fixed_payment,
}


def build_schedule(terms: LoanTerms, start: date) -> list[Installment]:
    """Genera la tabla de amortizacion completa.

    Args:
        terms: Condiciones validadas del prestamo.
        start: Fecha de inicio; la primera cuota vence un periodo despues.

    Returns:
        La lista de cuotas en orden, cada una con su desglose y saldo.

    Raises:
        ValueError: Si el esquema no tiene constructor asociado.
    """
    builder = _BUILDERS.get(terms.scheme)
    if builder is None:
        raise ValueError(f"Esquema no soportado: {terms.scheme}")

    return builder(terms, start)


def schedule_totals(schedule: list[Installment]) -> tuple[Decimal, Decimal, Decimal]:
    """Suma los totales de una tabla de amortizacion.

    Returns:
        Una tupla con (total de cuotas, total de interes, total de capital).
    """
    total_amount = sum((row.amount for row in schedule), Decimal("0.00"))
    total_interest = sum((row.interest_part for row in schedule), Decimal("0.00"))
    total_principal = sum((row.principal_part for row in schedule), Decimal("0.00"))
    return (round_money(total_amount), round_money(total_interest), round_money(total_principal))
