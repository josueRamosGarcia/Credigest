/** Llamadas de préstamos, simulación y pagaré. */

import { downloadFile, request } from "./client";
import type {
  LoanScheme,
  LoanStatus,
  Money,
  Paginated,
  Rate,
  RatePeriod,
} from "./types";

// Se reexportan para que las paginas importen todo desde aqui.
export type { LoanScheme, RatePeriod };

export interface ScheduleRow {
  number: number;
  due_date: string;
  amount: Money;
  interest_part: Money;
  principal_part: Money;
  balance: Money;
}

export interface SimulationInput {
  principal: number;
  interest_rate: number;
  rate_period: RatePeriod;
  scheme: LoanScheme;
  term_periods: number;
  start_date: string;
}

export interface Simulation {
  installment_amount: Money;
  installment_amount_last: Money;
  total_interest: Money;
  total_amount: Money;
  estimated_profit: Money;
  end_date: string;
  annual_equivalent_rate: Rate;
  schedule: ScheduleRow[];
}

export interface Installment {
  id: string;
  number: number;
  due_date: string;
  amount: Money;
  principal_part: Money;
  interest_part: Money;
  late_fee: Money;
  paid_amount: Money;
  status: string;
  paid_at: string | null;
}

export interface Loan {
  id: string;
  client_id: string;
  principal: Money;
  interest_rate: Rate;
  rate_period: RatePeriod;
  scheme: LoanScheme;
  term_periods: number;
  start_date: string;
  first_due_date: string;
  end_date: string;
  total_interest: Money;
  total_amount: Money;
  late_fee_rate: Rate;
  grace_days: number;
  status: LoanStatus;
}

export interface LoanDetail extends Loan {
  installments: Installment[];
}

export interface LoanInput extends SimulationInput {
  client_id: string;
  late_fee_rate?: number;
  grace_days?: number;
}

export interface LoanListParams {
  status?: LoanStatus;
  client_id?: string;
  page?: number;
  page_size?: number;
}

export async function simulate(input: SimulationInput): Promise<Simulation> {
  return request<Simulation>("/loans/simulate", { method: "POST", body: input });
}

export async function createLoan(input: LoanInput): Promise<LoanDetail> {
  return request<LoanDetail>("/loans", { method: "POST", body: input });
}

export async function listLoans(
  params: LoanListParams = {},
): Promise<Paginated<Loan>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.client_id) query.set("client_id", params.client_id);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.page_size ?? 20));

  return request<Paginated<Loan>>(`/loans?${query.toString()}`);
}

export async function getLoan(id: string): Promise<LoanDetail> {
  return request<LoanDetail>(`/loans/${id}`);
}

export async function getSchedule(id: string): Promise<ScheduleRow[]> {
  return request<ScheduleRow[]>(`/loans/${id}/schedule`);
}

export async function cancelLoan(id: string, reason: string): Promise<Loan> {
  return request<Loan>(`/loans/${id}/cancel`, {
    method: "POST",
    body: { reason },
  });
}

export async function downloadPagare(loanId: string): Promise<void> {
  await downloadFile(`/loans/${loanId}/pagare.pdf`, `pagare-${loanId.slice(0, 8)}.pdf`);
}

/** Etiquetas legibles de los esquemas de cálculo. */
export const SCHEME_LABELS: Record<LoanScheme, string> = {
  simple: "Interés simple sobre capital",
  saldo_insoluto: "Interés sobre saldo insoluto",
  cuota_fija: "Cuota fija precalculada",
};

/** Etiquetas legibles de las frecuencias. */
export const PERIOD_LABELS: Record<RatePeriod, string> = {
  semanal: "Semanal",
  quincenal: "Quincenal",
  mensual: "Mensual",
};

/** Etiquetas y colores de los estados del préstamo. */
export const LOAN_STATUS_LABELS: Record<LoanStatus, string> = {
  activo: "Activo",
  pagado: "Pagado",
  vencido: "Vencido",
  cancelado: "Cancelado",
};

export const LOAN_STATUS_STYLES: Record<LoanStatus, string> = {
  activo: "bg-blue-100 text-blue-800",
  pagado: "bg-green-100 text-green-800",
  vencido: "bg-red-100 text-red-800",
  cancelado: "bg-slate-100 text-slate-600",
};

/** Etiquetas de los estados de una cuota. */
export const INSTALLMENT_STATUS_LABELS: Record<string, string> = {
  pendiente: "Pendiente",
  parcial: "Parcial",
  pagada: "Pagada",
  vencida: "Vencida",
};

export const INSTALLMENT_STATUS_STYLES: Record<string, string> = {
  pendiente: "bg-slate-100 text-slate-700",
  parcial: "bg-amber-100 text-amber-800",
  pagada: "bg-green-100 text-green-800",
  vencida: "bg-red-100 text-red-800",
};
