# Credigest — Arquitectura

> Documento técnico derivado de `proyecto.md`. Define el stack, la estructura del sistema, el modelo de datos, la API, la seguridad y el despliegue. El backend está desarrollado en **Python**.

---

## 1. Principios de diseño

1. **Backend en Python, único cerebro del negocio.** Todos los cálculos financieros viven en el servidor; el frontend solo presenta resultados.
2. **API primero.** El backend expone una API REST documentada con OpenAPI; la web y la PWA consumen la misma API.
3. **Monolito modular.** Un solo despliegue de backend organizado por módulos de dominio, no microservicios. Menos complejidad operativa para un equipo de 3 personas.
4. **Aislamiento por tenant.** Cada financiera cliente es un tenant lógico; ninguna consulta cruza datos entre tenants.
5. **Servicios puros para el dinero.** Las fórmulas financieras se implementan en funciones puras, testeables y sin dependencia de la base de datos.
6. **Auditoría inmutable.** La bitácora se escribe como append-only y nunca se actualiza ni se borra desde la aplicación.

---

## 2. Stack tecnológico

| Capa | Tecnología | Justificación |
| :--- | :--- | :--- |
| Lenguaje backend | Python 3.12+ | Requisito del proyecto; ecosistema maduro para PDF, fechas y datos |
| Framework API | FastAPI | Alto rendimiento, tipado, validación con Pydantic y OpenAPI automático |
| Servidor ASGI | Uvicorn (+ Gunicorn en producción) | Estándar para FastAPI |
| ORM | SQLAlchemy 2.x | Modelado claro y consultas tipadas |
| Migraciones | Alembic | Versionado del esquema de base de datos |
| Base de datos | PostgreSQL 16 | Transacciones, integridad, índices y soporte de `JSONB` para auditoría |
| Validación | Pydantic v2 | Esquemas de entrada/salida y validación de CURP, montos y fechas |
| Autenticación | JWT (access + refresh) con `python-jose` o `pyjwt`; hash con `passlib[bcrypt]`; refresh tokens persistidos y revocables | Sesiones sin estado con revocación |
| UI | Tailwind CSS + shadcn/ui | Componentes accesibles y consistentes; interfaz en español |
| Cierre diario | Job programado (APScheduler o cron + script) | Calcula y persiste mora al cierre del día |
| PDF | WeasyPrint (HTML→PDF) o ReportLab | Pagarés y comprobantes con plantillas |
| Archivos | Almacenamiento de objetos compatible con S3 (MinIO en local) | Documentos fuera del servidor web, URLs firmadas |
| Tareas asíncronas | Celery + Redis, o FastAPI BackgroundTasks en el MVP | Envío de correos y generación de PDFs pesados |
| Frontend | React + TypeScript + Vite | Interfaz del administrador y prestamista |
| PWA cobrador | Misma base React con manifest y service worker | Un solo código para web y móvil |
| Gráficas | Recharts | Dashboard financiero |
| Pruebas backend | pytest + pytest-cov + httpx | Cobertura de reglas y endpoints |
| Calidad | Ruff, mypy, pre-commit | Consistencia y errores tempranos |
| CI/CD | GitHub Actions | Pruebas, lint y despliegue |
| Despliegue | Render/Railway/Fly.io + PostgreSQL gestionado + S3 | Bajo costo y operación simple |

> **Decisión:** no se desarrolla una app móvil nativa en el MVP. El cobrador usa la misma aplicación React como PWA responsive (ver `00-vision.md`, sección 8.2).

---

## 3. Vista general del sistema

```
┌──────────────────────────┐        ┌──────────────────────────┐
│  Navegador Admin/        │        │  Celular del Cobrador    │
│  Prestamista (React SPA) │        │  (PWA React responsive)  │
└────────────┬─────────────┘        └────────────┬─────────────┘
             │  HTTPS / JSON                     │
             └───────────────┬───────────────────┘
                             ▼
                  ┌──────────────────────┐
                  │  API FastAPI (Python)│
                  │  Auth · Servicios    │
                  │  Reglas de negocio   │
                  └──────┬───────┬───────┘
                         │       │
             ┌───────────▼──┐  ┌─▼────────────────┐
             │ PostgreSQL   │  │ Almacenamiento S3│
             │ datos + logs │  │ INE, comprobantes│
             └──────────────┘  │ pagarés PDF      │
                               └──────────────────┘
                         │
             ┌───────────▼───────────┐
             │ Redis + Worker        │
             │ correos, PDFs, reportes│
             └───────────────────────┘
```

### Componentes

| Componente | Responsabilidad |
| :--- | :--- |
| SPA React | Interfaz de administrador y prestamista; consume la API con JWT |
| PWA React | Misma SPA con instalación y caché de lectura para cobradores |
| API FastAPI | Autenticación, autorización, validaciones, cálculos y orquestación |
| PostgreSQL | Persistencia transaccional y bitácora de auditoría |
| Almacenamiento S3 | Documentos subidos y PDFs generados, accesibles por URL firmada |
| Redis + Worker | Envío de correos, generación diferida de PDFs y exportaciones |

---

## 4. Arquitectura del backend (capas)

```
app/
├── main.py                  # creación de la app, routers, middleware
├── core/
│   ├── config.py            # settings por variables de entorno (Pydantic Settings)
│   ├── security.py          # JWT, hash de contraseñas
│   └── deps.py              # dependencias: sesión DB, usuario actual, tenant, permisos
├── db/
│   ├── base.py              # Base declarativa de SQLAlchemy
│   ├── session.py           # engine y SessionLocal
│   └── migrations/          # Alembic
├── models/                  # tablas SQLAlchemy (una por entidad)
├── schemas/                 # Pydantic: Create/Update/Read por entidad
├── api/
│   └── v1/
│       ├── router.py        # agrupa routers por módulo
│       ├── auth.py
│       ├── users.py
│       ├── clients.py
│       ├── loans.py
│       ├── payments.py
│       ├── routes.py
│       ├── dashboard.py
│       ├── audit.py
│       └── settings.py
├── services/                # lógica de negocio y transacciones
│   ├── auth_service.py
│   ├── client_service.py
│   ├── loan_service.py
│   ├── payment_service.py
│   ├── collection_service.py
│   ├── dashboard_service.py
│   └── audit_service.py
├── domain/                  # reglas puras, sin DB
│   ├── interest.py          # esquemas de interés
│   ├── amortization.py      # tablas de amortización
│   ├── money.py             # redondeo y Decimal
│   └── validation.py        # CURP, fechas, montos
├── pdf/
│   ├── templates/           # plantillas HTML (Jinja2)
│   └── generator.py         # pagaré y comprobante
├── workers/
│   └── tasks.py             # Celery: correos, PDFs, exportaciones
└── tests/
    ├── unit/
    ├── integration/
    └── conftest.py
```

### Regla de dependencias

```
api  →  services  →  domain
                 →  models / db
```

- `domain` no importa nada de `db`, `api` ni `models`. Es Python puro y 100 % testeable.
- `api` no contiene cálculos; solo valida entrada, llama al servicio y formatea salida.
- `services` controla transacciones y auditoría.

---

## 5. Modelo de datos

### 5.1 Diagrama entidad-relación (texto)

```
tenant 1──N user
tenant 1──N client
tenant 1──N loan
tenant 1──N system_setting

client 1──N client_document
client 1──N client_reference
client 1──N loan

loan 1──N installment
loan 1──N payment

installment 1──N payment_application (N:M resuelto con tabla)
payment 1──N payment_application

user 1──N refresh_token
user 1──N password_reset_token
user 1──N quote
user 1──N collection_route
collection_route 1──N collection_route_item
collection_route_item N──1 client

tenant 1──N bank
tenant 1──N audit_log
user 1──N audit_log
```

### 5.2 Entidades

#### `tenant`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| name | varchar(150) | Nombre de la financiera |
| slug | varchar(50) | único global; usado para desambiguar el login |
| plan | enum(`basico`,`profesional`,`empresarial`) | Límites por plan (ver `RN-68`) |
| is_active | boolean | |
| created_at / updated_at | timestamptz | |

#### `user`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK, obligatorio |
| full_name | varchar(150) | |
| email | varchar(255) | único global (no solo por tenant) |
| phone | varchar(20) | |
| password_hash | varchar(255) | bcrypt |
| role | enum(`admin`,`prestamista`,`cobrador`) | |
| permissions | JSONB | ej. `{"edit_rate": false, "cancel_payment": true}` |
| is_active | boolean | |
| last_login_at | timestamptz | |
| created_at / updated_at | timestamptz | |

#### `refresh_token`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| user_id | UUID | FK |
| token_hash | varchar(255) | hash del token; nunca el token en claro |
| expires_at | timestamptz | |
| revoked_at | timestamptz | nullable |
| replaced_by | UUID | nullable; rotación de tokens |
| created_at | timestamptz | |

#### `password_reset_token`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| user_id | UUID | FK |
| token_hash | varchar(255) | |
| expires_at | timestamptz | |
| used_at | timestamptz | nullable |
| created_at | timestamptz | |

#### `client`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| full_name | varchar(200) | |
| curp | varchar(18) | validada, único por tenant |
| phone | varchar(20) | |
| address | text | |
| zone | varchar(80) | usada por rutas |
| status | enum(`activo`,`inactivo`) | |
| notes | text | |
| created_by | UUID | FK user |
| created_at / updated_at | timestamptz | |

Índices: `(tenant_id, curp)` único, `(tenant_id, full_name)`, `(tenant_id, zone)`.

#### `client_document`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| client_id | UUID | FK |
| doc_type | enum(`ine`,`comprobante_domicilio`,`otro`) | |
| file_key | varchar(500) | ruta en S3 |
| mime_type | varchar(100) | |
| size_bytes | integer | ≤ 10 MB |
| uploaded_by | UUID | FK user |
| created_at | timestamptz | |

#### `client_reference`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| client_id | UUID | FK |
| name | varchar(150) | |
| relationship | varchar(80) | parentesco |
| phone | varchar(20) | |
| address | text | |

#### `loan`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| client_id | UUID | FK |
| prestamista_id | UUID | FK user |
| principal | numeric(14,2) | monto prestado |
| interest_rate | numeric(8,4) | tasa por periodo (ej. 0.05 = 5 %) |
| rate_period | enum(`semanal`,`quincenal`,`mensual`) | |
| scheme | enum(`simple`,`saldo_insoluto`,`cuota_fija`) | |
| term_periods | integer | número de cuotas |
| start_date | date | |
| first_due_date | date | |
| total_interest | numeric(14,2) | calculado y congelado |
| total_amount | numeric(14,2) | principal + interés |
| late_fee_rate | numeric(8,4) | tasa moratoria del préstamo |
| grace_days | integer | días de gracia |
| status | enum(`activo`,`pagado`,`vencido`,`cancelado`) | |
| created_at / updated_at | timestamptz | |

> Los valores financieros del préstamo se **congelan** al aprobar; cambios posteriores de parámetros globales no lo afectan.

#### `installment`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| loan_id | UUID | FK |
| number | integer | 1..N |
| due_date | date | |
| amount | numeric(14,2) | cuota esperada |
| principal_part | numeric(14,2) | porción de capital |
| interest_part | numeric(14,2) | porción de interés |
| late_fee | numeric(14,2) | mora acumulada |
| paid_amount | numeric(14,2) | acumulado aplicado |
| status | enum(`pendiente`,`parcial`,`pagada`,`vencida`) | |
| paid_at | timestamptz | nullable |

Índice: `(loan_id, number)` único, `(due_date, status)`.

#### `payment`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| loan_id | UUID | FK |
| installment_id | UUID | FK nullable (pago adelantado) |
| folio | varchar(40) | único por tenant; formato `PAGO-{tenant}-{año}-{consecutivo}` |
| amount | numeric(14,2) | monto recibido |
| method | enum(`efectivo`,`spei`) | |
| spei_reference | varchar(100) | obligatorio si `spei` |
| payment_type | enum(`parcial`,`completo`,`adelantado`,`moratorio`) | etiqueta descriptiva; la aplicación siempre sigue `RN-29` |
| status | enum(`aplicado`,`anulado`) | |
| registered_by | UUID | FK user |
| cancelled_by | UUID | FK user nullable |
| cancel_reason | text | |
| created_at | timestamptz | |

#### `payment_application`
Distribución de un pago entre cuotas y conceptos (mora, interés, capital).

| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| payment_id | UUID | FK |
| installment_id | UUID | FK |
| concept | enum(`mora`,`interes`,`capital`) | |
| amount | numeric(14,2) | |

#### `quote` (cotización en borrador)
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| client_id | UUID | FK nullable |
| created_by | UUID | FK user |
| principal | numeric(14,2) | |
| interest_rate | numeric(8,4) | tasa por periodo |
| rate_period | enum(`semanal`,`quincenal`,`mensual`) | |
| scheme | enum(`simple`,`saldo_insoluto`,`cuota_fija`) | |
| term_periods | integer | |
| snapshot | JSONB | resultado de la simulación (cuotas y totales) |
| created_at / updated_at | timestamptz | |

> Post-MVP (RF-25). La tabla se define desde el MVP para no migrar después, pero la UI puede omitirla.

#### `bank` (catálogo del comparador)
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| name | varchar(150) | |
| annual_rate | numeric(8,4) | tasa anual de referencia |
| cat | numeric(8,4) | CAT estimado de referencia |
| opening_fee | numeric(14,2) | comisión de apertura |
| is_active | boolean | |
| updated_at | timestamptz | |

#### `notification` (correos y avisos)
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| user_id | UUID | FK nullable |
| channel | enum(`email`,`whatsapp`) | |
| template | varchar(80) | |
| payload | JSONB | sin datos sensibles en claro |
| status | enum(`pendiente`,`enviado`,`fallido`) | |
| error | text | nullable |
| sent_at | timestamptz | nullable |
| created_at | timestamptz | |

#### `collection_route`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| cobrador_id | UUID | FK user |
| zone | varchar(80) | |
| route_date | date | |
| status | enum(`borrador`,`activa`,`cerrada`) | |
| created_at | timestamptz | |

#### `collection_route_item`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| route_id | UUID | FK |
| client_id | UUID | FK |
| loan_id | UUID | FK |
| installment_id | UUID | FK |
| payment_id | UUID | FK nullable; pago registrado desde esta visita |
| order_index | integer | orden de visita |
| visit_status | enum(`pendiente`,`pagado`,`no_pagado`) | |
| notes | text | |

#### `system_setting`
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | UUID | PK |
| tenant_id | UUID | FK |
| default_late_fee_rate | numeric(8,4) | mora por defecto |
| default_scheme | enum | |
| grace_days | integer | |
| timezone | varchar(50) | `America/Mexico_City` |
| updated_by | UUID | FK user |
| updated_at | timestamptz | |

#### `audit_log` (append-only)
| Campo | Tipo | Notas |
| :--- | :--- | :--- |
| id | bigserial | PK |
| tenant_id | UUID | FK |
| user_id | UUID | FK nullable (acciones del sistema) |
| action | varchar(80) | `loan.create`, `payment.cancel`, etc. |
| entity | varchar(80) | |
| entity_id | UUID | |
| before | JSONB | estado previo |
| after | JSONB | estado nuevo |
| ip_address | inet | |
| user_agent | text | |
| created_at | timestamptz | default now() |

Regla a nivel de base de datos: `REVOKE UPDATE, DELETE` sobre `audit_log` para el rol de aplicación; solo `INSERT` y `SELECT`.

### 5.3 Reglas de integridad

- Todo registro de negocio lleva `tenant_id`; la sesión de base de datos aplica un filtro por tenant a nivel de repositorio.
- `numeric` para dinero, nunca `float`. El redondeo se hace a 2 decimales con `ROUND_HALF_UP`.
- Borrado lógico (`status = inactivo`) para clientes y usuarios; borrado físico solo por proceso administrativo.
- Un préstamo no puede tener dos calendarios activos: al cancelar se marca `cancelado` y se conserva el histórico.

---

## 6. API REST

Base: `/api/v1`. Autenticación: `Authorization: Bearer <access_token>`.

### 6.1 Autenticación

| Método | Ruta | Descripción |
| :--- | :--- | :--- |
| POST | `/auth/login` | Recibe correo, contraseña y `tenant_slug` opcional; devuelve access y refresh token |
| POST | `/auth/refresh` | Renueva el access token y rota el refresh |
| POST | `/auth/logout` | Revoca el refresh token |
| POST | `/auth/forgot-password` | Envía enlace de recuperación |
| POST | `/auth/reset-password` | Cambia contraseña con token |
| GET | `/auth/me` | Datos del usuario autenticado y permisos |

> El correo es único global. `tenant_slug` solo es necesario si el sistema opera con correos repetidos entre tenants; con la regla de unicidad global queda como dato opcional de diagnóstico.

### 6.2 Usuarios y configuración

| Método | Ruta | Rol |
| :--- | :--- | :--- |
| GET | `/users` | admin |
| POST | `/users` | admin |
| PATCH | `/users/{id}` | admin |
| PATCH | `/users/{id}/status` | admin |
| POST | `/users/{id}/reset-password` | admin (genera contraseña temporal si falla el correo) |
| GET | `/settings` | admin |
| PUT | `/settings` | admin |

### 6.3 Clientes

| Método | Ruta | Rol |
| :--- | :--- | :--- |
| GET | `/clients?search=&zone=&status=&page=` | admin, prestamista |
| POST | `/clients` | admin, prestamista |
| GET | `/clients/{id}` | admin, prestamista |
| PATCH | `/clients/{id}` | admin, prestamista |
| PATCH | `/clients/{id}/status` | admin, prestamista |
| POST | `/clients/{id}/documents` | admin, prestamista (multipart) |
| GET | `/clients/{id}/documents/{doc_id}/url` | admin, prestamista (URL firmada) |
| POST | `/clients/{id}/references` | admin, prestamista |
| GET | `/clients/{id}/loans` | admin, prestamista |

### 6.4 Préstamos y simulación

| Método | Ruta | Rol |
| :--- | :--- | :--- |
| POST | `/loans/simulate` | admin, prestamista |
| POST | `/loans` | admin, prestamista |
| GET | `/loans?status=&client_id=&page=` | admin, prestamista |
| GET | `/loans/{id}` | admin, prestamista |
| GET | `/loans/{id}/schedule` | admin, prestamista |
| GET | `/loans/{id}/payments` | admin, prestamista |
| POST | `/loans/{id}/cancel` | admin |
| GET | `/loans/{id}/pagare.pdf` | admin, prestamista |

### 6.5 Cobranza y pagos

| Método | Ruta | Rol |
| :--- | :--- | :--- |
| GET | `/routes?date=&zone=` | cobrador, admin |
| POST | `/routes` | admin |
| GET | `/routes/{id}` | cobrador asignado, admin |
| PATCH | `/routes/{id}/items/{item_id}` | cobrador |
| POST | `/routes/{id}/close` | admin, cobrador asignado |
| POST | `/payments` | admin, cobrador |
| GET | `/payments?loan_id=&from=&to=` | admin, prestamista |
| POST | `/payments/{id}/cancel` | admin, prestamista con permiso |
| GET | `/payments/{id}/receipt.pdf` | cobrador, admin |

### 6.6 Dashboard y auditoría

| Método | Ruta | Rol |
| :--- | :--- | :--- |
| GET | `/dashboard/summary?from=&to=&prestamista_id=&route_id=` | admin |
| GET | `/dashboard/aging` | admin |
| GET | `/dashboard/export.csv` | admin |
| GET | `/audit?from=&to=&user_id=&action=&page=` | admin |
| GET | `/audit/export.csv` | admin |

### 6.7 Comparador bancario

| Método | Ruta | Rol |
| :--- | :--- | :--- |
| GET | `/banks` | prestamista |
| POST | `/compare` | prestamista |

### 6.8 Ejemplos

**POST `/loans/simulate`**
```json
{
  "principal": 10000,
  "interest_rate": 0.05,
  "rate_period": "semanal",
  "scheme": "simple",
  "term_periods": 12,
  "start_date": "2026-11-02"
}
```
```json
{
  "installment_amount": 1333.33,
  "total_interest": 6000.00,
  "total_amount": 16000.00,
  "estimated_profit": 6000.00,
  "end_date": "2027-01-18",
  "schedule": [
    {"number": 1, "due_date": "2026-11-09", "amount": 1333.33, "interest_part": 500.00, "principal_part": 833.33, "balance": 9166.67}
  ]
}
```

**POST `/payments`**
```json
{
  "loan_id": "uuid",
  "installment_id": "uuid",
  "amount": 400.00,
  "method": "efectivo",
  "payment_type": "parcial"
}
```
```json
{
  "id": "uuid",
  "status": "aplicado",
  "applied": [
    {"concept": "mora", "amount": 0},
    {"concept": "interes", "amount": 250.00},
    {"concept": "capital", "amount": 150.00}
  ],
  "new_balance": 7850.00
}
```

### 6.9 Errores

Formato uniforme:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "La CURP no tiene un formato válido",
    "details": [{"field": "curp", "issue": "length"}]
  }
}
```

| HTTP | Uso |
| :--- | :--- |
| 400 | Regla de negocio violada (pago mayor al saldo) |
| 401 | Token ausente o inválido |
| 403 | Rol o permiso insuficiente |
| 404 | Recurso inexistente o de otro tenant |
| 409 | Conflicto (CURP duplicada) |
| 422 | Error de validación de esquema |
| 429 | Rate limit excedido |

---

## 7. Seguridad

| Tema | Implementación |
| :--- | :--- |
| Contraseñas | `bcrypt` con coste ≥ 12; política mínima de 10 caracteres |
| Tokens | Access 15 min, refresh 7 días, rotación y revocación en base (`refresh_token`) |
| Autorización | RBAC por rol + permisos granulares en `users.permissions` |
| Aislamiento | Middleware/dependencia inyecta `tenant_id`; repositorios lo aplican siempre |
| Archivos | Validación MIME y tamaño; nombres aleatorios; URLs firmadas con expiración de 5 min |
| Transporte | HTTPS obligatorio, HSTS en producción |
| CORS | Solo el dominio del frontend |
| Rate limiting | `slowapi` o límite en el proxy: 5 intentos de login por minuto por IP |
| Secretos | Variables de entorno; nunca en el repositorio |
| Logs | Sin datos sensibles (CURP, contraseñas, tokens) en logs de aplicación |
| Auditoría | Append-only a nivel de permisos de base de datos |

### Matriz de permisos (resumen)

| Acción | Admin | Prestamista | Cobrador |
| :--- | :---: | :---: | :---: |
| Gestionar usuarios y parámetros | ✅ | ❌ | ❌ |
| Ver dashboard global | ✅ | ❌ | ❌ |
| Ver auditoría | ✅ | ❌ | ❌ |
| Crear/editar clientes | ✅ | ✅ | ❌ |
| Simular y aprobar préstamos | ✅ | ✅ | ❌ |
| Generar pagaré | ✅ | ✅ | ❌ |
| Ver rutas asignadas | ✅ | ❌ | ✅ |
| Registrar pagos | ✅ | ❌ | ✅ |
| Anular pagos | ✅ | ⚠️ con permiso | ❌ |
| Comparador bancario | ✅ | ✅ | ❌ |

> El Administrador tiene acceso total por definición (`RN-61`); esta matriz describe al Prestamista y al Cobrador. No existen permisos de descuento ni condonación en el MVP.

Las reglas completas están en `03-reglas-de-negocio.md`.

---

## 8. Cálculos y precisión

- Todo importe se maneja con `Decimal` en Python y `numeric` en PostgreSQL.
- Funciones puras en `app/domain/`:
  - `calculate_simple_interest(principal, rate, periods)`
  - `build_amortization_declining(principal, rate, periods)`
  - `build_amortization_fixed_payment(principal, rate, periods)`
  - `apply_payment(loan, installment, amount)`
  - `calculate_late_fee(installment, today, rate, grace_days)`
- Las fechas se calculan con `dateutil.relativedelta` y zona horaria `America/Mexico_City`.
- La tasa se interpreta **por periodo** según `rate_period`; las equivalencias mensual/anual se calculan solo para mostrar.
- Redondeo: `ROUND_HALF_UP` a 2 decimales; el último periodo absorbe el ajuste de centavos para que la suma cuadre exactamente.

> Fórmulas completas en `03-reglas-de-negocio.md`.

### 8.1 Cierre diario de mora

Un job programado (cron a las 23:55 hora de México, o APScheduler dentro del worker) recorre las cuotas vencidas, calcula la mora devengada con `calculate_late_fee` y persiste el acumulado en `installment.late_fee`. Así se cumple `RN-20` sin recalcular todo el historial en cada consulta. El job es idempotente: puede ejecutarse dos veces el mismo día sin duplicar mora (guarda la última fecha de cálculo).

---

## 9. Generación de PDF

1. El servicio arma un contexto con cliente, préstamo, calendario y mora.
2. Renderiza una plantilla HTML con Jinja2 (`app/pdf/templates/pagare.html`).
3. WeasyPrint convierte el HTML a PDF.
4. El PDF se guarda en S3 y se devuelve por URL firmada.
5. Para préstamos con muchas cuotas, la generación se delega al worker y se notifica al usuario.

Ventaja de HTML→PDF: el diseño se ajusta con CSS y se reutiliza para el comprobante de pago.

---

## 10. Frontend

### Estructura sugerida

```
frontend/
├── src/
│   ├── api/            # cliente HTTP y tipos generados de OpenAPI
│   ├── auth/           # login, sesión, guardas de ruta
│   ├── components/     # UI reutilizable
│   ├── features/
│   │   ├── clients/
│   │   ├── loans/
│   │   ├── payments/
│   │   ├── routes/
│   │   ├── dashboard/
│   │   ├── audit/
│   │   └── settings/
│   ├── layouts/
│   └── pages/
├── public/manifest.webmanifest
└── vite.config.ts
```

- **Estado del servidor:** TanStack Query (caché, reintentos, invalidación).
- **Formularios:** React Hook Form + Zod.
- **Estilos:** Tailwind CSS + shadcn/ui, interfaz en español.
- **Rutas:** React Router con guardas por rol.
- **PWA:** service worker con Workbox y **caché de solo lectura** de la ruta del día. No hay cola de pagos offline en el MVP: registrar un pago exige conexión para evitar duplicados.

---

## 11. Entornos y despliegue

| Entorno | Uso | Infraestructura |
| :--- | :--- | :--- |
| Local | Desarrollo | Docker Compose: Postgres, Redis, MinIO, API, frontend |
| Staging | Pruebas y demo | Render/Railway con base gestionada y bucket separado |
| Producción | Clientes | Igual que staging con respaldos y monitoreo |

### Flujo CI/CD
1. Push a rama → GitHub Actions ejecuta Ruff, mypy y pytest.
2. Si pasa y la rama es `main` → build de imagen y despliegue a producción tras aprobación manual.
3. Migraciones Alembic se ejecutan como paso previo al despliegue.

### Variables de entorno (ejemplo, sin valores)
```
DATABASE_URL=
REDIS_URL=
JWT_SECRET=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=7
S3_ENDPOINT=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
SMTP_HOST=
SMTP_USER=
SMTP_PASSWORD=
FRONTEND_ORIGIN=
TZ=America/Mexico_City
```

### Monitoreo
- Logs estructurados en JSON con `request_id`.
- Health check `GET /health` y `GET /health/db`.
- Alertas por errores 5xx y latencia p95.
- Sentry (plan gratuito) para trazas de excepción.

---

## 12. Estrategia de pruebas

| Nivel | Herramienta | Qué cubre |
| :--- | :--- | :--- |
| Unitaria | pytest | Fórmulas de interés, amortización, mora, aplicación de pagos |
| Integración | pytest + httpx + Postgres de prueba | Endpoints, permisos, aislamiento por tenant |
| Contrato | OpenAPI schema | Compatibilidad entre frontend y backend |
| Frontend | Vitest + Testing Library | Formularios y componentes críticos |
| E2E | Playwright | Flujo cliente → préstamo → pagaré → pago |
| Manual | Checklist QA | Impresión de pagaré y uso en campo |

Casos mínimos obligatorios: los tres esquemas de interés, pago parcial, pago adelantado, pago con mora, anulación de pago, cobrador fuera de ruta, CURP duplicada.

---

## 13. Decisiones registradas (ADR resumidos)

| # | Decisión | Alternativas descartadas | Motivo |
| :--- | :--- | :--- | :--- |
| 1 | FastAPI en lugar de Django/Flask | Django, Flask | Tipado, OpenAPI automático y mejor encaje con servicios puros |
| 2 | Monolito modular | Microservicios | Equipo pequeño y plazo corto |
| 3 | PostgreSQL | MySQL, SQLite | Transacciones, `JSONB`, `numeric` robusto |
| 4 | PWA en lugar de app nativa | Flutter, React Native | Un solo código; el cobrador no requiere funciones nativas |
| 5 | WeasyPrint para PDF | ReportLab | Plantillas HTML/CSS más fáciles de mantener |
| 6 | `Decimal` para dinero | `float` | Evitar errores de redondeo |
| 7 | Auditoría append-only | Logs de aplicación | Requisito legal y de trazabilidad |
| 8 | Correo único global | Email único por tenant | El login no requiere conocer el tenant y evita ambigüedad |
| 9 | PWA solo con caché de lectura | Cola de pagos offline | Evita pagos duplicados sin clave de idempotencia |
| 10 | Límites de plan fijos, sin add-ons | Cobro por usuario extra | Menos complejidad en el MVP |
| 11 | Tailwind + shadcn/ui | MUI, Bootstrap | Componentes accesibles y control total del diseño |
