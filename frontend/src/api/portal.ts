/** Llamadas del portal de consulta para el cliente acreditado (CURP + PIN). */

import { ApiError, request } from "./client";
import type { LoanScheme, LoanStatus, Money, RatePeriod } from "./types";

const PORTAL_TOKEN_KEY = "credigest.portal_token";

export const portalSession = {
  get token(): string | null {
    return sessionStorage.getItem(PORTAL_TOKEN_KEY);
  },
  save(token: string): void {
    sessionStorage.setItem(PORTAL_TOKEN_KEY, token);
  },
  clear(): void {
    sessionStorage.removeItem(PORTAL_TOKEN_KEY);
  },
};

export interface PortalPinResult {
  client_id: string;
  pin: string;
  whatsapp_url: string;
}

export interface PortalTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  client_name: string;
  tenant_name: string;
}

export interface PortalInstallment {
  number: number;
  due_date: string;
  amount: Money;
  late_fee: Money;
  paid_amount: Money;
  pending_amount: Money;
  status: string;
  paid_at: string | null;
}

export interface PortalPayment {
  id: string;
  folio: string;
  amount: Money;
  method: string;
  created_at: string;
}

export interface PortalNextInstallment {
  number: number;
  due_date: string;
  pending_amount: Money;
  is_overdue: boolean;
}

export interface PortalLoan {
  id: string;
  folio: string;
  principal: Money;
  total_amount: Money;
  rate_period: RatePeriod;
  scheme: LoanScheme;
  term_periods: number;
  start_date: string;
  end_date: string;
  status: LoanStatus;
  paid_total: Money;
  remaining_total: Money;
  progress_percent: Money;
  paid_installments_count: number;
  next_installment: PortalNextInstallment | null;
  installments: PortalInstallment[];
  payments: PortalPayment[];
}

export interface PortalOverview {
  client_name: string;
  tenant_name: string;
  active_loans_count: number;
  total_paid: Money;
  total_remaining: Money;
  loans: PortalLoan[];
}

/** Genera o actualiza el PIN de 6 dígitos de un cliente (requiere sesión de empleado). */
export async function setClientPortalPin(
  clientId: string,
  pin?: string,
): Promise<PortalPinResult> {
  return request<PortalPinResult>(`/clients/${clientId}/portal-pin`, {
    method: "POST",
    body: pin ? { pin } : {},
  });
}

/** Inicia sesión en el portal del cliente con CURP y PIN de 6 dígitos. */
export async function portalLogin(
  curp: string,
  pin: string,
  tenantSlug?: string,
): Promise<PortalTokenResponse> {
  return request<PortalTokenResponse>("/portal/login", {
    method: "POST",
    body: {
      curp: curp.trim().toUpperCase(),
      pin: pin.trim(),
      tenant_slug: tenantSlug?.trim() || null,
    },
    skipAuth: true,
  });
}

/** Obtiene el estado de cuenta del cliente usando su token exclusivo del portal. */
export async function getPortalOverview(): Promise<PortalOverview> {
  const token = portalSession.token;
  if (!token) {
    throw new ApiError(401, "Inicia sesión con tu CURP y PIN.");
  }

  const response = await fetch("/api/v1/portal/me", {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (response.status === 401) {
    portalSession.clear();
    throw new ApiError(401, "Tu sesión de consulta expiró. Vuelve a ingresar.");
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      "No se pudo consultar tu estado de cuenta.",
    );
  }

  return (await response.json()) as PortalOverview;
}

/** Descarga un comprobante de pago en PDF desde el portal del cliente. */
export async function downloadPortalReceipt(
  paymentId: string,
  folio: string,
): Promise<void> {
  const token = portalSession.token;
  const response = await fetch(`/api/v1/portal/payments/${paymentId}/receipt.pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new ApiError(response.status, "No se pudo descargar el comprobante.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `comprobante-${folio}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
