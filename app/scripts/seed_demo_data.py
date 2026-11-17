"""Poblado de datos de demostracion para pruebas manuales y demos.

Inserta en la primera financiera activa:
- 2 clientes con referencias personales y PIN de 6 digitos para `/mi-credito`.
- 2 prestamos aprobados con su tabla de amortizacion.
- 4 abonos registrados (efectivo y SPEI) con desglose en `payment_application`.
- 1 ruta de cobro activa para la zona `Centro`.

Es idempotente: si los clientes de demo ya existen en la financiera, muestra
sus credenciales sin duplicar registros.

Uso::

    uv run python -m app.scripts.seed_demo_data
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.client import Client
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.client import ClientCreate, ClientReferenceCreate
from app.schemas.loan import LoanCreate
from app.schemas.payment import PaymentCreate
from app.services import client_service, loan_service, payment_service, route_service

CURP_MARIA = "LOPJ850312MDFZRN07"
PIN_MARIA = "123456"

CURP_JUAN = "GALJ900715HJCMPR06"
PIN_JUAN = "654321"


async def seed_demo_data() -> None:
    """Inserta clientes, prestamos, abonos y ruta de demostracion."""
    async with SessionLocal() as session:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.is_active.is_(True)).limit(1)
        )
        if tenant is None:
            raise RuntimeError(
                "No existe ninguna financiera activa. Ejecuta primero seed_tenant."
            )

        actor = await session.scalar(
            select(User)
            .where(User.tenant_id == tenant.id, User.is_active.is_(True))
            .order_by(User.created_at.asc())
            .limit(1)
        )
        if actor is None:
            raise RuntimeError("No existe ningun usuario activo en la financiera.")

        today = date.today()

        # --- Cliente 1: Maria Lopez Perez ---
        maria = await session.scalar(
            select(Client).where(
                Client.tenant_id == tenant.id, Client.curp == CURP_MARIA
            )
        )
        if maria is None:
            maria = await client_service.create_client(
                session,
                tenant.id,
                actor.id,
                ClientCreate(
                    full_name="María López Pérez",
                    curp=CURP_MARIA,
                    phone="8711234567",
                    address="Av. Juárez 123, Col. Centro, Torreón, Coahuila",
                    zone="Centro",
                    notes="Cliente puntual con negocio de abarrotes.",
                    references=[
                        ClientReferenceCreate(
                            name="Roberto López Pérez",
                            relationship="Hermano",
                            phone="8717654321",
                            address="Calle Hidalgo 45, Col. Centro, Torreón",
                        ),
                        ClientReferenceCreate(
                            name="Elena Martínez",
                            relationship="Vecina",
                            phone="8719988776",
                            address="Av. Juárez 129, Col. Centro, Torreón",
                        ),
                    ],
                ),
            )
            await client_service.set_portal_pin(
                session, tenant.id, maria.id, pin=PIN_MARIA, actor_id=actor.id
            )

            loan_maria = await loan_service.create_loan(
                session,
                tenant.id,
                actor.id,
                LoanCreate(
                    client_id=maria.id,
                    principal=Decimal("10000.00"),
                    interest_rate=Decimal("0.0500"),
                    rate_period="semanal",
                    scheme="simple",
                    term_periods=12,
                    start_date=today - timedelta(weeks=3),
                ),
            )

            for amount in (
                Decimal("1333.33"),
                Decimal("1333.33"),
                Decimal("1333.34"),
            ):
                await payment_service.register_payment(
                    session,
                    tenant.id,
                    actor.id,
                    PaymentCreate(
                        loan_id=loan_maria.id,
                        amount=amount,
                        method="efectivo",
                        payment_type="completo",
                    ),
                )

        # --- Cliente 2: Juan Garcia Hernandez ---
        juan = await session.scalar(
            select(Client).where(
                Client.tenant_id == tenant.id, Client.curp == CURP_JUAN
            )
        )
        if juan is None:
            juan = await client_service.create_client(
                session,
                tenant.id,
                actor.id,
                ClientCreate(
                    full_name="Juan García Hernández",
                    curp=CURP_JUAN,
                    phone="8715554433",
                    address="Blvd. Independencia 450, Col. Centro, Torreón",
                    zone="Centro",
                    notes="Taller mecánico, prefiere pagar por transferencia SPEI.",
                    references=[
                        ClientReferenceCreate(
                            name="Sofía Hernández",
                            relationship="Madre",
                            phone="8714443322",
                            address="Calle Mina 210, Gómez Palacio",
                        ),
                    ],
                ),
            )
            await client_service.set_portal_pin(
                session, tenant.id, juan.id, pin=PIN_JUAN, actor_id=actor.id
            )

            loan_juan = await loan_service.create_loan(
                session,
                tenant.id,
                actor.id,
                LoanCreate(
                    client_id=juan.id,
                    principal=Decimal("15000.00"),
                    interest_rate=Decimal("0.0300"),
                    rate_period="mensual",
                    scheme="cuota_fija",
                    term_periods=6,
                    start_date=today - timedelta(days=15),
                ),
            )

            await payment_service.register_payment(
                session,
                tenant.id,
                actor.id,
                PaymentCreate(
                    loan_id=loan_juan.id,
                    amount=Decimal("1500.00"),
                    method="spei",
                    spei_reference="SPEI987654321",
                    payment_type="parcial",
                ),
            )

        # --- Ruta de cobro para la zona Centro ---
        await route_service.create_route(
            session,
            tenant.id,
            zone="Centro",
            route_date=today + timedelta(days=30),
            cobrador_id=actor.id,
            created_by=actor.id,
        )

        print("====================================================")
        print(f"Datos de demostracion listos en: {tenant.name}")
        print("----------------------------------------------------")
        print("Cliente 1: María López Pérez")
        print(f"  CURP (para /mi-credito): {CURP_MARIA}")
        print(f"  PIN  (para /mi-credito): {PIN_MARIA}")
        print("  Prestamo: $10,000.00 MXN (12 semanas, 3 cuotas pagadas = 25% avance)")
        print("----------------------------------------------------")
        print("Cliente 2: Juan García Hernández")
        print(f"  CURP (para /mi-credito): {CURP_JUAN}")
        print(f"  PIN  (para /mi-credito): {PIN_JUAN}")
        print("  Prestamo: $15,000.00 MXN (6 meses, 1 abono SPEI de $1,500.00)")
        print("====================================================")


def main() -> None:  # pragma: no cover - punto CLI
    asyncio.run(seed_demo_data())


if __name__ == "__main__":  # pragma: no cover
    main()
