/**
 * Detalle de la ruta: la pantalla que usa el cobrador en campo.
 *
 * Diseñada para móvil: tarjetas grandes, botones que se puedan tocar con el
 * pulgar y el teléfono del cliente como enlace directo para llamar.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { registerPayment } from "@/api/payments";
import {
  ROUTE_STATUS_LABELS,
  VISIT_STATUS_STYLES,
  closeRoute,
  getRoute,
  updateRouteItem,
} from "@/api/routes";
import type { VisitStatus } from "@/api/types";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { formatCurrency, formatDate } from "@/lib/format";

export function RouteDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [payingItem, setPayingItem] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const route = useQuery({
    queryKey: ["routes", id],
    queryFn: () => getRoute(id),
    enabled: Boolean(id),
  });

  const markItem = useMutation({
    mutationFn: ({
      itemId,
      status,
    }: {
      itemId: string;
      status: VisitStatus;
    }) => updateRouteItem(id, itemId, { visit_status: status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["routes"] }),
  });

  const pay = useMutation({
    mutationFn: registerPayment,
    onSuccess: () => {
      setPayingItem(null);
      setAmount("");
      queryClient.invalidateQueries({ queryKey: ["routes"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (exc: unknown) => {
      setError(exc instanceof Error ? exc.message : "No se pudo registrar.");
    },
  });

  const close = useMutation({
    mutationFn: () => closeRoute(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["routes"] }),
  });

  if (route.isLoading) return <Spinner />;

  if (route.isError || !route.data) {
    return (
      <ErrorState
        message={
          route.error instanceof Error
            ? route.error.message
            : "No se pudo cargar la ruta."
        }
        onRetry={() => route.refetch()}
      />
    );
  }

  const data = route.data;
  const isClosed = data.status === "cerrada";
  const pending = data.items.filter((item) => item.visit_status === "pendiente");

  return (
    <div>
      <PageHeader
        title={`Ruta ${data.zone}`}
        description={`${formatDate(data.route_date)} · ${ROUTE_STATUS_LABELS[data.status]}`}
        actions={
          <>
            <Link to="/rutas" className="btn-secondary">
              Volver
            </Link>
            {!isClosed && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => close.mutate()}
                disabled={close.isPending}
              >
                {close.isPending ? "Cerrando…" : "Cerrar ruta"}
              </button>
            )}
          </>
        }
      />

      {error && (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Card>
          <p className="text-xs text-slate-500 uppercase">Total de visitas</p>
          <p className="mt-1 text-2xl font-semibold">{data.total_items}</p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 uppercase">Pendientes</p>
          <p className="mt-1 text-2xl font-semibold text-amber-700">
            {data.pending_items}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 uppercase">Por cobrar hoy</p>
          <p className="tabular mt-1 text-2xl font-semibold">
            {formatCurrency(
              pending
                .reduce((sum, item) => sum + Number(item.total_due), 0)
                .toFixed(2),
            )}
          </p>
        </Card>
      </div>

      {data.items.length === 0 && (
        <EmptyState
          title="Ruta sin visitas"
          description="No había cuotas pendientes en esa zona para esa fecha."
        />
      )}

      <div className="space-y-3">
        {data.items.map((item) => (
          <Card key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="tabular text-xs font-medium text-slate-400">
                    #{item.order_index}
                  </span>
                  <p className="font-semibold text-slate-900">
                    {item.client_name}
                  </p>
                  <Badge className={VISIT_STATUS_STYLES[item.visit_status]}>
                    {item.visit_status === "pendiente"
                      ? "Pendiente"
                      : item.visit_status === "pagado"
                        ? "Pagado"
                        : "No pagado"}
                  </Badge>
                </div>

                <p className="mt-1 text-sm text-slate-600">{item.client_address}</p>
                <p className="tabular mt-0.5 text-sm text-slate-500">
                  Cuota {item.installment_number} · vence{" "}
                  {formatDate(item.due_date)}
                </p>
              </div>

              <div className="text-right">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatCurrency(item.total_due)}
                </p>
                {Number(item.late_fee) > 0 && (
                  <p className="tabular text-xs text-red-600">
                    incluye mora {formatCurrency(item.late_fee)}
                  </p>
                )}
                <a
                  href={`tel:${item.client_phone}`}
                  className="mt-1 inline-block text-xs text-brand-700 hover:underline"
                >
                  Llamar {item.client_phone}
                </a>
              </div>
            </div>

            {!isClosed && (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                <button
                  type="button"
                  className="btn-primary px-3 py-1.5 text-xs"
                  onClick={() => {
                    setPayingItem(item.id);
                    setAmount(item.total_due);
                    setError(null);
                  }}
                >
                  Cobrar
                </button>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-xs"
                  onClick={() =>
                    markItem.mutate({ itemId: item.id, status: "no_pagado" })
                  }
                  disabled={markItem.isPending}
                >
                  No pagó
                </button>
              </div>
            )}

            {payingItem === item.id && (
              <div className="mt-3 rounded-lg border border-brand-200 bg-brand-50 p-3">
                <label className="label" htmlFor={`amount-${item.id}`}>
                  Monto recibido
                </label>
                <div className="flex flex-wrap items-end gap-2">
                  <input
                    id={`amount-${item.id}`}
                    type="number"
                    step="0.01"
                    className="input tabular max-w-[160px]"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                  />
                  <button
                    type="button"
                    className="btn-primary px-3 py-2 text-xs"
                    disabled={pay.isPending || !amount}
                    onClick={() => {
                      const numeric = Number(amount);
                      if (!numeric || numeric <= 0) {
                        setError("El monto debe ser mayor que cero.");
                        return;
                      }
                      pay.mutate({
                        loan_id: item.loan_id,
                        amount: numeric,
                        method: "efectivo",
                      });
                    }}
                  >
                    {pay.isPending ? "Registrando…" : "Confirmar"}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary px-3 py-2 text-xs"
                    onClick={() => {
                      setPayingItem(null);
                      setAmount("");
                    }}
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
