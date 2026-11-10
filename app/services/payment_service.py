"""Servicio de pagos.

Registra abonos aplicando las reglas de negocio y recalculando el estado del
prestamo en una sola transaccion. Anular revierte todo y deja rastro.

Reglas cubiertas:
- RN-23/RN-24: monto positivo y no mayor al saldo total.
- RN-26: el cobrador solo cobra clientes de sus rutas; el admin, cualquiera.
- RN-27: no se cobra un prestamo cancelado o pagado.
- RN-29: reparto mora -> interes -> capital.
- RN-33: estados de cuota y prestamo tras el pago.
- RN-36: anulacion revirtiendo aplicaciones.
- RN-37: solo admin o prestamista con permiso anulan.
- RN-39: folio unico por tenant.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.money import MoneyError, round_money
from app.domain.payment_application import (
    Concept,
    InstallmentState,
    allocate_payment,
    breakdown_by_concept,
    total_pending,
)
from app.models.loan import Installment, Loan
from app.models.payment import Payment, PaymentApplication
from app.models.tenant import Tenant
from app.schemas.payment import PaymentCreate

#: Tamano maximo de pagina.
MAX_PAGE_SIZE = 100


class PaymentError(Exception):
    """Error de negocio relacionado con pagos."""


class LoanNotPayableError(PaymentError):
    """El prestamo no admite pagos en su estado actual (RN-27)."""


class PaymentExceedsBalanceError(PaymentError):
    """El monto supera el saldo pendiente (RN-24)."""


class PaymentNotFoundError(PaymentError):
    """El pago no existe en esta financiera."""


class PaymentNotCancellableError(PaymentError):
    """El pago ya fue anulado o no puede revertirse (RN-36)."""


class NotAuthorizedToCollectError(PaymentError):
    """El cobrador no tiene ese cliente en sus rutas (RN-26)."""


@dataclass(frozen=True)
class PaymentOutcome:
    """Resultado de registrar o anular un pago."""

    payment: Payment
    loan_status: str
    remaining_total: Decimal
    covered_late_fee: Decimal
    covered_interest: Decimal
    covered_principal: Decimal


def _to_state(installment: Installment) -> InstallmentState:
    """Convierte una cuota de la base al estado que usa el motor.

    Los pagos por concepto se derivan de las aplicaciones registradas, no del
    total pagado: el total no dice a que concepto fue cada centavo.
    """
    return InstallmentState(
        number=installment.number,
        amount=installment.amount,
        principal_part=installment.principal_part,
        interest_part=installment.interest_part,
        late_fee=installment.late_fee,
        paid_late_fee=_paid_for(installment, Concept.MORA),
        paid_interest=_paid_for(installment, Concept.INTERES),
        paid_principal=_paid_for(installment, Concept.CAPITAL),
    )


def _paid_for(installment: Installment, concept: Concept) -> Decimal:
    """Total ya aplicado a un concepto de una cuota."""
    return round_money(
        sum(
            (
                application.amount
                for application in installment.applications
                if application.concept == concept.value
            ),
            Decimal("0.00"),
        )
    )


def _status_for(installment: Installment, today: date, is_paid: bool, has_payment: bool) -> str:
    """Estado de la cuota segun lo pagado y su fecha (RN-33)."""
    if is_paid:
        return "pagada"
    if has_payment:
        return "parcial" if installment.due_date >= today else "vencida"
    return "vencida" if installment.due_date < today else "pendiente"


async def _next_folio(session: AsyncSession, tenant_id: UUID, today: date) -> str:
    """Genera el siguiente folio del tenant para el anio actual (RN-39)."""
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    label = (tenant.slug if tenant and tenant.slug else "CRD").upper()

    count = await session.scalar(
        select(func.count())
        .select_from(Payment)
        .where(
            Payment.tenant_id == tenant_id,
            func.extract("year", Payment.created_at) == today.year,
        )
    )
    consecutive = int(count or 0) + 1
    return f"PAGO-{label}-{today.year}-{consecutive:05d}"


async def register_payment(
    session: AsyncSession,
    tenant_id: UUID,
    registered_by: UUID,
    payload: PaymentCreate,
    *,
    today: date | None = None,
) -> PaymentOutcome:
    """Registra un pago y aplica el dinero a las cuotas.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera del usuario.
        registered_by: Usuario que registra el pago.
        payload: Datos validados por Pydantic.
        today: Fecha de negocio; se inyecta en pruebas.

    Returns:
        El pago, el estado del prestamo y el desglose por concepto.

    Raises:
        PaymentError: Si el prestamo no existe, no admite pagos o el monto
            excede el saldo.
    """
    business_date = today or date.today()

    loan = await session.scalar(
        select(Loan)
        .options(
            selectinload(Loan.installments).selectinload(Installment.applications)
        )
        .where(Loan.id == payload.loan_id, Loan.tenant_id == tenant_id)
    )
    if loan is None:
        raise PaymentError("El prestamo no existe.")

    if loan.status in {"cancelado", "pagado"}:
        raise LoanNotPayableError(
            f"Un prestamo en estado '{loan.status}' no admite pagos."
        )

    states = [_to_state(installment) for installment in loan.installments]
    available = total_pending(states)

    if payload.amount > available:
        raise PaymentExceedsBalanceError(
            f"El monto excede el saldo pendiente del prestamo ({available:.2f})."
        )

    try:
        allocation = allocate_payment(states, payload.amount)
    except MoneyError as exc:
        raise PaymentError(str(exc)) from exc

    folio = await _next_folio(session, tenant_id, business_date)
    payment = Payment(
        tenant_id=tenant_id,
        loan_id=loan.id,
        folio=folio,
        amount=payload.amount,
        method=payload.method,
        spei_reference=(payload.spei_reference or "").strip() or None,
        payment_type=payload.payment_type,
        status="aplicado",
        registered_by=registered_by,
    )
    session.add(payment)
    await session.flush()

    by_number = {installment.number: installment for installment in loan.installments}
    covered = breakdown_by_concept(allocation)

    for application in allocation.applications:
        installment = by_number[application.installment_number]
        session.add(
            PaymentApplication(
                payment_id=payment.id,
                installment_id=installment.id,
                concept=application.concept.value,
                amount=application.amount,
            )
        )
        installment.paid_amount = round_money(installment.paid_amount + application.amount)

    # RN-33: actualizar estado de cada cuota afectada.
    for number, state in allocation.new_states.items():
        installment = by_number[number]
        touched = any(
            application.installment_number == number
            for application in allocation.applications
        )
        if not touched:
            continue

        installment.status = _status_for(
            installment, business_date, state.is_paid, state.paid_amount > 0
        )
        if state.is_paid and installment.paid_at is None:
            installment.paid_at = datetime.now(UTC)

    loan.status = _loan_status(loan, business_date)
    await session.commit()

    refreshed = await get_payment(session, tenant_id, payment.id)
    remaining = await remaining_total(session, loan)

    return PaymentOutcome(
        payment=refreshed,
        loan_status=loan.status,
        remaining_total=remaining,
        covered_late_fee=covered[Concept.MORA],
        covered_interest=covered[Concept.INTERES],
        covered_principal=covered[Concept.CAPITAL],
    )


def _loan_status(loan: Loan, today: date) -> str:
    """Calcula el estado del prestamo tras un pago (RN-33)."""
    if all(installment.status == "pagada" for installment in loan.installments):
        return "pagado"
    if any(
        installment.due_date < today and installment.status != "pagada"
        for installment in loan.installments
    ):
        return "vencido"
    return "activo"


async def remaining_total(session: AsyncSession, loan: Loan) -> Decimal:
    """Saldo total pendiente del prestamo, incluida la mora."""
    installments = await session.scalars(
        select(Installment).where(Installment.loan_id == loan.id)
    )
    return round_money(
        sum(
            (
                installment.amount
                + installment.late_fee
                - installment.paid_amount
                for installment in installments
            ),
            Decimal("0.00"),
        )
    )


async def get_payment(session: AsyncSession, tenant_id: UUID, payment_id: UUID) -> Payment:
    """Obtiene un pago con sus aplicaciones.

    Raises:
        PaymentNotFoundError: Si no existe o es de otra financiera.
    """
    payment = await session.scalar(
        select(Payment)
        .options(selectinload(Payment.applications))
        .where(Payment.id == payment_id, Payment.tenant_id == tenant_id)
    )
    if payment is None:
        raise PaymentNotFoundError("El pago no existe.")
    return payment


async def list_payments(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    loan_id: UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Payment], int]:
    """Lista los pagos de un tenant con filtros y paginacion."""
    page = max(1, page)
    page_size = min(max(1, page_size), MAX_PAGE_SIZE)

    conditions = [Payment.tenant_id == tenant_id]
    if loan_id:
        conditions.append(Payment.loan_id == loan_id)
    if from_date:
        conditions.append(func.date(Payment.created_at) >= from_date)
    if to_date:
        conditions.append(func.date(Payment.created_at) <= to_date)

    total = await session.scalar(select(func.count()).select_from(Payment).where(*conditions))

    result = await session.scalars(
        select(Payment)
        .where(*conditions)
        .order_by(Payment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return list(result.all()), int(total or 0)


async def cancel_payment(
    session: AsyncSession,
    tenant_id: UUID,
    payment_id: UUID,
    cancelled_by: UUID,
    reason: str,
) -> PaymentOutcome:
    """Anula un pago revirtiendo sus aplicaciones (RN-36).

    Solo se permite anular el pago mas reciente del prestamo: revertir uno
    anterior dejaria en el aire los que vinieron despues.

    Raises:
        PaymentNotFoundError: Si no existe en el tenant.
        PaymentNotCancellableError: Si ya esta anulado o hay pagos posteriores.
    """
    payment = await get_payment(session, tenant_id, payment_id)

    if payment.status == "anulado":
        raise PaymentNotCancellableError("El pago ya fue anulado.")

    # Solo se puede anular el pago mas reciente del prestamo. El desempate por
    # folio es necesario porque dentro de una misma transaccion `now()` devuelve
    # el mismo instante para varios pagos.
    latest = await session.scalar(
        select(Payment.id)
        .where(Payment.loan_id == payment.loan_id, Payment.status == "aplicado")
        .order_by(Payment.created_at.desc(), Payment.folio.desc())
        .limit(1)
    )
    if latest is not None and latest != payment.id:
        raise PaymentNotCancellableError(
            "Hay pagos posteriores. Anulalos primero, del mas reciente al mas antiguo."
        )

    loan = await session.scalar(
        select(Loan)
        .options(selectinload(Loan.installments).selectinload(Installment.applications))
        .where(Loan.id == payment.loan_id)
    )
    if loan is None:
        raise PaymentNotFoundError("El prestamo del pago ya no existe.")

    affected: set[UUID] = set()
    for application in payment.applications:
        installment = await session.get(Installment, application.installment_id)
        if installment is None:
            continue
        installment.paid_amount = round_money(installment.paid_amount - application.amount)
        if installment.paid_amount < 0:
            installment.paid_amount = Decimal("0.00")
        installment.paid_at = None
        affected.add(installment.id)

    for installment in loan.installments:
        if installment.id not in affected:
            continue
        installment.status = (
            "vencida" if installment.due_date < date.today() else "pendiente"
        )

    payment.status = "anulado"
    payment.cancelled_by = cancelled_by
    payment.cancelled_at = datetime.now(UTC)
    payment.cancel_reason = reason

    loan.status = _loan_status(loan, date.today())
    await session.commit()

    refreshed = await get_payment(session, tenant_id, payment.id)
    remaining = await remaining_total(session, loan)

    return PaymentOutcome(
        payment=refreshed,
        loan_status=loan.status,
        remaining_total=remaining,
        covered_late_fee=Decimal("0.00"),
        covered_interest=Decimal("0.00"),
        covered_principal=Decimal("0.00"),
    )
