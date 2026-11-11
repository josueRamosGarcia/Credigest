/** Llamadas del dashboard y de la auditoría. */

import { request } from "./client";
import type { Money, Paginated } from "./types";

export interface DashboardSummary {
  capital_prestado: Money;
  capital_recuperado: Money;
  capital_proyectado: Money;
  intereses_generados: Money;
  mora_cobrada: Money;
  utilidad_generada: Money;
  cartera_total: Money;
  cartera_vencida: Money;
  indice_morosidad: Money;
  prestamos_activos: number;
  prestamos_pagados: number;
  prestamos_vencidos: number;
}

export interface AgingBucket {
  label: string;
  min_days: number;
  max_days: number | null;
  amount: Money;
  installments: number;
}

export interface Aging {
  buckets: AgingBucket[];
  total_vencido: Money;
}

export interface CollectionDay {
  day: string;
  amount: Money;
}

export interface SummaryParams {
  from_date?: string;
  to_date?: string;
}

export async function getSummary(params: SummaryParams = {}): Promise<DashboardSummary> {
  const query = new URLSearchParams();
  if (params.from_date) query.set("from_date", params.from_date);
  if (params.to_date) query.set("to_date", params.to_date);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DashboardSummary>(`/dashboard/summary${suffix}`);
}

export async function getAging(): Promise<Aging> {
  return request<Aging>("/dashboard/aging");
}

export async function getCollections(
  params: SummaryParams = {},
): Promise<CollectionDay[]> {
  const query = new URLSearchParams();
  if (params.from_date) query.set("from_date", params.from_date);
  if (params.to_date) query.set("to_date", params.to_date);

  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<CollectionDay[]>(`/dashboard/collections${suffix}`);
}

export interface AuditEntry {
  id: number;
  created_at: string | null;
  user_id: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
}

export interface AuditListParams {
  from_date?: string;
  to_date?: string;
  user_id?: string;
  action?: string;
  entity?: string;
  page?: number;
  page_size?: number;
}

export async function listAudit(
  params: AuditListParams = {},
): Promise<Paginated<AuditEntry>> {
  const query = new URLSearchParams();
  if (params.from_date) query.set("from_date", params.from_date);
  if (params.to_date) query.set("to_date", params.to_date);
  if (params.user_id) query.set("user_id", params.user_id);
  if (params.action) query.set("action", params.action);
  if (params.entity) query.set("entity", params.entity);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 50));

  return request<Paginated<AuditEntry>>(`/audit?${query.toString()}`);
}

/** Etiquetas legibles de las acciones auditadas. */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  "client.create": "Alta de cliente",
  "client.update": "Edición de cliente",
  "client.status_change": "Cambio de estado de cliente",
  "loan.create": "Aprobación de préstamo",
  "loan.cancel": "Cancelación de préstamo",
  "loan.pagare_download": "Descarga de pagaré",
  "payment.create": "Registro de pago",
  "payment.cancel": "Anulación de pago",
  "route.create": "Generación de ruta",
};

/** Etiquetas de las franjas de antigüedad. */
export const AGING_LABELS: Record<string, string> = {
  al_dia: "Al día",
  dias_1_30: "1 a 30 días",
  dias_31_60: "31 a 60 días",
  dias_61_90: "61 a 90 días",
  mas_90: "Más de 90 días",
};
