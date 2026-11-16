/** Llamadas del comparador bancario (RF-45 a RF-47, RN-52 a RN-54). */

import { request } from "./client";
import type { LoanScheme, Money, Rate, RatePeriod } from "./types";

export interface BankItem {
  id: string;
  tenant_id: string;
  name: string;
  annual_rate: Rate;
  cat: Rate;
  opening_fee: Money;
  is_active: boolean;
  updated_at: string;
}

export interface BankCreateInput {
  name: string;
  annual_rate: Rate;
  cat?: Rate;
  opening_fee?: Money;
  is_active?: boolean;
}

export interface BankUpdateInput {
  name?: string;
  annual_rate?: Rate;
  cat?: Rate;
  opening_fee?: Money;
  is_active?: boolean;
}

export interface CompareInput {
  principal: Money;
  interest_rate: Rate;
  rate_period: RatePeriod;
  scheme: LoanScheme;
  term_periods: number;
  opening_fee?: Money;
  bank_ids?: string[];
}

export interface CompareRow {
  institution: string;
  is_own_offer: boolean;
  periodic_rate: Rate;
  annual_rate: Rate;
  estimated_cat: Money;
  installment_amount: Money;
  total_interest: Money;
  opening_fee: Money;
  total_cost: Money;
}

export interface CompareResult {
  disclaimer: string;
  own_offer: CompareRow;
  bank_offers: CompareRow[];
}

export async function listBanks(onlyActive = false): Promise<BankItem[]> {
  return request<BankItem[]>(`/banks?only_active=${String(onlyActive)}`);
}

export async function createBank(input: BankCreateInput): Promise<BankItem> {
  return request<BankItem>("/banks", { method: "POST", body: input });
}

export async function updateBank(
  id: string,
  input: BankUpdateInput,
): Promise<BankItem> {
  return request<BankItem>(`/banks/${id}`, { method: "PATCH", body: input });
}

export async function compareOffers(input: CompareInput): Promise<CompareResult> {
  return request<CompareResult>("/compare", { method: "POST", body: input });
}

