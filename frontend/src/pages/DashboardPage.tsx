/** Dashboard financiero: indicadores, antigüedad y cobranza. */

import { useQuery } from "@tanstack/react-query";

import {
  AGING_LABELS,
  getAging,
  getCollections,
  getSummary,
} from "@/api/dashboard";
import { Card, EmptyState, ErrorState, PageHeader, Spinner, StatCard } from "@/components/ui";
import { formatCurrency, formatDate } from "@/lib/format";

/** Barra horizontal simple para el aging. */
function AgingBar({
  label,
  amount,
  total,
  tone,
}: {
  label: string;
  amount: string;
  total: number;
  tone: string;
}) {
  const numeric = Number(amount);
  const percent = total > 0 ? (numeric / total) * 100 : 0;

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="tabular font-medium text-slate-900">
          {formatCurrency(amount)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${tone}`}
          style={{ width: `${Math.min(100, percent)}%` }}
        />
      </div>
    </div>
  );
}

export function DashboardPage() {
  const summary = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => getSummary(),
  });

  const aging = useQuery({
    queryKey: ["dashboard", "aging"],
    queryFn: getAging,
  });

  const collections = useQuery({
    queryKey: ["dashboard", "collections"],
    queryFn: () => getCollections(),
  });

  if (summary.isLoading) return <Spinner label="Calculando indicadores…" />;

  if (summary.isError) {
    return (
      <ErrorState
        message={
          summary.error instanceof Error
            ? summary.error.message
            : "No se pudo cargar el dashboard."
        }
        onRetry={() => summary.refetch()}
      />
    );
  }

  const data = summary.data!;
  const morosidad = Number(data.indice_morosidad);

  const agingTotal = (aging.data?.buckets ?? []).reduce(
    (sum, bucket) => sum + Number(bucket.amount),
    0,
  );

  return (
    <div>
      <PageHeader
        title="Dashboard financiero"
        description="Estado de la cartera y resultado del negocio."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Capital prestado"
          value={formatCurrency(data.capital_prestado)}
          hint="Colocación acumulada"
        />
        <StatCard
          label="Capital recuperado"
          value={formatCurrency(data.capital_recuperado)}
          hint="Solo la parte de capital cobrada"
          tone="good"
        />
        <StatCard
          label="Por cobrar"
          value={formatCurrency(data.capital_proyectado)}
          hint="Saldo pendiente de préstamos vigentes"
        />
        <StatCard
          label="Utilidad generada"
          value={formatCurrency(data.utilidad_generada)}
          hint={`Intereses ${formatCurrency(data.intereses_generados)} · Mora ${formatCurrency(data.mora_cobrada)}`}
          tone="good"
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Cartera total"
          value={formatCurrency(data.cartera_total)}
        />
        <StatCard
          label="Cartera vencida"
          value={formatCurrency(data.cartera_vencida)}
          tone={Number(data.cartera_vencida) > 0 ? "bad" : "neutral"}
        />
        <StatCard
          label="Índice de morosidad"
          value={`${data.indice_morosidad} %`}
          tone={morosidad > 30 ? "bad" : morosidad > 10 ? "warn" : "good"}
        />
        <StatCard
          label="Préstamos"
          value={String(
            data.prestamos_activos + data.prestamos_pagados + data.prestamos_vencidos,
          )}
          hint={`${data.prestamos_activos} activos · ${data.prestamos_vencidos} vencidos · ${data.prestamos_pagados} pagados`}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
            Antigüedad de la cartera
          </h2>

          {aging.isLoading && <Spinner label="Cargando…" />}

          {aging.data && (
            <div className="space-y-4">
              {aging.data.buckets.map((bucket) => (
                <AgingBar
                  key={bucket.label}
                  label={`${AGING_LABELS[bucket.label] ?? bucket.label} (${bucket.installments})`}
                  amount={bucket.amount}
                  total={agingTotal}
                  tone={
                    bucket.label === "al_dia"
                      ? "bg-green-500"
                      : bucket.label === "mas_90"
                        ? "bg-red-600"
                        : "bg-amber-500"
                  }
                />
              ))}

              <div className="flex justify-between border-t border-slate-200 pt-3 text-sm">
                <span className="font-medium text-slate-700">Total vencido</span>
                <span className="tabular font-semibold text-red-700">
                  {formatCurrency(aging.data.total_vencido)}
                </span>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
            Cobranza reciente
          </h2>

          {collections.isLoading && <Spinner label="Cargando…" />}

          {collections.data && collections.data.length === 0 && (
            <EmptyState
              title="Sin cobros registrados"
              description="Los pagos aparecerán aquí en cuanto se registren."
            />
          )}

          {collections.data && collections.data.length > 0 && (
            <ul className="divide-y divide-slate-100">
              {collections.data
                .slice()
                .reverse()
                .slice(0, 10)
                .map((row) => (
                  <li
                    key={row.day}
                    className="flex items-center justify-between py-2 text-sm"
                  >
                    <span className="text-slate-600">{formatDate(row.day)}</span>
                    <span className="tabular font-medium text-slate-900">
                      {formatCurrency(row.amount)}
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
