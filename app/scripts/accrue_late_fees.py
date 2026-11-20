"""Cierre diario de mora (RN-20, 02-arquitectura.md §8.1).

Recorre las cuotas vencidas de prestamos vigentes, calcula la mora devengada a
la fecha de corte con `app.domain.late_fee.calculate_late_fee` y actualiza
`installment.late_fee`, `installment.status` y `loan.status`.

El proceso es idempotente: calcula la mora acumulada desde `due_date` hasta
`today` sobre el saldo vencido sin incluir mora previa (RN-21), por lo que
ejecutarlo varias veces el mismo dia produce exactamente el mismo resultado.

Uso por linea de comandos (cron 23:55 America/Mexico_City):
    uv run python -m app.scripts.accrue_late_fees
"""

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.domain.late_fee import DAYS_IN_MONTH, calculate_late_fee, chargeable_days, is_overdue
from app.domain.money import round_money
from app.models.loan import Installment, Loan
from app.models.payment import PaymentApplication
from app.services.payment_service import business_today


@dataclass(frozen=True)
class AccrualResult:
    """Resumen de la ejecucion del cierre diario de mora."""

    evaluated_loans: int
    updated_installments: int
    overdue_loans: int
    total_late_fee: Decimal


def _is_applied(application: PaymentApplication) -> bool:
    """Indica si la aplicacion pertenece a un pago vigente (no anulado)."""
    payment = getattr(application, "payment", None)
    return payment is None or payment.status == "aplicado"


def _paid_by_concepts(installment: Installment, concepts: set[str]) -> Decimal:
    """Suma de pagos aplicados para los conceptos indicados."""
    total = sum(
        (
            app.amount
            for app in installment.applications
            if app.concept in concepts and _is_applied(app)
        ),
        Decimal("0.00"),
    )
    return round_money(total)


def _base_overdue_balance(installment: Installment) -> Decimal:
    """Saldo vencido de la cuota sin incluir mora previa ni pagos anulados (RN-19, RN-21)."""
    paid_non_late = _paid_by_concepts(installment, {"interes", "capital"})
    pending = installment.amount - paid_non_late
    return max(Decimal("0.00"), round_money(pending))


def compute_accrued_late_fee(
    installment: Installment,
    loan: Loan,
    reference: date,
) -> Decimal:
    """Calcula la mora acumulada sin reducirla nunca por debajo de lo ya pagado.

    - Si la cuota ya se calculo para `reference` o una fecha posterior, es
      idempotente y conserva el monto actual.
    - Si no tiene abonos previos, usa la formula acumulada exacta de RN-19.
    - Si ya tiene abonos parciales, acumula incrementalmente los dias nuevos
      desde `late_fee_calculated_on` sobre el saldo vencido actual, garantizando
      que `late_fee >= paid_late_fee`.
    """
    paid_non_late = _paid_by_concepts(installment, {"interes", "capital"})
    paid_late = _paid_by_concepts(installment, {"mora"})
    base_balance = max(Decimal("0.00"), round_money(installment.amount - paid_non_late))

    if (
        installment.late_fee_calculated_on is not None
        and reference <= installment.late_fee_calculated_on
    ):
        return max(installment.late_fee, paid_late)

    if paid_non_late == Decimal("0.00") and paid_late == Decimal("0.00"):
        fee = calculate_late_fee(
            balance=base_balance,
            rate=loan.late_fee_rate,
            due_date=installment.due_date,
            today=reference,
            grace_days=loan.grace_days,
            is_paid=False,
        )
        return max(fee.amount, installment.late_fee)

    if installment.late_fee_calculated_on is None:
        fee = calculate_late_fee(
            balance=base_balance,
            rate=loan.late_fee_rate,
            due_date=installment.due_date,
            today=reference,
            grace_days=loan.grace_days,
            is_paid=False,
        )
        return max(fee.amount, installment.late_fee, paid_late)

    prev_days = chargeable_days(
        installment.due_date, installment.late_fee_calculated_on, loan.grace_days
    )
    curr_days = chargeable_days(installment.due_date, reference, loan.grace_days)
    delta_days = max(0, curr_days - prev_days)

    if delta_days == 0 or base_balance == Decimal("0.00") or loan.late_fee_rate == 0:
        return max(installment.late_fee, paid_late)

    delta_fee = round_money(
        base_balance * loan.late_fee_rate * Decimal(delta_days) / DAYS_IN_MONTH
    )
    return round_money(max(installment.late_fee, paid_late) + delta_fee)


async def accrue_late_fees(
    session: AsyncSession,
    *,
    today: date | None = None,
    tenant_id: UUID | None = None,
) -> AccrualResult:
    """Calcula y consolida la mora de las cuotas vencidas a la fecha `today`."""
    reference = today or business_today()

    conditions: list[Any] = [Loan.status.in_(("activo", "vencido"))]
    if tenant_id is not None:
        conditions.append(Loan.tenant_id == tenant_id)

    loans = (
        await session.scalars(
            select(Loan)
            .options(
                selectinload(Loan.installments)
                .selectinload(Installment.applications)
                .selectinload(PaymentApplication.payment)
            )
            .where(*conditions)
        )
    ).all()

    updated_installments = 0
    overdue_loans = 0
    total_late_fee = Decimal("0.00")

    for loan in loans:
        has_overdue = False
        for installment in loan.installments:
            is_paid = installment.status == "pagada"
            if not is_overdue(installment.due_date, reference, is_paid=is_paid):
                continue

            has_overdue = True
            new_late_fee = compute_accrued_late_fee(installment, loan, reference)

            if (
                installment.late_fee != new_late_fee
                or installment.status != "vencida"
            ):
                installment.late_fee = new_late_fee
                installment.status = "vencida"
                updated_installments += 1

            if (
                installment.late_fee_calculated_on is None
                or reference > installment.late_fee_calculated_on
            ):
                installment.late_fee_calculated_on = reference

            total_late_fee = round_money(total_late_fee + installment.late_fee)

        if has_overdue:
            loan.status = "vencido"
            overdue_loans += 1
        elif loan.status == "vencido":
            loan.status = "activo"

    await session.commit()

    return AccrualResult(
        evaluated_loans=len(loans),
        updated_installments=updated_installments,
        overdue_loans=overdue_loans,
        total_late_fee=total_late_fee,
    )


async def _run_cli(cutoff: date | None) -> None:  # pragma: no cover - punto CLI
    async with SessionLocal() as session:
        result = await accrue_late_fees(session, today=cutoff)
        print(
            f"Cierre diario completado ({cutoff or date.today()}): "
            f"prestamos={result.evaluated_loans}, "
            f"cuotas_actualizadas={result.updated_installments}, "
            f"prestamos_vencidos={result.overdue_loans}, "
            f"mora_total={result.total_late_fee:.2f}"
        )


def main() -> None:  # pragma: no cover - punto CLI
    """Punto de entrada para ejecucion por cron."""
    parser = argparse.ArgumentParser(
        description="Ejecuta el cierre diario de mora (RN-20)."
    )
    parser.add_argument(
        "--date",
        help="Fecha de corte ISO (YYYY-MM-DD). Por defecto hoy.",
        default=None,
    )
    args = parser.parse_args()
    cutoff = date.fromisoformat(args.date) if args.date else None
    asyncio.run(_run_cli(cutoff))


if __name__ == "__main__":  # pragma: no cover
    main()

