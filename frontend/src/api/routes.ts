/** Llamadas de rutas de cobro. */

import { request } from "./client";
import type { Money, Paginated, RouteStatus, VisitStatus } from "./types";

export interface RouteItem {
  id: string;
  client_id: string;
  loan_id: string;
  installment_id: string;
  order_index: number;
  visit_status: VisitStatus;
  notes: string | null;
  client_name: string;
  client_address: string;
  client_phone: string;
  installment_number: number;
  due_date: string;
  amount_due: Money;
  late_fee: Money;
  total_due: Money;
}

export interface Route {
  id: string;
  cobrador_id: string;
  zone: string;
  route_date: string;
  status: RouteStatus;
  notes: string | null;
  total_items: number;
  pending_items: number;
}

export interface RouteDetail extends Route {
  items: RouteItem[];
}

export interface RouteInput {
  zone: string;
  route_date: string;
  cobrador_id?: string | null;
}

export interface RouteListParams {
  zone?: string;
  route_date?: string;
  status?: RouteStatus;
  cobrador_id?: string;
  page?: number;
  page_size?: number;
}

export async function listRoutes(
  params: RouteListParams = {},
): Promise<Paginated<Route>> {
  const query = new URLSearchParams();
  if (params.zone) query.set("zone", params.zone);
  if (params.route_date) query.set("route_date", params.route_date);
  if (params.status) query.set("status", params.status);
  if (params.cobrador_id) query.set("cobrador_id", params.cobrador_id);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 20));

  return request<Paginated<Route>>(`/routes?${query.toString()}`);
}

export async function getRoute(id: string): Promise<RouteDetail> {
  return request<RouteDetail>(`/routes/${id}`);
}

export async function createRoute(input: RouteInput): Promise<RouteDetail> {
  return request<RouteDetail>("/routes", { method: "POST", body: input });
}

export async function updateRouteItem(
  routeId: string,
  itemId: string,
  input: { visit_status?: VisitStatus; notes?: string | null },
): Promise<RouteItem> {
  return request<RouteItem>(`/routes/${routeId}/items/${itemId}`, {
    method: "PATCH",
    body: input,
  });
}

export async function reorderRoute(
  routeId: string,
  itemIds: string[],
): Promise<RouteDetail> {
  return request<RouteDetail>(`/routes/${routeId}/reorder`, {
    method: "POST",
    body: { item_ids: itemIds },
  });
}

export async function closeRoute(routeId: string): Promise<Route> {
  return request<Route>(`/routes/${routeId}/close`, { method: "POST" });
}

export const VISIT_STATUS_LABELS: Record<VisitStatus, string> = {
  pendiente: "Pendiente",
  pagado: "Pagado",
  no_pagado: "No pagado",
};

export const VISIT_STATUS_STYLES: Record<VisitStatus, string> = {
  pendiente: "bg-slate-100 text-slate-700",
  pagado: "bg-green-100 text-green-800",
  no_pagado: "bg-red-100 text-red-800",
};

export const ROUTE_STATUS_LABELS: Record<RouteStatus, string> = {
  borrador: "Borrador",
  activa: "Activa",
  cerrada: "Cerrada",
};
