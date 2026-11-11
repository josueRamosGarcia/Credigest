/**
 * Tipos compartidos de la API.
 *
 * Los montos son `string` a propósito: el backend serializa los decimales como
 * texto ("1333.33") para no perder precisión. El frontend nunca debe
 * convertirlos a `number` para guardarlos.
 */

/** Importe monetario ya formateado por el backend, por ejemplo "1333.33". */
export type Money = string;

/** Tasa como fracción por periodo, por ejemplo "0.0500". */
export type Rate = string;

export type Role = "admin" | "prestamista" | "cobrador";

export type LoanScheme = "simple" | "saldo_insoluto" | "cuota_fija";

export type RatePeriod = "semanal" | "quincenal" | "mensual";

export type LoanStatus = "activo" | "pagado" | "vencido" | "cancelado";

export type ClientStatus = "activo" | "inactivo";

export type PaymentMethod = "efectivo" | "spei";

export type PaymentType = "parcial" | "completo" | "adelantado" | "moratorio";

export type VisitStatus = "pendiente" | "pagado" | "no_pagado";

export type RouteStatus = "borrador" | "activa" | "cerrada";

/** Paginación que devuelven los listados. */
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** Formato de error de FastAPI cuando falla la validación. */
export interface ValidationError {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
}
