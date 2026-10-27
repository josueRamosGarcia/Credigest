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
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

La API queda en `http://localhost:8000` y la documentación interactiva en `http://localhost:8000/docs`.

> La base de datos de desarrollo usa el puerto **5433** para no chocar con otros
> PostgreSQL que ya escuchen en 5432.

Verificar que está en línea:

```bash
curl http://localhost:8000/health
```

> Si usas WSL2 y el navegador de Windows no abre esa dirección, revisa la sección
> [Solución de problemas](#el-navegador-no-abre-httplocalhost8000-wsl2).

## Pruebas y calidad

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```

## Migraciones

```bash
uv run alembic upgrade head                                  # aplicar
uv run alembic revision --autogenerate -m "descripcion"      # crear
uv run alembic downgrade -1                                  # revertir una
```

## Crear una financiera y su administrador

No hay autorregistro: cada financiera se crea con un script idempotente.

```bash
uv run python -m app.scripts.seed_tenant \
  --name "Mi Financiera" \
  --slug mi-financiera \
  --admin-name "Nombre Completo" \
  --admin-email admin@mifinanciera.mx \
  --admin-password "una-clave-de-al-menos-10"
```

La contraseña también se puede pasar por la variable `SEED_ADMIN_PASSWORD`
para no dejarla en el historial del shell.

> Crea el tenant, su configuración global (10 % de mora, 5 días de gracia) y un
> usuario `admin`. Falla de forma limpia si el slug o el correo ya existen.

## Solución de problemas

### El navegador no abre `http://localhost:8000` (WSL2)

Si trabajas en Windows con WSL2, el servidor corre dentro de Linux y el navegador de
Windows debe alcanzarlo por red. Cuando el reenvío de `localhost` falla, aparece
"no se puede acceder a este sitio" aunque dentro de Linux todo funcione.

**Solución recomendada:** arranca uvicorn escuchando en todas las interfaces y entra
por la IP interna de WSL.

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Consulta la IP de WSL (cambia al reiniciar WSL):

```bash
hostname -I | awk '{print $1}'
```

Abre en el navegador de Windows:

```
http://<IP-de-WSL>:8000/docs
```

**Alternativa:** desde PowerShell de Windows ejecuta `wsl --shutdown`, vuelve a abrir
la terminal y prueba de nuevo `http://localhost:8000`.

> `--host 0.0.0.0` expone la API a tu red local. Úsalo solo en desarrollo y en redes
> de confianza.
