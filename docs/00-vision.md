# Credigest — Visión del producto

> Documento de visión derivado de `proyecto.md`. Define qué es Credigest, para quién existe, qué problema resuelve y hasta dónde llega su alcance.

---

## 1. Identidad del proyecto

| Campo | Valor |
| :--- | :--- |
| **Nombre del producto** | Credigest |
| **Tipo** | SaaS (Software as a Service) de gestión de préstamos |
| **Mercado** | México (microfinanzas y préstamo informal profesionalizado) |
| **Institución** | Instituto Tecnológico de La Laguna — Ingeniería en Sistemas Computacionales |
| **Materia** | Gestión de Proyectos de Software |
| **Equipo** | David Jiménez García, Josue Leonardo Ramos García, Eduardo Eutimio González López |
| **Stack base** | Python (FastAPI + SQLAlchemy) como backend; React como frontend; PostgreSQL como base de datos |
| **Horizonte** | 6 meses para un MVP funcional con proyección comercial |

---

## 2. Problema

Los prestamistas independientes y las pequeñas financieras en México operan normalmente con:

- Hojas de cálculo de Excel propensas a errores de cálculo y de captura.
- Registros en papel que se pierden, se deterioran o no son consultables.
- Falta de control sobre los cobradores que trabajan en campo.
- Dificultad para calcular intereses, amortizaciones y moratorios correctamente.
- Documentación legal deficiente (pagarés mal elaborados o incompletos).
- Ausencia de indicadores financieros para decidir a quién prestar y cómo cobrar.

El resultado es pérdida de dinero, cartera incobrable no detectada a tiempo, conflictos legales por documentos mal hechos y una operación que no puede escalar.

---

## 3. Propuesta de valor

1. **Centralización total:** clientes, préstamos, pagos, rutas, documentos y auditoría en una sola plataforma.
2. **Flexibilidad de esquemas:** interés simple sobre capital original, interés sobre saldo insoluto y cuota fija precalculada.
3. **Cumplimiento documental:** pagarés en PDF con tabla de amortización, cláusulas de mora y datos del cliente, listos para firma.
4. **Control multi-usuario:** roles de Administrador, Prestamista y Cobrador con permisos diferenciados.
5. **Trazabilidad completa:** bitácora de auditoría de todas las operaciones sensibles.
6. **Movilidad:** el cobrador trabaja desde el celular mediante una PWA (aplicación web progresiva) responsive, sin instalar una app nativa.

---

## 4. Solución: módulos del producto

| Módulo | Qué resuelve | Actor principal |
| :--- | :--- | :--- |
| **Gestión de clientes** | Alta, edición, documentos (INE, comprobante), referencias e historial | Prestamista |
| **Simulador / cotizador** | Cálculo de cuota, interés total, ganancia y fecha de término | Prestamista |
| **Generador de documentos** | Pagaré y tabla de amortización en PDF | Prestamista |
| **Cobranza y rutas** | Lista diaria de cobro por zona/fecha y registro de abonos | Cobrador |
| **Dashboard financiero** | Capital prestado, recuperado, proyectado, utilidad y morosidad | Administrador |
| **Análisis comparativo bancario** | Comparación contra ofertas bancarias (tasa, CAT, comisiones, costo total) | Prestamista |
| **Configuración y usuarios** | Cuentas, roles, permisos y parámetros globales | Administrador |
| **Auditoría** | Bitácora filtrable y exportable de operaciones | Administrador |

---

## 5. Actores y necesidades

### 5.1 Administrador
Persona con capital y responsabilidad sobre la operación. Necesita configurar usuarios y reglas del negocio, vigilar la salud financiera del negocio y auditar movimientos sospechosos.

### 5.2 Prestamista
Responsable de evaluar y colocar créditos. Necesita registrar clientes con su documentación, simular condiciones, generar el pagaré y comparar su oferta con la banca.

### 5.3 Cobrador
Trabaja en campo. Necesita una lista clara y ordenada de a quién cobrar, cuánto y dónde; y registrar el pago en el momento, emitiendo comprobante.

---

## 6. Segmento objetivo

**Segmento primario**
- Prestamistas independientes con 50–500 clientes activos.
- Pequeñas financieras (SOFOMes no reguladas).
- Cooperativas de ahorro y préstamo.

**Segmento secundario**
- Casas de empeño con servicio de préstamos.
- Prestamistas en zonas rurales y semiurbanas.

**Perfil del cliente ideal**
- 1–10 empleados, incluidos cobradores.
- Cartera activa de $500,000 a $5,000,000 MXN.
- Operación actual en Excel o papel.
- Disposición a pagar entre $500 y $2,000 MXN mensuales.

---

## 7. Modelo de negocio (resumen)

Suscripciones mensuales y anuales con estructura escalonada por número de clientes y usuarios:

| Plan | Precio mensual | Precio anual | Incluye |
| :--- | ---: | ---: | :--- |
| Básico | $149 MXN | $1,490 MXN | Hasta 50 clientes, simulador, pagarés, registro de pagos |
| Profesional | $299 MXN | $2,990 MXN | Hasta 200 clientes, dashboard, rutas de cobro, SPEI |
| Empresarial | $599 MXN | $5,990 MXN | 10 usuarios, clientes ilimitados, comparador bancario, soporte prioritario |

**Meta financiera año 1:** 50 suscriptores activos, MRR de $15,000 MXN, punto de equilibrio entre el mes 8 y 10.

> El detalle comercial completo vive en `proyecto.md`. Este documento no lo duplica; solo lo resume para dar contexto al producto.

---

## 8. Alcance

### 8.1 Dentro del alcance (MVP)
- Autenticación y gestión de usuarios con tres roles.
- CRUD de clientes con referencias y carga de documentos.
- Simulación de préstamos con tres esquemas y tres frecuencias.
- Generación de pagaré y tabla de amortización en PDF.
- Registro de pagos (efectivo/SPEI) con pagos parciales y adelantados.
- Rutas de cobro filtradas por zona y fecha.
- Dashboard financiero con indicadores básicos.
- Auditoría de operaciones.
- PWA responsive para el cobrador.

### 8.2 Fuera del alcance inicial (post-MVP)
- App móvil nativa (iOS/Android) publicada en tiendas.
- Integración bancaria real vía API SPEI (el MVP registra referencias manualmente).
- Firma electrónica avanzada del pagaré.
- Facturación (CFDI) y cobro automático de suscripciones.
- Scoring crediticio con buró de crédito.
- Reportería avanzada y BI externo.
- Multi-sucursal con contabilidad formal.

### 8.3 Supuestos
- Cada cliente del SaaS (financiera) es un **tenant** lógico aislado en la misma base de datos.
- El pagaré generado es un documento de apoyo; la validez legal final es responsabilidad del usuario.
- Los cálculos de CAT y comparación bancaria son estimaciones informativas, no ofertas vinculantes.
- Se requiere conexión a Internet; no se promete operación offline en el MVP (solo caché de lectura en la PWA).

### 8.4 Restricciones
- Equipo de 3 personas con tiempo parcial y plazo de 6 meses.
- Presupuesto de infraestructura reducido ($0–500 MXN/mes).
- Sin experiencia previa en el dominio financiero formal; se apoya en asesoría docente y documentación.

---

## 9. Objetivos y métricas de éxito

| Objetivo | Métrica | Meta |
| :--- | :--- | :--- |
| Producto usable | Flujo cliente → préstamo → pagaré completado sin soporte | ≥ 90 % de pruebas de usuario |
| Exactitud financiera | Diferencias entre cálculo del sistema y cálculo validado manualmente | 0 diferencias en casos de prueba |
| Adopción | Suscriptores activos al mes 12 | 50 |
| Retención | Churn mensual | < 5 % |
| Rendimiento | Tiempo de respuesta de endpoints principales (p95) | < 500 ms |
| Calidad | Cobertura de pruebas en reglas de cálculo y pagos | ≥ 80 % |

---

## 10. Riesgos de producto

| Riesgo | Probabilidad | Impacto | Mitigación |
| :--- | :--- | :--- | :--- |
| Baja adopción inicial | Media | Alto | Trial gratuito y onboarding asistido |
| Tiempo limitado (6 meses) | Alta | Medio | Priorizar MVP y dividir tareas |
| Problemas técnicos | Media | Medio | Arquitectura simple y pruebas continuas |
| Falta de experiencia en el dominio | Media | Medio | Asesoría docente y documentación de reglas |
| Churn elevado | Media | Alto | Soporte proactivo y mejoras constantes |
| Errores en cálculos financieros | Media | Alto | Reglas documentadas y pruebas unitarias exhaustivas |

---

## 11. Documentos relacionados

| Documento | Contenido |
| :--- | :--- |
| `01-requisitos.md` | Requisitos funcionales y no funcionales, casos de uso y criterios de aceptación |
| `02-arquitectura.md` | Stack, modelo de datos, API, estructura del código, seguridad y despliegue |
| `03-reglas-de-negocio.md` | Fórmulas de interés, amortización, mora, aplicación de pagos y permisos |
| `04-roadmap.md` | Fases, entregables, calendario de 6 meses y plan de pruebas |
