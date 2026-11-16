"""Motor puro de analisis comparativo bancario (RF-45 a RF-47, RN-52 a RN-54).

Calcula el costo total, la cuota periodica y el CAT estimado de una oferta
propia frente a instituciones del catalogo bancario sin depender de FastAPI
ni de la base de datos.

Formula base de CAT estimado (RN-52):
    CAT_estimado = ((1 + tasa_mensual)^12 - 1) * 100 + comisiones_anualizadas
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.interest import (
    Frequency,
    LoanTerms,
    Scheme,
    annual_equivalent_rate,
    first_installment,
    total_interest,
)
from app.domain.money import (
    MoneyError,
    require_non_negative_rate,
    require_positive_amount,
    round_money,
    round_rate,
    to_decimal,
)

#: Leyenda informativa obligatoria en toda comparacion (RN-53, RF-47).
DISCLAIMER_TEXT = (
    "Resultados estimados con fines informativos; "
    "no constituyen una oferta de crédito."
)

#: Periodos por anio segun la frecuencia para convertir tasa anual bancaria.
PERIODS_PER_YEAR: dict[Frequency, Decimal] = {
    Frequency.SEMANAL: Decimal(52),
    Frequency.QUINCENAL: Decimal(24),
    Frequency.MENSUAL: Decimal(12),
}

#: Meses equivalentes por periodo para anualizar comisiones de apertura.
MONTHS_PER_PERIOD: dict[Frequency, Decimal] = {
    Frequency.SEMANAL: Decimal(12) / Decimal(52),
    Frequency.QUINCENAL: Decimal("0.5"),
    Frequency.MENSUAL: Decimal(1),
}


@dataclass(frozen=True)
class BankOfferInput:
    """Datos de una institucion bancaria del catalogo (RN-54)."""

    name: str
    annual_rate: Decimal
    opening_fee: Decimal
    reference_cat: Decimal | None = None


@dataclass(frozen=True)
class ComparisonRow:
    """Fila resultante de comparar una institucion o la oferta propia (RF-46)."""

    institution: str
    is_own_offer: bool
    periodic_rate: Decimal
    annual_rate: Decimal
    estimated_cat: Decimal
    installment_amount: Decimal
    total_interest: Decimal
    opening_fee: Decimal
    total_cost: Decimal


def estimate_cat(
    monthly_rate: Decimal | int | str,
    principal: Decimal | int | str,
    opening_fee: Decimal | int | str = Decimal("0.00"),
    term_months: Decimal | int | str = Decimal(12),
) -> Decimal:
    """Calcula el CAT estimado expresado como porcentaje (RN-52).

    Aplica la formula documentada en 03-reglas-de-negocio.md §11::

        CAT_estimado = ((1 + tasa_mensual)^12 - 1) * 100 + comisiones_anualizadas

    Args:
        monthly_rate: Tasa mensual como fraccion (ej. 0.03 = 3 % mensual).
        principal: Monto del credito.
        opening_fee: Comision de apertura en pesos MXN.
        term_months: Plazo equivalente en meses (> 0).

    Returns:
        El CAT estimado en puntos porcentuales (ej. `42.58` para 42.58 %),
        redondeado con `ROUND_HALF_UP` a 2 decimales.
    """
    rate = require_non_negative_rate(
        round_rate(to_decimal(monthly_rate, "tasa mensual")), "tasa mensual"
    )
    amount = require_positive_amount(
        round_money(to_decimal(principal, "monto")), "monto"
    )
    fee = round_money(to_decimal(opening_fee, "comision de apertura"))
    if fee < 0:
        raise MoneyError("La comision de apertura no puede ser negativa.")

    months = to_decimal(term_months, "plazo en meses")
    if months <= 0:
        raise MoneyError("El plazo en meses debe ser mayor que cero.")

    effective_annual = ((Decimal(1) + rate) ** 12 - Decimal(1)) * Decimal(100)
    annualized_fee = (fee / amount) * (Decimal(12) / months) * Decimal(100)

    return round_money(effective_annual + annualized_fee)


def evaluate_own_offer(
    terms: LoanTerms,
    institution_name: str = "Tu oferta",
    opening_fee: Decimal | int | str = Decimal("0.00"),
) -> ComparisonRow:
    """Calcula los indicadores comparativos de la oferta propia del prestamista."""
    fee = round_money(to_decimal(opening_fee, "comision de apertura"))
    if fee < 0:
        raise MoneyError("La comision de apertura no puede ser negativa.")

    nominal_annual = round_rate(
        terms.rate * PERIODS_PER_YEAR[terms.frequency]
    )
    monthly_rate = round_rate(nominal_annual / Decimal(12))
    annual_rate = annual_equivalent_rate(terms.rate, terms.frequency)
    term_months = MONTHS_PER_PERIOD[terms.frequency] * Decimal(terms.periods)

    interest = total_interest(terms)
    installment = first_installment(terms)
    cat = estimate_cat(monthly_rate, terms.principal, fee, term_months)
    total_cost = round_money(terms.principal + interest + fee)

    return ComparisonRow(
        institution=institution_name,
        is_own_offer=True,
        periodic_rate=terms.rate,
        annual_rate=annual_rate,
        estimated_cat=cat,
        installment_amount=installment,
        total_interest=interest,
        opening_fee=fee,
        total_cost=total_cost,
    )


def evaluate_bank_offer(
    bank: BankOfferInput,
    *,
    principal: Decimal | int | str,
    periods: int,
    frequency: Frequency,
    scheme: Scheme = Scheme.CUOTA_FIJA,
) -> ComparisonRow:
    """Evalua una institucion bancaria para el mismo monto, plazo y frecuencia."""
    annual = require_non_negative_rate(
        round_rate(to_decimal(bank.annual_rate, "tasa anual")), "tasa anual"
    )
    fee = round_money(to_decimal(bank.opening_fee, "comision de apertura"))
    if fee < 0:
        raise MoneyError("La comision de apertura no puede ser negativa.")

    periodic_rate = round_rate(annual / PERIODS_PER_YEAR[frequency])
    bank_terms = LoanTerms.create(
        principal=principal,
        rate=periodic_rate,
        periods=periods,
        frequency=frequency,
        scheme=scheme,
    )

    monthly_rate = round_rate(annual / Decimal(12))
    term_months = MONTHS_PER_PERIOD[frequency] * Decimal(bank_terms.periods)
    calculated_cat = estimate_cat(
        monthly_rate, bank_terms.principal, fee, term_months
    )

    interest = total_interest(bank_terms)
    installment = first_installment(bank_terms)
    total_cost = round_money(bank_terms.principal + interest + fee)

    return ComparisonRow(
        institution=bank.name,
        is_own_offer=False,
        periodic_rate=periodic_rate,
        annual_rate=annual,
        estimated_cat=calculated_cat,
        installment_amount=installment,
        total_interest=interest,
        opening_fee=fee,
        total_cost=total_cost,
    )
