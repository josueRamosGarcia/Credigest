"""Servicio del dashboard financiero.

Todas las cifras se calculan en el servidor con consultas agregadas: el
frontend solo las presenta (RN-47).

Reglas cubiertas:
- RN-47: definicion de cada indicador.
- RN-48: la fecha de corte aplica distinto a colocacion y a cobranza.
- RN-49: los pagos anulados se excluyen siempre.
- RN-50: la morosidad se expresa con 2 decimales.
- RN-51: el aging se calcula por cuota vencida, no por prestamo.

Nota sobre zonas horarias: `payment.created_at` es `timestamptz`, que PostgreSQL
guarda en UTC. Comparar `func.date(created_at)` contra una fecha local daria un
dia de diferencia despues de las 18:00 hora de Mexico. Por eso todas las
comparaciones convierten primero a la zona del negocio.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.money import round_money
from app.models.collection_route import CollectionRoute, CollectionRouteItem
from app.models.loan import Installment, Loan
from app.models.payment import Payment, PaymentApplication

#: Estados de prestamo considerados vigentes para la cartera.
ACTIVE_LOAN_STATUSES = ("activo", "vencido")

#: Rangos de aging en dias, en el orden que espera el reporte (RN-51).
AGING_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("al_dia", 0, 0),
    ("dias_1_30", 1, 30),
    ("dias_31_60", 31, 60),
    ("dias_61_90", 61, 90),
    ("mas_90", 91, None),
)


@dataclass(frozen=True)
class DashboardSummary:
    """Indicadores principales del negocio."""

    capital_prestado: Decimal
    capital_recuperado: Decimal
    capital_proyectado: Decimal
    intereses_generados: Decimal
    mora_cobrada: Decimal
    utilidad_generada: Decimal
    cartera_total: Decimal
    cartera_vencida: Decimal
    indice_morosidad: Decimal

    #: Numero de prestamos y clientes con actividad, para contexto.
    prestamos_activos: int
    prestamos_pagados: int
    prestamos_vencidos: int


@dataclass(frozen=True)
class AgingBucket:
    """Una franja de antiguedad de la cartera vencida."""

    label: str
    min_days: int
    max_days: int | None
    amount: Decimal
    installments: int


@dataclass(frozen=True)
class AgingReport:
    """Reporte de antiguedad de saldos."""

    buckets: list[AgingBucket] = field(default_factory=list)
    total_vencido: Decimal = Decimal("0.00")


def local_date(column: Any) -> Any:
    """Convierte una columna `timestamptz` a fecha en la zona del negocio.

    Sin esto, un pago registrado a las 20:00 hora de Mexico aparece con la fecha
    del dia siguiente, porque PostgreSQL lo guarda en UTC.
    """
    timezone = get_settings().timezone
    return func.date(func.timezone(timezone, column))


def _today_in_tz() -> date:
    """Fecha actual en la zona horaria configurada del negocio (RN-05)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def _to_decimal(value: Decimal | int | float | None) -> Decimal:
    """Convierte el resultado de una agregacion a Decimal redondeado."""
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return round_money(value)
    return round_money(Decimal(str(value)))


def _loan_scope_conditions(
    tenant_id: UUID,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> list[Any]:
    """Condiciones de alcance para prestamos segun filtros (RF-42)."""
    conditions: list[Any] = [Loan.tenant_id == tenant_id]
    if prestamista_id is not None:
        conditions.append(Loan.lender_id == prestamista_id)
    if route_id is not None:
        route_loans = (
            select(CollectionRouteItem.loan_id)
            .join(
                CollectionRoute,
                CollectionRoute.id == CollectionRouteItem.route_id,
            )
            .where(
                CollectionRoute.tenant_id == tenant_id,
                CollectionRoute.id == route_id,
            )
        )
        conditions.append(Loan.id.in_(route_loans))
    return conditions


def _payments_in_range(
    tenant_id: UUID,
    from_date: date | None,
    to_date: date | None,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> Select[Any]:
    """Subconsulta con los pagos aplicados del tenant en el rango (RN-49, RF-42)."""
    conditions: list[Any] = [
        Payment.tenant_id == tenant_id,
        Payment.status == "aplicado",
    ]
    if from_date is not None:
        conditions.append(local_date(Payment.created_at) >= from_date)
    if to_date is not None:
        conditions.append(local_date(Payment.created_at) <= to_date)
    if prestamista_id is not None or route_id is not None:
        loan_ids = select(Loan.id).where(
            *_loan_scope_conditions(tenant_id, prestamista_id, route_id)
        )
        conditions.append(Payment.loan_id.in_(loan_ids))

    return select(Payment.id).where(*conditions)


async def _sum_applications(
    session: AsyncSession,
    tenant_id: UUID,
    concept: str,
    from_date: date | None,
    to_date: date | None,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> Decimal:
    """Suma lo aplicado a un concepto en los pagos del rango."""
    payments = _payments_in_range(
        tenant_id, from_date, to_date, prestamista_id, route_id
    ).subquery()

    total = await session.scalar(
        select(func.coalesce(func.sum(PaymentApplication.amount), 0)).where(
            PaymentApplication.concept == concept,
            PaymentApplication.payment_id.in_(select(payments.c.id)),
        )
    )
    return _to_decimal(total)


async def _sum_principal_placed(
    session: AsyncSession,
    tenant_id: UUID,
    from_date: date | None,
    to_date: date | None,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> Decimal:
    """Capital colocado en el rango, excluyendo prestamos cancelados (RN-48)."""
    conditions = [
        *_loan_scope_conditions(tenant_id, prestamista_id, route_id),
        Loan.status != "cancelado",
    ]
    if from_date is not None:
        conditions.append(Loan.start_date >= from_date)
    if to_date is not None:
        conditions.append(Loan.start_date <= to_date)

    total = await session.scalar(
        select(func.coalesce(func.sum(Loan.principal), 0)).where(*conditions)
    )
    return _to_decimal(total)


async def _portfolio(
    session: AsyncSession,
    tenant_id: UUID,
    today: date,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> tuple[Decimal, Decimal]:
    """Devuelve (cartera total pendiente, cartera vencida).

    La cartera total es todo lo que falta cobrar de prestamos vigentes. La
    vencida es la parte cuya fecha ya paso (RN-47, RN-51).
    """
    scope = _loan_scope_conditions(tenant_id, prestamista_id, route_id)
    total = await session.scalar(
        select(
            func.coalesce(
                func.sum(Installment.amount + Installment.late_fee - Installment.paid_amount),
                0,
            )
        )
        .select_from(Installment)
        .join(Loan, Loan.id == Installment.loan_id)
        .where(
            *scope,
            Loan.status.in_(ACTIVE_LOAN_STATUSES),
            Installment.status.in_(("pendiente", "parcial", "vencida")),
        )
    )

    overdue = await session.scalar(
        select(
            func.coalesce(
                func.sum(Installment.amount + Installment.late_fee - Installment.paid_amount),
                0,
            )
        )
        .select_from(Installment)
        .join(Loan, Loan.id == Installment.loan_id)
        .where(
            *scope,
            Loan.status.in_(ACTIVE_LOAN_STATUSES),
            Installment.status.in_(("pendiente", "parcial", "vencida")),
            Installment.due_date < today,
        )
    )

    return (_to_decimal(total), _to_decimal(overdue))


async def _loan_counts(
    session: AsyncSession,
    tenant_id: UUID,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> tuple[int, int, int]:
    """Cuenta prestamos activos, pagados y vencidos."""
    rows = await session.execute(
        select(Loan.status, func.count())
        .where(*_loan_scope_conditions(tenant_id, prestamista_id, route_id))
        .group_by(Loan.status)
    )
    counts = {status: int(count) for status, count in rows.all()}

    return (
        counts.get("activo", 0),
        counts.get("pagado", 0),
        counts.get("vencido", 0),
    )


async def _pending_principal(
    session: AsyncSession,
    tenant_id: UUID,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
) -> Decimal:
    """Saldo de capital pendiente de prestamos activos/vencidos (RN-47)."""
    scope = _loan_scope_conditions(tenant_id, prestamista_id, route_id)
    active_loan_ids = (
        select(Loan.id)
        .where(*scope, Loan.status.in_(ACTIVE_LOAN_STATUSES))
        .subquery()
    )

    total_principal = await session.scalar(
        select(func.coalesce(func.sum(Installment.principal_part), 0)).where(
            Installment.loan_id.in_(select(active_loan_ids.c.id))
        )
    )
    paid_principal = await session.scalar(
        select(func.coalesce(func.sum(PaymentApplication.amount), 0))
        .select_from(PaymentApplication)
        .join(Payment, Payment.id == PaymentApplication.payment_id)
        .where(
            Payment.tenant_id == tenant_id,
            Payment.status == "aplicado",
            Payment.loan_id.in_(select(active_loan_ids.c.id)),
            PaymentApplication.concept == "capital",
        )
    )
    return round_money(
        max(Decimal("0.00"), _to_decimal(total_principal) - _to_decimal(paid_principal))
    )


async def summary(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    prestamista_id: UUID | None = None,
    route_id: UUID | None = None,
    today: date | None = None,
) -> DashboardSummary:
    """Calcula los indicadores principales (RN-47, RF-42).

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera cuyos indicadores se calculan.
        from_date: Inicio del rango para colocacion y cobranza.
        to_date: Fin del rango.
        prestamista_id: Filtra por el prestamista que coloco el credito.
        route_id: Filtra por los prestamos incluidos en una ruta de cobro.
        today: Fecha de corte para la cartera vencida.

    Returns:
        Los indicadores del dashboard.
    """
    reference = today or _today_in_tz()

    capital_prestado = await _sum_principal_placed(
        session, tenant_id, from_date, to_date, prestamista_id, route_id
    )
    capital_recuperado = await _sum_applications(
        session, tenant_id, "capital", from_date, to_date, prestamista_id, route_id
    )
    intereses = await _sum_applications(
        session, tenant_id, "interes", from_date, to_date, prestamista_id, route_id
    )
    mora = await _sum_applications(
        session, tenant_id, "mora", from_date, to_date, prestamista_id, route_id
    )

    cartera_total, cartera_vencida = await _portfolio(
        session, tenant_id, reference, prestamista_id, route_id
    )
    capital_proyectado = await _pending_principal(
        session, tenant_id, prestamista_id, route_id
    )

    activos, pagados, vencidos = await _loan_counts(
        session, tenant_id, prestamista_id, route_id
    )

    if cartera_total > 0:
        morosidad = round_money(cartera_vencida / cartera_total * Decimal(100))
    else:
        morosidad = Decimal("0.00")

    return DashboardSummary(
        capital_prestado=capital_prestado,
        capital_recuperado=capital_recuperado,
        capital_proyectado=capital_proyectado,
        intereses_generados=intereses,
        mora_cobrada=mora,
        utilidad_generada=round_money(intereses + mora),
        cartera_total=cartera_total,
        cartera_vencida=cartera_vencida,
        indice_morosidad=morosidad,
        prestamos_activos=activos,
        prestamos_pagados=pagados,
        prestamos_vencidos=vencidos,
    )


async def aging(
    session: AsyncSession, tenant_id: UUID, *, today: date | None = None
) -> AgingReport:
    """Calcula la antiguedad de la cartera vencida (RN-51).

    Se agrupa por cuota, no por prestamo: un prestamo puede tener cuotas al dia
    y cuotas vencidas al mismo tiempo.

    Args:
        session: Sesion de base de datos.
        tenant_id: Financiera.
        today: Fecha de corte.

    Returns:
        Las franjas con monto e cantidad de cuotas.
    """
    reference = today or _today_in_tz()

    rows = await session.execute(
        select(
            Installment.due_date,
            Installment.amount + Installment.late_fee - Installment.paid_amount,
        )
        .select_from(Installment)
        .join(Loan, Loan.id == Installment.loan_id)
        .where(
            Loan.tenant_id == tenant_id,
            Loan.status.in_(ACTIVE_LOAN_STATUSES),
            Installment.status.in_(("pendiente", "parcial", "vencida")),
        )
    )

    totals: dict[str, Decimal] = {label: Decimal("0.00") for label, _, _ in AGING_BUCKETS}
    counts: dict[str, int] = {label: 0 for label, _, _ in AGING_BUCKETS}

    for due_date, pending in rows.all():
        days = (reference - due_date).days
        label = _bucket_for(days)
        amount = _to_decimal(pending)

        totals[label] = round_money(totals[label] + amount)
        counts[label] += 1

    buckets = [
        AgingBucket(
            label=label,
            min_days=min_days,
            max_days=max_days,
            amount=totals[label],
            installments=counts[label],
        )
        for label, min_days, max_days in AGING_BUCKETS
    ]

    total_vencido = round_money(sum((bucket.amount for bucket in buckets[1:]), Decimal("0.00")))

    return AgingReport(buckets=buckets, total_vencido=total_vencido)


def _bucket_for(days: int) -> str:
    """Devuelve la franja de aging a la que pertenece un atraso.

    Un saldo con fecha futura cuenta como "al dia".
    """
    if days <= 0:
        return "al_dia"

    for label, min_days, max_days in AGING_BUCKETS:
        if label == "al_dia":
            continue
        if days >= min_days and (max_days is None or days <= max_days):
            return label

    return "mas_90"


async def collections_by_day(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    from_date: date,
    to_date: date,
) -> list[tuple[date, Decimal]]:
    """Total cobrado por dia en el rango.

    Sirve para la grafica de flujo de caja del dashboard.
    """
    # Se reutiliza la misma expresion para SELECT, GROUP BY y ORDER BY:
    # si se genera una nueva en cada clausula, PostgreSQL no las reconoce como
    # equivalentes y rechaza la consulta.
    day = local_date(Payment.created_at).label("day")

    rows = await session.execute(
        select(
            day,
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .where(
            Payment.tenant_id == tenant_id,
            Payment.status == "aplicado",
            day >= from_date,
            day <= to_date,
        )
        .group_by(day)
        .order_by(day)
    )

    return [(day_value, _to_decimal(total)) for day_value, total in rows.all()]
