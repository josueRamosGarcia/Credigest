# ============================================================================
# Etapa 1: Compilacion del Frontend (React + TypeScript + Vite)
# ============================================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ============================================================================
# Etapa 2: Runtime del Backend (Python 3.12 + FastAPI + WeasyPrint + SPA)
# ============================================================================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Mexico_City

# Librerias nativas requeridas por WeasyPrint para generar pagares y comprobantes PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Instalar dependencias de Python desde uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copiar codigo del backend, migraciones y el frontend compilado
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/storage

EXPOSE 8000

# Al iniciar: aplica migraciones, opcionalmente crea tenant/demo si se definieron variables y arranca Uvicorn
CMD ["sh", "-c", "\
  uv run alembic upgrade head && \
  if [ -n \"$SEED_ADMIN_EMAIL\" ] && [ -n \"$SEED_ADMIN_PASSWORD\" ]; then \
    uv run python -m app.scripts.seed_tenant \
      --name \"${SEED_TENANT_NAME:-Financiera Demo}\" \
      --slug \"${SEED_TENANT_SLUG:-demo}\" \
      --admin-name \"${SEED_ADMIN_NAME:-Administrador}\" \
      --admin-email \"$SEED_ADMIN_EMAIL\" \
      --admin-password \"$SEED_ADMIN_PASSWORD\" || true; \
  fi && \
  if [ \"$SEED_DEMO_DATA\" = \"true\" ]; then \
    uv run python -m app.scripts.seed_demo_data || true; \
  fi && \
  uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' \
"]
