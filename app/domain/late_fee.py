"""Calculo de mora por atraso en el pago.

La mora es el recargo que se cobra cuando el cliente paga despues de la fecha
de vencimiento. Se devenga por dia y se prorratea sobre 30 dias.

Reglas de negocio cubiertas:
- RN-17: una cuota es vencida si su fecha paso y no esta pagada.
- RN-18: los dias de atraso no descuentan los dias de gracia; la gracia se
  aplica despues, al calcular los dias que si generan mora.
- RN-19: ``mora = saldo_vencido * tasa_mensual * (dias_efectivos / 30)``.
- RN-20: el resultado se calcula al consultar; la consolidacion diaria es
  responsabilidad del servicio, no de esta funcion.
- RN-21: la mora no genera interes sobre si misma (no es compuesta).
- RN-22: la tasa del prestamo prevalece sobre la tasa global del tenant.

Este modulo es puro: recibe fechas, montos y tasas; devuelve el recargo.
No consulta base de datos ni conoce la existencia de FastAPI.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.money import (
    MoneyError,
    require_non_negative_rate,
    round_money,
    round_rate,
    to_decimal,
)

#: Base de prorrateo de la tasa moratoria mensual (RN-19).
DAYS_IN_MONTH = Decimal(30)


@dataclass(frozen=True)
class LateFee:
    """Resultado del calculo de mora de una cuota.

    Attributes:
        days_late: Dias transcurridos desde el vencimiento (RN-18).
        chargeable_days: Dias que si generan mora, ya descontada la gracia.
        balance: Saldo vencido sobre el que se calculo el recargo.
        rate: Tasa moratoria mensual aplicada.
        amount: Recargo resultante, redondeado a 2 decimales.
    """

    days_late: int
    chargeable_days: int
    balance: Decimal
    rate: Decimal
    amount: Decimal

    @property
    def is_chargeable(self) -> bool:
        """Indica si el atraso ya genera recargo."""
        return self.amount > 0


def days_late(due_date: date, today: date) -> int:
    """Dias transcurridos desde el vencimiento (RN-18).

    Devuelve 0 si la cuota aun no vence o si vence hoy. Los dias de gracia
    **no** se descuentan aqui: se aplican en `chargeable_days`.
    """
    difference = (today - due_date).days
    return max(0, difference)


def chargeable_days(due_date: date, today: date, grace_days: int = 0) -> int:
    """Dias de atraso que efectivamente generan mora (RN-19).

    Args:
        due_date: Fecha de vencimiento de la cuota.
        today: Fecha de calculo.
        grace_days: Dias de tolerancia configurados en el prestamo o tenant.

    Returns:
        ``max(0, dias_atraso - dias_gracia)``.

    Raises:
        MoneyError: Si los dias de gracia son negativos.
    """
    if isinstance(grace_days, bool) or not isinstance(grace_days, int):
        raise MoneyError("Los dias de gracia deben ser un numero entero.")
    if grace_days < 0:
        raise MoneyError("Los dias de gracia no pueden ser negativos.")

    return max(0, days_late(due_date, today) - grace_days)


def is_overdue(due_date: date, today: date, is_paid: bool = False) -> bool:
    """Determina si una cuota esta vencida (RN-17).

    Una cuota pagada nunca esta vencida, aunque su fecha haya pasado.
    """
    if is_paid:
        return False
    return due_date < today


def calculate_late_fee(
    balance: Decimal | int | str,
    rate: Decimal | int | str,
    due_date: date,
    today: date,
    grace_days: int = 0,
    *,
    is_paid: bool = False,
) -> LateFee:
    """Calcula la mora de una cuota a una fecha dada (RN-19).

    La formula es::

        dias_efectivos = max(0, (hoy - vencimiento).days - gracia)
        mora = saldo * tasa_mensual * dias_efectivos / 30

    Args:
        balance: Saldo vencido de la cuota (cuota menos lo ya pagado). No debe
            incluir mora previamente generada, porque la mora no es compuesta
            (RN-21).
        rate: Tasa moratoria **mensual** como fraccion (0.10 = 10 %).
        due_date: Fecha de vencimiento de la cuota.
        today: Fecha de calculo.
        grace_days: Dias de tolerancia antes de cobrar mora.
        is_paid: Si la cuota ya esta pagada, la mora es cero.

    Returns:
        Un objeto `LateFee` con el desglose y el importe.

    Raises:
        MoneyError: Si el saldo es negativo, la tasa es negativa o los dias de
            gracia no son validos.
    """
    normalized_balance = round_money(to_decimal(balance, "saldo"))
    if normalized_balance < 0:
        raise MoneyError("El saldo vencido no puede ser negativo.")

    normalized_rate = require_non_negative_rate(
        round_rate(to_decimal(rate, "tasa moratoria")), "tasa moratoria"
    )

    late = days_late(due_date, today)
    chargeable = 0 if is_paid else chargeable_days(due_date, today, grace_days)

    if chargeable == 0 or normalized_balance == 0 or normalized_rate == 0:
        return LateFee(
            days_late=late,
            chargeable_days=chargeable,
            balance=normalized_balance,
            rate=normalized_rate,
            amount=Decimal("0.00"),
        )

    recargo = normalized_balance * normalized_rate * Decimal(chargeable) / DAYS_IN_MONTH

    return LateFee(
        days_late=late,
        chargeable_days=chargeable,
        balance=normalized_balance,
        rate=normalized_rate,
        amount=round_money(recargo),
    )


def resolve_late_fee_rate(
    loan_rate: Decimal | int | str | None,
    global_rate: Decimal | int | str,
) -> Decimal:
    """Elige la tasa moratoria aplicable a un prestamo (RN-22).

    La tasa configurada en el prestamo prevalece sobre la global del tenant.
    Si el prestamo no tiene tasa propia, se usa la global vigente al aprobarlo.

    Args:
        loan_rate: Tasa del prestamo, o `None` si no se definio.
        global_rate: Tasa global del tenant.

    Returns:
        La tasa que debe aplicarse, normalizada a 4 decimales.
    """
    chosen = global_rate if loan_rate is None else loan_rate
    normalized = round_rate(to_decimal(chosen, "tasa moratoria"))
    return require_non_negative_rate(normalized, "tasa moratoria")


def total_pending_with_late_fee(
    pending_amount: Decimal,
    late_fee: LateFee,
) -> Decimal:
    """Suma lo pendiente de la cuota mas la mora devengada.

    Es el monto que el cobrador debe cobrar si quiere cerrar la cuota hoy.
    """
    if pending_amount < 0:
        raise MoneyError("El monto pendiente no puede ser negativo.")
    return round_money(pending_amount + late_fee.amount)
