"""Creacion del tenant inicial y su primer administrador.

No existe autorregistro (RF-52). Una financiera nueva se crea con este script,
que es idempotente: si el tenant ya existe, no duplica nada.

Uso::

    uv run python -m app.scripts.seed_tenant \
        --name "Financiera Ejemplo" \
        --slug financiera-ejemplo \
        --admin-name "Administrador" \
        --admin-email admin@ejemplo.mx \
        --admin-password "cambiar-esta-clave"

La contrasena se recibe por argumento o por la variable de entorno
``SEED_ADMIN_PASSWORD``. Nunca se escribe en el codigo.
"""

import argparse
import asyncio
import os
import sys
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.system_setting import SystemSetting
from app.models.tenant import Tenant
from app.models.user import User


class SeedError(RuntimeError):
    """Error al crear el tenant inicial."""


async def seed_tenant(
    name: str,
    slug: str,
    admin_name: str,
    admin_email: str,
    admin_password: str,
) -> tuple[Tenant, User]:
    """Crea un tenant con su configuracion y primer administrador.

    Args:
        name: Nombre de la financiera.
        slug: Identificador legible, unico.
        admin_name: Nombre completo del administrador.
        admin_email: Correo del administrador, unico global.
        admin_password: Contrasena en claro; se guarda hasheada.

    Returns:
        El tenant y el usuario creados.

    Raises:
        SeedError: Si el slug o el correo ya existen.
    """
    if len(admin_password) < 10:
        raise SeedError("La contrasena debe tener al menos 10 caracteres.")

    async with SessionLocal() as session:
        existing_tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
        if existing_tenant is not None:
            raise SeedError(f"Ya existe un tenant con el slug '{slug}'.")

        existing_user = await session.scalar(select(User).where(User.email == admin_email))
        if existing_user is not None:
            raise SeedError(f"Ya existe un usuario con el correo '{admin_email}'.")

        tenant = Tenant(name=name, slug=slug, plan="empresarial")
        session.add(tenant)
        await session.flush()

        session.add(
            SystemSetting(
                tenant_id=tenant.id,
                default_late_fee_rate=Decimal("0.1000"),
                default_scheme="simple",
                grace_days=5,
                timezone="America/Mexico_City",
            )
        )

        admin = User(
            tenant_id=tenant.id,
            full_name=admin_name,
            email=admin_email,
            password_hash=hash_password(admin_password),
            role="admin",
            permissions={},
        )
        session.add(admin)

        await session.commit()
        await session.refresh(admin)

        return tenant, admin


def _build_parser() -> argparse.ArgumentParser:
    """Construye el parser de argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(description="Crea una financiera y su primer administrador.")
    parser.add_argument("--name", required=True, help="Nombre de la financiera.")
    parser.add_argument("--slug", required=True, help="Identificador legible unico.")
    parser.add_argument("--admin-name", required=True, help="Nombre del administrador.")
    parser.add_argument("--admin-email", required=True, help="Correo del administrador.")
    parser.add_argument(
        "--admin-password",
        default=None,
        help="Contrasena del administrador. Si se omite, se lee de SEED_ADMIN_PASSWORD.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada del script."""
    args = _build_parser().parse_args(argv)

    password = args.admin_password or os.environ.get("SEED_ADMIN_PASSWORD")
    if not password:
        print(
            "Falta la contrasena: usa --admin-password o la variable SEED_ADMIN_PASSWORD.",
            file=sys.stderr,
        )
        return 2

    try:
        tenant, admin = asyncio.run(
            seed_tenant(
                name=args.name,
                slug=args.slug,
                admin_name=args.admin_name,
                admin_email=args.admin_email,
                admin_password=password,
            )
        )
    except SeedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Tenant creado: {tenant.name} ({tenant.slug})")
    print(f"Administrador creado: {admin.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
