"""Punto de entrada de la API de Credigest."""

from fastapi import FastAPI

from app.api.v1.loans import router as loans_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="API de gestion de prestamos para prestamistas y pequenas financieras.",
    version="0.1.0",
)

app.include_router(loans_router, prefix="/api/v1")


@app.get("/health", tags=["salud"])
async def health() -> dict[str, str]:
    """Verifica que la API este en linea."""
    return {"status": "ok"}
