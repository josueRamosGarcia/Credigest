"""Punto de entrada de la API de Credigest."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.clients import router as clients_router
from app.api.v1.comparator import banks_router, compare_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.documents import router as documents_router
from app.api.v1.loans import router as loans_router
from app.api.v1.payments import router as payments_router
from app.api.v1.routes import router as routes_router
from app.api.v1.users import router as users_router
from app.api.v1.users import settings_router
from app.core.config import get_settings
from app.db.session import get_session

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="API de gestion de prestamos para prestamistas y pequenas financieras.",
    version="0.1.0",
)

app.include_router(audit_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(banks_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(compare_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(loans_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(routes_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/health", tags=["salud"])
async def health() -> dict[str, str]:
    """Verifica que la API este en linea."""
    return {"status": "ok"}


@app.get("/health/db", tags=["salud"])
async def health_db(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Verifica la conectividad con PostgreSQL (02-arquitectura.md §11)."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - fallo de infraestructura
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible.",
        ) from exc
    return {"status": "ok", "database": "ok"}
