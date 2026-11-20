"""Endpoints del portal de consulta para el cliente acreditado (`/api/v1/portal`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import login_limiter
from app.core.request_meta import request_meta
from app.db.session import get_session
from app.models.client import Client
from app.models.loan import Loan
from app.models.tenant import Tenant
from app.models.user import User
from app.pdf.generator import MissingDependencyError, PdfError
from app.pdf.receipt import (
    build_receipt_context,
    receipt_filename,
    render_receipt_pdf,
)
from app.schemas.portal import (
    PortalLoginRequest,
    PortalOverviewResponse,
    PortalTokenResponse,
)
from app.services import payment_service, portal_service

router = APIRouter(prefix="/portal", tags=["portal del cliente"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_bearer = HTTPBearer(auto_error=False)


def _require_portal_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> tuple[UUID, UUID]:
    """Extrae y valida el token exclusivo `client_portal`."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de consulta del cliente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return portal_service.decode_portal_token(credentials.credentials)
    except portal_service.PortalAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


PortalAuthDep = Annotated[tuple[UUID, UUID], Depends(_require_portal_auth)]


@router.post(
    "/login",
    response_model=PortalTokenResponse,
    summary="Iniciar sesion en el portal del cliente (CURP + PIN)",
    description=(
        "Valida la CURP y el PIN de 6 digitos del cliente y emite un token "
        "de solo lectura exclusivo para consultar sus propios prestamos."
    ),
)
async def portal_login(
    payload: PortalLoginRequest,
    session: SessionDep,
    request: Request,
) -> PortalTokenResponse:
    """Autentica al cliente con CURP y PIN de 6 digitos."""
    meta = request_meta(request)
    client_key = f"portal:{meta.ip_address or 'desconocido'}"
    allowed, retry_after = login_limiter.check(client_key)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiados intentos fallidos. "
                f"Vuelve a intentarlo en {retry_after} segundos."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    try:
        client, tenant = await portal_service.authenticate_client(
            session,
            payload.curp,
            payload.pin,
            tenant_slug=payload.tenant_slug,
        )
    except portal_service.AmbiguousTenantError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except portal_service.PortalAuthError as exc:
        login_limiter.hit(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    login_limiter.reset(client_key)
    token, expires_in = portal_service.create_portal_token(client.id, tenant.id)

    return PortalTokenResponse(
        access_token=token,
        expires_in=expires_in,
        client_name=client.full_name,
        tenant_name=tenant.name,
    )


@router.get(
    "/me",
    response_model=PortalOverviewResponse,
    summary="Estado de cuenta y progreso de prestamos del cliente",
    description=(
        "Devuelve el avance de pago, proximo vencimiento, calendario de cuotas "
        "e historial de abonos de todos los prestamos del cliente autenticado."
    ),
)
async def portal_me(
    auth: PortalAuthDep,
    session: SessionDep,
) -> PortalOverviewResponse:
    """Devuelve el resumen y progreso de los prestamos del cliente."""
    client_id, tenant_id = auth
    try:
        return await portal_service.get_portal_overview(
            session, tenant_id, client_id
        )
    except portal_service.PortalAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


@router.get(
    "/payments/{payment_id}/receipt.pdf",
    summary="Descargar comprobante de pago desde el portal del cliente",
    response_class=Response,
)
async def portal_download_receipt(
    payment_id: UUID,
    auth: PortalAuthDep,
    session: SessionDep,
) -> Response:
    """Permite al cliente descargar el comprobante PDF de un pago propio."""
    client_id, tenant_id = auth

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El perfil del cliente ya no esta disponible.",
        )

    try:
        payment = await payment_service.get_payment(session, tenant_id, payment_id)
    except payment_service.PaymentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    if payment.status != "aplicado":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El comprobante no esta disponible.",
        )

    loan = await session.scalar(
        select(Loan).where(
            Loan.id == payment.loan_id,
            Loan.tenant_id == tenant_id,
            Loan.client_id == client_id,
            Loan.status != "cancelado",
        )
    )
    if loan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El comprobante no pertenece a tu cuenta.",
        )

    registered_by = None
    if payment.registered_by:
        registered_by = await session.scalar(
            select(User).where(User.id == payment.registered_by)
        )

    remaining = await payment_service.remaining_total(session, loan)
    applications = [(app.concept, app.amount) for app in payment.applications]

    try:
        receipt_context = build_receipt_context(
            tenant=tenant,
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
