/** Detalle de un cliente: datos, referencias, préstamos y documentos. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import {
  DOCUMENT_LABELS,
  changeClientStatus,
  formatBytes,
  getClient,
  listDocuments,
} from "@/api/clients";
import {
  LOAN_STATUS_LABELS,
  LOAN_STATUS_STYLES,
  listLoans,
  PERIOD_LABELS,
} from "@/api/loans";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { formatCurrency, formatDate, formatRate } from "@/lib/format";

export function ClientDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();

  const client = useQuery({
    queryKey: ["clients", id],
    queryFn: () => getClient(id),
    enabled: Boolean(id),
  });

  const loans = useQuery({
    queryKey: ["loans", { client_id: id }],
    queryFn: () => listLoans({ client_id: id, page_size: 50 }),
    enabled: Boolean(id),
  });

  const documents = useQuery({
    queryKey: ["clients", id, "documents"],
    queryFn: () => listDocuments(id),
    enabled: Boolean(id),
  });

  const toggleStatus = useMutation({
    mutationFn: (status: "activo" | "inactivo") => changeClientStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });

  if (client.isLoading) return <Spinner />;

  if (client.isError || !client.data) {
    return (
      <ErrorState
        message={
          client.error instanceof Error
            ? client.error.message
            : "No se pudo cargar el cliente."
        }
        onRetry={() => client.refetch()}
      />
    );
  }

  const data = client.data;
  const isActive = data.status === "activo";

  return (
    <div>
      <PageHeader
        title={data.full_name}
        description={`CURP ${data.curp}`}
        actions={
          <>
            <Link to="/clientes" className="btn-secondary">
              Volver
            </Link>
            <button
              type="button"
              className={isActive ? "btn-secondary" : "btn-primary"}
              onClick={() => toggleStatus.mutate(isActive ? "inactivo" : "activo")}
              disabled={toggleStatus.isPending}
            >
              {isActive ? "Desactivar" : "Activar"}
            </button>
            {isActive && (
              <Link
                to={`/prestamos/nuevo?cliente=${data.id}`}
                className="btn-primary"
              >
                Nuevo préstamo
              </Link>
            )}
          </>
        }
      />

      {toggleStatus.isError && (
        <p className="field-error mb-4">
          {toggleStatus.error instanceof Error
            ? toggleStatus.error.message
            : "No se pudo cambiar el estado."}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
            Datos generales
          </h2>

          <dl className="space-y-3 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Estado</dt>
              <dd className="mt-0.5">
                <Badge
                  className={
                    isActive
                      ? "bg-green-100 text-green-800"
                      : "bg-slate-100 text-slate-600"
                  }
                >
                  {isActive ? "Activo" : "Inactivo"}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Teléfono</dt>
              <dd className="tabular mt-0.5">{data.phone}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Dirección</dt>
              <dd className="mt-0.5">{data.address}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Zona</dt>
              <dd className="mt-0.5">{data.zone ?? "Sin asignar"}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Fecha de nacimiento</dt>
              <dd className="tabular mt-0.5">{formatDate(data.birth_date)}</dd>
            </div>
            {data.notes && (
              <div>
                <dt className="text-xs text-slate-500">Notas</dt>
                <dd className="mt-0.5">{data.notes}</dd>
              </div>
            )}
          </dl>
        </Card>

        <Card className="lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
            Referencias personales
          </h2>

          {data.references.length === 0 ? (
            <p className="text-sm text-slate-500">Sin referencias registradas.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.references.map((reference) => (
                <li key={reference.id} className="py-3 first:pt-0 last:pb-0">
                  <p className="text-sm font-medium text-slate-900">
                    {reference.name}{" "}
                    <span className="font-normal text-slate-500">
                      · {reference.relationship}
                    </span>
                  </p>
                  <p className="tabular text-xs text-slate-500">
                    {reference.phone} · {reference.address}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Historial de préstamos
        </h2>

        {loans.isLoading && <Spinner />}

        {loans.data && loans.data.items.length === 0 && (
          <EmptyState
            title="Sin préstamos"
            description="Este cliente todavía no tiene créditos registrados."
          />
        )}

        {loans.data && loans.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs tracking-wide text-slate-500 uppercase">
                <tr>
                  <th className="py-2 pr-4 font-medium">Monto</th>
                  <th className="py-2 pr-4 font-medium">Tasa</th>
                  <th className="py-2 pr-4 font-medium">Plazo</th>
                  <th className="py-2 pr-4 font-medium">Inicio</th>
                  <th className="py-2 pr-4 font-medium">Total</th>
                  <th className="py-2 pr-4 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loans.data.items.map((loan) => (
                  <tr key={loan.id}>
                    <td className="tabular py-3 pr-4">
                      <Link
                        to={`/prestamos/${loan.id}`}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {formatCurrency(loan.principal)}
                      </Link>
                    </td>
                    <td className="tabular py-3 pr-4 text-slate-600">
                      {formatRate(loan.interest_rate)}{" "}
                      {PERIOD_LABELS[loan.rate_period].toLowerCase()}
                    </td>
                    <td className="tabular py-3 pr-4 text-slate-600">
                      {loan.term_periods} pagos
                    </td>
                    <td className="tabular py-3 pr-4 text-slate-600">
                      {formatDate(loan.start_date)}
                    </td>
                    <td className="tabular py-3 pr-4 text-slate-600">
                      {formatCurrency(loan.total_amount)}
                    </td>
                    <td className="py-3 pr-4">
                      <Badge className={LOAN_STATUS_STYLES[loan.status]}>
                        {LOAN_STATUS_LABELS[loan.status]}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Documentos
        </h2>

        {documents.isLoading && <Spinner />}

        {documents.data && documents.data.length === 0 && (
          <p className="text-sm text-slate-500">
            Sin documentos cargados. La carga de archivos estará disponible
            próximamente.
          </p>
        )}

        {documents.data && documents.data.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {documents.data.map((document) => (
              <li
                key={document.id}
                className="flex items-center justify-between py-2 text-sm"
              >
                <span className="text-slate-700">
                  {DOCUMENT_LABELS[document.doc_type] ?? document.doc_type}
                </span>
                <span className="tabular text-xs text-slate-500">
                  {formatBytes(document.size_bytes)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
