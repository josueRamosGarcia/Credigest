/** Historial de pagos de la financiera. */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  PAYMENT_METHOD_LABELS,
  listPayments,
} from "@/api/payments";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Spinner,
} from "@/components/ui";
import { formatCurrency, formatDateTime } from "@/lib/format";

const PAGE_SIZE = 20;

export function PaymentsPage() {
  const [page, setPage] = useState(1);

  const payments = useQuery({
    queryKey: ["payments", { page }],
    queryFn: () => listPayments({ page, page_size: PAGE_SIZE }),
    placeholderData: (previous) => previous,
  });

  return (
    <div>
      <PageHeader
        title="Pagos"
        description="Todos los abonos registrados, del más reciente al más antiguo."
      />

      {payments.isLoading && <Spinner />}

      {payments.isError && (
        <ErrorState
          message={
            payments.error instanceof Error
              ? payments.error.message
              : "No se pudieron cargar los pagos."
          }
          onRetry={() => payments.refetch()}
        />
      )}

      {payments.data && payments.data.items.length === 0 && (
        <EmptyState
          title="Sin pagos"
          description="Los abonos aparecerán aquí en cuanto se registren."
        />
      )}

      {payments.data && payments.data.items.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Folio</th>
                <th className="px-4 py-3 font-medium">Fecha</th>
                <th className="px-4 py-3 font-medium">Monto</th>
                <th className="px-4 py-3 font-medium">Forma</th>
                <th className="px-4 py-3 font-medium">Referencia</th>
                <th className="px-4 py-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {payments.data.items.map((payment) => (
                <tr key={payment.id} className="hover:bg-slate-50">
                  <td className="tabular px-4 py-3 font-medium text-slate-700">
                    {payment.folio}
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {formatDateTime(payment.created_at)}
                  </td>
                  <td className="tabular px-4 py-3 font-medium">
                    {formatCurrency(payment.amount)}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {PAYMENT_METHOD_LABELS[payment.method]}
                  </td>
                  <td className="tabular px-4 py-3 text-slate-600">
                    {payment.spei_reference ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      className={
                        payment.status === "aplicado"
                          ? "bg-green-100 text-green-800"
                          : "bg-slate-100 text-slate-600"
                      }
                    >
                      {payment.status === "aplicado" ? "Aplicado" : "Anulado"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {payments.data && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={payments.data.total}
          onChange={setPage}
        />
      )}
    </div>
  );
}
