"""Endpoints de prestamos.

La simulacion es publica: es una calculadora y no expone datos. Todo lo demas
requiere autenticacion y filtra por el tenant del usuario.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, require_role
from app.db.session import get_session
from app.domain.amortization import build_schedule
from app.domain.interest import (
    Frequency,
    LoanTerms,
    Scheme,
    annual_equivalent_rate,
    due_date,
    first_installment,
    last_installment,
    total_amount,
    total_interest,
)
from app.schemas.loan import (
    LoanCancelRequest,
    LoanCreate,
    LoanDetail,
    LoanListResponse,
    LoanRead,
    ScheduleRow,
    SimulateRequest,
    SimulateResponse,
)
from app.services import loan_service

router = APIRouter(prefix="/loans", tags=["prestamos"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LenderDep = Annotated[object, Depends(require_role("prestamista"))]


def _not_found(message: str) -> HTTPException:
    """Error uniforme de recurso inexistente."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _parse_frequency(raw: str) -> Frequency:
    """Convierte el texto de la peticion en una frecuencia valida."""
    try:
        return Frequency(raw)
    except ValueError as exc:
        valid = ", ".join(frequency.value for frequency in Frequency)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Frecuencia no valida: {raw!r}. Valores permitidos: {valid}.",
        ) from exc


def _parse_scheme(raw: str) -> Scheme:
    """Convierte el texto de la peticion en un esquema valido."""
    try:
        return Scheme(raw)
    except ValueError as exc:
        valid = ", ".join(scheme.value for scheme in Scheme)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Esquema no valido: {raw!r}. Valores permitidos: {valid}.",
        ) from exc


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="Simular un prestamo",
    description=(
        "Calcula cuota, interes total y tabla de amortizacion sin guardar nada (RN-12). "
        "La tasa se interpreta por periodo segun la frecuencia (RN-04)."
    ),
)
async def simulate(payload: SimulateRequest) -> SimulateResponse:
    """Devuelve el resultado de la simulacion de un prestamo.

    Args:
        payload: Condiciones propuestas por el prestamista.

    Returns:
        La cuota, los totales, la fecha de termino y la tabla completa.

    Raises:
        HTTPException: 422 si los valores no cumplen las reglas de negocio.
    """
    frequency = _parse_frequency(payload.rate_period)
    scheme = _parse_scheme(payload.scheme)

    # Pydantic ya garantiza principal > 0, tasa >= 0 y plazo entero positivo,
    # asi que las validaciones de dominio no pueden fallar aqui.
    terms = LoanTerms.create(
        principal=payload.principal,
        rate=payload.interest_rate,
        periods=payload.term_periods,
        frequency=frequency,
        scheme=scheme,
    )

    schedule = build_schedule(terms, payload.start_date)
    interest = total_interest(terms)

    return SimulateResponse(
        installment_amount=first_installment(terms),
        installment_amount_last=last_installment(terms),
        total_interest=interest,
        total_amount=total_amount(terms),
        estimated_profit=interest,
        end_date=due_date(payload.start_date, terms.frequency, terms.periods),
        annual_equivalent_rate=annual_equivalent_rate(terms.rate, terms.frequency),
        schedule=[
            ScheduleRow(
                number=row.number,
                due_date=row.due_date,
                amount=row.amount,
                interest_part=row.interest_part,
                principal_part=row.principal_part,
                balance=row.balance,
            )
            for row in schedule
        ],
    )


@router.get(
    "",
    response_model=LoanListResponse,
    summary="Listar prestamos",
    description="Devuelve los prestamos de la financiera del usuario.",
)
async def list_loans(
    context: CurrentUserDep,
    session: SessionDep,
    loan_status: Annotated[
        str | None,
        Query(alias="status", pattern="^(activo|pagado|vencido|cancelado)$"),
    ] = None,
    client_id: Annotated[UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LoanListResponse:
    """Lista los prestamos con paginacion."""
    items, total = await loan_service.list_loans(
        session,
        context.tenant_id,
        status=loan_status,
        client_id=client_id,
        page=page,
        page_size=page_size,
    )

    return LoanListResponse(
        items=[LoanRead.model_validate(loan) for loan in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=LoanDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Aprobar un prestamo",
    description=(
        "Convierte una simulacion en un prestamo real: congela las condiciones y "
        "genera el calendario de cuotas. Requiere rol de prestamista o admin."
    ),
)
async def create_loan(
    payload: LoanCreate,
    context: CurrentUserDep,
    session: SessionDep,
) -> LoanDetail:
    """Aprueba un prestamo y devuelve su calendario.

    Raises:
        HTTPException: 404 si el cliente no existe; 409 si esta inactivo o tiene
            atrasos graves.
    """
    try:
        loan = await loan_service.create_loan(
            session, context.tenant_id, context.user.id, payload
        )
    except loan_service.ClientNotFoundForLoanError as exc:
        raise _not_found(str(exc)) from exc
    except loan_service.InactiveClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except loan_service.ClientHasOverdueDebtError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    return LoanDetail.model_validate(loan)


@router.get(
    "/{loan_id}",
    response_model=LoanDetail,
    summary="Consultar un prestamo",
)
async def get_loan(
    loan_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> LoanDetail:
    """Devuelve un prestamo con su calendario.

    Raises:
        HTTPException: 404 si no existe o es de otra financiera.
    """
    try:
        loan = await loan_service.get_loan_detail(session, context.tenant_id, loan_id)
    except loan_service.LoanNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    return LoanDetail.model_validate(loan)


@router.get(
    "/{loan_id}/schedule",
    response_model=list[ScheduleRow],
    summary="Consultar el calendario de cuotas",
)
async def get_schedule(
    loan_id: UUID,
    context: CurrentUserDep,
    session: SessionDep,
) -> list[ScheduleRow]:
    """Devuelve el calendario con los saldos calculados.

    El saldo no se guarda en cada cuota: se recalcula desde las condiciones
    congeladas del prestamo, que son inmutables.
    """
    try:
        loan = await loan_service.get_loan(session, context.tenant_id, loan_id)
    except loan_service.LoanNotFoundError as exc:
        raise _not_found(str(exc)) from exc

    terms = LoanTerms.create(
        principal=loan.principal,
        rate=loan.interest_rate,
        periods=loan.term_periods,
        frequency=Frequency(loan.rate_period),
        scheme=Scheme(loan.scheme),
    )
    schedule = build_schedule(terms, loan.start_date)

    return [
        ScheduleRow(
            number=row.number,
            due_date=row.due_date,
            amount=row.amount,
            interest_part=row.interest_part,
            principal_part=row.principal_part,
            balance=row.balance,
        )
        for row in schedule
    ]


@router.post(
    "/{loan_id}/cancel",
    response_model=LoanRead,
    summary="Cancelar un prestamo",
    description=(
        "Marca el prestamo como cancelado conservando su historico. "
        "Solo el Administrador puede hacerlo."
    ),
)
async def cancel_loan(
    loan_id: UUID,
    payload: LoanCancelRequest,
    context: CurrentUserDep,
    session: SessionDep,
) -> LoanRead:
    """Cancela un prestamo con un motivo.

    Raises:
        HTTPException: 404 si no existe; 409 si ya esta pagado o cancelado.
    """
    try:
        loan = await loan_service.cancel_loan(
            session, context.tenant_id, loan_id, payload.reason
        )
    except loan_service.LoanNotFoundError as exc:
        raise _not_found(str(exc)) from exc
    except loan_service.LoanNotCancellableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    return LoanRead.model_validate(loan)
