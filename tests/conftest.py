"""Configuracion compartida de las pruebas.

Las pruebas de integracion usan una base de datos separada, `credigest_test`,
creada y destruida por el fixture de sesion. Cada prueba corre dentro de una
transaccion que se revierte al terminar, de modo que no se contaminan entre si.

Si la base de prueba no esta disponible, los fixtures se saltan con un mensaje
claro en lugar de fallar de forma confusa.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import app

TEST_DATABASE_URL = get_settings().database_url.replace("/credigest", "/credigest_test")


@pytest.fixture(scope="session")
async def _prepare_database() -> AsyncIterator[None]:
    """Crea el esquema de prueba al inicio y lo elimina al final."""
    admin_engine = create_async_engine(
        get_settings().database_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )

    try:
        async with admin_engine.connect() as connection:
            from sqlalchemy import text

            await connection.execute(text("DROP DATABASE IF EXISTS credigest_test"))
            await connection.execute(text("CREATE DATABASE credigest_test"))
    except Exception as exc:  # pragma: no cover - depende del entorno
        await admin_engine.dispose()
        pytest.skip(f"No se pudo preparar la base de prueba: {exc}")

    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield

    await test_engine.dispose()
    async with admin_engine.connect() as connection:
        from sqlalchemy import text

        await connection.execute(text("DROP DATABASE IF EXISTS credigest_test"))
    await admin_engine.dispose()


@pytest.fixture
async def db_session(_prepare_database: None) -> AsyncIterator[AsyncSession]:
    """Sesion envuelta en una transaccion que se revierte al terminar."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, class_=AsyncSession
    )
    session = session_factory()

    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def api_client(
    db_session: AsyncSession, _prepare_database: None
) -> AsyncIterator[AsyncClient]:
    """Cliente HTTP que usa la misma transaccion de la prueba."""

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


def pytest_configure(config: Any) -> None:
    """Registra marcadores personalizados."""
    config.addinivalue_line("markers", "db: prueba que requiere PostgreSQL")


__all__ = ["TEST_DATABASE_URL", "asyncio"]
