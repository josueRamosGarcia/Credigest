/**
 * Pantalla de Análisis Comparativo Bancario (CU-09, RF-45 a RF-47, RN-52 a RN-54).
 *
 * Permite al Prestamista y al Administrador comparar su oferta de crédito frente
 * al catálogo de instituciones bancarias de referencia y exportar la tabla.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import {
  type BankItem,
  type CompareResult,
  compareOffers,
  createBank,
  listBanks,
  updateBank,
} from "@/api/comparator";
import { PERIOD_LABELS, SCHEME_LABELS } from "@/api/loans";
import type { LoanScheme, RatePeriod } from "@/api/types";
import { useAuth } from "@/auth/useAuth";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { formatCurrency, formatRate, percentToRate, todayIso } from "@/lib/format";

export function ComparatorPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();

  // Condiciones propias a simular
  const [principal, setPrincipal] = useState("10000");
  const [ratePercent, setRatePercent] = useState("3");
  const [ratePeriod, setRatePeriod] = useState<RatePeriod>("mensual");
  const [scheme, setScheme] = useState<LoanScheme>("cuota_fija");
  const [termPeriods, setTermPeriods] = useState("12");
  const [openingFee, setOpeningFee] = useState("0");
  const [selectedBankIds, setSelectedBankIds] = useState<string[]>([]);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // Gestión del catálogo (solo Administrador)
  const [showNewBank, setShowNewBank] = useState(false);
  const [bankName, setBankName] = useState("");
  const [bankAnnualPercent, setBankAnnualPercent] = useState("36");
  const [bankFee, setBankFee] = useState("0");
  const [bankError, setBankError] = useState<string | null>(null);

  const banksQuery = useQuery({
    queryKey: ["banks"],
    queryFn: () => listBanks(false),
  });

  const compareMutation = useMutation({
    mutationFn: () =>
      compareOffers({
        principal: Number(principal).toFixed(2),
        interest_rate: percentToRate(ratePercent),
        rate_period: ratePeriod,
        scheme,
        term_periods: Number(termPeriods),
        opening_fee: Number(openingFee || "0").toFixed(2),
        bank_ids: selectedBankIds.length > 0 ? selectedBankIds : undefined,
      }),
    onSuccess: (data) => {
      setFormError(null);
      setResult(data);
    },
    onError: (err) => {
      setFormError(
        err instanceof Error
          ? err.message
          : "No se pudo realizar la comparación.",
      );
    },
  });

  const createBankMutation = useMutation({
    mutationFn: () =>
      createBank({
        name: bankName.trim(),
        annual_rate: percentToRate(bankAnnualPercent),
        opening_fee: Number(bankFee || "0").toFixed(2),
        is_active: true,
      }),
    onSuccess: () => {
      setBankError(null);
      setBankName("");
      setBankAnnualPercent("36");
      setBankFee("0");
      setShowNewBank(false);
      void queryClient.invalidateQueries({ queryKey: ["banks"] });
    },
    onError: (err) => {
      setBankError(
        err instanceof Error ? err.message : "No se pudo agregar el banco.",
      );
    },
  });

  const toggleBankStatusMutation = useMutation({
    mutationFn: (bank: BankItem) =>
      updateBank(bank.id, { is_active: !bank.is_active }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["banks"] });
    },
  });

  const handleCompare = (event: FormEvent) => {
    event.preventDefault();
    if (Number(principal) <= 0) {
      setFormError("El monto debe ser mayor que cero.");
      return;
    }
    if (Number(termPeriods) < 1) {
      setFormError("El plazo debe ser de al menos 1 periodo.");
      return;
    }
    compareMutation.mutate();
  };

  const handleCreateBank = (event: FormEvent) => {
    event.preventDefault();
    if (bankName.trim().length < 2) {
      setBankError("Ingresa el nombre de la institución.");
      return;
    }
    createBankMutation.mutate();
  };

  const toggleSelectedBank = (bankId: string) => {
    setSelectedBankIds((prev) =>
      prev.includes(bankId)
        ? prev.filter((id) => id !== bankId)
        : [...prev, bankId],
    );
  };

  const handleExportCsv = () => {
    if (!result) return;
    const rows = [result.own_offer, ...result.bank_offers];
    const headers = [
      "Institución",
      "Tipo",
      "Tasa periódica (%)",
      "Tasa anual (%)",
      "CAT estimado (%)",
      "Cuota periódica",
      "Interés total",
      "Comisión apertura",
      "Costo total",
    ];
    const lines = [
      headers.join(","),
      ...rows.map((row) =>
        [
          `"${row.institution.replace(/"/g, '""')}"`,
          row.is_own_offer ? "Oferta propia" : "Referencia bancaria",
          (Number(row.periodic_rate) * 100).toFixed(2),
          (Number(row.annual_rate) * 100).toFixed(2),
          row.estimated_cat,
          row.installment_amount,
          row.total_interest,
          row.opening_fee,
          row.total_cost,
        ].join(","),
      ),
      `"${result.disclaimer}"`,
    ];

    const blob = new Blob([lines.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `comparativo-bancario-${todayIso()}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Análisis comparativo bancario"
        description="Compara las condiciones de tu préstamo frente a ofertas de referencia de instituciones bancarias."
        actions={
          <div className="flex gap-2">
            {result && (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleExportCsv}
              >
                Exportar CSV
              </button>
            )}
            {isAdmin && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowNewBank((prev) => !prev)}
              >
                {showNewBank ? "Cerrar alta" : "Agregar banco al catálogo"}
              </button>
            )}
          </div>
        }
      />

      {showNewBank && isAdmin && (
        <Card>
          <h2 className="text-base font-semibold text-slate-900">
            Nueva institución en el catálogo (RN-54)
          </h2>
          <form
            onSubmit={handleCreateBank}
            className="mt-4 grid gap-4 sm:grid-cols-3"
          >
            <div>
              <label htmlFor="bank-name" className="label">
                Institución y producto
              </label>
              <input
                id="bank-name"
                type="text"
                required
                className="input"
                placeholder="Ej. Santander (Crédito Personal)"
                value={bankName}
                onChange={(e) => setBankName(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="bank-annual-rate" className="label">
                Tasa anual de referencia (%)
              </label>
              <input
                id="bank-annual-rate"
                type="number"
                step="0.01"
                min="0"
                max="500"
                className="input"
                value={bankAnnualPercent}
                onChange={(e) => setBankAnnualPercent(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="bank-fee" className="label">
                Comisión de apertura (MXN)
              </label>
              <input
                id="bank-fee"
                type="number"
                step="0.01"
                min="0"
                className="input"
                value={bankFee}
                onChange={(e) => setBankFee(e.target.value)}
              />
            </div>

            {bankError && (
              <div className="sm:col-span-3">
                <Alert tone="error">{bankError}</Alert>
              </div>
            )}

            <div className="sm:col-span-3 flex justify-end gap-2">
              <button
                type="submit"
                className="btn-primary"
                disabled={createBankMutation.isPending}
              >
                {createBankMutation.isPending
                  ? "Guardando…"
                  : "Guardar institución"}
              </button>
            </div>
          </form>
        </Card>
      )}

      {/* Formulario de condiciones propias */}
      <Card>
        <h2 className="text-base font-semibold text-slate-900">
          Condiciones de tu préstamo
        </h2>
        <form
          onSubmit={handleCompare}
          className="mt-4 grid gap-4 sm:grid-cols-3"
        >
          <div>
            <label htmlFor="cmp-principal" className="label">
              Monto a prestar (MXN)
            </label>
            <input
              id="cmp-principal"
              type="number"
              min="1"
              step="0.01"
              required
              className="input"
              value={principal}
              onChange={(e) => setPrincipal(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="cmp-rate" className="label">
              Tasa por periodo (%)
            </label>
            <input
              id="cmp-rate"
              type="number"
              min="0"
              step="0.01"
              required
              className="input"
              value={ratePercent}
              onChange={(e) => setRatePercent(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="cmp-period" className="label">
              Frecuencia de pago
            </label>
            <select
              id="cmp-period"
              className="input"
              value={ratePeriod}
              onChange={(e) => setRatePeriod(e.target.value as RatePeriod)}
            >
              {(Object.keys(PERIOD_LABELS) as RatePeriod[]).map((key) => (
                <option key={key} value={key}>
                  {PERIOD_LABELS[key]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="cmp-scheme" className="label">
              Esquema de cálculo
            </label>
            <select
              id="cmp-scheme"
              className="input"
              value={scheme}
              onChange={(e) => setScheme(e.target.value as LoanScheme)}
            >
              {(Object.keys(SCHEME_LABELS) as LoanScheme[]).map((key) => (
                <option key={key} value={key}>
                  {SCHEME_LABELS[key]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="cmp-term" className="label">
              Plazo (número de cuotas)
            </label>
            <input
              id="cmp-term"
              type="number"
              min="1"
              max="520"
              required
              className="input"
              value={termPeriods}
              onChange={(e) => setTermPeriods(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="cmp-fee" className="label">
              Comisión de apertura propia (MXN)
            </label>
            <input
              id="cmp-fee"
              type="number"
              min="0"
              step="0.01"
              className="input"
              value={openingFee}
              onChange={(e) => setOpeningFee(e.target.value)}
            />
          </div>

          {formError && (
            <div className="sm:col-span-3">
              <Alert tone="error">{formError}</Alert>
            </div>
          )}

          <div className="sm:col-span-3 flex justify-end">
            <button
              type="submit"
              className="btn-primary"
              disabled={compareMutation.isPending}
            >
              {compareMutation.isPending ? "Calculando…" : "Comparar ofertas"}
            </button>
          </div>
        </form>
      </Card>

      {/* Resultado comparativo */}
      {result && (
        <div className="space-y-4">
          <Alert tone="info">{result.disclaimer}</Alert>

          <div className="card overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
                <tr>
                  <th className="px-4 py-3 font-medium">Institución</th>
                  <th className="px-4 py-3 font-medium text-right">
                    Tasa periódica
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Tasa anual
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    CAT estimado
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Cuota periódica
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Intereses
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Comisión
                  </th>
                  <th className="px-4 py-3 font-medium text-right">
                    Costo total
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {[result.own_offer, ...result.bank_offers].map((row) => (
                  <tr
                    key={row.institution}
                    className={
                      row.is_own_offer
                        ? "bg-brand-50/70 font-medium"
                        : "hover:bg-slate-50"
                    }
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-900">{row.institution}</span>
                        {row.is_own_offer && (
                          <Badge className="bg-brand-100 text-brand-800">
                            Tu oferta
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="tabular px-4 py-3 text-right text-slate-700">
                      {formatRate(row.periodic_rate)}
                    </td>
                    <td className="tabular px-4 py-3 text-right text-slate-700">
                      {formatRate(row.annual_rate)}
                    </td>
                    <td className="tabular px-4 py-3 text-right font-semibold text-slate-900">
                      {row.estimated_cat} %
                    </td>
                    <td className="tabular px-4 py-3 text-right text-slate-700">
                      {formatCurrency(row.installment_amount)}
                    </td>
                    <td className="tabular px-4 py-3 text-right text-slate-700">
                      {formatCurrency(row.total_interest)}
                    </td>
                    <td className="tabular px-4 py-3 text-right text-slate-700">
                      {formatCurrency(row.opening_fee)}
                    </td>
                    <td className="tabular px-4 py-3 text-right font-semibold text-slate-900">
                      {formatCurrency(row.total_cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Catálogo de instituciones bancarias */}
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Catálogo de instituciones de referencia
            </h2>
            <p className="text-xs text-slate-500">
              Marca las instituciones específicas que quieras incluir o deja
              todas sin marcar para comparar contra todas las activas.
            </p>
          </div>
        </div>

        {banksQuery.isLoading && <Spinner />}
        {banksQuery.isError && (
          <ErrorState
            message="No se pudo cargar el catálogo bancario."
            onRetry={() => banksQuery.refetch()}
          />
        )}
        {banksQuery.data && banksQuery.data.length === 0 && (
          <EmptyState
            title="Sin instituciones en el catálogo"
            description="El administrador puede registrar instituciones bancarias de referencia."
          />
        )}

        {banksQuery.data && banksQuery.data.length > 0 && (
          <div className="divide-y divide-slate-100">
            {banksQuery.data.map((bank) => (
              <div
                key={bank.id}
                className="flex flex-wrap items-center justify-between gap-3 py-2.5 text-sm"
              >
                <label className="flex items-center gap-2.5">
                  <input
                    type="checkbox"
                    disabled={!bank.is_active}
                    checked={selectedBankIds.includes(bank.id)}
                    onChange={() => toggleSelectedBank(bank.id)}
                  />
                  <span className="font-medium text-slate-900">
                    {bank.name}
                  </span>
                  {!bank.is_active && (
                    <Badge className="bg-slate-100 text-slate-600">
                      Inactivo
                    </Badge>
                  )}
                </label>

                <div className="flex items-center gap-4 text-xs text-slate-600">
                  <span className="tabular">
                    Tasa anual: {formatRate(bank.annual_rate)}
                  </span>
                  <span className="tabular">
                    Comisión: {formatCurrency(bank.opening_fee)}
                  </span>
                  {isAdmin && (
                    <button
                      type="button"
                      className="btn-secondary px-2 py-1 text-xs"
                      disabled={toggleBankStatusMutation.isPending}
                      onClick={() => toggleBankStatusMutation.mutate(bank)}
                    >
                      {bank.is_active ? "Desactivar" : "Activar"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

