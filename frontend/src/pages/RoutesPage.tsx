/** Rutas de cobro: listado y armado del día. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ROLE_LABELS } from "@/api/auth";
import {
  ROUTE_STATUS_LABELS,
  VISIT_STATUS_LABELS,
  VISIT_STATUS_STYLES,
  createRoute,
  listRouteCollectors,
  listRouteZones,
  listRoutes,
} from "@/api/routes";
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
import { formatDate, todayIso } from "@/lib/format";
import { SUGGESTED_TORREON_ZONES } from "@/lib/geo";

const CUSTOM_ZONE_VALUE = "__custom__";

export function RoutesPage() {
  const { user } = useAuth();
  const canCreateRoute = user?.role !== "cobrador";
  const queryClient = useQueryClient();
  const [zoneDraft, setZoneDraft] = useState<string | null>(null);
  const [customZone, setCustomZone] = useState("");
  const [routeDate, setRouteDate] = useState(todayIso());
  const [collectorDraft, setCollectorDraft] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const routes = useQuery({
    queryKey: ["routes", { routeDate }],
    queryFn: () => listRoutes({ route_date: routeDate, page_size: 50 }),
  });

  const zones = useQuery({
    queryKey: ["routes", "zones", routeDate],
    queryFn: () => listRouteZones(routeDate),
    enabled: canCreateRoute,
  });

  const collectors = useQuery({
    queryKey: ["routes", "collectors"],
    queryFn: listRouteCollectors,
    enabled: canCreateRoute,
  });

  const defaultZone =
    zones.data?.[0]?.zone ?? SUGGESTED_TORREON_ZONES[0] ?? "";
  const selectedZone = zoneDraft ?? defaultZone;
  const resolvedZone =
    selectedZone === CUSTOM_ZONE_VALUE
      ? customZone.trim()
      : selectedZone.trim();

  const defaultCollectorId =
    collectors.data?.find((item) => item.role === "cobrador")?.id ??
    user?.id ??
    "";
  const selectedCollectorId = collectorDraft ?? defaultCollectorId;

  const creation = useMutation({
    mutationFn: createRoute,
    onSuccess: (route) => {
      void queryClient.invalidateQueries({ queryKey: ["routes"] });
      setShowForm(false);
      setZoneDraft(null);
      setCustomZone("");
      setCollectorDraft(null);
      return route;
    },
  });

  return (
    <div>
      <PageHeader
        title="Rutas de cobro"
        description="Lista de visitas del día por zona."
        actions={
          canCreateRoute ? (
            <button
              type="button"
              className="btn-primary"
              onClick={() => setShowForm((value) => !value)}
            >
              Generar ruta
            </button>
          ) : undefined
        }
      />

      {canCreateRoute && showForm && (
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
              <select
                id="zone"
                className="input min-w-[240px]"
                value={selectedZone}
                onChange={(event) => setZoneDraft(event.target.value)}
              >
                {zones.data && zones.data.length > 0 ? (
                  zones.data.map((item) => (
                    <option key={item.zone} value={item.zone}>
                      {item.zone} · {item.pending_installments}{" "}
                      {item.pending_installments === 1
                        ? "cuota pendiente"
                        : "cuotas pendientes"}{" "}
                      ({item.active_clients}{" "}
                      {item.active_clients === 1 ? "cliente" : "clientes"})
                    </option>
                  ))
                ) : (
                  SUGGESTED_TORREON_ZONES.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))
                )}
                <option value={CUSTOM_ZONE_VALUE}>+ Escribir otra zona…</option>
              </select>
            </div>

            {selectedZone === CUSTOM_ZONE_VALUE && (
              <div>
                <label className="label" htmlFor="custom_zone">
                  Nombre de la zona
                </label>
                <input
                  id="custom_zone"
                  className="input"
                  placeholder="Ej. Viñedos"
                  value={customZone}
                  onChange={(event) => setCustomZone(event.target.value)}
                />
              </div>
            )}

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

            <div>
              <label className="label" htmlFor="cobrador_id">
                Cobrador asignado
              </label>
              <select
                id="cobrador_id"
                className="input min-w-[210px]"
                value={selectedCollectorId}
                onChange={(event) => setCollectorDraft(event.target.value)}
              >
                {collectors.data && collectors.data.length > 0 ? (
                  collectors.data.map((collector) => (
                    <option key={collector.id} value={collector.id}>
                      {collector.full_name} ({ROLE_LABELS[collector.role]})
                    </option>
                  ))
                ) : (
                  <option value={user?.id ?? ""}>
                    {user?.full_name ?? "Usuario actual"}
                  </option>
                )}
              </select>
            </div>

            <button
              type="button"
              className="btn-primary"
              disabled={!resolvedZone || creation.isPending}
              onClick={() =>
                creation.mutate({
                  zone: resolvedZone,
                  route_date: routeDate,
                  cobrador_id: selectedCollectorId || undefined,
                })
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
          description={
            canCreateRoute
              ? "Genera una ruta indicando la zona a cobrar."
              : "No tienes rutas asignadas para esa fecha."
          }
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
                    {route.cobrador_name ? ` · ${route.cobrador_name}` : ""}
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
                  {VISIT_STATUS_LABELS.pagado}: {route.paid_items ?? 0}
                </Badge>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
