# Credigest — Requisitos

> Especificación de requisitos derivada de `proyecto.md`. Sigue el estándar de identificadores `RF-xx` (funcional), `RNF-xx` (no funcional) y `CU-xx` (caso de uso) para poder rastrearlos en tareas, pruebas y commits.

---

## 1. Convenciones

| Prefijo | Significado | Ejemplo |
| :--- | :--- | :--- |
| `RF` | Requisito funcional | `RF-07` |
| `RNF` | Requisito no funcional | `RNF-03` |
| `CU` | Caso de uso | `CU-04` |
| `HU` | Historia de usuario (viene de `proyecto.md`) | `HU-2.2` |

Prioridad: **Must** (imprescindible para el MVP), **Should** (deseable en el MVP), **Could** (post-MVP).

---

## 2. Requisitos funcionales

### 2.1 Autenticación y usuarios

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-01 | El sistema debe permitir iniciar sesión con correo y contraseña, devolviendo un token de acceso (JWT). El correo es único global y el login no requiere conocer el tenant. | Must | Todos |
| RF-02 | El sistema debe permitir cerrar sesión e invalidar el token de refresco. | Must | Todos |
| RF-03 | El Administrador debe poder crear, editar, desactivar y reactivar usuarios. | Must | Administrador |
| RF-04 | Al crear un usuario se le debe asignar uno de los roles: `admin`, `prestamista` o `cobrador`. | Must | Administrador |
| RF-05 | El Administrador debe poder definir permisos granulares por usuario (modificar tasas, anular pagos). Los descuentos y condonaciones quedan fuera del MVP. | Should | Administrador |
| RF-06 | El sistema debe enviar las credenciales iniciales al nuevo usuario por correo electrónico. Si el envío falla, el Administrador debe poder definir una contraseña temporal. | Should | Sistema |
| RF-07 | El usuario debe poder cambiar su contraseña y recuperarla mediante correo. | Must | Todos |
| RF-08 | Toda creación, modificación o desactivación de usuario debe registrarse en la bitácora de auditoría. | Must | Sistema |
| RF-52 | El sistema debe permitir crear un tenant (financiera) y su primer administrador mediante seed o proceso manual; no existe autorregistro en el MVP. | Must | Sistema |

### 2.2 Parámetros del sistema

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-09 | El Administrador debe poder configurar la tasa de interés moratorio por defecto. | Must | Administrador |
| RF-10 | El Administrador debe poder configurar el esquema de cálculo predeterminado. | Must | Administrador |
| RF-11 | El Administrador debe poder configurar los días de gracia antes de aplicar mora. | Must | Administrador |
| RF-12 | Los parámetros globales deben aplicar a nuevos préstamos sin alterar los ya creados. | Must | Sistema |

### 2.3 Clientes

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-13 | El Prestamista debe poder registrar un cliente con nombre completo, CURP, teléfono y dirección. | Must | Prestamista |
| RF-14 | El sistema debe validar el formato de la CURP (18 caracteres, estructura oficial) y evitar duplicados por tenant. | Must | Sistema |
| RF-15 | El Prestamista debe poder adjuntar INE y comprobante de domicilio en formato PDF, JPG o PNG. | Must | Prestamista |
| RF-16 | El Prestamista debe poder registrar referencias personales (nombre, parentesco, teléfono, dirección). | Must | Prestamista |
| RF-17 | El sistema debe mostrar el historial de préstamos del cliente. | Must | Prestamista |
| RF-18 | El sistema debe permitir buscar y filtrar clientes por nombre, CURP, teléfono y estado. | Must | Prestamista |
| RF-19 | El sistema debe permitir editar los datos de un cliente, dejando rastro en auditoría. | Must | Prestamista |
| RF-20 | El sistema no debe permitir eliminar clientes con historial de préstamos (activos, vencidos o pagados); solo desactivarlos. | Must | Sistema |

### 2.4 Simulación y cotización

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-21 | El sistema debe simular préstamos con frecuencia semanal, quincenal y mensual. | Must | Prestamista |
| RF-22 | El sistema debe soportar tres esquemas: interés simple sobre capital original, interés sobre saldo insoluto y cuota fija precalculada. | Must | Prestamista |
| RF-23 | La simulación debe devolver cuota periódica, interés total, ganancia estimada, importe total y fecha tentativa de término. La tasa se captura por periodo (según la frecuencia) y las equivalencias mensual/anual son solo informativas. | Must | Prestamista |
| RF-24 | La simulación no debe persistir datos; solo al aprobar se crea el préstamo. | Must | Sistema |
| RF-25 | El Prestamista debe poder guardar una cotización como borrador y recuperarla después. | Could | Prestamista |
| RF-26 | El Prestamista debe poder aprobar una simulación y convertirla en préstamo activo con su tabla de amortización. | Must | Prestamista |

### 2.5 Documentos

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-27 | El sistema debe generar un pagaré en PDF con datos del cliente, condiciones del préstamo e intereses moratorios. | Must | Prestamista |
| RF-28 | El pagaré debe incluir la tabla de amortización completa (número de pago, fecha, cuota, interés, capital, saldo). | Must | Prestamista |
| RF-29 | El sistema debe permitir descargar y reimprimir el pagaré de un préstamo existente. | Must | Prestamista |
| RF-30 | El sistema debe permitir generar un comprobante de pago en PDF por cada abono registrado. | Must | Cobrador |

### 2.6 Cobranza

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-31 | El Cobrador debe poder consultar una ruta de cobro filtrada por zona y fecha. | Must | Cobrador |
| RF-32 | La ruta debe mostrar nombre, dirección, teléfono, saldo adeudado y cuota programada por cliente. | Must | Cobrador |
| RF-33 | La ruta debe ordenar los clientes de forma configurable (por zona, por fecha de vencimiento o proximidad). | Should | Cobrador |
| RF-34 | El Cobrador debe poder registrar un pago en efectivo o por transferencia SPEI (con referencia). | Must | Cobrador |
| RF-35 | El sistema debe permitir pagos parciales, pagos completos, pagos adelantados y pagos aplicados a intereses moratorios. | Must | Cobrador |
| RF-36 | Al registrar un pago, el sistema debe recalcular el saldo insoluto y el estado del préstamo. | Must | Cobrador |
| RF-37 | El sistema debe emitir un comprobante digital y permitir compartirlo por WhatsApp o correo. | Should | Cobrador |
| RF-38 | El Cobrador solo debe ver los clientes y préstamos de las rutas que le fueron asignadas. | Must | Sistema |
| RF-39 | El sistema debe permitir marcar una cuota como "no pagada" con motivo (cliente ausente, promesa de pago). | Should | Cobrador |
| RF-40 | El Administrador o Prestamista con permiso debe poder anular un pago, registrando el motivo en auditoría. | Should | Administrador |

### 2.7 Dashboard financiero

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-41 | El dashboard debe mostrar capital total prestado, capital recuperado, capital proyectado, intereses generados, utilidad e índice de morosidad. | Must | Administrador |
| RF-42 | El dashboard debe permitir filtrar por rango de fechas, prestamista y ruta de cobro. | Must | Administrador |
| RF-43 | El dashboard debe mostrar la cartera vencida separada por rangos de atraso (1–30, 31–60, 61–90, +90 días). | Should | Administrador |
| RF-44 | El dashboard debe permitir exportar la información a CSV (formato único del MVP). | Should | Administrador |

### 2.8 Análisis comparativo bancario

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-45 | El Prestamista debe poder comparar las condiciones de su préstamo contra instituciones bancarias de un catálogo estático configurable por el Administrador (alcance mínimo del MVP). | Should | Prestamista |
| RF-46 | La comparación debe mostrar tasa, CAT estimado, cuota, comisiones y costo total del crédito. | Should | Prestamista |
| RF-47 | El sistema debe aclarar que los resultados son estimaciones informativas y no ofertas vinculantes. | Must | Sistema |

### 2.9 Auditoría

| ID | Requisito | Prioridad | Actor |
| :--- | :--- | :--- | :--- |
| RF-48 | El sistema debe registrar en bitácora: usuario, fecha/hora, acción, entidad afectada, valores anteriores y nuevos, e IP. | Must | Sistema |
| RF-49 | El Administrador debe poder filtrar la bitácora por fecha, usuario y tipo de acción. | Must | Administrador |
| RF-50 | La bitácora debe ser inmutable: no se permite editar ni borrar registros desde la aplicación. | Must | Sistema |
| RF-51 | El Administrador debe poder exportar la bitácora filtrada. | Should | Administrador |

---

## 3. Requisitos no funcionales

### 3.1 Rendimiento y escalabilidad

| ID | Requisito |
| :--- | :--- |
| RNF-01 | Los endpoints de lectura deben responder en menos de 500 ms (p95) con hasta 10,000 clientes por tenant. |
| RNF-02 | La generación de un PDF debe completarse en menos de 3 segundos para préstamos de hasta 60 cuotas. |
| RNF-03 | La arquitectura debe permitir escalar horizontalmente la API sin estado (stateless), usando almacenamiento externo para archivos. |
| RNF-04 | Las consultas del dashboard deben resolverse con índices y, si es necesario, vistas materializadas. |

### 3.2 Seguridad

| ID | Requisito |
| :--- | :--- |
| RNF-05 | Toda comunicación debe viajar por HTTPS. |
| RNF-06 | Las contraseñas deben almacenarse con hash `bcrypt` o `argon2`; nunca en texto plano. |
| RNF-07 | La API debe autenticar con JWT de acceso (corto) y refresco (largo), con revocación. |
| RNF-08 | El acceso a datos debe estar aislado por tenant; ninguna consulta puede cruzar tenants. |
| RNF-09 | Los archivos subidos deben validarse por tipo MIME y tamaño máximo (10 MB), y almacenarse fuera del servidor web público con URLs firmadas. |
| RNF-10 | Debe aplicarse rate limiting en login y recuperación de contraseña. |
| RNF-11 | Los datos sensibles (CURP, INE) deben cifrarse en reposo a nivel de base de datos o de disco. |
| RNF-12 | La bitácora de auditoría no debe ser alterable por usuarios de la aplicación. |

### 3.3 Usabilidad y accesibilidad

| ID | Requisito |
| :--- | :--- |
| RNF-13 | La interfaz del cobrador debe ser usable en pantallas desde 360 px de ancho. |
| RNF-14 | Los formularios deben mostrar validaciones claras en español, junto al campo afectado. |
| RNF-15 | Las acciones destructivas (anular pago, desactivar cliente) deben pedir confirmación explícita. |
| RNF-16 | La interfaz debe cumplir un contraste mínimo AA según WCAG 2.1 en textos principales. |

### 3.4 Disponibilidad y respaldo

| ID | Requisito |
| :--- | :--- |
| RNF-17 | Disponibilidad objetivo del 99 % mensual en horario operativo (07:00–21:00, hora de México). |
| RNF-18 | Respaldo diario automático de la base de datos con retención mínima de 30 días. |
| RNF-19 | Debe existir un procedimiento documentado de restauración con prueba trimestral. |

### 3.5 Mantenibilidad y calidad

| ID | Requisito |
| :--- | :--- |
| RNF-20 | El backend debe usar Python 3.12+, tipado estático y `ruff`/`mypy` en integración continua. |
| RNF-21 | Las reglas de cálculo y aplicación de pagos deben tener pruebas unitarias con cobertura ≥ 80 %. |
| RNF-22 | El código debe seguir una estructura por capas (API, servicios, repositorios, modelos) documentada en `02-arquitectura.md`. |
| RNF-23 | Los cambios de esquema de base de datos deben gestionarse con migraciones versionadas (Alembic). |
| RNF-24 | Los endpoints deben documentarse automáticamente con OpenAPI y ejemplos de request/response. |

### 3.6 Legalidad y privacidad

| ID | Requisito |
| :--- | :--- |
| RNF-25 | El sistema debe permitir anonimizar los datos personales del cliente a solicitud del titular. La bitácora de auditoría se conserva con identificadores internos y sin datos personales, conforme a la obligación de conservación. |
| RNF-26 | Debe mostrarse un aviso de privacidad y recabarse consentimiento para el tratamiento de datos. |
| RNF-27 | Los documentos generados deben indicar que son un apoyo y no sustituyen asesoría legal. |

---

## 4. Casos de uso

### CU-01 — Iniciar sesión
- **Actor:** Administrador, Prestamista, Cobrador.
- **Precondición:** Usuario activo con credenciales válidas.
- **Flujo principal:**
  1. El usuario ingresa correo y contraseña.
  2. El sistema valida credenciales y estado del usuario.
  3. El sistema emite token de acceso y de refresco.
  4. El sistema redirige al inicio correspondiente al rol.
- **Flujos alternativos:** credenciales inválidas → mensaje genérico sin revelar si el correo existe; usuario inactivo → acceso denegado.
- **Postcondición:** sesión activa y evento registrado en auditoría.

### CU-02 — Crear usuario y asignar rol
- **Actor:** Administrador.
- **Precondición:** Sesión de Administrador.
- **Flujo principal:**
  1. El Administrador entra a "Configuración y Usuarios" y elige "Crear Usuario".
  2. Captura nombre, correo y teléfono.
  3. Asigna rol (`prestamista` o `cobrador`) y permisos específicos.
  4. Guarda. El sistema crea la cuenta, envía credenciales y registra auditoría.
- **Postcondición:** Usuario activo con rol y permisos.
- **Regla asociada:** solo el Administrador puede asignar el rol `admin`.

### CU-03 — Registrar cliente con documentación
- **Actor:** Prestamista.
- **Flujo principal:**
  1. Abre "Gestión de Clientes" → "Nuevo Cliente".
  2. Captura datos generales (nombre, CURP, teléfono, dirección).
  3. Sube INE y comprobante de domicilio.
  4. Agrega referencias personales.
  5. Consulta historial previo (si existe).
  6. Guarda. El sistema valida CURP y duplicados y almacena el perfil.
- **Flujos alternativos:** CURP inválida o duplicada → se bloquea el guardado con mensaje; archivo inválido → se rechaza.
- **Postcondición:** Cliente activo con documentos asociados.

### CU-04 — Simular y aprobar préstamo
- **Actor:** Prestamista.
- **Flujo principal:**
  1. Entra al "Cotizador Rápido".
  2. Ingresa monto, tasa, frecuencia y plazo.
  3. Selecciona esquema de cálculo.
  4. Presiona "Simular": el sistema calcula cuota, interés total, ganancia y fecha de término.
  5. Si el cliente acepta, presiona "Aprobar y Generar Documentos".
  6. El sistema crea el préstamo, su calendario de cuotas y el pagaré en PDF.
- **Flujos alternativos:** el cliente no acepta → modifica condiciones y vuelve a simular sin persistir.
- **Postcondición:** Préstamo activo con calendario y documentos generados.

### CU-05 — Generar pagaré
- **Actor:** Prestamista.
- **Precondición:** Préstamo aprobado.
- **Flujo principal:**
  1. El Prestamista solicita el pagaré del préstamo.
  2. El sistema arma el PDF con datos del cliente, condiciones, mora y tabla de amortización.
  3. El sistema devuelve el archivo para descarga o impresión.
- **Postcondición:** PDF disponible y descarga registrada en auditoría.

### CU-06 — Consultar ruta de cobro
- **Actor:** Cobrador.
- **Flujo principal:**
  1. Inicia sesión en la PWA.
  2. Entra a "Cobranza / Rutas".
  3. Selecciona zona y fecha.
  4. El sistema lista clientes con cuotas pendientes o vencidas, ordenados.
  5. El Cobrador consulta los datos de contacto y montos.
- **Postcondición:** Ruta visible; sin cambios de datos.

### CU-07 — Registrar pago y emitir comprobante
- **Actor:** Cobrador.
- **Precondición:** Cobrador asignado al cliente; cuota pendiente.
- **Flujo principal:**
  1. Busca al cliente en la ruta y consulta la cuota.
  2. Recibe el pago (efectivo o SPEI con referencia).
  3. Ingresa monto y método; indica tipo (parcial, completo, adelantado, moratorio).
  4. El sistema valida el monto, lo aplica según las reglas de negocio y recalcula saldos.
  5. El sistema confirma, emite comprobante y actualiza el estado del préstamo.
- **Flujos alternativos:** monto mayor al saldo → se rechaza o se aplica solo el saldo con confirmación; pago duplicado → advertencia.
- **Postcondición:** Pago registrado, saldo actualizado, comprobante disponible, auditoría registrada.

### CU-08 — Consultar dashboard y auditar
- **Actor:** Administrador.
- **Flujo principal:**
  1. Entra al "Dashboard Financiero".
  2. El sistema calcula y muestra indicadores.
  3. Filtra por fecha, prestamista o ruta.
  4. Si detecta algo anómalo, entra a "Historial y Auditoría".
  5. Filtra por fecha, usuario y acción; consulta movimientos.
  6. Exporta el reporte.
- **Postcondición:** Reporte descargado; consulta registrada.

### CU-09 — Comparar con oferta bancaria
- **Actor:** Prestamista.
- **Flujo principal:**
  1. Abre "Análisis Comparativo Bancario".
  2. Ingresa condiciones propias y elige instituciones del catálogo.
  3. El sistema calcula y muestra tabla comparativa (tasa, CAT, cuota, comisiones, costo total).
  4. El Prestamista usa el resultado como argumento comercial.
- **Postcondición:** Comparación visible; puede exportarse.

### CU-10 — Anular pago
- **Actor:** Administrador o Prestamista con permiso.
- **Flujo principal:**
  1. Busca el pago por cliente, préstamo o folio.
  2. Solicita anulación e indica motivo.
  3. El sistema revierte la aplicación del pago, recalcula saldos y registra auditoría.
- **Postcondición:** Pago anulado y saldos restaurados.

---

## 5. Criterios de aceptación (formato Gherkin)

### RF-21/RF-22 — Simulación por esquema
```gherkin
Escenario: Interés simple sobre capital original
  Dado un préstamo de 10,000 MXN a 12 semanas con tasa 5% semanal sobre capital
  Cuando el prestamista simula con esquema "simple"
  Entonces la cuota debe ser 1,333.33 MXN
  Y el interés total debe ser 6,000.00 MXN
  Y el importe total debe ser 16,000.00 MXN
```

```gherkin
Escenario: Cuota fija precalculada
  Dado un préstamo de 10,000 MXN a 12 meses con tasa 3% mensual
  Cuando el prestamista simula con esquema "cuota_fija"
  Entonces la cuota debe calcularse con la fórmula de anualidad
  Y la suma de capital de la tabla debe ser igual al monto prestado
```

### RF-35/RF-36 — Pago parcial
```gherkin
Escenario: Pago parcial menor a la cuota
  Dado un préstamo con cuota de 1,000 MXN y saldo insoluto de 8,000 MXN
  Cuando el cobrador registra un pago de 400 MXN
  Entonces el sistema debe aplicar el pago según el orden definido
  Y el saldo insoluto debe disminuir en la porción de capital aplicada
  Y la cuota debe quedar marcada como parcialmente pagada
```

### RF-38 — Aislamiento del cobrador
```gherkin
Escenario: Cobrador no ve clientes fuera de su ruta
  Dado un cobrador asignado a la zona "Centro"
  Y un cliente de la zona "Norte"
  Cuando el cobrador consulta su ruta
  Entonces el cliente de la zona "Norte" no debe aparecer
  Y una petición directa a su préstamo debe responder 403
```

### RF-50 — Inmutabilidad de auditoría
```gherkin
Escenario: No se puede modificar la bitácora
  Dado un registro de auditoría existente
  Cuando cualquier usuario intenta actualizarlo o eliminarlo desde la API
  Entonces el sistema debe responder 405 o 403
  Y el registro debe permanecer intacto
```

### RF-20 — Cliente con historial de préstamos
```gherkin
Escenario: No eliminar cliente con historial
  Dado un cliente con al menos un préstamo activo, vencido o pagado
  Cuando el prestamista intenta eliminarlo
  Entonces el sistema debe rechazar la operación
  Y ofrecer la opción de desactivarlo
```

---

## 6. Matriz de trazabilidad (resumen)

| Historia de `proyecto.md` | Casos de uso | Requisitos |
| :--- | :--- | :--- |
| HU-1.1 Configuración y usuarios | CU-02 | RF-03 a RF-12, RF-52 |
| HU-1.2 Dashboard y auditoría | CU-08 | RF-41 a RF-51 |
| HU-2.1 Registro de cliente | CU-03 | RF-13 a RF-20 |
| HU-2.2 Cotización y pagaré | CU-04, CU-05 | RF-21 a RF-30 |
| HU-2.3 Comparación bancaria | CU-09 | RF-45 a RF-47 |
| HU-3.1 Rutas de cobro | CU-06 | RF-31 a RF-33, RF-38 |
| HU-3.2 Registro de abono | CU-07 | RF-34 a RF-40 |

---

## 7. Fuera de alcance de esta especificación

- Reglas matemáticas detalladas → ver `03-reglas-de-negocio.md`.
- Decisiones de tecnología y modelo de datos → ver `02-arquitectura.md`.
- Calendario y entregables → ver `04-roadmap.md`.
