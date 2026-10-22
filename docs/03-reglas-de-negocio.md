# Credigest — Reglas de negocio

> Reglas funcionales y financieras que el backend en Python debe implementar. Cada regla tiene un identificador `RN-xx` para referenciarla en código, pruebas y revisiones.

---

## 1. Convenciones de dinero y fechas

| Regla | Descripción |
| :--- | :--- |
| **RN-01** | Todo importe monetario se representa con `Decimal` en Python y `numeric(14,2)` en PostgreSQL. Nunca `float`. |
| **RN-02** | El redondeo es `ROUND_HALF_UP` a 2 decimales. |
| **RN-03** | En una tabla de amortización, el último periodo absorbe la diferencia de centavos para que la suma de capital sea exactamente igual al monto prestado y la suma de cuotas sea exactamente el total. |
| **RN-04** | Las tasas se guardan como fracción decimal **por periodo** (5 % → `0.05`) según la frecuencia del préstamo (`rate_period`). Las equivalencias mensual o anual son solo informativas y no se usan para el cálculo. |
| **RN-05** | Las fechas se manejan en zona `America/Mexico_City`. Las fechas de vencimiento son tipo `date`, sin hora. |
| **RN-06** | Los cálculos financieros del préstamo se congelan al aprobarlo. Cambiar parámetros globales después **no** modifica préstamos existentes. |

---

## 2. Frecuencias de pago

| Valor | Periodo | Avance entre cuotas |
| :--- | :--- | :--- |
| `semanal` | 7 días | `relativedelta(weeks=1)` |
| `quincenal` | 15 días | `relativedelta(days=15)` |
| `mensual` | 1 mes | `relativedelta(months=1)` |

**RN-07** — La primera fecha de vencimiento se calcula sumando un periodo a la fecha de inicio. Las siguientes se calculan desde la fecha de inicio (no desde la anterior) para evitar el arrastre en meses de distinta duración:

```python
from dateutil.relativedelta import relativedelta

def due_date(start: date, period: str, n: int) -> date:
    if period == "semanal":
        return start + relativedelta(weeks=n)
    if period == "quincenal":
        return start + relativedelta(days=15 * n)
    return start + relativedelta(months=n)
```

**RN-08** — Si una fecha cae en día no laborable, el vencimiento **no** se mueve automáticamente en el MVP; se muestra tal cual y el cobrador decide. (Post-MVP: parámetro de días inhábiles.)

---

## 3. Esquemas de interés

Notación:
- `P` = capital prestado (principal)
- `i` = tasa de interés por periodo
- `n` = número de periodos (plazo)
- `A` = cuota periódica
- `B_k` = saldo insoluto al final del periodo `k`

### 3.1 Interés simple sobre capital original (`simple`)

El interés se calcula siempre sobre el capital original, no sobre el saldo.

```
Interés total       = P × i × n
Importe total       = P + (P × i × n)
Cuota periódica     = Importe total / n
Interés por cuota   = P × i
Capital por cuota   = P / n
Saldo después de k  = P − (k × P / n)
```

**Ejemplo** — $10,000 a 12 semanas, 5 % semanal:

```
Interés total   = 10,000 × 0.05 × 12 = 6,000.00
Importe total   = 16,000.00
Cuota           = 16,000 / 12   = 1,333.33
Interés/cuota   = 500.00
Capital/cuota   = 833.33
```

Ventaja: el prestamista conoce desde el inicio su ganancia exacta. Desventaja: el cliente paga intereses sobre capital ya amortizado.

### 3.2 Interés sobre saldo insoluto (`saldo_insoluto`)

El interés se calcula sobre el saldo pendiente en cada periodo. Se amortiza capital en partes iguales.

```
Capital por cuota   = P / n
Interés del periodo = B_(k−1) × i
Cuota del periodo   = (P / n) + (B_(k−1) × i)
B_k                 = B_(k−1) − (P / n)
Interés total       = Σ interés de cada periodo
```

**Ejemplo** — $10,000 a 4 meses, 3 % mensual:

| # | Saldo inicial | Interés | Capital | Cuota | Saldo final |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 10,000.00 | 300.00 | 2,500.00 | 2,800.00 | 7,500.00 |
| 2 | 7,500.00 | 225.00 | 2,500.00 | 2,725.00 | 5,000.00 |
| 3 | 5,000.00 | 150.00 | 2,500.00 | 2,650.00 | 2,500.00 |
| 4 | 2,500.00 | 75.00 | 2,500.00 | 2,575.00 | 0.00 |
| **Total** | | **750.00** | **10,000.00** | **10,750.00** | |

Ventaja: más justo para el cliente. Desventaja: la cuota decrece y la ganancia no es fija.

### 3.3 Cuota fija precalculada (`cuota_fija`)

Cuota constante calculada con la fórmula de anualidad:

```
A = P × i / (1 − (1 + i)^(−n))       si i > 0
A = P / n                             si i = 0
```

Desglose por periodo:

```
Interés_k = B_(k−1) × i
Capital_k = A − Interés_k
B_k       = B_(k−1) − Capital_k
```

**Ejemplo** — $10,000 a 12 meses, 3 % mensual:

```
A = 10,000 × 0.03 / (1 − 1.03^(−12)) ≈ 1,004.62
```

| # | Saldo inicial | Interés | Capital | Cuota | Saldo final |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 10,000.00 | 300.00 | 704.62 | 1,004.62 | 9,295.38 |
| 2 | 9,295.38 | 278.86 | 725.76 | 1,004.62 | 8,569.62 |
| … | … | … | … | … | … |
| 12 | 975.35 | 29.27 | 975.35 | 1,004.62 | 0.00 |

Ventaja: cuota predecible para el cliente. Es el esquema típico de crédito al consumo.

**RN-09** — Si `i = 0`, la cuota fija equivale a `P / n` y no hay interés.
**RN-10** — Si `n = 0` o `P <= 0`, la simulación debe rechazarse con error de validación.
**RN-11** — La tasa debe ser `>= 0`. Tasas negativas se rechazan.

---

## 4. Cotizador rápido

**RN-12** — La simulación es efímera: no crea préstamo ni cuotas. Devuelve:

| Campo | Cálculo |
| :--- | :--- |
| `installment_amount` | Cuota del primer periodo |
| `total_interest` | Suma de intereses |
| `total_amount` | Principal + interés total |
| `estimated_profit` | Igual a `total_interest` (sin mora) |
| `end_date` | Fecha de vencimiento de la cuota `n` |
| `schedule` | Tabla completa (opcional según UI) |

**RN-13** — Si el esquema es `saldo_insoluto`, la cuota mostrada como "cuota periódica" es la **primera** (la más alta), y la respuesta incluye `installment_amount_last` para mostrar el rango.

---

## 5. Aprobación del préstamo

**RN-14** — Al aprobar una simulación:
1. Se crea el registro `loan` con valores congelados.
2. Se generan `n` registros `installment` con fechas y montos.
3. Se marca `installment 1` como la siguiente cuota a cobrar.
4. Se registra auditoría `loan.create`.
5. Se encola la generación del pagaré.

**RN-15** — No se puede aprobar un préstamo para un cliente `inactivo`.
**RN-16** — No se puede aprobar si el cliente ya tiene un préstamo `activo` con cuotas vencidas mayores a 90 días, salvo que el Administrador lo autorice explícitamente (registrando el motivo).

---

## 6. Mora

**RN-17** — Definición de vencida: una cuota con `due_date < hoy` y `status != pagada`.

**RN-18** — Días de atraso:
```
días_atraso = hoy − due_date
```
No se cuentan los `grace_days` configurados.

**RN-19** — La tasa moratoria es **mensual** y se prorratea por día sobre 30:

```
días_mora_efectivos = max(0, días_atraso − grace_days)
mora = saldo_vencido × late_fee_rate × (días_mora_efectivos / 30)
```

Donde `saldo_vencido` es el monto pendiente de la cuota (cuota − pagado), sin incluir mora ya generada.

**RN-20** — La mora se devenga por día, pero no se persiste como cargo diario independiente. Se calcula al consultar o al registrar un pago, y se consolida en `installment.late_fee` mediante el **cierre diario** programado (23:55, hora de México) definido en `02-arquitectura.md` §8.1. El job es idempotente y guarda la fecha del último cálculo para no duplicar mora.

**RN-21** — La mora no genera interés compuesto sobre sí misma en el MVP.

**RN-22** — La mora configurada en el préstamo prevalece sobre la global. Si el préstamo no tiene, se usa la global vigente al aprobarlo.

**Ejemplo** — Cuota de $1,000 con 10 días de atraso, 5 días de gracia, tasa moratoria 10 % mensual:

```
días_mora_efectivos = 10 − 5 = 5
mora = 1,000 × 0.10 × (5 / 30) = 16.67
```

---

## 7. Registro y aplicación de pagos

### 7.1 Validaciones previas

| Regla | Validación |
| :--- | :--- |
| **RN-23** | El monto debe ser `> 0`. |
| **RN-24** | El monto no puede exceder el saldo total pendiente (capital + interés + mora) del préstamo. Si excede, se rechaza con 400. |
| **RN-25** | Si el método es `spei`, la referencia es obligatoria (mínimo 6 caracteres). |
| **RN-26** | El cobrador solo puede registrar pagos de clientes incluidos en sus rutas asignadas. El Administrador puede registrar pagos de cualquier cliente del tenant. |
| **RN-27** | No se permite registrar pagos sobre un préstamo `cancelado` o `pagado`. |
| **RN-28** | Un pago idéntico (mismo préstamo, monto, fecha y usuario) dentro de 60 segundos se considera duplicado y se advierte. |

### 7.2 Orden de aplicación

**RN-29** — Todo pago se distribuye en este orden estricto, sin importar el `payment_type` (que es solo una etiqueta descriptiva):

```
1. Mora acumulada de cuotas vencidas (la más antigua primero)
2. Interés del periodo de la cuota más antigua pendiente
3. Capital de esa cuota
4. Si sobra, se repite con la siguiente cuota pendiente
5. Si aún sobra (pago adelantado), se aplica a cuotas futuras en el mismo orden
```

**RN-30** — Cada aplicación se guarda en `payment_application` con su `concept` (`mora`, `interes`, `capital`).

**RN-31** — El pago puede cubrir varias cuotas; no se obliga a que sea exacto.

**RN-32** — Los pagos no se aplican a "capital puro" sin cubrir interés y mora. Las condonaciones y descuentos quedan fuera del MVP; cuando se implementen, requerirán un registro contable separado.

### 7.3 Estados resultantes

**RN-33** — Después de aplicar un pago:

| Condición | Estado de la cuota | Estado del préstamo |
| :--- | :--- | :--- |
| `paid_amount == 0` | `pendiente` o `vencida` según fecha | `activo` o `vencido` |
| `0 < paid_amount < amount + late_fee` | `parcial` | `activo` o `vencido` |
| `paid_amount >= amount + late_fee` | `pagada` | `activo` |
| Todas las cuotas `pagada` | — | `pagado` |
| Existe cuota vencida | — | `vencido` |

**RN-34** — El saldo insoluto se recalcula como:
```
saldo_insoluto = Σ (amount + late_fee − paid_amount) de cuotas no pagadas
```

**RN-35** — Un pago adelantado aplicado a cuotas futuras no cambia la fecha de vencimiento; solo reduce su saldo pendiente. La cuota se marca `pagada` cuando su saldo llega a cero, aunque sea antes de su fecha.

### 7.4 Anulación de pago

**RN-36** — Anular un pago:
1. Valida que no existan pagos posteriores aplicados al mismo préstamo. Si existen, se rechaza con 409 indicando que deben anularse primero los más recientes.
2. Marca `payment.status = anulado`, guarda `cancelled_by`, `cancel_reason` y fecha.
3. Revierte cada `payment_application` restando el monto de la cuota correspondiente.
4. Recalcula estados de cuotas y del préstamo.
5. Registra auditoría `payment.cancel` con el estado antes y después.

**RN-37** — Solo el Administrador o un Prestamista con permiso `cancel_payment` pueden anular. El Cobrador nunca.
**RN-38** — No se puede anular un pago si el préstamo ya está `pagado` y el pago es el que lo cerró, salvo autorización del Administrador con motivo.

---

## 8. Comprobantes

**RN-39** — Cada pago aplicado genera un folio legible: `PAGO-{tenant_corto}-{año}-{consecutivo}`.
**RN-40** — El comprobante incluye: folio, fecha, cliente, préstamo, monto, método, referencia SPEI, desglose aplicado y saldo restante.
**RN-41** — Un pago anulado conserva su folio pero se marca como ANULADO y no se puede reemitir como vigente.

---

## 9. Rutas de cobro

**RN-42** — Una ruta agrupa cuotas pendientes o vencidas de una zona y fecha para un cobrador.
**RN-43** — Solo se incluyen clientes con al menos una cuota con `due_date <= fecha_ruta` y saldo pendiente > 0.
**RN-44** — El orden por defecto es por fecha de vencimiento y luego por nombre. Puede reordenarse manualmente por el cobrador (se guarda `order_index`).
**RN-45** — Un cobrador solo ve rutas con `cobrador_id = su id`. Un Administrador ve todas.
**RN-46** — Si un pago se registra desde la ruta, el ítem cambia a `pagado`; si el cliente no paga, se marca `no_pagado` con motivo.

---

## 10. Dashboard financiero

**RN-47** — Definiciones de indicadores (todas calculadas en el servidor):

| Indicador | Fórmula |
| :--- | :--- |
| Capital prestado | `Σ loan.principal` de préstamos no cancelados en el rango |
| Capital recuperado | `Σ payment_application.amount` con `concept = capital` de pagos aplicados |
| Capital proyectado | `Σ saldo de capital pendiente` de préstamos activos/vencidos |
| Intereses generados | `Σ payment_application.amount` con `concept = interes` |
| Mora cobrada | `Σ payment_application.amount` con `concept = mora` |
| Utilidad generada | Intereses generados + mora cobrada |
| Índice de morosidad | `cartera_vencida / cartera_total × 100` |
| Cartera vencida | `Σ saldo pendiente` de cuotas vencidas |

**RN-48** — Los filtros de fecha aplican sobre `payment.created_at` para cobros y sobre `loan.start_date` para colocación. La UI debe indicar qué fecha se está filtrando.
**RN-49** — Los pagos anulados se excluyen de todos los indicadores.
**RN-50** — El índice de morosidad se expresa con 2 decimales y porcentaje.

### Aging de cartera

| Rango | Días de atraso |
| :--- | :--- |
| Al día | 0 |
| 1–30 | 1 a 30 |
| 31–60 | 31 a 60 |
| 61–90 | 61 a 90 |
| +90 | más de 90 |

**RN-51** — El aging se calcula por cuota vencida, no por préstamo completo.

---

## 11. Comparador bancario

**RN-52** — El CAT mostrado es una **estimación** calculada con tasa, comisiones y plazo; no replica la metodología oficial del Banco de México al detalle.
**RN-53** — Toda pantalla y PDF comparativo debe incluir la leyenda: *"Resultados estimados con fines informativos; no constituyen una oferta de crédito."*
**RN-54** — El catálogo de bancos es configurable por el Administrador y no se actualiza automáticamente.

Fórmula base usada:
```
CAT_estimado = ((1 + tasa_mensual)^12 − 1) × 100 + comisiones_anualizadas
```

---

## 12. Clientes

**RN-55** — La CURP se valida con la estructura oficial: 4 letras, 6 dígitos de fecha, 1 letra de sexo, 2 letras de entidad, 3 consonantes, 1 homoclave/dígito. Se normaliza a mayúsculas y sin espacios.
**RN-56** — La CURP es única por tenant. Un mismo cliente puede existir en dos financieras distintas.
**RN-57** — No se elimina un cliente con préstamos activos, vencidos o pagados; solo se desactiva.
**RN-58** — Desactivar un cliente impide crear nuevos préstamos, pero conserva su historial y documentos.
**RN-59** — Un cliente desactivado no aparece en nuevas rutas de cobro, pero sus cuotas siguen siendo cobrables desde búsqueda directa (decisión del Prestamista).
**RN-60** — Los documentos se guardan con nombre aleatorio y solo se accede por URL firmada de corta duración.

---

## 13. Usuarios, roles y permisos

### 13.1 Roles base

| Rol | Descripción |
| :--- | :--- |
| `admin` | Control total del tenant: usuarios, parámetros, dashboard, auditoría |
| `prestamista` | Clientes, préstamos, pagarés, comparador; puede cobrar si se le asigna ruta |
| `cobrador` | Consulta rutas y registra pagos únicamente |

### 13.2 Permisos granulares

| Permiso | Default admin | Default prestamista | Default cobrador |
| :--- | :---: | :---: | :---: |
| `create_user` | ✅ | ❌ | ❌ |
| `edit_settings` | ✅ | ❌ | ❌ |
| `view_dashboard` | ✅ | ❌ | ❌ |
| `view_audit` | ✅ | ❌ | ❌ |
| `create_client` | ✅ | ✅ | ❌ |
| `edit_client` | ✅ | ✅ | ❌ |
| `create_loan` | ✅ | ✅ | ❌ |
| `edit_rate` | ✅ | ❌ | ❌ |
| `cancel_payment` | ✅ | ❌ | ❌ |
| `register_payment` | ✅ | ❌ | ✅ |
| `view_assigned_routes` | ✅ | ❌ | ✅ |

**RN-61** — El rol define el conjunto máximo de acciones; los permisos granulares solo pueden restringir, nunca ampliar más allá del rol. **El Administrador siempre tiene todas las acciones**, incluido registrar pagos y crear clientes, sin importar la matriz.
**RN-62** — Un usuario no puede desactivarse a sí mismo ni quitarse el rol `admin` si es el último administrador activo del tenant.
**RN-63** — Cambiar permisos aplica en el siguiente inicio de sesión o al refrescar el token.

---

## 14. Auditoría

**RN-64** — Se auditan como mínimo: login, logout, creación/edición/desactivación de usuario, cambio de permisos, cambio de parámetros, alta/edición/desactivación de cliente, carga de documentos, creación/aprobación/cancelación de préstamo, generación de pagaré, registro/anulación de pago, exportación de dashboard y auditoría.

**RN-65** — Cada registro incluye `before` y `after` en JSONB solo con los campos modificados. Los campos sensibles (contraseña, token) nunca se registran.

**RN-66** — La bitácora es append-only: la aplicación no expone endpoints de update ni delete, y el rol de base de datos no tiene privilegios de modificación.

**RN-67** — La retención mínima es de 5 años. La exportación está disponible para el Administrador.

---

## 15. Límites por plan

| Límite | Básico | Profesional | Empresarial |
| :--- | ---: | ---: | ---: |
| Usuarios | 5 | 12 | 30 |
| Clientes activos | 50 | 200 | Ilimitado |
| Dashboard | ❌ | ✅ | ✅ |
| Rutas de cobro | ❌ | ✅ | ✅ |
| Comparador bancario | ❌ | ❌ | ✅ |
| Almacenamiento de documentos | 2 GB | 15 GB | 60 GB |

**RN-68** — Al alcanzar el límite de clientes o usuarios, el sistema bloquea nuevas altas con un mensaje que invita a subir de plan. Los límites son fijos por plan en el MVP; no existen usuarios extra ni add-ons.
**RN-69** — Los datos existentes no se eliminan si el tenant baja de plan; solo se bloquean nuevas altas por encima del límite.

**RN-70** — Anonimización de datos personales: a solicitud del titular, se reemplazan nombre, CURP, teléfono, dirección y referencias por valores seudónimos, y se eliminan los documentos. La bitácora de auditoría se conserva con identificadores internos (UUID) y sin datos personales, conforme a la obligación de conservación (`RN-67`). La anonimización se registra en auditoría como `client.anonymize`.

---

## 16. Resumen de estados

### Préstamo
```
activo ──(todas las cuotas pagadas)──▶ pagado
   │
   ├──(cuota vencida)──▶ vencido ──(se regulariza)──▶ activo
   │
   └──(cancelación admin)──▶ cancelado
```

### Cuota
```
pendiente ──(pago parcial)──▶ parcial ──(completa)──▶ pagada
    │                              │
    └──(pasa la fecha)──▶ vencida ◀┘
```

### Pago
```
aplicado ──(anulación con permiso)──▶ anulado
```

---

## 17. Tabla de referencia rápida

| ID | Tema | Resumen |
| :--- | :--- | :--- |
| RN-01 a RN-06 | Dinero y fechas | Decimal, redondeo, congelamiento |
| RN-07 a RN-08 | Frecuencias | Cálculo de fechas de vencimiento |
| RN-09 a RN-13 | Intereses | Tres esquemas y cotizador |
| RN-14 a RN-16 | Aprobación | Creación del préstamo y calendario |
| RN-17 a RN-22 | Mora | Prorrateo y gracia |
| RN-23 a RN-38 | Pagos | Validación, aplicación y anulación |
| RN-39 a RN-41 | Comprobantes | Folios y contenido |
| RN-42 a RN-46 | Rutas | Armado y visibilidad |
| RN-47 a RN-51 | Dashboard | Indicadores y aging |
| RN-52 a RN-54 | Comparador | Estimaciones y leyenda |
| RN-55 a RN-60 | Clientes | CURP, unicidad y borrado lógico |
| RN-61 a RN-63 | Permisos | Rol y granularidad |
| RN-64 a RN-67 | Auditoría | Eventos e inmutabilidad |
| RN-68 a RN-70 | Planes y privacidad | Límites fijos y anonimización |
