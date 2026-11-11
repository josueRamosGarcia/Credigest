/**
 * Anulación de un pago.
 *
 * Un pago nunca se borra: se anula con un motivo y queda en el historial. Solo
 * se puede anular el pago más reciente del préstamo, porque revertir uno
 * anterior dejaría los posteriores calculados sobre saldos que ya no existen.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/api/client";
import { cancelPayment } from "@/api/payments";
import { Alert, Card } from "@/components/ui";
import { formatCurrency } from "@/lib/format";

interface Props {
  paymentId: string;
  folio: string;
  amount: string;
  onDone: () => void;
  onCancel: () => void;
}

export function CancelPaymentForm({ paymentId, folio, amount, onDone, onCancel }: Props) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => cancelPayment(paymentId, reason.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payments"] });
      queryClient.invalidateQueries({ queryKey: ["loans"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["routes"] });
      onDone();
    },
  });

  const isPermissionError =
    mutation.error instanceof ApiError && mutation.error.status === 403;

  return (
    <Card className="border-amber-200 bg-amber-50">
      <h2 className="mb-2 text-sm font-semibold text-amber-900">
        Anular el pago {folio}
      </h2>

      <p className="mb-3 text-sm text-amber-900">
        Se revertirán {formatCurrency(amount)} de las cuotas correspondientes y el
        saldo del préstamo volverá a subir. El pago queda en el historial marcado
        como anulado.
      </p>

      {mutation.isError && (
        <div className="mb-3">
          <Alert tone="error">
            {isPermissionError
              ? "Tu usuario no tiene permiso para anular pagos. Pídeselo al administrador."
              : mutation.error instanceof Error
                ? mutation.error.message
                : "No se pudo anular el pago."}
          </Alert>
        </div>
      )}

      <label className="label" htmlFor="cancel-reason">
        Motivo de la anulación
      </label>
      <textarea
        id="cancel-reason"
        className="input min-h-20 bg-white"
        placeholder="Por ejemplo: se registró el monto equivocado"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
      />
      <p className="mt-1 text-xs text-amber-800">
        Mínimo 10 caracteres. Queda registrado en la auditoría con tu usuario.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-danger"
          disabled={reason.trim().length < 10 || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? "Anulando…" : "Confirmar anulación"}
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </Card>
  );
}
