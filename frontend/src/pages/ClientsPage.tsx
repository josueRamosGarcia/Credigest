/** Listado de clientes con búsqueda y filtros. */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { listClients } from "@/api/clients";
import type { ClientStatus } from "@/api/types";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Spinner,
} from "@/components/ui";
import { formatDate } from "@/lib/format";

const PAGE_SIZE = 20;

export function ClientsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ClientStatus | "">("");
  const [page, setPage] = useState(1);

  const clients = useQuery({
    queryKey: ["clients", { search, status, page }],
    queryFn: () =>
      listClients({
        search: search || undefined,
        status: status || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: (previous) => previous,
  });

  return (
    <div>
      <PageHeader
        title="Clientes"
        description="Personas que han solicitado o tienen crédito contigo."
        actions={
          <Link to="/clientes/nuevo" className="btn-primary">
            Nuevo cliente
          </Link>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="search"
          className="input max-w-xs"
          placeholder="Buscar por nombre, CURP o teléfono"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />

        <select
          className="input max-w-[180px]"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ClientStatus | "");
            setPage(1);
          }}
        >
          <option value="">Todos los estados</option>
          <option value="activo">Activos</option>
          <option value="inactivo">Inactivos</option>
        </select>
      </div>

      {clients.isLoading && <Spinner />}

      {clients.isError && (
        <ErrorState
          message={
            clients.error instanceof Error
              ? clients.error.message
              : "No se pudieron cargar los clientes."
          }
          onRetry={() => clients.refetch()}
        />
      )}

      {clients.data && clients.data.items.length === 0 && (
        <EmptyState
          title="Todavía no hay clientes"
          description="Registra al primero para poder otorgarle un préstamo."
          action={
            <Link to="/clientes/nuevo" className="btn-primary">
              Registrar cliente
            </Link>
          }
        />
      )}

      {clients.data && clients.data.items.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Nombre</th>
                <th className="px-4 py-3 font-medium">CURP</th>
                <th className="px-4 py-3 font-medium">Teléfono</th>
                <th className="px-4 py-3 font-medium">Zona</th>
                <th className="px-4 py-3 font-medium">Nacimiento</th>
                <th className="px-4 py-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {clients.data.items.map((client) => (
                <tr key={client.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/clientes/${client.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {client.full_name}
                    </Link>
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">{client.curp}</td>
                  <td className="tabular px-4 py-3 text-slate-600">{client.phone}</td>
                  <td className="px-4 py-3 text-slate-600">{client.zone ?? "—"}</td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {formatDate(client.birth_date)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      className={
                        client.status === "activo"
                          ? "bg-green-100 text-green-800"
                          : "bg-slate-100 text-slate-600"
                      }
                    >
                      {client.status === "activo" ? "Activo" : "Inactivo"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {clients.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={clients.data.total}
          onChange={setPage}
        />
      )}
    </div>
  );
}
