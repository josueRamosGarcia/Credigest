# Credigest — Roadmap

> Plan de ejecución derivado de `proyecto.md`. Horizonte de **6 meses** para un MVP funcional, con entregas incrementales cada dos semanas. El backend se desarrolla en **Python (FastAPI + SQLAlchemy + PostgreSQL)**.

---

## 1. Objetivo del roadmap

Entregar un MVP usable por un prestamista real al final del mes 6, que cubra el ciclo completo:

> **Cliente → simulación → aprobación → pagaré → ruta de cobro → pago → dashboard → auditoría**

El alcance detallado está en `00-vision.md` (sección 8) y los requisitos en `01-requisitos.md`.

---

## 2. Equipo y responsabilidades

| Persona | Rol | Responsabilidad principal |
| :--- | :--- | :--- |
| David Jiménez García | Líder / Backend | Arquitectura, modelo de datos, API, reglas de negocio, despliegue |
| Josue Leonardo Ramos García | Frontend / UI | SPA React, PWA del cobrador, diseño y experiencia |
| Eduardo Eutimio González López | Analista / QA | Levantamiento, pruebas, documentación, validación con usuarios |

**Capacidad estimada:** 3 personas × ~15 horas/semana × 24 semanas ≈ **1,080 horas**. Se reserva un 20 % para imprevistos y trámites escolares → **~860 horas efectivas**.

---

## 3. Fases y calendario

Se asume inicio en la **semana 1** con 24 semanas totales. Ajustar fechas al calendario escolar real.

### Fase 0 — Preparación (Semanas 1–2)

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| Repositorio, ramas y convenciones | Líder | `main` protegida, plantilla de PR, `README` con setup |
| Entorno Docker Compose (Postgres, Redis, MinIO) | Líder | `docker compose up` levanta todo |
| Esqueleto FastAPI + Alembic | Líder | `GET /health` responde y migración inicial corre |
| Esqueleto React + Vite + TypeScript | Frontend | Pantalla base y build de producción |
| CI con Ruff, mypy y pytest | Líder | Pipeline verde en un PR de prueba |
| Prototipo de UI en Figma | Frontend | Flujos de los tres roles revisados |
| Plan de pruebas y plantilla de casos | QA | Documento aprobado por el equipo |

**Riesgo de fase:** subestimar la configuración. Mitigación: usar plantillas y no personalizar de más.

### Fase 1 — Núcleo de negocio (Semanas 3–6)

Objetivo: cálculos financieros correctos y probados antes de construir pantallas.

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| `domain/interest.py` con los tres esquemas | Líder | 100 % cubierto por pruebas; casos validados a mano |
| `domain/amortization.py` con las tres tablas | Líder | Suma de capital = principal; último periodo ajusta centavos |
| `domain/money.py` y validaciones | Líder | Redondeo `ROUND_HALF_UP` probado |
| Endpoint `/loans/simulate` | Líder | Respuesta con tabla y totales; OpenAPI documentado |
| Pantalla de cotizador | Frontend | Consume la simulación y muestra resultados |
| Batería de casos de prueba financieros | QA | Al menos 20 escenarios con resultado esperado |

**Hito M1 (fin de semana 6):** el cotizador funciona de punta a punta con datos reales.

### Fase 2 — Autenticación, usuarios y clientes (Semanas 7–10)

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| Modelo `tenant`, `user`, `system_setting` | Líder | Migraciones y seeds; creación de tenant y primer admin por seed |
| Login, refresh, logout, recuperación | Líder | Tokens con expiración y revocación persistida |
| RBAC y permisos granulares | Líder | Matriz de `03-reglas-de-negocio.md` aplicada |
| CRUD de usuarios y parámetros | Líder | Solo admin; contraseña temporal si falla el correo |
| Modelo `client`, documentos y referencias | Líder | CURP validada y única por tenant |
| Pantallas de login, usuarios y configuración | Frontend | Guardas por rol |
| CRUD de clientes con carga de archivos | Frontend | Validación de tamaño y tipo |
| Pruebas de permisos y aislamiento por tenant | QA | Ningún acceso cruzado posible |

**Hito M2 (fin de semana 10):** un administrador crea usuarios y un prestamista entra y da de alta clientes con documentos.

### Fase 3 — Préstamos y documentos (Semanas 11–14)

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| Modelo `loan` e `installment` | Líder | Congelamiento de condiciones |
| Endpoint de aprobación y calendario | Líder | Genera cuotas y auditoría |
| Generación de pagaré PDF | Líder | Plantilla con datos, mora y tabla |
| Comprobante de pago PDF | Líder | Reutiliza plantilla base |
| Pantallas de préstamos y detalle | Frontend | Descarga e impresión del pagaré |
| Pruebas de PDF y contenido | QA | Revisión de campos y totales |
| Validación con un prestamista real | QA | Retroalimentación registrada |

**Hito M3 (fin de semana 14):** flujo cliente → préstamo → pagaré completo y validado por un usuario externo.

### Fase 4 — Cobranza y pagos (Semanas 15–18)

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| Modelo `payment` y `payment_application` | Líder | Aplicación en orden mora → interés → capital |
| Motor de mora y estados | Líder | Casos con gracia y sin gracia probados |
| Endpoint de registro y anulación de pagos | Líder | Permisos y recálculo correctos |
| Rutas de cobro por zona y fecha | Líder | Filtrado y orden |
| Pantalla de ruta en la PWA | Frontend | Usable en 360 px |
| Registro de pago desde el celular | Frontend | Efectivo y SPEI; comprobante compartible |
| Pruebas de pagos parciales, adelantados y mora | QA | Casos límite documentados |
| Prueba de campo simulada | QA | Un cobrador completa una ruta de 5 clientes |

**Hito M4 (fin de semana 18):** un cobrador completa una ruta y registra pagos desde el celular.

### Fase 5 — Dashboard, comparador y auditoría (Semanas 19–22)

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| Endpoints de dashboard y aging | Líder | Indicadores según `RN-47` |
| Exportación CSV | Líder | Archivo válido y filtrado |
| Bitácora append-only y consulta | Líder | Sin endpoints de modificación |
| Comparador bancario (catálogo estático) | Líder | Tabla con CAT estimado y leyenda |
| Pantallas de dashboard y auditoría | Frontend | Gráficas y filtros |
| Pantalla de comparador | Frontend | Exportable |
| Pruebas de indicadores con datos controlados | QA | Resultados verificados a mano |

> **Decisión de fase 4:** si al terminar la fase 4 el avance es menor al 80 % de lo planeado, el comparador bancario se pospone a post-MVP y la fase 5 se concentra en dashboard y auditoría.

**Hito M5 (fin de semana 22):** el administrador ve su operación completa y puede auditar movimientos.

### Fase 6 — Endurecimiento y lanzamiento (Semanas 23–24)

| Entregable | Responsable | Criterio de terminado |
| :--- | :--- | :--- |
| Revisión de seguridad (OWASP básico) | Líder | Sin hallazgos críticos |
| Respaldos y restauración probada | Líder | Restauración exitosa en staging |
| Monitoreo y alertas | Líder | Health checks y errores 5xx |
| Optimización de consultas del dashboard | Líder | p95 < 500 ms con datos de prueba |
| Pruebas E2E con Playwright | QA | Flujo principal en verde |
| Manual de usuario y de administrador | QA | Publicado en `docs/` |
| Despliegue a producción y demo final | Todos | URL accesible y demo grabada |

**Hito M6 (fin de semana 24):** MVP en producción con demo y documentación completa.

---

## 4. Vista de calendario

| Mes | Semanas | Foco | Hito |
| :--- | :--- | :--- | :--- |
| 1 | 1–4 | Preparación + inicio del dominio | — |
| 2 | 5–8 | Cálculos, cotizador, auth y clientes | M1 (sem. 6) |
| 3 | 9–12 | Usuarios, clientes, préstamos | M2 (sem. 10) |
| 4 | 13–16 | Pagaré, cobranza y pagos | M3 (sem. 14) |
| 5 | 17–20 | Rutas, PWA y dashboard | M4 (sem. 18) |
| 6 | 21–24 | Auditoría, comparador, hardening y lanzamiento | M5 (sem. 22), M6 (sem. 24) |

---

## 5. Priorización del alcance (MoSCoW)

### Must (MVP)
- RF-01 a RF-04, RF-07 a RF-24, RF-26 a RF-30, RF-31 a RF-32, RF-34 a RF-36, RF-38, RF-41 a RF-42, RF-48 a RF-50, RF-52.
- RNF-05 a RNF-12, RNF-17 a RNF-23.

### Should
- RF-05, RF-06, RF-25, RF-33, RF-37, RF-39, RF-40, RF-43 a RF-47, RF-51.
- RNF-13 a RNF-16, RNF-24 a RNF-27.

> El comparador bancario (RF-45 a RF-47) se mantiene como *Should* con catálogo estático; al final de la fase 4 el equipo decide si entra al MVP o se pospone. El comprobante de pago (RF-30) pasa a *Must* porque es parte del cierre de la cobranza.

### Could (post-MVP)
- Guardar cotizaciones como borrador.
- Exportación avanzada y reportes programados.
- Descuentos y condonaciones.
- Firma electrónica del pagaré.
- Integración real con API SPEI.
- App nativa en tiendas.
- Scoring con buró de crédito.
- Facturación CFDI y cobro automático de suscripciones.

### Won't (este ciclo)
- Multi-sucursal con contabilidad formal.
- Operación offline completa.
- Integraciones con sistemas contables externos.

---

## 6. Plan de pruebas

| Tipo | Cuándo | Responsable | Herramienta |
| :--- | :--- | :--- | :--- |
| Unitaria de dominio | Cada PR | Líder | pytest |
| Integración de API | Cada PR | Líder | pytest + httpx |
| Frontend de componentes | Cada PR | Frontend | Vitest |
| E2E | Fin de cada fase | QA | Playwright |
| Regresión manual | Antes de cada hito | QA | Checklist |
| Seguridad básica | Fase 6 | Líder | Revisión OWASP + `bandit` |
| Prueba con usuario real | Fases 3 y 5 | QA | Sesión guiada |

**Casos obligatorios antes de lanzar:**
1. Los tres esquemas de interés con cifras verificadas.
2. Pago parcial, completo, adelantado y con mora.
3. Anulación de pago y recálculo de saldos.
4. Cobrador intentando ver un cliente fuera de su ruta → 403.
5. CURP duplicada dentro del mismo tenant → 409.
6. Cliente con préstamo activo no se puede eliminar.
7. Bitácora inmutable.
8. Generación e impresión del pagaré.
9. Restauración de respaldo.
10. Flujo E2E completo en móvil.

---

## 7. Definición de terminado (DoD)

Una tarea se considera terminada cuando:
- El código está en `main` con PR revisado por otra persona.
- Tiene pruebas automatizadas y pasan en CI.
- Está documentado en OpenAPI o en `docs/` si aplica.
- Cumple los criterios de aceptación de `01-requisitos.md`.
- Fue probado en staging.
- No introduce secretos ni datos personales reales en el repositorio.

---

## 8. Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Señal temprana | Mitigación |
| :--- | :--- | :--- | :--- | :--- |
| Subestimar cálculos financieros | Media | Alto | Casos que no cuadran al centavo | Congelar fórmulas en fase 1 y validar a mano |
| Tiempo escolar insuficiente | Alta | Medio | Retraso > 1 semana en un hito | Recortar "Should", no "Must" |
| Alcance creciente | Alta | Alto | Nuevas ideas a mitad de fase | Backlog congelado por fase; cambios solo por acuerdo |
| Baja adopción | Media | Alto | Pocas pruebas beta | Onboarding asistido y trial |
| Problemas de PDF en producción | Media | Medio | Diferencias local vs servidor | Probar en contenedor con mismas fuentes |
| Deuda de seguridad | Media | Alto | Permisos mal aplicados | Pruebas de autorización desde fase 2 |
| Dependencia de una sola persona | Media | Alto | Solo el líder toca backend | Revisiones cruzadas y documentación |
| Churn elevado | Media | Alto | Cancelaciones tempranas | Soporte proactivo y mejoras continuas |

---

## 9. Métricas de seguimiento

| Métrica | Frecuencia | Meta |
| :--- | :--- | :--- |
| Requisitos Must completados | Semanal | 100 % al fin de fase 6 |
| Cobertura de pruebas del dominio | Semanal | ≥ 80 % |
| Defectos abiertos críticos | Semanal | 0 al cierre de cada fase |
| Velocidad del equipo (puntos) | Por sprint | Estable a partir de fase 2 |
| Latencia p95 de API | Por release | < 500 ms |
| Errores 5xx | Diario en producción | < 0.5 % de peticiones |
| Usuarios beta activos | Mensual | 5 al mes 5; 10 al mes 6 |

---

## 10. Backlog post-MVP (orden sugerido)

1. Guardado y recuperación de cotizaciones.
2. Recordatorios automáticos de pago por WhatsApp/correo.
3. Conciliación de pagos SPEI con archivo bancario.
4. Reportes programados y envío automático.
5. Firma electrónica del pagaré.
6. App nativa si la PWA resulta insuficiente en campo.
7. Scoring alternativo con historial interno.
8. Multi-sucursal y permisos por sucursal.
9. Facturación y cobro recurrente de suscripciones.
10. Panel de soporte y autoservicio de onboarding.

---

## 11. Entregables documentales al cierre

| Documento | Estado esperado |
| :--- | :--- |
| `00-vision.md` | Vigente y revisado |
| `01-requisitos.md` | Actualizado con cambios aprobados |
| `02-arquitectura.md` | Refleja el sistema desplegado |
| `03-reglas-de-negocio.md` | Validado contra el código |
| `04-roadmap.md` | Cerrado con resultados reales |
| `docs/manual-usuario.md` | Nuevo, en fase 6 |
| `docs/manual-administrador.md` | Nuevo, en fase 6 |
| `docs/api.md` o Swagger publicado | Nuevo, en fase 6 |
| Guion y video de demo | Nuevo, en fase 6 |
