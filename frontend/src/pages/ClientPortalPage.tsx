/**
 * Portal de consulta para el cliente acreditado (`/mi-credito`).
 *
 * Totalmente independiente del panel de empleados: el cliente ingresa con su
 * CURP y su PIN de 6 dígitos para consultar el avance de sus préstamos, su
 * próximo pago, su calendario de cuotas y descargar sus comprobantes de abono.
 */

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  INSTALLMENT_STATUS_LABELS,
  INSTALLMENT_STATUS_STYLES,
  LOAN_STATUS_LABELS,
  LOAN_STATUS_STYLES,
  PERIOD_LABELS,
} from "@/api/loans";
import {
  downloadPortalReceipt,
  getPortalOverview,
  type PortalLoan,
  portalLogin,
  type PortalOverview,
  portalSession,
} from "@/api/portal";
import { Alert, Badge, Card, EmptyState, Spinner, StatCard } from "@/components/ui";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";

function LoanProgressCard({ loan }: { loan: PortalLoan }) {
  const [tab, setTab] = useState<"cuotas" | "pagos">("cuotas");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const progress = Math.min(100, Math.max(0, Number(loan.progress_percent)));

  const handleDownload = async (paymentId: string, folio: string) => {
    setDownloadingId(paymentId);
    setDownloadError(null);
    try {
      await downloadPortalReceipt(paymentId, folio);
    } catch (err) {
      setDownloadError(
        err instanceof Error
          ? err.message
          : "El generador de PDF no está disponible en este momento.",
      );
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <Card className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-slate-900">
              Préstamo {formatCurrency(loan.principal)}
            </h3>
            <Badge className={LOAN_STATUS_STYLES[loan.status]}>
              {LOAN_STATUS_LABELS[loan.status]}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            Folio {loan.folio} · Pago{" "}
            {PERIOD_LABELS[loan.rate_period].toLowerCase()} · Del{" "}
            {formatDate(loan.start_date)} al {formatDate(loan.end_date)}
          </p>
        </div>

        <div className="text-right">
          <p className="text-xs text-slate-500">Total del crédito</p>
          <p className="tabular text-base font-semibold text-slate-900">
            {formatCurrency(loan.total_amount)}
          </p>
        </div>
      </div>

      {/* Barra de progreso del préstamo */}
      <div>
        <div className="mb-1.5 flex items-baseline justify-between text-sm">
          <span className="font-medium text-slate-700">
            Avance de pago: {loan.progress_percent} %
          </span>
          <span className="tabular text-xs text-slate-500">
            {loan.paid_installments_count} de {loan.term_periods} cuotas
            liquidadas
          </span>
        </div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-brand-600 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between text-xs text-slate-600">
          <span>
            Pagado:{" "}
            <strong className="tabular text-green-700">
              {formatCurrency(loan.paid_total)}
            </strong>
          </span>
          <span>
            Restante:{" "}
            <strong className="tabular text-slate-900">
              {formatCurrency(loan.remaining_total)}
            </strong>
          </span>
        </div>
      </div>

      {/* Tarjeta de próximo pago */}
      {loan.next_installment ? (
        <div
          className={`rounded-xl border p-4 ${
            loan.next_installment.is_overdue
              ? "border-red-200 bg-red-50"
              : "border-brand-200 bg-brand-50/60"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold tracking-wide uppercase text-slate-600">
                {loan.next_installment.is_overdue
                  ? "Cuota vencida pendiente"
                  : "Próximo pago programado"}
              </p>
              <p className="mt-1 text-sm text-slate-800">
                Cuota #{loan.next_installment.number} · Vence el{" "}
                <strong className="tabular">
                  {formatDate(loan.next_installment.due_date)}
                </strong>
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-500">Monto a cubrir</p>
              <p className="tabular text-xl font-bold text-slate-900">
                {formatCurrency(loan.next_installment.pending_amount)}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <Alert tone="success">
          ¡Felicidades! Este préstamo se encuentra liquidado en su totalidad.
        </Alert>
      )}

      {/* Selector de pestañas: Cuotas vs Abonos */}
      <div>
        <div className="mb-3 flex gap-2 border-b border-slate-200 pb-2">
          <button
            type="button"
            onClick={() => setTab("cuotas")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              tab === "cuotas"
                ? "bg-brand-50 text-brand-700"
                : "text-slate-600 hover:bg-slate-50"
            }`}
          >
            Calendario de cuotas ({loan.installments.length})
          </button>
          <button
            type="button"
            onClick={() => setTab("pagos")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              tab === "pagos"
                ? "bg-brand-50 text-brand-700"
                : "text-slate-600 hover:bg-slate-50"
            }`}
          >
            Mis abonos ({loan.payments.length})
          </button>
        </div>

        {downloadError && (
          <div className="mb-3">
            <Alert tone="error">{downloadError}</Alert>
          </div>
        )}

        {tab === "cuotas" ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Vencimiento</th>
                  <th className="px-3 py-2 font-medium text-right">Cuota</th>
                  <th className="px-3 py-2 font-medium text-right">Mora</th>
                  <th className="px-3 py-2 font-medium text-right">Abonado</th>
                  <th className="px-3 py-2 font-medium text-right">
                    Pendiente
                  </th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loan.installments.map((inst) => (
                  <tr key={inst.number} className="hover:bg-slate-50">
                    <td className="tabular px-3 py-2 font-medium text-slate-900">
                      {inst.number}
                    </td>
                    <td className="tabular px-3 py-2 text-slate-600">
                      {formatDate(inst.due_date)}
                    </td>
                    <td className="tabular px-3 py-2 text-right text-slate-700">
                      {formatCurrency(inst.amount)}
                    </td>
                    <td className="tabular px-3 py-2 text-right text-slate-600">
                      {formatCurrency(inst.late_fee)}
                    </td>
                    <td className="tabular px-3 py-2 text-right text-green-700">
                      {formatCurrency(inst.paid_amount)}
                    </td>
                    <td className="tabular px-3 py-2 text-right font-medium text-slate-900">
                      {formatCurrency(inst.pending_amount)}
                    </td>
                    <td className="px-3 py-2">
                      <Badge
                        className={
                          INSTALLMENT_STATUS_STYLES[inst.status] ??
                          "bg-slate-100 text-slate-700"
                        }
                      >
                        {INSTALLMENT_STATUS_LABELS[inst.status] ?? inst.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : loan.payments.length === 0 ? (
          <p className="py-4 text-center text-sm text-slate-500">
            Todavía no hay abonos registrados en este préstamo.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs tracking-wide text-slate-500 uppercase">
                <tr>
                  <th className="px-3 py-2 font-medium">Folio</th>
                  <th className="px-3 py-2 font-medium">Fecha</th>
                  <th className="px-3 py-2 font-medium">Método</th>
                  <th className="px-3 py-2 font-medium text-right">Monto</th>
                  <th className="px-3 py-2 font-medium text-right">
                    Comprobante
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loan.payments.map((pay) => (
                  <tr key={pay.id} className="hover:bg-slate-50">
                    <td className="tabular px-3 py-2 font-medium text-slate-900">
                      {pay.folio}
                    </td>
                    <td className="tabular px-3 py-2 text-slate-600">
                      {formatDateTime(pay.created_at)}
                    </td>
                    <td className="px-3 py-2 capitalize text-slate-600">
                      {pay.method}
                    </td>
                    <td className="tabular px-3 py-2 text-right font-medium text-green-700">
                      {formatCurrency(pay.amount)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="btn-secondary px-2.5 py-1 text-xs"
                        disabled={downloadingId === pay.id}
                        onClick={() => void handleDownload(pay.id, pay.folio)}
                      >
                        {downloadingId === pay.id
                          ? "Descargando…"
                          : "Descargar PDF"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

export function ClientPortalPage() {
  const [curp, setCurp] = useState("");
  const [pin, setPin] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [needsSlug, setNeedsSlug] = useState(false);

  const [overview, setOverview] = useState<PortalOverview | null>(null);
  const [loading, setLoading] = useState(() => Boolean(portalSession.token));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    if (!portalSession.token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getPortalOverview();
      setOverview(data);
    } catch (err) {
      setOverview(null);
      setError(
        err instanceof Error
          ? err.message
          : "No se pudo cargar tu estado de cuenta.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (curp.trim().length !== 18) {
      setError("Tu CURP debe tener exactamente 18 caracteres.");
      return;
    }
    if (!/^\d{6}$/.test(pin.trim())) {
      setError("El PIN debe ser de 6 dígitos numéricos.");
      return;
    }

    setSubmitting(true);
    try {
      const tokenRes = await portalLogin(
        curp,
        pin,
        tenantSlug.trim() || undefined,
      );
      portalSession.save(tokenRes.access_token);
      await loadOverview();
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "No se pudo iniciar sesión.";
      if (msg.toLowerCase().includes("mas de una financiera")) {
        setNeedsSlug(true);
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    portalSession.clear();
    setOverview(null);
    setPin("");
    setError(null);
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Spinner label="Cargando tu estado de cuenta…" />
      </div>
    );
  }

  // Vista autenticada del cliente
  if (overview) {
    return (
      <div className="min-h-screen bg-slate-50">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-4">
            <div>
              <p className="text-xs font-medium tracking-wide uppercase text-brand-700">
                {overview.tenant_name}
              </p>
              <h1 className="text-lg font-semibold text-slate-900">
                Hola, {overview.client_name}
              </h1>
            </div>
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={handleLogout}
            >
              Cerrar consulta
            </button>
          </div>
        </header>

        <main className="mx-auto max-w-4xl space-y-6 p-4 md:py-8">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              label="Préstamos vigentes"
              value={String(overview.active_loans_count)}
              hint="Créditos en curso"
            />
            <StatCard
              label="Total abonado"
              value={formatCurrency(overview.total_paid)}
              hint="Pagos aplicados"
              tone="good"
            />
            <StatCard
              label="Saldo total por pagar"
              value={formatCurrency(overview.total_remaining)}
              hint="Capital, interés y mora pendiente"
              tone={Number(overview.total_remaining) > 0 ? "warn" : "good"}
            />
          </div>

          {overview.loans.length === 0 ? (
            <EmptyState
              title="No tienes préstamos registrados"
              description="Cuando tu financiera apruebe tu crédito, podrás seguir tu avance desde aquí."
            />
          ) : (
            <div className="space-y-6">
              {overview.loans.map((loan) => (
                <LoanProgressCard key={loan.id} loan={loan} />
              ))}
            </div>
          )}
        </main>
      </div>
    );
  }

  // Formulario de acceso con CURP + PIN de 6 dígitos
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-3xl font-semibold tracking-tight text-brand-700">
            Mi Crédito
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Consulta el avance de tus préstamos, tu próximo pago y tus
            comprobantes.
          </p>
        </div>

        <form onSubmit={handleLogin} className="card space-y-4 p-6">
          {error && <Alert tone="error">{error}</Alert>}

          <div>
            <label htmlFor="portal-curp" className="label">
              Tu CURP (18 caracteres)
            </label>
            <input
              id="portal-curp"
              type="text"
              required
              maxLength={18}
              className="input uppercase"
              placeholder="LOPJ850312MDFZRN07"
              value={curp}
              onChange={(e) => setCurp(e.target.value.toUpperCase())}
            />
          </div>

          <div>
            <label htmlFor="portal-pin" className="label">
              PIN de 6 dígitos
            </label>
            <input
              id="portal-pin"
              type="password"
              inputMode="numeric"
              required
              maxLength={6}
              className="input tracking-widest"
              placeholder="••••••"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            />
            <p className="mt-1 text-xs text-slate-500">
              Solicita tu PIN de 6 dígitos a tu prestamista.
            </p>
          </div>

          {needsSlug && (
            <div>
              <label htmlFor="portal-slug" className="label">
                Código de tu financiera
              </label>
              <input
                id="portal-slug"
                type="text"
                className="input"
                placeholder="Ej. demo"
                value={tenantSlug}
                onChange={(e) => setTenantSlug(e.target.value)}
              />
            </div>
          )}

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={submitting}
          >
            {submitting ? "Consultando…" : "Ver mis préstamos"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-500">
          ¿Eres personal de la financiera?{" "}
          <Link to="/login" className="font-medium text-brand-700 hover:underline">
            Inicia sesión aquí
          </Link>
        </p>
      </div>
    </div>
  );
}
