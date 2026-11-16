# Credigest — Manual de Usuario (Prestamista y Cobrador)

> Guía práctica de operación diaria para los roles **Prestamista** y **Cobrador** en Credigest.

---

## 1. Inicio de sesión y seguridad

1. Ingresa a la dirección web de Credigest desde tu computadora o celular.
2. Captura tu **correo electrónico** y **contraseña** proporcionados por el Administrador de tu financiera.
3. Por seguridad, el sistema bloquea temporalmente los intentos tras **5 intentos fallidos por minuto** (`RNF-10`).
4. Al terminar tu jornada, usa el botón **Cerrar sesión** (o **Salir** en móvil) para revocar tu sesión.

---

## 2. Operación del Prestamista

### 2.1 Gestión de clientes (`CU-03`)
1. En el menú lateral, entra a **Clientes** → **Nuevo cliente**.
2. Captura:
   - **Nombre completo**, **CURP** (18 caracteres oficiales), **teléfono**, **dirección** y **zona de cobro** (ej. `Centro`, `Norte`).
   - Al menos una **referencia personal** (nombre, parentesco, teléfono y dirección).
3. Una vez creado el perfil, en la sección **Documentos** puedes subir:
   - Identificación oficial (**INE**) y **Comprobante de domicilio** en formato PDF, JPG, PNG o WEBP (máximo 10 MB).
4. **Desactivación (`RN-57`, `RN-58`):** Los clientes con historial de préstamos nunca se eliminan; si un cliente ya no operará, cámbialo a estado **Inactivo** para conservar su expediente.

### 2.2 Simular y aprobar un préstamo (`CU-04`, `CU-05`)
1. Entra a **Préstamos** → **Nuevo préstamo**.
2. Ingresa el **monto**, la **tasa por periodo (%)**, la **frecuencia** (`Semanal`, `Quincenal` o `Mensual`), el **plazo** (número de cuotas) y el **esquema de cálculo**:
   - **Interés simple sobre capital:** el interés se calcula siempre sobre el monto original.
   - **Interés sobre saldo insoluto:** amortización constante de capital e interés decreciente.
   - **Cuota fija precalculada:** anualidad con pagos periódicos iguales.
3. Presiona **Simular** para revisar la cuota periódica, el interés total, la fecha de término y la tabla de amortización completa sin guardar datos (`RN-12`).
4. Cuando el cliente acepte las condiciones, selecciona al cliente y presiona **Aprobar préstamo**:
   - Las condiciones financieras quedan **congeladas** (`RN-06`).
   - Desde el detalle del préstamo, presiona **Descargar pagaré PDF** para imprimir y recabar la firma autógrafa del acreditado.

### 2.3 Análisis comparativo bancario (`CU-09`)
1. Entra a **Comparador** en el menú principal.
2. Captura las condiciones de tu préstamo y elige las instituciones bancarias de referencia.
3. Presiona **Comparar ofertas** para obtener la tabla con tasa periódica, tasa anual, **CAT estimado**, cuota periódica, comisiones y costo total (`RF-46`).
4. Puedes descargar la tabla en formato **CSV** para compartirla con el cliente. Recuerda que los resultados son estimaciones con fines informativos (`RN-53`).

---

## 3. Operación del Cobrador (PWA Móvil)

### 3.1 Instalar la aplicación en el celular
1. Abre Credigest desde el navegador de tu teléfono (Chrome en Android o Safari en iOS).
2. Selecciona **Agregar a la pantalla de inicio**.
3. La aplicación guarda una **caché de solo lectura** de las rutas consultadas para que puedas ver direcciones y saldos aunque pierdas señal temporalmente; sin embargo, **registrar un abono requiere conexión a Internet** para evitar cobros duplicados.

### 3.2 Consultar la ruta del día (`CU-06`)
1. Al iniciar sesión como Cobrador, verás tus **Rutas de cobro** asignadas (`RN-45`).
2. Abre la ruta de la fecha actual para ver la lista ordenada de paradas con nombre del cliente, dirección, teléfono, número de cuota, mora acumulada y total exigible.
3. Si el cliente no se encuentra o solicita reagendar, marca la parada como **No pagado** indicando el motivo en las notas (`RF-39`, `RN-46`).

### 3.3 Registrar un abono y entregar comprobante (`CU-07`)
1. Selecciona la cuota del cliente y captura el **monto recibido** y el **método de pago**:
   - **Efectivo**
   - **Transferencia SPEI** (requiere capturar la referencia de al menos 6 caracteres, `RN-25`).
2. El sistema distribuye automáticamente el dinero en el orden estricto **Mora → Interés → Capital** empezando por la cuota más antigua (`RN-29`).
3. Una vez aplicado el abono:
   - Descarga el **Comprobante PDF** (formato ticket de 80 mm) o presiona **Enviar por WhatsApp** para compartir el folio y el saldo restante directamente al teléfono del cliente (`RF-30`, `RF-37`).
4. Al terminar todas las visitas del día, presiona **Cerrar ruta**.

