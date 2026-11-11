/** Bitácora de auditoría: consulta y filtros. */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { AUDIT_ACTION_LABELS, listAudit } from "@/api/dashboard";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Spinner,
} from "@/components/ui";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 50;

export function AuditPage() {
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);

  const entries = useQuery({
    queryKey: ["audit", { action, entity, page }],
    queryFn: () =>
      listAudit({
        action: action || undefined,
        entity: entity || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: (previous) => previous,
  });

  return (
    <div>
      <PageHeader
        title="Auditoría"
        description="Registro de todas las operaciones sensibles. No se puede modificar ni borrar."
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          className="input max-w-[240px]"
          value={action}
          onChange={(event) => {
            setAction(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Todas las acciones</option>
          {Object.entries(AUDIT_ACTION_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>

        <select
          className="input max-w-[180px]"
          value={entity}
          onChange={(event) => {
            setEntity(event.target.value);
            setPage(1);
          }}
        >
          <option value="">Todas las entidades</option>
          <option value="client">Cliente</option>
          <option value="loan">Préstamo</option>
          <option value="payment">Pago</option>
          <option value="collection_route">Ruta</option>
        </select>
      </div>

      {entries.isLoading && <Spinner />}

      {entries.isError && (
        <ErrorState
          message={
            entries.error instanceof Error
              ? entries.error.message
              : "No se pudo cargar la bitácora."
          }
          onRetry={() => entries.refetch()}
        />
      )}

      {entries.data && entries.data.items.length === 0 && (
        <EmptyState
          title="Sin movimientos"
          description="Las operaciones aparecerán aquí conforme se realicen."
        />
      )}

      {entries.data && entries.data.items.length > 0 && (
        <div className="card divide-y divide-slate-100">
          {entries.data.items.map((entry) => (
            <div key={entry.id} className="p-4">
              <button
                type="button"
                className="flex w-full flex-wrap items-start justify-between gap-2 text-left"
                onClick={() =>
                  setExpanded((current) => (current === entry.id ? null : entry.id))
                }
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-900">
                    {AUDIT_ACTION_LABELS[entry.action] ?? entry.action}
                  </p>
                  <p className="tabular text-xs text-slate-500">
                    {formatDateTime(entry.created_at)} ·{" "}
                    {entry.ip_address ?? "sin IP"}
                  </p>
                </div>
                <Badge className="bg-slate-100 text-slate-600">
                  {entry.entity}
                </Badge>
              </button>

              {expanded === entry.id && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="mb-1 text-xs font-medium text-slate-500 uppercase">
                      Antes
                    </p>
                    <pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
                      {entry.before
                        ? JSON.stringify(entry.before, null, 2)
                        : "—"}
                    </pre>
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium text-slate-500 uppercase">
                      Después
                    </p>
                    <pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
                      {entry.after ? JSON.stringify(entry.after, null, 2) : "—"}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {entries.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={entries.data.total}
          onChange={setPage}
        />
      )}
    </div>
  );
}
