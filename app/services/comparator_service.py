"""Servicio del comparador bancario (RF-45 a RF-47, RN-52 a RN-54)."""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.comparator import (
    DISCLAIMER_TEXT,
    BankOfferInput,
    ComparisonRow,
    evaluate_bank_offer,
    evaluate_own_offer,
)
from app.domain.interest import Frequency, LoanTerms, Scheme
from app.models.bank import Bank
from app.schemas.comparator import BankCreate, BankUpdate, CompareRequest
from app.services import audit_service

#: Catalogo estatico inicial de referencia para una financiera nueva (RF-45).
DEFAULT_BANKS: tuple[tuple[str, str, str, str], ...] = (
    ("BBVA México (Crédito Personal)", "0.3990", "0.5120", "350.00"),
    ("Banorte (Crédito de Nómina)", "0.3490", "0.4480", "250.00"),
    ("Citibanamex (Crédito Personal)", "0.4200", "0.5560", "400.00"),
    ("Banco Azteca (Préstamo Personal)", "0.6800", "0.9620", "0.00"),
    ("BanCoppel (Préstamo Digital)", "0.6200", "0.8450", "0.00"),
)


class ComparatorError(Exception):
    """Error de negocio del comparador bancario."""


class BankNotFoundError(ComparatorError):
    """La institucion bancaria no existe en esta financiera."""


async def ensure_default_catalog(session: AsyncSession, tenant_id: UUID) -> None:
    """Inicializa el catalogo estatico del tenant si aun no tiene bancos."""
    existing = await session.scalar(
        select(func.count()).select_from(Bank).where(Bank.tenant_id == tenant_id)
    )
    if int(existing or 0) > 0:
        return

    for name, annual_rate, cat, opening_fee in DEFAULT_BANKS:
        session.add(
            Bank(
                tenant_id=tenant_id,
                name=name,
                annual_rate=Decimal(annual_rate),
                cat=Decimal(cat),
                opening_fee=Decimal(opening_fee),
                is_active=True,
            )
        )
    await session.commit()


async def list_banks(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    only_active: bool = False,
) -> Sequence[Bank]:
    """Lista las instituciones bancarias del tenant, inicializando el catalogo si esta vacio."""
    await ensure_default_catalog(session, tenant_id)

    conditions = [Bank.tenant_id == tenant_id]
    if only_active:
        conditions.append(Bank.is_active.is_(True))

    result = await session.scalars(
        select(Bank).where(*conditions).order_by(Bank.name.asc())
    )
    return result.all()


async def get_bank(session: AsyncSession, tenant_id: UUID, bank_id: UUID) -> Bank:
    """Obtiene una institucion bancaria del tenant."""
    bank = await session.scalar(
        select(Bank).where(Bank.id == bank_id, Bank.tenant_id == tenant_id)
    )
    if bank is None:
        raise BankNotFoundError("La institucion bancaria no existe.")
    return bank


async def create_bank(
    session: AsyncSession,
    tenant_id: UUID,
    actor_id: UUID,
    payload: BankCreate,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Bank:
    """Agrega una institucion al catalogo de la financiera (RN-54)."""
    await ensure_default_catalog(session, tenant_id)

    bank = Bank(
        tenant_id=tenant_id,
        name=payload.name,
        annual_rate=payload.annual_rate,
        cat=payload.cat,
        opening_fee=payload.opening_fee,
        is_active=payload.is_active,
    )
    session.add(bank)
    await session.flush()

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="bank.create",
        entity="bank",
        entity_id=bank.id,
        after={
            "name": bank.name,
            "annual_rate": str(bank.annual_rate),
            "opening_fee": str(bank.opening_fee),
            "is_active": bank.is_active,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    await session.refresh(bank)
    return bank


async def update_bank(
    session: AsyncSession,
    tenant_id: UUID,
    bank_id: UUID,
    actor_id: UUID,
    payload: BankUpdate,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Bank:
    """Actualiza una institucion del catalogo bancario (RN-54)."""
    bank = await get_bank(session, tenant_id, bank_id)

    before = {
        "name": bank.name,
        "annual_rate": str(bank.annual_rate),
        "cat": str(bank.cat),
        "opening_fee": str(bank.opening_fee),
        "is_active": bank.is_active,
    }

    if payload.name is not None:
        bank.name = payload.name
    if payload.annual_rate is not None:
        bank.annual_rate = payload.annual_rate
    if payload.cat is not None:
        bank.cat = payload.cat
    if payload.opening_fee is not None:
        bank.opening_fee = payload.opening_fee
    if payload.is_active is not None:
        bank.is_active = payload.is_active

    after = {
        "name": bank.name,
        "annual_rate": str(bank.annual_rate),
        "cat": str(bank.cat),
        "opening_fee": str(bank.opening_fee),
        "is_active": bank.is_active,
    }

    await audit_service.record(
        session,
        tenant_id=tenant_id,
        user_id=actor_id,
        action="bank.update",
        entity="bank",
        entity_id=bank.id,
        before=before,
        after=after,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await session.commit()
    await session.refresh(bank)
    return bank


async def compare_offers(
    session: AsyncSession,
    tenant_id: UUID,
    tenant_name: str,
    payload: CompareRequest,
) -> tuple[str, ComparisonRow, list[ComparisonRow]]:
    """Compara la oferta propia contra las instituciones activas del catalogo."""
    banks = await list_banks(session, tenant_id, only_active=True)
    if payload.bank_ids:
        selected_ids = set(payload.bank_ids)
        banks = [bank for bank in banks if bank.id in selected_ids]

    frequency = Frequency(payload.rate_period)
    scheme = Scheme(payload.scheme)
    terms = LoanTerms.create(
        principal=payload.principal,
        rate=payload.interest_rate,
        periods=payload.term_periods,
        frequency=frequency,
        scheme=scheme,
    )

    own_row = evaluate_own_offer(
        terms,
        institution_name=tenant_name,
        opening_fee=payload.opening_fee,
    )

    bank_rows = [
        evaluate_bank_offer(
            BankOfferInput(
                name=bank.name,
                annual_rate=bank.annual_rate,
                opening_fee=bank.opening_fee,
                reference_cat=bank.cat,
            ),
            principal=payload.principal,
            periods=payload.term_periods,
            frequency=frequency,
        )
        for bank in banks
    ]

    return DISCLAIMER_TEXT, own_row, bank_rows

