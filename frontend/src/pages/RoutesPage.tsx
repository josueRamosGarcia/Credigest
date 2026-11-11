/** Rutas de cobro: listado y armado del día. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  ROUTE_STATUS_LABELS,
  VISIT_STATUS_LABELS,
  VISIT_STATUS_STYLES,
  createRoute,
  listRoutes,
} from "@/api/routes";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { formatDate, todayIso } from "@/lib/format";

export function RoutesPage() {
  const queryClient = useQueryClient();
  const [zone, setZone] = useState("");
  const [routeDate, setRouteDate] = useState(todayIso());
  const [showForm, setShowForm] = useState(false);

  const routes = useQuery({
    queryKey: ["routes", { routeDate }],
    queryFn: () => listRoutes({ route_date: routeDate, page_size: 50 }),
  });

  const creation = useMutation({
    mutationFn: createRoute,
    onSuccess: (route) => {
      queryClient.invalidateQueries({ queryKey: ["routes"] });
      setShowForm(false);
      setZone("");
      return route;
    },
  });

  return (
    <div>
      <PageHeader
        title="Rutas de cobro"
        description="Lista de visitas del día por zona."
        actions={
          <button
            type="button"
            className="btn-primary"
            onClick={() => setShowForm((value) => !value)}
          >
            Generar ruta
          </button>
        }
      />

      {showForm && (
        <Card className="mb-6">
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
            Nueva ruta
          </h2>

          {creation.isError && (
            <div className="mb-3">
              <Alert tone="error">
                {creation.error instanceof Error
                  ? creation.error.message
                  : "No se pudo generar la ruta."}
              </Alert>
            </div>
          )}

          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="label" htmlFor="zone">
                Zona
              </label>
              <input
                id="zone"
                className="input"
                placeholder="Centro"
                value={zone}
                onChange={(event) => setZone(event.target.value)}
              />
            </div>

            <div>
              <label className="label" htmlFor="route_date">
                Fecha
              </label>
              <input
                id="route_date"
                type="date"
                className="input"
                value={routeDate}
                onChange={(event) => setRouteDate(event.target.value)}
              />
            </div>

            <button
              type="button"
              className="btn-primary"
              disabled={!zone.trim() || creation.isPending}
              onClick={() =>
                creation.mutate({ zone: zone.trim(), route_date: routeDate })
              }
            >
              {creation.isPending ? "Generando…" : "Generar"}
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowForm(false)}
            >
              Cancelar
            </button>
          </div>

          <p className="mt-3 text-xs text-slate-500">
            Se incluyen las cuotas pendientes o vencidas de clientes activos en esa
            zona, con vencimiento hasta la fecha indicada.
          </p>
        </Card>
      )}

      <div className="mb-4 max-w-xs">
        <label className="label" htmlFor="filter_date">
          Ver rutas del día
        </label>
        <input
          id="filter_date"
          type="date"
          className="input"
          value={routeDate}
          onChange={(event) => setRouteDate(event.target.value)}
        />
      </div>

      {routes.isLoading && <Spinner />}

      {routes.isError && (
        <ErrorState
          message={
            routes.error instanceof Error
              ? routes.error.message
              : "No se pudieron cargar las rutas."
          }
          onRetry={() => routes.refetch()}
        />
      )}

      {routes.data && routes.data.items.length === 0 && (
        <EmptyState
          title="Sin rutas para esa fecha"
          description="Genera una ruta indicando la zona a cobrar."
        />
      )}

      {routes.data && routes.data.items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {routes.data.items.map((route) => (
            <Link
              key={route.id}
              to={`/rutas/${route.id}`}
              className="card block p-5 transition-shadow hover:shadow-md"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold text-slate-900">{route.zone}</p>
                  <p className="text-sm text-slate-600">
                    {formatDate(route.route_date)}
                  </p>
                </div>
                <Badge
                  className={
                    route.status === "cerrada"
                      ? "bg-slate-100 text-slate-600"
                      : "bg-brand-100 text-brand-800"
                  }
                >
                  {ROUTE_STATUS_LABELS[route.status]}
                </Badge>
              </div>

              <p className="mt-3 text-sm text-slate-600">
                {route.pending_items} de {route.total_items} pendientes
              </p>

              <div className="mt-3 flex gap-2">
                <Badge className={VISIT_STATUS_STYLES.pendiente}>
                  {VISIT_STATUS_LABELS.pendiente}: {route.pending_items}
                </Badge>
                <Badge className={VISIT_STATUS_STYLES.pagado}>
                  {VISIT_STATUS_LABELS.pagado}:{" "}
                  {route.total_items - route.pending_items}
                </Badge>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
