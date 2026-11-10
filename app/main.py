"""Punto de entrada de la API de Credigest."""

from fastapi import FastAPI

from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.clients import router as clients_router
from app.api.v1.loans import router as loans_router
from app.api.v1.payments import router as payments_router
from app.api.v1.routes import router as routes_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="API de gestion de prestamos para prestamistas y pequenas financieras.",
    version="0.1.0",
)

app.include_router(audit_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(loans_router, prefix="/api/v1")
app.include_router(payments_router, prefix="/api/v1")
app.include_router(routes_router, prefix="/api/v1")


@app.get("/health", tags=["salud"])
async def health() -> dict[str, str]:
    """Verifica que la API este en linea."""
    return {"status": "ok"}
