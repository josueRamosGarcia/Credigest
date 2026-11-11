/** Alta de un cliente con validación de CURP y referencias. */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useFieldArray, useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { createClient } from "@/api/clients";
import { Alert, Card, PageHeader } from "@/components/ui";

const referenceSchema = z.object({
  name: z.string().min(1, "Escribe el nombre"),
  relationship: z.string().min(1, "Indica el parentesco"),
  phone: z.string().min(7, "El teléfono es muy corto"),
  address: z.string().min(1, "Escribe la dirección"),
});

const schema = z.object({
  full_name: z.string().min(3, "Escribe el nombre completo"),
  curp: z.string().length(18, "La CURP debe tener 18 caracteres"),
  phone: z.string().min(7, "El teléfono es muy corto").max(20, "El teléfono es muy largo"),
  address: z.string().min(5, "Escribe la dirección completa"),
  zone: z.string().optional(),
  notes: z.string().optional(),
  references: z.array(referenceSchema).max(10),
});

type FormValues = z.infer<typeof schema>;

export function ClientNewPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      curp: "",
      phone: "",
      address: "",
      zone: "",
      notes: "",
      references: [],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "references" });

  const mutation = useMutation({
    mutationFn: createClient,
    onSuccess: (client) => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      navigate(`/clientes/${client.id}`);
    },
  });

  const onSubmit = (values: FormValues) => {
    mutation.mutate({
      full_name: values.full_name.trim(),
      curp: values.curp.trim().toUpperCase(),
      phone: values.phone.trim(),
      address: values.address.trim(),
      zone: values.zone?.trim() || null,
      notes: values.notes?.trim() || null,
      references: values.references,
    });
  };

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Nuevo cliente"
        description="Captura los datos y, si los tienes, las referencias personales."
        actions={
          <Link to="/clientes" className="btn-secondary">
            Cancelar
          </Link>
        }
      />

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6" noValidate>
        {mutation.isError && (
          <Alert tone="error">
            {mutation.error instanceof Error
              ? mutation.error.message
              : "No se pudo registrar el cliente."}
          </Alert>
        )}

        <Card>
          <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
            Datos generales
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label" htmlFor="full_name">
                Nombre completo
              </label>
              <input
                id="full_name"
                className="input"
                placeholder="María López Pérez"
                {...register("full_name")}
              />
              {errors.full_name && (
                <p className="field-error">{errors.full_name.message}</p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="curp">
                CURP
              </label>
              <input
                id="curp"
                className="input uppercase"
                placeholder="LOPJ850312MDFZRN07"
                maxLength={18}
                {...register("curp")}
              />
              {errors.curp && <p className="field-error">{errors.curp.message}</p>}
              <p className="mt-1 text-xs text-slate-500">
                Se valida el formato y el dígito verificador.
              </p>
            </div>

            <div>
              <label className="label" htmlFor="phone">
                Teléfono
              </label>
              <input
                id="phone"
                className="input"
                placeholder="8711234567"
                {...register("phone")}
              />
              {errors.phone && <p className="field-error">{errors.phone.message}</p>}
            </div>

            <div className="sm:col-span-2">
              <label className="label" htmlFor="address">
                Dirección
              </label>
              <input
                id="address"
                className="input"
                placeholder="Av. Juárez 123, Col. Centro, Torreón, Coahuila"
                {...register("address")}
              />
              {errors.address && (
                <p className="field-error">{errors.address.message}</p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="zone">
                Zona de cobro
              </label>
              <input
                id="zone"
                className="input"
                placeholder="Centro"
                {...register("zone")}
              />
              <p className="mt-1 text-xs text-slate-500">
                Agrupa al cliente en las rutas de cobro.
              </p>
            </div>

            <div>
              <label className="label" htmlFor="notes">
                Notas
              </label>
              <input
                id="notes"
                className="input"
                placeholder="Opcional"
                {...register("notes")}
              />
            </div>
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
              Referencias personales
            </h2>
            <button
              type="button"
              className="btn-secondary px-3 py-1 text-xs"
              onClick={() =>
                append({ name: "", relationship: "", phone: "", address: "" })
              }
            >
              Agregar
            </button>
          </div>

          {fields.length === 0 && (
            <p className="text-sm text-slate-500">
              Sin referencias. Puedes agregarlas ahora o después.
            </p>
          )}

          <div className="space-y-4">
            {fields.map((field, index) => (
              <div
                key={field.id}
                className="rounded-lg border border-slate-200 p-4"
              >
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-xs font-medium text-slate-500">
                    Referencia {index + 1}
                  </p>
                  <button
                    type="button"
                    className="text-xs text-red-600 hover:underline"
                    onClick={() => remove(index)}
                  >
                    Quitar
                  </button>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="label">Nombre</label>
                    <input
                      className="input"
                      {...register(`references.${index}.name`)}
                    />
                    {errors.references?.[index]?.name && (
                      <p className="field-error">
                        {errors.references[index]?.name?.message}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="label">Parentesco</label>
                    <input
                      className="input"
                      placeholder="Hermano, vecina, etc."
                      {...register(`references.${index}.relationship`)}
                    />
                    {errors.references?.[index]?.relationship && (
                      <p className="field-error">
                        {errors.references[index]?.relationship?.message}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="label">Teléfono</label>
                    <input
                      className="input"
                      {...register(`references.${index}.phone`)}
                    />
                    {errors.references?.[index]?.phone && (
                      <p className="field-error">
                        {errors.references[index]?.phone?.message}
                      </p>
                    )}
                  </div>

                  <div>
                    <label className="label">Dirección</label>
                    <input
                      className="input"
                      {...register(`references.${index}.address`)}
                    />
                    {errors.references?.[index]?.address && (
                      <p className="field-error">
                        {errors.references[index]?.address?.message}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="flex justify-end gap-3">
          <Link to="/clientes" className="btn-secondary">
            Cancelar
          </Link>
          <button type="submit" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting ? "Guardando…" : "Guardar cliente"}
          </button>
        </div>
      </form>
    </div>
  );
}
