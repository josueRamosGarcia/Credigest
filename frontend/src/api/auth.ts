/** Llamadas de autenticación. */

import { request } from "./client";
import type { Role } from "./types";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface CurrentUser {
  id: string;
  tenant_id: string;
  full_name: string;
  email: string;
  role: Role;
  permissions: Record<string, boolean>;
  tenant_name: string;
  tenant_slug: string | null;
  tenant_plan: string;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  return request<TokenPair>("/auth/login", {
    method: "POST",
    body: { email, password },
    skipAuth: true,
  });
}

export async function logout(refreshToken: string): Promise<void> {
  await request<void>("/auth/logout", {
    method: "POST",
    body: { refresh_token: refreshToken },
    skipAuth: true,
  });
}

export async function me(): Promise<CurrentUser> {
  return request<CurrentUser>("/auth/me");
}

/** Etiqueta legible del rol, para mostrar en la interfaz. */
export const ROLE_LABELS: Record<Role, string> = {
  admin: "Administrador",
  prestamista: "Prestamista",
  cobrador: "Cobrador",
};
