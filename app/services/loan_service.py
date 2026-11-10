"""Servicio de prestamos.

Convierte una simulacion en un prestamo real: persiste las condiciones
congeladas y genera el calendario de cuotas en una sola transaccion. Si algo
falla, no queda un prestamo a medias.

Reglas de negocio cubiertas:
- RN-06/RN-14: las condiciones se congelan al aprobar.
- RN-15: no se presta a un cliente inactivo.
- RN-16: no se presta si el cliente tiene cuotas vencidas de mas de 90 dias.
- RN-22: la tasa moratoria del prestamo prevalece sobre la global.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.amortization import build_schedule
from app.domain.interest import (
    Frequency,
    LoanTerms,
    Scheme,
    first_installment,
    total_amount,
    total_interest,
)
from app.domain.money import round_money
from app.models.client import Client
from app.models.loan import Installment, Loan
from app.models.system_setting import SystemSetting
from app.schemas.loan import LoanCreate

#: Dias de atraso a partir de los cuales se bloquea un prestamo nuevo (RN-16).
BLOCKING_OVERDUE_DAYS = 90

#: Tamano maximo de pagina.
MAX_PAGE_SIZE = 100


class LoanError(Exception):
    """Error de negocio relacionado con prestamos."""


class ClientNotFoundForLoanError(LoanError):
    """El cliente no existe en esta financiera."""


class InactiveClientError(LoanError):
    """No se puede prestar a un cliente desactivado (RN-15)."""


class ClientHasOverdueDebtError(LoanError):
    """El cliente tiene cuotas vencidas de mas de 90 dias (RN-16)."""


class LoanNotFoundError(LoanError):
    """El prestamo no existe en esta financiera."""


class LoanNotCancellableError(LoanError):
    """El prestamo no puede cancelarse en su estado actual."""


async def get_loan(session: AsyncSession, tenant_id: UUID, loan_id: UUID) -> Loan:
    """Obtiene un prestamo del tenant indicado.

    Raises:
        LoanNotFoundError: Si no existe o es de otra financiera.
    """
    loan = await session.scalar(
        select(Loan).where(Loan.id == loan_id, Loan.tenant_id == tenant_id)
    )
    if loan is None:
        raise LoanNotFoundError("El prestamo no existe.")
    return loan


async def get_loan_detail(session: AsyncSession, tenant_id: UUID, loan_id: UUID) -> Loan:
    """Obtiene un prestamo con su calendario precargado."""
    loan = await session.scalar(
        select(Loan)
        .options(selectinload(Loan.installments))
        .where(Loan.id == loan_id, Loan.tenant_id == tenant_id)
    )
    if loan is None:
        raise LoanNotFoundError("El prestamo no existe.")
    return loan


async def _settings(session: AsyncSession, tenant_id: UUID) -> SystemSetting | None:
    """Devuelve la configuracion global del tenant, si existe."""
    return await session.scalar(
        select(SystemSetting).where(SystemSetting.tenant_id == tenant_id)
    )


async def _has_blocking_overdue(session: AsyncSession, client_id: UUID, today: date) -> bool:
    """Indica si el cliente tiene cuotas vencidas de mas de 90 dias (RN-16)."""
    cutoff = today.toordinal() - BLOCKING_OVERDUE_DAYS
    cutoff_date = date.fromordinal(cutoff)

    overdue = await session.scalar(
        select(func.count())
        .select_from(Installment)
        .join(Loan, Loan.id == Installment.loan_id)
        .where(
            Loan.client_id == client_id,
            Loan.status.in_(["activo", "vencido"]),
            Installment.status.in_(["pendiente", "parcial", "vencida"]),
            Installment.due_date < cutoff_date,
        )
    )
    return bool(overdue)


async def create_loan(
    session: AsyncSession,
    tenant_id: UUID,
    lender_id: UUID,
    payload: LoanCreate,
) -> Loan:
    """Aprueba un prestamo y genera su calendario.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera que otorga el credito.
        lender_id: Usuario que lo coloca.
        payload: Condiciones ya validadas por Pydantic.

    Returns:
        El prestamo con sus cuotas generadas.

    Raises:
        ClientNotFoundForLoanError: Si el cliente no existe en el tenant.
        InactiveClientError: Si el cliente esta desactivado (RN-15).
        ClientHasOverdueDebtError: Si tiene atrasos graves (RN-16).
    """
    client = await session.scalar(
        select(Client).where(Client.id == payload.client_id, Client.tenant_id == tenant_id)
    )
    if client is None:
        raise ClientNotFoundForLoanError("El cliente no existe.")

    if client.status != "activo":
        raise InactiveClientError("No se puede prestar a un cliente desactivado.")

    if await _has_blocking_overdue(session, client.id, payload.start_date):
        raise ClientHasOverdueDebtError(
            "El cliente tiene cuotas vencidas de mas de "
            f"{BLOCKING_OVERDUE_DAYS} dias. Requiere autorizacion del administrador."
        )

    frequency = Frequency(payload.rate_period)
    scheme = Scheme(payload.scheme)
    terms = LoanTerms.create(
        principal=payload.principal,
        rate=payload.interest_rate,
        periods=payload.term_periods,
        frequency=frequency,
        scheme=scheme,
    )

    # RN-22: la tasa del prestamo manda; si no viene, se usa la global.
    settings = await _settings(session, tenant_id)
    late_fee_rate = payload.late_fee_rate
    if late_fee_rate is None:
        late_fee_rate = settings.default_late_fee_rate if settings else Decimal("0.1000")

    grace_days = payload.grace_days
    if grace_days is None:
        grace_days = settings.grace_days if settings else 0

    schedule = build_schedule(terms, payload.start_date)

    loan = Loan(
        tenant_id=tenant_id,
        client_id=client.id,
        lender_id=lender_id,
        principal=terms.principal,
        interest_rate=terms.rate,
        rate_period=terms.frequency.value,
        scheme=terms.scheme.value,
        term_periods=terms.periods,
        start_date=payload.start_date,
        first_due_date=schedule[0].due_date,
        end_date=schedule[-1].due_date,
        total_interest=total_interest(terms),
        total_amount=total_amount(terms),
        late_fee_rate=late_fee_rate,
        grace_days=grace_days,
        status="activo",
    )
    session.add(loan)
    await session.flush()

    for row in schedule:
        session.add(
            Installment(
                loan_id=loan.id,
                number=row.number,
                due_date=row.due_date,
                amount=row.amount,
                principal_part=row.principal_part,
                interest_part=row.interest_part,
                late_fee=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                status="pendiente",
            )
        )

    await session.commit()
    return await get_loan_detail(session, tenant_id, loan.id)


async def list_loans(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    status: str | None = None,
    client_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[Sequence[Loan], int]:
    """Lista los prestamos de un tenant con filtros y paginacion."""
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    conditions = [Loan.tenant_id == tenant_id]
    if status:
        conditions.append(Loan.status == status)
    if client_id:
        conditions.append(Loan.client_id == client_id)

    total = await session.scalar(select(func.count()).select_from(Loan).where(*conditions))

    result = await session.scalars(
        select(Loan)
        .where(*conditions)
        .order_by(Loan.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return result.all(), int(total or 0)


async def cancel_loan(
    session: AsyncSession, tenant_id: UUID, loan_id: UUID, reason: str
) -> Loan:
    """Cancela un prestamo en estado activo o vencido.

    El prestamo no se borra: se conserva el historico con su motivo.

    Raises:
        LoanNotFoundError: Si no existe en el tenant.
        LoanNotCancellableError: Si ya esta pagado o cancelado.
    """
    loan = await get_loan(session, tenant_id, loan_id)

    if loan.status in {"pagado", "cancelado"}:
        raise LoanNotCancellableError(
            f"Un prestamo en estado '{loan.status}' no puede cancelarse."
        )

    loan.status = "cancelado"
    loan.cancel_reason = reason
    await session.commit()
    return loan


async def first_installment_amount(loan: Loan) -> Decimal:
    """Cuota inicial del prestamo, calculada a partir de sus condiciones.

    Se recalcula en lugar de guardarse porque el calendario ya la contiene y no
    conviene duplicar el dato.
    """
    terms = LoanTerms.create(
        principal=loan.principal,
        rate=loan.interest_rate,
        periods=loan.term_periods,
        frequency=Frequency(loan.rate_period),
        scheme=Scheme(loan.scheme),
    )
    return round_money(first_installment(terms))
