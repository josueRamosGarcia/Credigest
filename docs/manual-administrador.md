# Credigest — Manual del Administrador

> Guía de configuración, supervisión financiera, auditoría, cierre diario y respaldos para el rol **Administrador**.

---

## 1. Alta inicial de una financiera (`RF-52`)

Para inicializar una nueva financiera (tenant) y su primer Administrador desde el servidor:

```bash
uv run python -m app.scripts.seed_tenant \
  --name "Mi Financiera" \
  --slug mi-financiera \
  --admin-name "Administrador General" \
  --admin-email admin@mifinanciera.mx \
  --admin-password "una-clave-segura-de-10+"
```

---

## 2. Configuración global y gestión de usuarios (`CU-02`)

Desde el menú **Configuración** (`/configuracion`):

### 2.1 Parámetros globales (`RF-09` a `RF-12`)
- **Tasa moratoria mensual (%):** porcentaje que se prorratea entre 30 días sobre el saldo vencido de cada cuota (`RN-19`).
- **Esquema de cálculo predeterminado:** esquema sugerido al abrir el cotizador (`simple`, `saldo_insoluto` o `cuota_fija`).
- **Días de gracia:** días naturales de tolerancia después del vencimiento antes de devengar mora (`RN-18`).
- Modificar estos parámetros **solo aplica a préstamos nuevos**; los préstamos aprobados previamente conservan sus condiciones congeladas (`RN-06`).

### 2.2 Usuarios, roles y permisos granulares (`RF-03` a `RF-06`, `RN-61` a `RN-63`)
1. Presiona **Nuevo usuario** y asigna el rol:
   - `admin`: control total de la financiera.
   - `prestamista`: clientes, préstamos, pagarés y comparador.
   - `cobrador`: consulta de rutas asignadas y registro de abonos.
2. Si dejas en blanco el campo de contraseña inicial, Credigest genera una **contraseña temporal** aleatoria que se muestra en pantalla para que la entregues al integrante (`RF-06`).
3. Puedes habilitar o revocar permisos granulares (`edit_rate` para modificar tasas y `cancel_payment` para anular abonos) y restablecer la contraseña de cualquier usuario. Al hacerlo, todas sus sesiones activas se revocan de inmediato (`RN-63`).
4. Por protección operativa (`RN-62`), no es posible desactivar tu propia cuenta ni dejar a la financiera sin al menos un Administrador activo.

### 2.3 Límites por plan (`RN-68`)
| Plan | Usuarios activos | Clientes activos |
| :--- | ---: | ---: |
| `basico` | 5 | 50 |
| `profesional` | 12 | 200 |
| `empresarial` | 30 | Ilimitado |

---

## 3. Cierre diario de mora (`RN-20`)

El cálculo y consolidación de cargos moratorios es idempotente y debe programarse todos los días a las **23:55 (hora de la Ciudad de México)** mediante `cron`:

```cron
55 23 * * * cd /ruta/a/credigest && uv run python -m app.scripts.accrue_late_fees >> /var/log/credigest-mora.log 2>&1
```

También puede ejecutarse bajo demanda desde la API:
```bash
curl -X POST http://localhost:8000/api/v1/dashboard/accrue-late-fees \
  -H "Authorization: Bearer <access_token>"
```

---

## 4. Dashboard financiero, bitácora y privacidad (`CU-08`, `RN-64`, `RN-70`)

- **Dashboard (`/dashboard`):** muestra capital prestado, recuperado, por cobrar, utilidad generada, índice de morosidad y antigüedad de saldos (`aging`). Permite filtrar por fechas y descargar el reporte en **CSV** (`RF-44`).
- **Auditoría (`/auditoria`):** bitácora inmutable (`append-only`, `RF-50`) filtrable por fecha, usuario, entidad y acción, con exportación a **CSV** (`RF-51`). Nunca almacena contraseñas, tokens ni CURP en claro (`RN-65`).
- **Anonimización ARCO (`RNF-25`, `RN-70`):** cuando un titular solicita la cancelación de sus datos personales, ejecuta:
  ```bash
  curl -X POST http://localhost:8000/api/v1/clients/<client_id>/anonymize \
    -H "Authorization: Bearer <access_token>"
  ```
  Esto sustituye nombre, CURP, teléfono y dirección por seudónimos, borra documentos y referencias, desactiva el registro y conserva la trazabilidad contable con identificadores internos.

---

## 5. Respaldo, restauración y monitoreo (`RNF-18`, `RNF-19`)

### 5.1 Health checks
- `GET /health` — verifica que el proceso de la API responda.
- `GET /health/db` — verifica conectividad con PostgreSQL (`SELECT 1`).

### 5.2 Respaldo diario de PostgreSQL (`RNF-18`)
Programar en `cron` un volcado comprimido diario con retención de 30 días:

```bash
pg_dump -Fc -h localhost -p 5433 -U postgres credigest > "backup-credigest-$(date +%F).dump"
find /ruta/backups -name "backup-credigest-*.dump" -mtime +30 -delete
```

### 5.3 Procedimiento de restauración (`RNF-19`)
Para restaurar un respaldo en una base limpia o entorno de staging (probar trimestralmente):

```bash
createdb -h localhost -p 5433 -U postgres credigest_restore
pg_restore -h localhost -p 5433 -U postgres -d credigest_restore --no-owner "backup-credigest-YYYY-MM-DD.dump"
```

