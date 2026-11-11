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
- Librerías del sistema para generar PDF (ver abajo)

### Librerías del sistema para PDF

La generación del pagaré usa **WeasyPrint**, que necesita librerías nativas que no
vienen con Python. Sin ellas, el endpoint del pagaré responde `503`.

**Ubuntu / Debian / WSL2:**

```bash
sudo apt update
sudo apt install -y \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libcairo2 \
  libgdk-pixbuf-2.0-0 \
  fonts-dejavu-core \
  shared-mime-info
```

**Fedora:**

```bash
sudo dnf install -y pango cairo gdk-pixbuf2 dejavu-sans-fonts shared-mime-info
```

**macOS (Homebrew):**

```bash
brew install pango cairo gdk-pixbuf libffi
```

**Arch:**

```bash
sudo pacman -S pango cairo gdk-pixbuf2 ttf-dejavu shared-mime-info
```

Verificar que quedaron instaladas:

```bash
uv run python -c "import weasyprint; print(weasyprint.__version__)"
```

Si imprime un número de versión, todo está listo. Si muestra un error sobre
`libgobject`, falta alguna de las librerías de arriba.

> El endpoint del pagaré no se cae si faltan: responde `503` con el comando exacto
> que hay que ejecutar. El resto de la API funciona con normalidad.

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

## Autenticación

Todas las rutas salvo `/health`, `/docs` y `POST /api/v1/loans/simulate`
requieren la cabecera `Authorization: Bearer <access_token>`.

| Método | Ruta | Para qué |
| :--- | :--- | :--- |
| POST | `/api/v1/auth/login` | Correo y contraseña → par de tokens |
| POST | `/api/v1/auth/refresh` | Canjea el refresh por un par nuevo (rota el anterior) |
| POST | `/api/v1/auth/logout` | Revoca el refresh indicado |
| GET | `/api/v1/auth/me` | Perfil, rol, permisos y datos de la financiera |

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.mx","password":"clave-segura-123"}'
```

- **Access token:** 15 minutos. Viaja en cada petición.
- **Refresh token:** 7 días. Se guarda hasheado en la base y se rota en cada uso.
  Reutilizar uno revocado cierra todas las sesiones del usuario.
- El token solo contiene identificadores: nunca nombre, correo ni CURP.

### Límite de intentos de inicio de sesión

El login acepta **5 intentos por minuto por IP**. Al superarlos responde `429` con
la cabecera `Retry-After`. El contador vive en memoria del proceso; si más adelante
se corre con varios workers, conviene moverlo a Redis.

## Frontend

La interfaz está en `frontend/` con React, TypeScript, Vite y Tailwind CSS.

```bash
cd frontend
npm install
npm run dev
```

Abre `http://localhost:5173`. Vite reenvía las llamadas a `/api` hacia
`http://127.0.0.1:8000`, así que **el backend debe estar corriendo**.

| Comando | Para qué |
| :--- | :--- |
| `npm run dev` | Servidor de desarrollo con recarga |
| `npm run build` | Compila para producción en `dist/` |
| `npm test` | Pruebas con Vitest |
| `npm run lint` | Revisión de estilo con oxlint |
| `npm run typecheck` | Verificación de tipos |

### Pantallas por rol

| Rol | Pantallas |
| :--- | :--- |
| Administrador | Dashboard, clientes, préstamos, pagos, rutas y auditoría |
| Prestamista | Clientes, préstamos con cotizador y pagos |
| Cobrador | Ruta del día y registro de pagos desde el celular |

### Instalar como aplicación en el celular (PWA)

La interfaz es una PWA: se puede instalar en el teléfono y abrir como una app.

1. Compila para producción: `npm run build`
2. Sirve la carpeta `dist/` por HTTPS (o con `npm run preview` para probar).
3. Abre la URL en el celular y elige **"Agregar a la pantalla de inicio"**.

> El service worker solo se registra en producción. Sirve caché **de solo
> lectura**: los datos se consultan sin señal, pero registrar un pago exige
> conexión, para evitar duplicados.

> Si abres el frontend desde Windows y el proxy no alcanza el backend en WSL2,
> arranca uvicorn con `--host 0.0.0.0` y usa la IP de WSL (ver más abajo).

## Módulos de la API

| Módulo | Rutas base | Para qué |
| :--- | :--- | :--- |
| Autenticación | `/api/v1/auth` | Login, refresh, logout y perfil |
| Clientes | `/api/v1/clients` | Alta, edición, referencias y documentos |
| Préstamos | `/api/v1/loans` | Simulación, aprobación, calendario y pagaré |
| Pagos | `/api/v1/payments` | Registro, consulta y anulación |
| Rutas de cobro | `/api/v1/routes` | Armado diario por zona y fecha |
| Dashboard | `/api/v1/dashboard` | Indicadores, aging y cobranza diaria |
| Auditoría | `/api/v1/audit` | Consulta y exportación de la bitácora |

La documentación interactiva con todos los esquemas está en `/docs`.

## Generar el pagaré

```bash
curl -X GET http://localhost:8000/api/v1/loans/<id>/pagare.pdf \
  -H "Authorization: Bearer <access_token>" \
  --output pagare.pdf
```

El documento incluye los datos del deudor, las condiciones del crédito, la tabla de
amortización completa, las cláusulas de mora y el espacio para firmas. Con 60 cuotas
ocupa aproximadamente 3 páginas.

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

## Comprobante de pago

Después de registrar un pago se puede descargar su comprobante:

```bash
curl -X GET http://localhost:8000/api/v1/payments/<id>/receipt.pdf \
  -H "Authorization: Bearer <access_token>" \
  --output comprobante.pdf
```

Formato angosto (80 mm), listo para impresora de tickets o para enviar como imagen.

También hay un enlace de WhatsApp con el resumen en texto:

```bash
curl -X GET http://localhost:8000/api/v1/payments/<id>/whatsapp \
  -H "Authorization: Bearer <access_token>"
```

Devuelve una URL `wa.me` que abre la aplicación sin necesitar la API de WhatsApp.

## Documentos de clientes

Se guardan en disco, bajo `STORAGE_DIR` (por defecto `storage/`). La ruta se
organiza como `<tenant>/<cliente>/<tipo>-<aleatorio>.<ext>`.

| Método | Ruta | Para qué |
| :--- | :--- | :--- |
| POST | `/api/v1/clients/{id}/documents` | Subir (multipart: `file` y `doc_type`) |
| GET | `/api/v1/clients/{id}/documents/{doc}` | Descargar |
| DELETE | `/api/v1/clients/{id}/documents/{doc}` | Eliminar |

Se aceptan PDF, JPG, PNG y WEBP de hasta 10 MB. El nombre original se descarta y
la ruta interna nunca se expone.

> Para producción en varios servidores conviene cambiar `LocalStorage` por una
> implementación de S3. La interfaz `Storage` está pensada para eso.
