/**
 * Formulario para registrar un pago.
 *
 * El cobrador solo indica cuánto recibió y cómo; el reparto entre mora, interés
 * y capital lo decide el servidor. Después del pago se muestra el desglose, que
 * es lo que el cliente necesita ver en el comprobante.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  PAYMENT_TYPE_LABELS,
  registerPayment,
  type PaymentResult,
} from "@/api/payments";
import type { PaymentType } from "@/api/types";
import { Alert, Card } from "@/components/ui";
import { formatCurrency } from "@/lib/format";

const schema = z
  .object({
    amount: z.coerce.number().positive("El monto debe ser mayor que cero"),
    method: z.enum(["efectivo", "spei"]),
    payment_type: z.enum(["parcial", "completo", "adelantado", "moratorio"]),
    spei_reference: z.string().optional(),
  })
  .refine(
    (values) =>
      values.method !== "spei" || (values.spei_reference ?? "").trim().length >= 6,
    {
      message: "La referencia SPEI debe tener al menos 6 caracteres",
      path: ["spei_reference"],
    },
  );

// `z.coerce` acepta texto del input y devuelve numero. Se distinguen ambos
// tipos para que react-hook-form sepa que entra y que sale.
type FormInput = z.input<typeof schema>;
type FormOutput = z.output<typeof schema>;

interface Props {
  loanId: string;
  pendingTotal: string;
  onDone: () => void;
  onCancel: () => void;
}

export function PaymentForm({ loanId, pendingTotal, onDone, onCancel }: Props) {
  const [result, setResult] = useState<PaymentResult | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(schema),
    defaultValues: {
      amount: Number(pendingTotal),
      method: "efectivo",
      payment_type: "completo",
      spei_reference: "",
    },
  });

  const method = watch("method");

  const mutation = useMutation({
    mutationFn: (values: FormOutput) =>
      registerPayment({
        ...values,
        loan_id: loanId,
        spei_reference:
          values.method === "spei" ? values.spei_reference : undefined,
      }),
    onSuccess: (data) => setResult(data),
  });

  const onSubmit = (values: FormOutput) => {
    mutation.mutate(values);
  };

  if (result) {
    return (
      <Card className="border-green-200 bg-green-50">
        <h2 className="mb-3 text-sm font-semibold text-green-900">
          Pago registrado · {result.payment.folio}
        </h2>

        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-green-700">Mora cubierta</dt>
            <dd className="tabular font-medium">
              {formatCurrency(result.covered_late_fee)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-green-700">Interés cubierto</dt>
            <dd className="tabular font-medium">
              {formatCurrency(result.covered_interest)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-green-700">Capital cubierto</dt>
            <dd className="tabular font-medium">
              {formatCurrency(result.covered_principal)}
            </dd>
          </div>
        </dl>

        <p className="mt-4 border-t border-green-200 pt-3 text-sm">
          Saldo pendiente del préstamo:{" "}
          <strong className="tabular">
            {formatCurrency(result.remaining_total)}
          </strong>
        </p>

        <button type="button" className="btn-primary mt-4" onClick={onDone}>
          Listo
        </button>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
        Registrar pago
      </h2>

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        {mutation.isError && (
          <div className="mb-4">
            <Alert tone="error">
              {mutation.error instanceof Error
                ? mutation.error.message
                : "No se pudo registrar el pago."}
            </Alert>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="amount">
              Monto recibido
            </label>
            <input
              id="amount"
              type="number"
              step="0.01"
              className="input tabular"
              {...register("amount")}
            />
            {errors.amount && <p className="field-error">{errors.amount.message}</p>}
            <p className="mt-1 text-xs text-slate-500">
              Pendiente total: {formatCurrency(pendingTotal)}
            </p>
          </div>

          <div>
            <label className="label" htmlFor="method">
              Forma de pago
            </label>
            <select id="method" className="input" {...register("method")}>
              <option value="efectivo">Efectivo</option>
              <option value="spei">Transferencia SPEI</option>
            </select>
          </div>

          {method === "spei" && (
            <div>
              <label className="label" htmlFor="spei_reference">
                Referencia SPEI
              </label>
              <input
                id="spei_reference"
                className="input"
                placeholder="Folio o clave de rastreo"
                {...register("spei_reference")}
              />
              {errors.spei_reference && (
                <p className="field-error">{errors.spei_reference.message}</p>
              )}
            </div>
          )}

          <div>
            <label className="label" htmlFor="payment_type">
              Tipo de pago
            </label>
            <select id="payment_type" className="input" {...register("payment_type")}>
              {(Object.keys(PAYMENT_TYPE_LABELS) as PaymentType[]).map((type) => (
                <option key={type} value={type}>
                  {PAYMENT_TYPE_LABELS[type]}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "Registrando…" : "Registrar pago"}
          </button>
          <button type="button" className="btn-secondary" onClick={onCancel}>
            Cancelar
          </button>
        </div>

        <p className="mt-3 text-xs text-slate-500">
          El dinero se aplica primero a la mora, luego al interés y al final al
          capital, empezando por la cuota más antigua.
        </p>
      </form>
    </Card>
  );
}
