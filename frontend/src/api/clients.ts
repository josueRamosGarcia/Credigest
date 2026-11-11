/** Llamadas de clientes. */

import { request } from "./client";
import type { ClientStatus, Money, Paginated } from "./types";

export interface ClientReference {
  id: string;
  name: string;
  relationship: string;
  phone: string;
  address: string;
}

export interface Client {
  id: string;
  full_name: string;
  curp: string;
  phone: string;
  address: string;
  zone: string | null;
  birth_date: string | null;
  status: ClientStatus;
  notes: string | null;
}

export interface ClientDetail extends Client {
  references: ClientReference[];
}

export interface ClientDocument {
  id: string;
  doc_type: string;
  mime_type: string;
  size_bytes: number;
}

export interface ReferenceInput {
  name: string;
  relationship: string;
  phone: string;
  address: string;
}

export interface ClientInput {
  full_name: string;
  curp: string;
  phone: string;
  address: string;
  zone?: string | null;
  notes?: string | null;
  references?: ReferenceInput[];
}

export interface ClientListParams {
  search?: string;
  zone?: string;
  status?: ClientStatus;
  page?: number;
  page_size?: number;
}

export async function listClients(
  params: ClientListParams = {},
): Promise<Paginated<Client>> {
  const query = new URLSearchParams();
  if (params.search) query.set("search", params.search);
  if (params.zone) query.set("zone", params.zone);
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 20));

  return request<Paginated<Client>>(`/clients?${query.toString()}`);
}

export async function getClient(id: string): Promise<ClientDetail> {
  return request<ClientDetail>(`/clients/${id}`);
}

export async function createClient(input: ClientInput): Promise<ClientDetail> {
  return request<ClientDetail>("/clients", { method: "POST", body: input });
}

export async function updateClient(
  id: string,
  input: Partial<ClientInput>,
): Promise<ClientDetail> {
  return request<ClientDetail>(`/clients/${id}`, { method: "PATCH", body: input });
}

export async function changeClientStatus(
  id: string,
  status: ClientStatus,
): Promise<Client> {
  return request<Client>(`/clients/${id}/status`, {
    method: "PATCH",
    body: { status },
  });
}

export async function addReference(
  clientId: string,
  input: ReferenceInput,
): Promise<ClientReference> {
  return request<ClientReference>(`/clients/${clientId}/references`, {
    method: "POST",
    body: input,
  });
}

export async function listDocuments(clientId: string): Promise<ClientDocument[]> {
  return request<ClientDocument[]>(`/clients/${clientId}/documents`);
}

/** Documento con su etiqueta legible. */
export const DOCUMENT_LABELS: Record<string, string> = {
  ine: "Identificación oficial (INE)",
  comprobante_domicilio: "Comprobante de domicilio",
  otro: "Otro documento",
};

/** Formato de tamaño de archivo legible. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Saldo pendiente de un cliente no viene en el listado; se usa en detalle. */
export type { Money };
