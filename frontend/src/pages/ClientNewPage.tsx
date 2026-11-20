/** Alta de un cliente con validación de CURP, domicilio estructurado y pin en Torreón. */

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { createClient, listClientZones } from "@/api/clients";
import { LocationPickerMap } from "@/components/LocationPickerMap";
import { Alert, Card, PageHeader } from "@/components/ui";
import {
  DEFAULT_CITY,
  DEFAULT_STATE,
  composeAddress,
  geocodeTorreonAddress,
  mergeZoneOptions,
} from "@/lib/geo";

const CUSTOM_ZONE_VALUE = "__custom__";

const referenceSchema = z.object({
  name: z.string().min(1, "Escribe el nombre"),
  relationship: z.string().min(1, "Indica el parentesco"),
  phone: z.string().min(7, "El teléfono es muy corto"),
  address: z.string().min(1, "Escribe la dirección"),
});

const schema = z.object({
  full_name: z.string().min(3, "Escribe el nombre completo"),
  curp: z.string().length(18, "La CURP debe tener 18 caracteres"),
  phone: z
    .string()
    .min(7, "El teléfono es muy corto")
    .max(20, "El teléfono es muy largo"),
  street: z.string().min(2, "Escribe la calle"),
  exterior_number: z.string().min(1, "Indica el número"),
  neighborhood: z.string().min(2, "Escribe la colonia"),
  postal_code: z
    .string()
    .regex(/^(\d{5})?$/, "El C.P. debe tener 5 dígitos")
    .optional(),
  city: z.string().min(2, "Escribe la ciudad"),
  state: z.string().min(2, "Escribe el estado"),
  zone: z.string().optional(),
  custom_zone: z.string().optional(),
  notes: z.string().optional(),
  references: z.array(referenceSchema).max(10),
});

type FormValues = z.infer<typeof schema>;

export function ClientNewPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [geocoding, setGeocoding] = useState(false);
  const [geoNotice, setGeoNotice] = useState<string | null>(null);

  const zonesQuery = useQuery({
    queryKey: ["clients", "zones"],
    queryFn: listClientZones,
  });

  const zoneOptions = useMemo(
    () => mergeZoneOptions(zonesQuery.data ?? []),
    [zonesQuery.data],
  );

  const {
    register,
    control,
    getValues,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      curp: "",
      phone: "",
      street: "",
      exterior_number: "",
      neighborhood: "",
      postal_code: "",
      city: DEFAULT_CITY,
      state: DEFAULT_STATE,
      zone: "Centro",
      custom_zone: "",
      notes: "",
      references: [],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "references",
  });

  const [isCustomZone, setIsCustomZone] = useState(false);

  const mutation = useMutation({
    mutationFn: createClient,
    onSuccess: (client) => {
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
      void queryClient.invalidateQueries({ queryKey: ["routes", "zones"] });
      navigate(`/clientes/${client.id}`);
    },
  });

  const handleLocateOnMap = async () => {
    const vals = getValues();
    if (!vals.street.trim() && !vals.neighborhood.trim()) {
      setGeoNotice(
        "Escribe al menos la calle o la colonia para buscar en el mapa de Torreón.",
      );
      return;
    }

    setGeocoding(true);
    setGeoNotice(null);
    try {
      const found = await geocodeTorreonAddress({
        street: vals.street,
        exterior_number: vals.exterior_number,
        neighborhood: vals.neighborhood,
        postal_code: vals.postal_code,
        city: vals.city,
        state: vals.state,
      });

      if (!found) {
        setGeoNotice(
          "No se encontró automáticamente. Haz clic en el mapa de Torreón para colocar el pin.",
        );
        return;
      }

      setLatitude(Number(found.lat.toFixed(6)));
      setLongitude(Number(found.lng.toFixed(6)));
      setGeoNotice(
        found.approximate
          ? "Ubicación aproximada por colonia/calle. Arrastra el pin para ajustar a la casa exacta."
          : "Dirección ubicada en el mapa. Puedes arrastrar el pin si necesitas ajustarla.",
      );
    } catch {
      setGeoNotice(
        "No se pudo consultar el mapa en este momento. Puedes colocar el pin manualmente.",
      );
    } finally {
      setGeocoding(false);
    }
  };

  const onSubmit = (values: FormValues) => {
    const resolvedZone =
      values.zone === CUSTOM_ZONE_VALUE
        ? values.custom_zone?.trim() || null
        : values.zone?.trim() || null;

    const fullAddress = composeAddress({
      street: values.street,
      exterior_number: values.exterior_number,
      neighborhood: values.neighborhood,
      postal_code: values.postal_code,
      city: values.city,
      state: values.state,
    });

    mutation.mutate({
      full_name: values.full_name.trim(),
      curp: values.curp.trim().toUpperCase(),
      phone: values.phone.trim(),
      address: fullAddress,
      street: values.street.trim(),
      exterior_number: values.exterior_number.trim(),
      neighborhood: values.neighborhood.trim(),
      postal_code: values.postal_code?.trim() || null,
      city: values.city.trim(),
      state: values.state.trim(),
      latitude: latitude !== null ? latitude.toFixed(6) : null,
      longitude: longitude !== null ? longitude.toFixed(6) : null,
      zone: resolvedZone,
      notes: values.notes?.trim() || null,
      references: values.references,
    });
  };

  const zoneField = register("zone");

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Nuevo cliente"
        description="Captura los datos personales, domicilio estructurado y ubicación en Torreón."
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
                placeholder="LOPJ850312MDFZRN00"
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

            <div>
              <label className="label" htmlFor="zone">
                Zona de cobro
              </label>
              <select
                id="zone"
                className="input"
                {...zoneField}
                onChange={(event) => {
                  zoneField.onChange(event);
                  setIsCustomZone(event.target.value === CUSTOM_ZONE_VALUE);
                }}
              >
                <option value="">Sin zona asignada</option>
                {zoneOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
                <option value={CUSTOM_ZONE_VALUE}>+ Agregar otra zona…</option>
              </select>
              <p className="mt-1 text-xs text-slate-500">
                Agrupa al cliente en el selector de rutas de cobro.
              </p>
            </div>

            {isCustomZone ? (
              <div>
                <label className="label" htmlFor="custom_zone">
                  Nombre de la nueva zona
                </label>
                <input
                  id="custom_zone"
                  className="input"
                  placeholder="Ej. Residencial El Fresno"
                  {...register("custom_zone")}
                />
              </div>
            ) : (
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
            )}

            {isCustomZone && (
              <div className="sm:col-span-2">
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
            )}
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
                Domicilio y ubicación en mapa (Torreón)
              </h2>
              <p className="text-xs text-slate-500">
                Estos campos arman la dirección del pagaré y permiten ubicar al
                cliente en el mapa de rutas.
              </p>
            </div>
            <button
              type="button"
              className="btn-secondary px-3 py-1.5 text-xs"
              disabled={geocoding}
              onClick={() => void handleLocateOnMap()}
            >
              {geocoding ? "Buscando…" : "Buscar dirección en el mapa"}
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-6">
            <div className="sm:col-span-4">
              <label className="label" htmlFor="street">
                Calle o avenida
              </label>
              <input
                id="street"
                className="input"
                placeholder="Av. Juárez"
                {...register("street")}
              />
              {errors.street && (
                <p className="field-error">{errors.street.message}</p>
              )}
            </div>

            <div className="sm:col-span-2">
              <label className="label" htmlFor="exterior_number">
                Número
              </label>
              <input
                id="exterior_number"
                className="input"
                placeholder="123"
                {...register("exterior_number")}
              />
              {errors.exterior_number && (
                <p className="field-error">{errors.exterior_number.message}</p>
              )}
            </div>

            <div className="sm:col-span-4">
              <label className="label" htmlFor="neighborhood">
                Colonia
              </label>
              <input
                id="neighborhood"
                className="input"
                placeholder="Centro"
                {...register("neighborhood")}
              />
              {errors.neighborhood && (
                <p className="field-error">{errors.neighborhood.message}</p>
              )}
            </div>

            <div className="sm:col-span-2">
              <label className="label" htmlFor="postal_code">
                C.P. (opcional)
              </label>
              <input
                id="postal_code"
                className="input tabular"
                placeholder="27000"
                maxLength={5}
                {...register("postal_code")}
              />
              {errors.postal_code && (
                <p className="field-error">{errors.postal_code.message}</p>
              )}
            </div>

            <div className="sm:col-span-3">
              <label className="label" htmlFor="city">
                Ciudad
              </label>
              <input id="city" className="input" {...register("city")} />
              {errors.city && (
                <p className="field-error">{errors.city.message}</p>
              )}
            </div>

            <div className="sm:col-span-3">
              <label className="label" htmlFor="state">
                Estado
              </label>
              <input id="state" className="input" {...register("state")} />
              {errors.state && (
                <p className="field-error">{errors.state.message}</p>
              )}
            </div>
          </div>

          <div className="mt-4 space-y-2">
            {geoNotice && <Alert tone="info">{geoNotice}</Alert>}

            <LocationPickerMap
              latitude={latitude}
              longitude={longitude}
              onChange={(lat, lng) => {
                setLatitude(lat);
                setLongitude(lng);
              }}
            />

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
              <span>
                {latitude !== null && longitude !== null
                  ? `Pin guardado: ${latitude.toFixed(6)}, ${longitude.toFixed(6)} (arrástralo para ajustar)`
                  : "Haz clic en el mapa o usa «Buscar dirección en el mapa» para marcar la ubicación."}
              </span>
              {latitude !== null && longitude !== null && (
                <button
                  type="button"
                  className="text-red-600 hover:underline"
                  onClick={() => {
                    setLatitude(null);
                    setLongitude(null);
                  }}
                >
                  Quitar ubicación
                </button>
              )}
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
          <button
            type="submit"
            className="btn-primary"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Guardando…" : "Guardar cliente"}
          </button>
        </div>
      </form>
    </div>
  );
}
