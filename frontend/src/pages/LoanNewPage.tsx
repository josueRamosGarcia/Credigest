/**
 * Cotizador de préstamos.
 *
 * Muestra el resultado en vivo mientras se captura, y permite aprobar el
 * préstamo cuando el cliente acepta. La simulación no guarda nada en el
 * servidor; solo la aprobación crea el préstamo.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { listClients } from "@/api/clients";
import {
  PERIOD_LABELS,
  SCHEME_LABELS,
  createLoan,
  simulate,
  type LoanScheme,
  type RatePeriod,
  type Simulation,
} from "@/api/loans";
import { Alert, Badge, Card, PageHeader, Spinner } from "@/components/ui";
import { formatCurrency, formatDate, formatRate, todayIso } from "@/lib/format";

const schema = z.object({
  client_id: z.string().min(1, "Selecciona un cliente"),
  principal: z.coerce.number().positive("El monto debe ser mayor que cero"),
  interest_percent: z.coerce
    .number()
    .min(0, "La tasa no puede ser negativa")
    .max(100, "La tasa parece demasiado alta"),
  rate_period: z.enum(["semanal", "quincenal", "mensual"]),
  scheme: z.enum(["simple", "saldo_insoluto", "cuota_fija"]),
  term_periods: z.coerce
    .number()
    .int("Debe ser un número entero")
    .min(1, "Al menos un pago")
    .max(520, "Máximo 520 pagos"),
  start_date: z.string().min(1, "Indica la fecha de inicio"),
});

// z.coerce acepta texto del input y devuelve numero.
type FormInput = z.input<typeof schema>;
type FormOutput = z.output<typeof schema>;

export function LoanNewPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const preselectedClient = params.get("cliente") ?? "";

  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);

  const clients = useQuery({
    queryKey: ["clients", { page_size: 100 }],
    queryFn: () => listClients({ page_size: 100, status: "activo" }),
  });

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(schema),
    defaultValues: {
      client_id: preselectedClient,
      principal: 10000,
      interest_percent: 5,
      rate_period: "semanal",
      scheme: "simple",
      term_periods: 12,
      start_date: todayIso(),
    },
  });

  const values = useWatch({ control });

  const simulationMutation = useMutation({
    mutationFn: simulate,
  });

  // Simula automáticamente cuando cambian las condiciones, con una pequeña
  // espera para no disparar una petición por cada tecla.
  useEffect(() => {
    const timer = setTimeout(() => {
      const principal = Number(values.principal);
      const rate = Number(values.interest_percent);
      const periods = Number(values.term_periods);

      if (!principal || principal <= 0) return;
      if (Number.isNaN(rate) || rate < 0) return;
      if (!periods || periods < 1 || periods > 520) return;
      if (!values.start_date) return;

      setSimulationError(null);
      simulationMutation
        .mutateAsync({
          principal,
          interest_rate: rate / 100,
          rate_period: values.rate_period as RatePeriod,
          scheme: values.scheme as LoanScheme,
          term_periods: periods,
          start_date: values.start_date,
        })
        .then(setSimulation)
        .catch((exc: unknown) => {
          setSimulation(null);
          setSimulationError(
            exc instanceof Error ? exc.message : "No se pudo simular.",
          );
        });
    }, 400);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    values.principal,
    values.interest_percent,
    values.rate_period,
    values.scheme,
    values.term_periods,
    values.start_date,
  ]);

  const approval = useMutation({
    mutationFn: createLoan,
    onSuccess: (loan) => navigate(`/prestamos/${loan.id}`),
  });

  const onSubmit = (form: FormOutput) => {
    approval.mutate({
      client_id: form.client_id,
      principal: form.principal,
      interest_rate: form.interest_percent / 100,
      rate_period: form.rate_period,
      scheme: form.scheme,
      term_periods: form.term_periods,
      start_date: form.start_date,
    });
  };

  return (
    <div>
      <PageHeader
        title="Nuevo préstamo"
        description="Simula las condiciones y apruébalas cuando el cliente acepte."
        actions={
          <Link to="/prestamos" className="btn-secondary">
            Cancelar
          </Link>
        }
      />

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        {approval.isError && (
          <div className="mb-4">
            <Alert tone="error">
              {approval.error instanceof Error
                ? approval.error.message
                : "No se pudo aprobar el préstamo."}
            </Alert>
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="lg:col-span-2">
            <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
              Condiciones
            </h2>

            <div className="space-y-4">
              <div>
                <label className="label" htmlFor="client_id">
                  Cliente
                </label>
                <select id="client_id" className="input" {...register("client_id")}>
                  <option value="">Selecciona un cliente</option>
                  {clients.data?.items.map((client) => (
                    <option key={client.id} value={client.id}>
                      {client.full_name} · {client.curp}
                    </option>
                  ))}
                </select>
                {errors.client_id && (
                  <p className="field-error">{errors.client_id.message}</p>
                )}
              </div>

              <div>
                <label className="label" htmlFor="principal">
                  Monto a prestar
                </label>
                <input
                  id="principal"
                  type="number"
                  step="0.01"
                  className="input tabular"
                  {...register("principal")}
                />
                {errors.principal && (
                  <p className="field-error">{errors.principal.message}</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label" htmlFor="interest_percent">
                    Tasa por periodo (%)
                  </label>
                  <input
                    id="interest_percent"
                    type="number"
                    step="0.01"
                    className="input tabular"
                    {...register("interest_percent")}
                  />
                  {errors.interest_percent && (
                    <p className="field-error">{errors.interest_percent.message}</p>
                  )}
                </div>

                <div>
                  <label className="label" htmlFor="rate_period">
                    Frecuencia
                  </label>
                  <select id="rate_period" className="input" {...register("rate_period")}>
                    {(Object.keys(PERIOD_LABELS) as RatePeriod[]).map((period) => (
                      <option key={period} value={period}>
                        {PERIOD_LABELS[period]}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="label" htmlFor="scheme">
                  Esquema de cálculo
                </label>
                <select id="scheme" className="input" {...register("scheme")}>
                  {(Object.keys(SCHEME_LABELS) as LoanScheme[]).map((scheme) => (
                    <option key={scheme} value={scheme}>
                      {SCHEME_LABELS[scheme]}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label" htmlFor="term_periods">
                    Número de pagos
                  </label>
                  <input
                    id="term_periods"
                    type="number"
                    className="input tabular"
                    {...register("term_periods")}
                  />
                  {errors.term_periods && (
                    <p className="field-error">{errors.term_periods.message}</p>
                  )}
                </div>

                <div>
                  <label className="label" htmlFor="start_date">
                    Fecha de inicio
                  </label>
                  <input
                    id="start_date"
                    type="date"
                    className="input"
                    {...register("start_date")}
                  />
                </div>
              </div>
            </div>
          </Card>

          <div className="space-y-4 lg:col-span-3">
            {simulationError && <Alert tone="error">{simulationError}</Alert>}

            {!simulation && !simulationError && (
              <Card>
                <Spinner label="Calculando…" />
              </Card>
            )}

            {simulation && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-brand-200 bg-brand-50 p-4">
                    <p className="text-xs font-medium text-brand-700 uppercase">
                      Cuota {simulation.installment_amount === simulation.installment_amount_last
                        ? ""
                        : "inicial"}
                    </p>
                    <p className="tabular mt-1 text-2xl font-semibold text-brand-900">
                      {formatCurrency(simulation.installment_amount)}
                    </p>
                    {simulation.installment_amount !==
                      simulation.installment_amount_last && (
                      <p className="tabular mt-1 text-xs text-brand-700">
                        Última: {formatCurrency(simulation.installment_amount_last)}
                      </p>
                    )}
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <p className="text-xs font-medium text-slate-500 uppercase">
                      Total a pagar
                    </p>
                    <p className="tabular mt-1 text-2xl font-semibold text-slate-900">
                      {formatCurrency(simulation.total_amount)}
                    </p>
                    <p className="tabular mt-1 text-xs text-slate-500">
                      Interés: {formatCurrency(simulation.total_interest)}
                    </p>
                  </div>
                </div>

                <Card>
                  <div className="grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                      <p className="text-xs text-slate-500">Ganancia estimada</p>
                      <p className="tabular font-medium text-green-700">
                        {formatCurrency(simulation.estimated_profit)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Último pago</p>
                      <p className="tabular font-medium">
                        {formatDate(simulation.end_date)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Tasa anual equivalente</p>
                      <p className="tabular font-medium">
                        {formatRate(simulation.annual_equivalent_rate)}
                      </p>
                    </div>
                  </div>
                </Card>

                <Card>
                  <h2 className="mb-3 text-sm font-semibold tracking-wide text-slate-700 uppercase">
                    Tabla de amortización
                  </h2>

                  <div className="max-h-80 overflow-y-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="sticky top-0 bg-white text-slate-500 uppercase">
                        <tr>
                          <th className="py-2 pr-3 font-medium">#</th>
                          <th className="py-2 pr-3 font-medium">Vence</th>
                          <th className="py-2 pr-3 font-medium">Cuota</th>
                          <th className="py-2 pr-3 font-medium">Interés</th>
                          <th className="py-2 pr-3 font-medium">Capital</th>
                          <th className="py-2 pr-3 font-medium">Saldo</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {simulation.schedule.map((row) => (
                          <tr key={row.number}>
                            <td className="tabular py-2 pr-3 text-slate-500">
                              {row.number}
                            </td>
                            <td className="tabular py-2 pr-3">
                              {formatDate(row.due_date)}
                            </td>
                            <td className="tabular py-2 pr-3">
                              {formatCurrency(row.amount)}
                            </td>
                            <td className="tabular py-2 pr-3 text-slate-600">
                              {formatCurrency(row.interest_part)}
                            </td>
                            <td className="tabular py-2 pr-3 text-slate-600">
                              {formatCurrency(row.principal_part)}
                            </td>
                            <td className="tabular py-2 pr-3 text-slate-600">
                              {formatCurrency(row.balance)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <Badge className="bg-slate-100 text-slate-600">
                    La simulación no guarda nada
                  </Badge>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={approval.isPending}
                  >
                    {approval.isPending
                      ? "Aprobando…"
                      : "Aprobar y generar préstamo"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
