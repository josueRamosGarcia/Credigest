/** Detalle del préstamo: calendario, pagos y acciones. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  INSTALLMENT_STATUS_LABELS,
  INSTALLMENT_STATUS_STYLES,
  LOAN_STATUS_LABELS,
  LOAN_STATUS_STYLES,
  PERIOD_LABELS,
  SCHEME_LABELS,
  cancelLoan,
  downloadPagare,
  getLoan,
} from "@/api/loans";
import {
  CONCEPT_LABELS,
  PAYMENT_METHOD_LABELS,
  downloadReceipt,
  getWhatsappLink,
  listPayments,
} from "@/api/payments";
import { PaymentForm } from "@/features/payments/PaymentForm";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { formatCurrency, formatDate, formatDateTime, formatRate } from "@/lib/format";

export function LoanDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [showPayment, setShowPayment] = useState(false);
  const [showCancel, setShowCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [downloading, setDownloading] = useState(false);

  const loan = useQuery({
    queryKey: ["loans", id],
    queryFn: () => getLoan(id),
    enabled: Boolean(id),
  });

  const payments = useQuery({
    queryKey: ["payments", { loan_id: id }],
    queryFn: () => listPayments({ loan_id: id, page_size: 50 }),
    enabled: Boolean(id),
  });

  const cancel = useMutation({
    mutationFn: (reason: string) => cancelLoan(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["loans"] });
      setShowCancel(false);
      setCancelReason("");
    },
  });

  if (loan.isLoading) return <Spinner />;

  if (loan.isError || !loan.data) {
    return (
      <ErrorState
        message={
          loan.error instanceof Error
            ? loan.error.message
            : "No se pudo cargar el préstamo."
        }
        onRetry={() => loan.refetch()}
      />
    );
  }

  const data = loan.data;
  const canPay = data.status === "activo" || data.status === "vencido";
  const canCancel = canPay;

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await downloadPagare(data.id);
    } finally {
      setDownloading(false);
    }
  };

  const totalPaid = data.installments.reduce(
    (sum, row) => sum + Number(row.paid_amount),
    0,
  );
  const totalPending = data.installments.reduce(
    (sum, row) =>
      sum + (Number(row.amount) + Number(row.late_fee) - Number(row.paid_amount)),
    0,
  );

  return (
    <div>
      <PageHeader
        title={`Préstamo de ${formatCurrency(data.principal)}`}
        description={`${SCHEME_LABELS[data.scheme]} · ${formatRate(data.interest_rate)} ${PERIOD_LABELS[data.rate_period].toLowerCase()}`}
        actions={
          <>
            <Link to="/prestamos" className="btn-secondary">
              Volver
            </Link>
            <button
              type="button"
              className="btn-secondary"
              onClick={handleDownload}
              disabled={downloading}
            >
              {downloading ? "Generando…" : "Descargar pagaré"}
            </button>
            {canPay && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => setShowPayment((value) => !value)}
              >
                Registrar pago
              </button>
            )}
            {canCancel && (
              <button
                type="button"
                className="btn-secondary text-red-700"
                onClick={() => setShowCancel((value) => !value)}
              >
                Cancelar
              </button>
            )}
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Badge className={LOAN_STATUS_STYLES[data.status]}>
          {LOAN_STATUS_LABELS[data.status]}
        </Badge>
        <span className="text-sm text-slate-600">
          Inicio {formatDate(data.start_date)} · término {formatDate(data.end_date)}
        </span>
      </div>

      {showPayment && (
        <div className="mb-6">
          <PaymentForm
            loanId={data.id}
            pendingTotal={totalPending.toFixed(2)}
            onDone={() => {
              setShowPayment(false);
              queryClient.invalidateQueries({ queryKey: ["loans"] });
              queryClient.invalidateQueries({ queryKey: ["payments"] });
              queryClient.invalidateQueries({ queryKey: ["dashboard"] });
            }}
            onCancel={() => setShowPayment(false)}
          />
        </div>
      )}

      {showCancel && (
        <Card className="mb-6">
          <h2 className="mb-3 text-sm font-semibold text-slate-700">
            Cancelar préstamo
          </h2>
          <p className="mb-3 text-sm text-slate-600">
            El préstamo se conserva en el historial con su motivo. No se borra.
          </p>
          <textarea
            className="input min-h-20"
            placeholder="Motivo de la cancelación (mínimo 5 caracteres)"
            value={cancelReason}
            onChange={(event) => setCancelReason(event.target.value)}
          />
          {cancel.isError && (
            <p className="field-error">
              {cancel.error instanceof Error
                ? cancel.error.message
                : "No se pudo cancelar."}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="btn-danger"
              disabled={cancelReason.trim().length < 5 || cancel.isPending}
              onClick={() => cancel.mutate(cancelReason.trim())}
            >
              {cancel.isPending ? "Cancelando…" : "Confirmar cancelación"}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowCancel(false)}
            >
              Cerrar
            </button>
          </div>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <p className="text-xs text-slate-500 uppercase">Capital</p>
          <p className="tabular mt-1 text-xl font-semibold">
            {formatCurrency(data.principal)}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 uppercase">Interés total</p>
          <p className="tabular mt-1 text-xl font-semibold">
            {formatCurrency(data.total_interest)}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 uppercase">Pagado</p>
          <p className="tabular mt-1 text-xl font-semibold text-green-700">
            {formatCurrency(totalPaid.toFixed(2))}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-slate-500 uppercase">Pendiente</p>
          <p className="tabular mt-1 text-xl font-semibold text-slate-900">
            {formatCurrency(totalPending.toFixed(2))}
          </p>
        </Card>
      </div>

      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Calendario de pagos
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="py-2 pr-4 font-medium">#</th>
                <th className="py-2 pr-4 font-medium">Vence</th>
                <th className="py-2 pr-4 font-medium">Cuota</th>
                <th className="py-2 pr-4 font-medium">Interés</th>
                <th className="py-2 pr-4 font-medium">Capital</th>
                <th className="py-2 pr-4 font-medium">Mora</th>
                <th className="py-2 pr-4 font-medium">Pagado</th>
                <th className="py-2 pr-4 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.installments.map((row) => (
                <tr key={row.id}>
                  <td className="tabular py-2 pr-4 text-slate-500">{row.number}</td>
                  <td className="tabular py-2 pr-4">{formatDate(row.due_date)}</td>
                  <td className="tabular py-2 pr-4">{formatCurrency(row.amount)}</td>
                  <td className="tabular py-2 pr-4 text-slate-600">
                    {formatCurrency(row.interest_part)}
                  </td>
                  <td className="tabular py-2 pr-4 text-slate-600">
                    {formatCurrency(row.principal_part)}
                  </td>
                  <td className="tabular py-2 pr-4 text-slate-600">
                    {Number(row.late_fee) > 0
                      ? formatCurrency(row.late_fee)
                      : "—"}
                  </td>
                  <td className="tabular py-2 pr-4 text-slate-600">
                    {Number(row.paid_amount) > 0
                      ? formatCurrency(row.paid_amount)
                      : "—"}
                  </td>
                  <td className="py-2 pr-4">
                    <Badge className={INSTALLMENT_STATUS_STYLES[row.status]}>
                      {INSTALLMENT_STATUS_LABELS[row.status] ?? row.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Pagos registrados
        </h2>

        {payments.isLoading && <Spinner />}

        {payments.data && payments.data.items.length === 0 && (
          <EmptyState title="Sin pagos" description="Aún no se ha registrado ningún abono." />
        )}

        {payments.data && payments.data.items.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {payments.data.items.map((payment) => (
              <li
                key={payment.id}
                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
              >
                <div>
                  <p className="font-medium text-slate-900">
                    {formatCurrency(payment.amount)}{" "}
                    <span className="font-normal text-slate-500">
                      · {PAYMENT_METHOD_LABELS[payment.method]}
                    </span>
                  </p>
                  <p className="tabular text-xs text-slate-500">
                    {payment.folio} · {formatDateTime(payment.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge
                    className={
                      payment.status === "aplicado"
                        ? "bg-green-100 text-green-800"
                        : "bg-slate-100 text-slate-600"
                    }
                  >
                    {payment.status === "aplicado" ? "Aplicado" : "Anulado"}
                  </Badge>
                  <button
                    type="button"
                    className="text-xs text-brand-700 hover:underline"
                    onClick={() => downloadReceipt(payment.id, payment.folio)}
                  >
                    PDF
                  </button>
                  <button
                    type="button"
                    className="text-xs text-green-700 hover:underline"
                    onClick={async () => {
                      const { url } = await getWhatsappLink(payment.id);
                      window.open(url, "_blank", "noopener,noreferrer");
                    }}
                  >
                    WhatsApp
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {payments.data && payments.data.items.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">
          Conceptos aplicados:{" "}
          {Object.values(CONCEPT_LABELS).join(", ")}.
        </p>
      )}
    </div>
  );
}
