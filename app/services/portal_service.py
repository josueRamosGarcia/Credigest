"""Servicio del portal de consulta para el cliente acreditado.

Garantiza aislamiento estricto:
1. El token emitido lleva `type="client_portal"`, por lo que es rechazado en
   cualquier endpoint de empleados (`get_current_user` exige `type="access"`).
2. Solo expone montos, progreso, cuotas y abonos propios del cliente; nunca
   notas internas del prestamista, documentos ni referencias.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.security import DUMMY_PASSWORD_HASH, verify_password
from app.domain.money import round_money
from app.domain.validation import CurpError, normalize_curp
from app.models.client import Client
from app.models.loan import Loan
from app.models.payment import Payment
from app.models.tenant import Tenant
from app.schemas.portal import (
    PortalInstallmentRead,
    PortalLoanSummary,
    PortalNextInstallment,
    PortalOverviewResponse,
    PortalPaymentRead,
)
from app.services.payment_service import business_today

PORTAL_TOKEN_MINUTES = 60


class PortalAuthError(Exception):
    """Credenciales o token del portal no validos."""


class AmbiguousTenantError(PortalAuthError):
    """La misma CURP existe en mas de una financiera y requiere `tenant_slug`."""


def create_portal_token(client_id: UUID, tenant_id: UUID) -> tuple[str, int]:
    """Crea un JWT de solo lectura exclusivo para el portal del cliente."""
    settings = get_settings()
    now = datetime.now(UTC).replace(microsecond=0)
    expires_at = now + timedelta(minutes=PORTAL_TOKEN_MINUTES)

    claims = {
        "sub": str(client_id),
        "tid": str(tenant_id),
        "role": "client",
        "type": "client_portal",
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(
        claims, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    return token, PORTAL_TOKEN_MINUTES * 60


def decode_portal_token(token: str) -> tuple[UUID, UUID]:
    """Valida un token de tipo `client_portal` y devuelve `(client_id, tenant_id)`."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "tid", "role", "type", "jti", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise PortalAuthError("Tu sesion de consulta expiro. Ingresa de nuevo.") from exc
    except jwt.InvalidTokenError as exc:
        raise PortalAuthError("Token de consulta no valido.") from exc

    if claims.get("type") != "client_portal":
        raise PortalAuthError("Este token no pertenece al portal de clientes.")

    try:
        return UUID(claims["sub"]), UUID(claims["tid"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PortalAuthError("Token de consulta mal formado.") from exc


async def authenticate_client(
    session: AsyncSession,
    curp: str,
    pin: str,
    *,
    tenant_slug: str | None = None,
) -> tuple[Client, Tenant]:
    """Valida CURP y PIN de 6 digitos del cliente."""
    try:
        normalized_curp = normalize_curp(curp)
    except CurpError as exc:
        verify_password(pin, DUMMY_PASSWORD_HASH)
        raise PortalAuthError("CURP o PIN incorrectos.") from exc

    stmt = (
        select(Client, Tenant)
        .join(Tenant, Tenant.id == Client.tenant_id)
        .where(
            Client.curp == normalized_curp,
            Tenant.is_active.is_(True),
        )
    )
    if tenant_slug:
        stmt = stmt.where(Tenant.slug == tenant_slug.lower().strip())

    rows = (await session.execute(stmt)).all()

    if not rows:
        verify_password(pin, DUMMY_PASSWORD_HASH)
        raise PortalAuthError("CURP o PIN incorrectos.")

    if len(rows) > 1 and not tenant_slug:
        raise AmbiguousTenantError(
            "Tu CURP esta registrada en mas de una financiera. "
            "Indica el codigo de la financiera para continuar."
        )

    client, tenant = rows[0]
    if not client.portal_pin_hash or not verify_password(pin, client.portal_pin_hash):
        raise PortalAuthError("CURP o PIN incorrectos.")

    if client.status != "activo":
        raise PortalAuthError("Tu cuenta de cliente no se encuentra activa.")

    return client, tenant


def _loan_folio(tenant: Tenant, loan: Loan) -> str:
    """Genera un identificador legible del prestamo para mostrar al cliente."""
    prefix = (tenant.slug or "CRD").upper()
    return f"PREST-{prefix}-{loan.start_date.year}-{loan.id.hex[:6].upper()}"


async def get_portal_overview(
    session: AsyncSession,
    tenant_id: UUID,
    client_id: UUID,
    *,
    today: date | None = None,
) -> PortalOverviewResponse:
    """Construye el estado de cuenta completo del cliente con sus prestamos y pagos."""
    reference_today = today or business_today()

    client = await session.scalar(
        select(Client).where(Client.id == client_id, Client.tenant_id == tenant_id)
    )
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if (
        client is None
        or client.status != "activo"
        or tenant is None
        or not tenant.is_active
    ):
        raise PortalAuthError("El perfil del cliente ya no esta disponible.")

    loans = (
        await session.scalars(
            select(Loan)
            .options(selectinload(Loan.installments))
            .where(
                Loan.tenant_id == tenant_id,
                Loan.client_id == client_id,
                Loan.status != "cancelado",
            )
            .order_by(Loan.created_at.desc())
        )
    ).all()

    loan_ids = [loan.id for loan in loans]
    payments_by_loan: dict[UUID, list[Payment]] = {loan_id: [] for loan_id in loan_ids}
    if loan_ids:
        payments = (
            await session.scalars(
                select(Payment)
                .where(
                    Payment.tenant_id == tenant_id,
                    Payment.loan_id.in_(loan_ids),
                    Payment.status == "aplicado",
                )
                .order_by(Payment.created_at.desc())
            )
        ).all()
        for payment in payments:
            payments_by_loan[payment.loan_id].append(payment)

    loan_summaries: list[PortalLoanSummary] = []
    total_paid_all = Decimal("0.00")
    total_remaining_all = Decimal("0.00")
    active_loans_count = 0

    for loan in loans:
        if loan.status in {"activo", "vencido"}:
            active_loans_count += 1

        paid_total = round_money(
            sum((inst.paid_amount for inst in loan.installments), Decimal("0.00"))
        )
        remaining_total = round_money(
            sum((inst.pending_amount for inst in loan.installments), Decimal("0.00"))
        )
        total_expected = round_money(paid_total + remaining_total)

        if total_expected > 0:
            progress = round_money(
                (paid_total / total_expected) * Decimal("100")
            )
        else:
            progress = Decimal("100.00")

        paid_count = sum(
            1 for inst in loan.installments if inst.status == "pagada"
        )

        pending_installments = [
            inst
            for inst in loan.installments
            if inst.status != "pagada" and inst.pending_amount > 0
        ]
        next_inst: PortalNextInstallment | None = None
        if pending_installments:
            first_pending = pending_installments[0]
            next_inst = PortalNextInstallment(
                number=first_pending.number,
                due_date=first_pending.due_date,
                pending_amount=first_pending.pending_amount,
                is_overdue=first_pending.due_date < reference_today,
            )

        total_paid_all = round_money(total_paid_all + paid_total)
        total_remaining_all = round_money(total_remaining_all + remaining_total)

        loan_summaries.append(
            PortalLoanSummary(
                id=loan.id,
                folio=_loan_folio(tenant, loan),
                principal=loan.principal,
                total_amount=loan.total_amount,
                rate_period=loan.rate_period,
                scheme=loan.scheme,
                term_periods=loan.term_periods,
                start_date=loan.start_date,
                end_date=loan.end_date,
                status=loan.status,
                paid_total=paid_total,
                remaining_total=remaining_total,
                progress_percent=progress,
                paid_installments_count=paid_count,
                next_installment=next_inst,
                installments=[
                    PortalInstallmentRead(
                        number=inst.number,
                        due_date=inst.due_date,
                        amount=inst.amount,
                        late_fee=inst.late_fee,
                        paid_amount=inst.paid_amount,
                        pending_amount=inst.pending_amount,
                        status=inst.status,
                        paid_at=inst.paid_at,
                    )
                    for inst in loan.installments
                ],
                payments=[
                    PortalPaymentRead(
                        id=pay.id,
                        folio=pay.folio,
                        amount=pay.amount,
                        method=pay.method,
                        created_at=pay.created_at,
                    )
                    for pay in payments_by_loan.get(loan.id, [])
                ],
            )
        )

    return PortalOverviewResponse(
        client_name=client.full_name,
        tenant_name=tenant.name,
        active_loans_count=active_loans_count,
        total_paid=total_paid_all,
        total_remaining=total_remaining_all,
        loans=loan_summaries,
    )
