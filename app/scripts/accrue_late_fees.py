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
from app.domain.late_fee import calculate_late_fee, is_overdue
from app.domain.money import round_money
from app.models.loan import Installment, Loan


@dataclass(frozen=True)
class AccrualResult:
    """Resumen de la ejecucion del cierre diario de mora."""

    evaluated_loans: int
    updated_installments: int
    overdue_loans: int
    total_late_fee: Decimal


def _base_overdue_balance(installment: Installment) -> Decimal:
    """Saldo vencido de la cuota sin incluir mora previa (RN-19, RN-21)."""
    paid_non_late = sum(
        (
            app.amount
            for app in installment.applications
            if app.concept in {"interes", "capital"}
        ),
        Decimal("0.00"),
    )
    pending = installment.amount - round_money(paid_non_late)
    return max(Decimal("0.00"), round_money(pending))


async def accrue_late_fees(
    session: AsyncSession,
    *,
    today: date | None = None,
    tenant_id: UUID | None = None,
) -> AccrualResult:
    """Calcula y consolida la mora de las cuotas vencidas a la fecha `today`."""
    reference = today or date.today()

    conditions: list[Any] = [Loan.status.in_(("activo", "vencido"))]
    if tenant_id is not None:
        conditions.append(Loan.tenant_id == tenant_id)

    loans = (
        await session.scalars(
            select(Loan)
            .options(
                selectinload(Loan.installments).selectinload(
                    Installment.applications
                )
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
            base_balance = _base_overdue_balance(installment)
            fee = calculate_late_fee(
                balance=base_balance,
                rate=loan.late_fee_rate,
                due_date=installment.due_date,
                today=reference,
                grace_days=loan.grace_days,
                is_paid=is_paid,
            )

            if (
                installment.late_fee != fee.amount
                or installment.status != "vencida"
            ):
                installment.late_fee = fee.amount
                installment.status = "vencida"
                updated_installments += 1

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

