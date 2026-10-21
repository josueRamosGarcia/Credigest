# Credigest

Sistema SaaS de gestión de préstamos para prestamistas y pequeñas financieras en México.
Roles: Administrador, Prestamista, Cobrador. Documentación completa en `/docs`.

## Stack (decidido)

**Backend (Python)**
- Python 3.12+ con FastAPI
- SQLAlchemy 2.x + Alembic (migraciones)
- PostgreSQL 16
- Pydantic v2 para validación
- JWT (access + refresh) con `passlib[bcrypt]`
- PDFs con WeasyPrint (plantillas HTML + Jinja2)
- Pruebas con `pytest` + `pytest-cov` + `httpx`
- Calidad con `ruff` y `mypy`
- Gestor de dependencias y entorno: `uv`

**Frontend**
- React + TypeScript + Vite
- TanStack Query para estado del servidor
- React Hook Form + Zod para formularios
- PWA responsive para el cobrador (misma base React)
- Pruebas con Vitest + Testing Library

## Reglas de negocio críticas

- NUNCA usar números decimales flotantes (`float`) para dinero. En Python usar `Decimal`; en PostgreSQL usar `numeric(14,2)`. Redondeo `ROUND_HALF_UP` a 2 decimales.
- Todo cambio de saldo, pago, anulación o edición de tasa debe registrarse en la bitácora de auditoría.
- Los pagos nunca se borran: se anulan con un registro de anulación (trazabilidad).
- Los datos personales (CURP, INE) son sensibles: no se escriben en logs.
- El aislamiento por tenant es obligatorio: ninguna consulta puede cruzar datos entre financieras.
- La lógica financiera se congela al aprobar un préstamo; cambiar parámetros globales no altera préstamos existentes.

## Cómo trabajar

- Un módulo a la vez, definido en `docs/04-roadmap.md`.
- La lógica de cálculo vive en `app/domain/` como funciones puras con pruebas, sin dependencia de la base de datos ni de FastAPI.
- La API no calcula: valida, llama al servicio y formatea. Los cálculos viven en `app/domain/`; las transacciones en `app/services/`.
- Cada función de cálculo financiero debe tener pruebas con ejemplos calculados a mano.
- Respetar las reglas numeradas (`RF-xx`, `RNF-xx`, `RN-xx`) de `docs/01-requisitos.md` y `docs/03-reglas-de-negocio.md`.
- Cambios pequeños: máximo 3-5 archivos por tarea.
- No introducir secretos en el código; usar variables de entorno (ver `docs/02-arquitectura.md`, sección 11).

## Comandos

**Backend**
- `uv sync` — instalar dependencias
- `uv run uvicorn app.main:app --reload` — servidor de desarrollo
- `uv run pytest` — pruebas
- `uv run ruff check .` y `uv run mypy app` — lint y tipos
- `uv run alembic upgrade head` — aplicar migraciones

**Frontend** (en `frontend/`)
- `npm run dev` — servidor de desarrollo
- `npm test` — pruebas con Vitest
- `npm run lint`

## Fuera de alcance por ahora

Cobro de suscripciones, app móvil nativa, integración real con SPEI/WhatsApp, firma electrónica y scoring con buró de crédito.
