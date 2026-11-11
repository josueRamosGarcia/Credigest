/** Listado de préstamos. */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  LOAN_STATUS_LABELS,
  LOAN_STATUS_STYLES,
  PERIOD_LABELS,
  listLoans,
} from "@/api/loans";
import type { LoanStatus } from "@/api/types";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Spinner,
} from "@/components/ui";
import { formatCurrency, formatDate, formatRate } from "@/lib/format";

const PAGE_SIZE = 20;

export function LoansPage() {
  const [status, setStatus] = useState<LoanStatus | "">("");
  const [page, setPage] = useState(1);

  const loans = useQuery({
    queryKey: ["loans", { status, page }],
    queryFn: () =>
      listLoans({ status: status || undefined, page, page_size: PAGE_SIZE }),
    placeholderData: (previous) => previous,
  });

  return (
    <div>
      <PageHeader
        title="Préstamos"
        description="Créditos otorgados y su estado actual."
        actions={
          <Link to="/prestamos/nuevo" className="btn-primary">
            Nuevo préstamo
          </Link>
        }
      />

      <div className="mb-4">
        <select
          className="input max-w-[200px]"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as LoanStatus | "");
            setPage(1);
          }}
        >
          <option value="">Todos los estados</option>
          {(Object.keys(LOAN_STATUS_LABELS) as LoanStatus[]).map((key) => (
            <option key={key} value={key}>
              {LOAN_STATUS_LABELS[key]}
            </option>
          ))}
        </select>
      </div>

      {loans.isLoading && <Spinner />}

      {loans.isError && (
        <ErrorState
          message={
            loans.error instanceof Error
              ? loans.error.message
              : "No se pudieron cargar los préstamos."
          }
          onRetry={() => loans.refetch()}
        />
      )}

      {loans.data && loans.data.items.length === 0 && (
        <EmptyState
          title="Sin préstamos"
          description="Cuando apruebes el primero aparecerá aquí."
          action={
            <Link to="/prestamos/nuevo" className="btn-primary">
              Crear préstamo
            </Link>
          }
        />
      )}

      {loans.data && loans.data.items.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Monto</th>
                <th className="px-4 py-3 font-medium">Tasa</th>
                <th className="px-4 py-3 font-medium">Pagos</th>
                <th className="px-4 py-3 font-medium">Inicio</th>
                <th className="px-4 py-3 font-medium">Total</th>
                <th className="px-4 py-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loans.data.items.map((loan) => (
                <tr key={loan.id} className="hover:bg-slate-50">
                  <td className="tabular px-4 py-3">
                    <Link
                      to={`/prestamos/${loan.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {formatCurrency(loan.principal)}
                    </Link>
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {formatRate(loan.interest_rate)}{" "}
                    {PERIOD_LABELS[loan.rate_period].toLowerCase()}
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {loan.term_periods}
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {formatDate(loan.start_date)}
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {formatCurrency(loan.total_amount)}
                  </td>
                  <td className="px-4 py-3">
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

      {loans.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={loans.data.total}
          onChange={setPage}
        />
      )}
    </div>
  );
}
