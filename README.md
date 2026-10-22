# Credigest

SaaS de gestión de préstamos para prestamistas independientes y pequeñas financieras en México.

## Documentación

- `docs/00-vision.md` — visión, alcance y métricas
- `docs/01-requisitos.md` — requisitos funcionales y no funcionales
- `docs/02-arquitectura.md` — stack, modelo de datos y API
- `docs/03-reglas-de-negocio.md` — reglas financieras y de permisos
- `docs/04-roadmap.md` — fases y entregables

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 16 (para desarrollo local, vía Docker)

## Puesta en marcha

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload
```

La API queda en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.

Verificar que está en línea:

```bash
curl http://localhost:8000/health
```

## Pruebas y calidad

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```
