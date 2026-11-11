"""Endpoints de pagos.

Registrar un pago exige autenticacion. El Administrador puede cobrar cualquier
prestamo; el cobrador y el prestamista, los de la financiera. La anulacion esta
reservada al Administrador y a quien tenga el permiso `cancel_payment` (RN-37).
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AuthContext, CurrentUserDep, get_current_user
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.models.client import Client
from app.models.loan import Loan
from app.models.user import User
from app.pdf.generator import MissingDependencyError, PdfError
from app.pdf.receipt import (
    build_receipt_context,
    receipt_filename,
    render_receipt_pdf,
    whatsapp_link,
)
from app.schemas.payment import (
    PaymentCancelRequest,
    PaymentCreate,
    PaymentDetail,
    PaymentListResponse,
    PaymentRead,
    PaymentResult,
)
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["pagos"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _not_found(message: str) -> HTTPException:
    """Error uniforme de recurso inexistente."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _conflict(message: str) -> HTTPException:
    """Error de regla de negocio."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


@router.post(
    "",
    response_model=PaymentResult,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un pago",
    description=(
        "Aplica el monto a las cuotas pendientes en orden: mora, luego interes y "
        "al final capital, empezando por la cuota mas antigua (RN-29)."
    ),
)
async def register_payment(
    payload: PaymentCreate,
    context: CurrentUserDep,
    session: SessionDep,
    request: Request,
) -> PaymentResult:
    """Registra un abono y devuelve el desglose.

    Raises:
        HTTPException: 404 si el prestamo no existe; 409 si no admite pagos o
            el monto excede el saldo.
    """
    try:
        meta = request_meta(request)
        outcome = await payment_service.register_payment(
            session,
            context.tenant_id,
            context.user.id,
            payload,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except payment_service.LoanNotPayableError as exc:
        raise _conflict(str(exc)) from exc
    except payment_service.PaymentExceedsBalanceError as exc:
        raise _conflict(str(exc)) from exc
    except payment_service.PaymentError as exc:
        raise _not_found(str(exc)) from exc

    return PaymentResult(
        payment=PaymentDetail.model_validate(outcome.payment),
        loan_status=outcome.loan_status,
        remaining_total=outcome.remaining_total,
        covered_late_fee=outcome.covered_late_fee,
        covered_interest=outcome.covered_interest,
        covered_principal=outcome.covered_principal,
    )


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="Listar pagos",
    description="Devuelve los pagos de la financiera del usuario.",
)
async def list_payments(
    context: CurrentUserDep,
    session: SessionDep,
    loan_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaymentListResponse:
    """Lista los pagos con filtros y paginacion."""
    items, total = await payment_service.list_payments(
        session,
        context.tenant_id,
        loan_id=loan_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )

    return PaymentListResponse(
        items=[PaymentRead.model_validate(payment) for payment in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentDetail,
    summary="Consultar un pago",
)
async def get_payment(
    payment_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> PaymentDetail:
    """Devuelve un pago con su desglose por concepto.

    Raises:
        HTTPException: 404 si no existe o es de otra financiera.
    """
    try:
        payment = await payment_service.get_payment(session, context.tenant_id, payment_id)
    except payment_service.PaymentNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    return PaymentDetail.model_validate(payment)


@router.post(
    "/{payment_id}/cancel",
    response_model=PaymentResult,
    summary="Anular un pago",
    description=(
        "Revierte las aplicaciones y recalcula los saldos. Solo se permite anular "
        "el pago mas reciente del prestamo (RN-36)."
    ),
)
async def cancel_payment(
    payment_id: UUID,
    payload: PaymentCancelRequest,
    context: Annotated[AuthContext, Depends(get_current_user)],
    session: SessionDep,
    request: Request,
) -> PaymentResult:
    """Anula un pago con un motivo.

    Raises:
        HTTPException: 403 sin permiso; 404 si no existe; 409 si ya esta
            anulado o hay pagos posteriores.
    """
    if not context.has_permission("cancel_payment"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu usuario no tiene permiso para anular pagos.",
        )

    try:
        meta = request_meta(request)
        outcome = await payment_service.cancel_payment(
            session,
            context.tenant_id,
            payment_id,
            context.user.id,
            payload.reason,
            ip_address=meta.ip_address,
            user_agent=meta.user_agent,
        )
    except payment_service.PaymentNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except payment_service.PaymentNotCancellableError as exc:
        raise _conflict(str(exc)) from exc

    return PaymentResult(
        payment=PaymentDetail.model_validate(outcome.payment),
        loan_status=outcome.loan_status,
        remaining_total=outcome.remaining_total,
        covered_late_fee=outcome.covered_late_fee,
        covered_interest=outcome.covered_interest,
        covered_principal=outcome.covered_principal,
    )


@router.get(
    "/{payment_id}/receipt.pdf",
    summary="Descargar el comprobante de pago",
    description=(
        "Genera un PDF de formato angosto con el folio, el cliente, el monto, "
        "el desglose por concepto y el saldo restante."
    ),
    response_class=Response,
)
async def download_receipt(
    payment_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> Response:
    """Devuelve el comprobante listo para imprimir o enviar.

    Raises:
        HTTPException: 404 si el pago no existe; 503 si falta WeasyPrint.
    """
    try:
        payment = await payment_service.get_payment(session, context.tenant_id, payment_id)
    except payment_service.PaymentNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    loan = await session.scalar(select(Loan).where(Loan.id == payment.loan_id))
    if loan is None:
        raise _not_found("El préstamo del pago ya no existe.")

    client = await session.scalar(select(Client).where(Client.id == loan.client_id))
    if client is None:
        raise _not_found("El cliente del préstamo ya no existe.")

    registered_by = None
    if payment.registered_by:
        registered_by = await session.scalar(
            select(User).where(User.id == payment.registered_by)
        )

    remaining = await payment_service.remaining_total(session, loan)
    applications = [(app.concept, app.amount) for app in payment.applications]

    try:
        receipt_context = build_receipt_context(
            tenant=context.tenant,
            client=client,
            loan=loan,
            payment=payment,
            applications=applications,
            remaining_total=remaining,
            registered_by=registered_by,
        )
        content = render_receipt_pdf(receipt_context)
    except MissingDependencyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{receipt_filename(payment)}"',
            "Content-Length": str(len(content)),
        },
    )


@router.get(
    "/{payment_id}/whatsapp",
    summary="Enlace de WhatsApp con el resumen del pago",
    description=(
        "Devuelve una URL de wa.me con el resumen listo para enviar al cliente. "
        "No requiere la API de WhatsApp."
    ),
)
async def whatsapp_summary(
    payment_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    """Devuelve el enlace de WhatsApp para compartir el comprobante."""
    try:
        payment = await payment_service.get_payment(session, context.tenant_id, payment_id)
    except payment_service.PaymentNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    loan = await session.scalar(select(Loan).where(Loan.id == payment.loan_id))
    if loan is None:
        raise _not_found("El préstamo del pago ya no existe.")

    client = await session.scalar(select(Client).where(Client.id == loan.client_id))
    if client is None:
        raise _not_found("El cliente del préstamo ya no existe.")

    return {
        "url": whatsapp_link(
            client.phone,
            tenant_name=context.tenant.name,
            payment=payment,
        ),
        "phone": client.phone,
    }
