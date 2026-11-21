"""Punto de entrada de la API de Credigest."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
from app.api.v1.portal import router as portal_router
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

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
app.include_router(portal_router, prefix="/api/v1")
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


_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if (_FRONTEND_DIST / "index.html").is_file():  # pragma: no cover - build de produccion
    _ASSETS_DIR = _FRONTEND_DIST / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Sirve archivos estaticos de la PWA o `index.html` para rutas de React Router."""
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json", "health")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        candidate = (_FRONTEND_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and _FRONTEND_DIST in candidate.parents
        ):
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
