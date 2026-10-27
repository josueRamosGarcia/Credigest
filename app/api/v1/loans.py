"""Endpoint del cotizador rapido de prestamos.

Este modulo solo valida, delega en el dominio y formatea. Ningun calculo vive
aqui: la logica esta en `app.domain.interest` y `app.domain.amortization`.
"""


from fastapi import APIRouter, HTTPException, status

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
from app.schemas.loan import ScheduleRow, SimulateRequest, SimulateResponse

router = APIRouter(prefix="/loans", tags=["prestamos"])


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
