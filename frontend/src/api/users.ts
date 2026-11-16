/** Llamadas de gestión de usuarios y configuración global (solo Administrador). */

import { request } from "./client";
import type { LoanScheme, Paginated, Rate, Role } from "./types";

export interface UserAccount {
  id: string;
  tenant_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  role: Role;
  permissions: Record<string, boolean>;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface UserCreated extends UserAccount {
  temporary_password: string | null;
}

export interface UserCreateInput {
  full_name: string;
  email: string;
  phone?: string | null;
  role: Role;
  permissions?: Record<string, boolean>;
  password?: string | null;
}

export interface UserUpdateInput {
  full_name?: string;
  phone?: string | null;
  role?: Role;
  permissions?: Record<string, boolean>;
}

export interface UserListParams {
  role?: Role;
  is_active?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface PasswordResetResponse {
  user_id: string;
  temporary_password: string;
}

export interface SystemSetting {
  id: string;
  tenant_id: string;
  default_late_fee_rate: Rate;
  default_scheme: LoanScheme;
  grace_days: number;
  timezone: string;
  updated_at: string;
}

export interface SystemSettingInput {
  default_late_fee_rate: Rate;
  default_scheme: LoanScheme;
  grace_days: number;
  timezone: string;
}

/** Permisos granulares configurables por usuario (RF-05, RN-61). */
export const PERMISSION_LABELS: Record<string, string> = {
  edit_rate: "Modificar tasas en préstamos",
  cancel_payment: "Anular pagos registrados",
  create_client: "Registrar clientes",
  edit_client: "Editar clientes",
  create_loan: "Aprobar préstamos",
  register_payment: "Registrar pagos",
  view_assigned_routes: "Consultar rutas asignadas",
};

export async function listUsers(
  params: UserListParams = {},
): Promise<Paginated<UserAccount>> {
  const query = new URLSearchParams();
  if (params.role) query.set("role", params.role);
  if (params.is_active !== undefined) {
    query.set("is_active", String(params.is_active));
  }
  if (params.search) query.set("search", params.search);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 20));

  return request<Paginated<UserAccount>>(`/users?${query.toString()}`);
}

export async function createUser(input: UserCreateInput): Promise<UserCreated> {
  return request<UserCreated>("/users", { method: "POST", body: input });
}

export async function updateUser(
  id: string,
  input: UserUpdateInput,
): Promise<UserAccount> {
  return request<UserAccount>(`/users/${id}`, { method: "PATCH", body: input });
}

export async function changeUserStatus(
  id: string,
  is_active: boolean,
): Promise<UserAccount> {
  return request<UserAccount>(`/users/${id}/status`, {
    method: "PATCH",
    body: { is_active },
  });
}

export async function resetUserPassword(
  id: string,
  password?: string,
): Promise<PasswordResetResponse> {
  return request<PasswordResetResponse>(`/users/${id}/reset-password`, {
    method: "POST",
    body: password ? { password } : {},
  });
}

export async function getSystemSettings(): Promise<SystemSetting> {
  return request<SystemSetting>("/settings");
}

export async function updateSystemSettings(
  input: SystemSettingInput,
): Promise<SystemSetting> {
  return request<SystemSetting>("/settings", { method: "PUT", body: input });
}

