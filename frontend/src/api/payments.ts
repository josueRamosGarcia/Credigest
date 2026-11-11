/** Llamadas de pagos. */

import { request } from "./client";
import type { Money, Paginated, PaymentMethod, PaymentType } from "./types";

export interface PaymentApplication {
  installment_id: string;
  concept: string;
  amount: Money;
}

export interface Payment {
  id: string;
  loan_id: string;
  folio: string;
  amount: Money;
  method: PaymentMethod;
  spei_reference: string | null;
  payment_type: PaymentType;
  status: "aplicado" | "anulado";
  registered_by: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  created_at: string;
}

export interface PaymentDetail extends Payment {
  applications: PaymentApplication[];
}

export interface PaymentResult {
  payment: PaymentDetail;
  loan_status: string;
  remaining_total: Money;
  covered_late_fee: Money;
  covered_interest: Money;
  covered_principal: Money;
}

export interface PaymentInput {
  loan_id: string;
  amount: number;
  method: PaymentMethod;
  spei_reference?: string | null;
  payment_type?: PaymentType;
  notes?: string | null;
}

export interface PaymentListParams {
  loan_id?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}

export async function registerPayment(input: PaymentInput): Promise<PaymentResult> {
  return request<PaymentResult>("/payments", { method: "POST", body: input });
}

export async function listPayments(
  params: PaymentListParams = {},
): Promise<Paginated<Payment>> {
  const query = new URLSearchParams();
  if (params.loan_id) query.set("loan_id", params.loan_id);
  if (params.from_date) query.set("from_date", params.from_date);
  if (params.to_date) query.set("to_date", params.to_date);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 20));

  return request<Paginated<Payment>>(`/payments?${query.toString()}`);
}

export async function getPayment(id: string): Promise<PaymentDetail> {
  return request<PaymentDetail>(`/payments/${id}`);
}

export async function cancelPayment(id: string, reason: string): Promise<PaymentResult> {
  return request<PaymentResult>(`/payments/${id}/cancel`, {
    method: "POST",
    body: { reason },
  });
}

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  efectivo: "Efectivo",
  spei: "Transferencia SPEI",
};

export const PAYMENT_TYPE_LABELS: Record<PaymentType, string> = {
  parcial: "Pago parcial",
  completo: "Pago completo",
  adelantado: "Pago adelantado",
  moratorio: "Pago de mora",
};

export const CONCEPT_LABELS: Record<string, string> = {
  mora: "Mora",
  interes: "Interés",
  capital: "Capital",
};
