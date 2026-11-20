/** Detalle de un cliente: datos, referencias, préstamos y documentos. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  changeClientStatus,
  getClient,
  listClientZones,
  updateClient,
} from "@/api/clients";
import {
  LOAN_STATUS_LABELS,
  LOAN_STATUS_STYLES,
  listLoans,
  PERIOD_LABELS,
} from "@/api/loans";
import { type PortalPinResult, setClientPortalPin } from "@/api/portal";
import { LocationPickerMap } from "@/components/LocationPickerMap";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { DocumentsSection } from "@/features/clients/DocumentsSection";
import { formatCurrency, formatDate, formatRate } from "@/lib/format";
import {
  DEFAULT_CITY,
  DEFAULT_STATE,
  buildGoogleMapsStopUrl,
  geocodeTorreonAddress,
  mergeZoneOptions,
  parseCoordinate,
} from "@/lib/geo";

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

  const toggleStatus = useMutation({
    mutationFn: (status: "activo" | "inactivo") => changeClientStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
    },
  });

  const [pinResult, setPinResult] = useState<PortalPinResult | null>(null);
  const [customPin, setCustomPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);

  // Edición rápida de domicilio, zona y ubicación en el mapa de Torreón.
  const [editingLocation, setEditingLocation] = useState(false);
  const [street, setStreet] = useState("");
  const [exteriorNumber, setExteriorNumber] = useState("");
  const [neighborhood, setNeighborhood] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [city, setCity] = useState(DEFAULT_CITY);
  const [stateName, setStateName] = useState(DEFAULT_STATE);
  const [zone, setZone] = useState("");
  const [customZone, setCustomZone] = useState("");
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [geocoding, setGeocoding] = useState(false);
  const [geoNotice, setGeoNotice] = useState<string | null>(null);

  const zonesQuery = useQuery({
    queryKey: ["clients", "zones"],
    queryFn: listClientZones,
    enabled: editingLocation,
  });

  const zoneOptions = useMemo(
    () => mergeZoneOptions(zonesQuery.data ?? []),
    [zonesQuery.data],
  );

  const updateLocationMutation = useMutation({
    mutationFn: () => {
      const resolvedZone =
        zone === "__custom__" ? customZone.trim() || null : zone.trim() || null;
      return updateClient(id, {
        street: street.trim() || null,
        exterior_number: exteriorNumber.trim() || null,
        neighborhood: neighborhood.trim() || null,
        postal_code: postalCode.trim() || null,
        city: city.trim() || null,
        state: stateName.trim() || null,
        zone: resolvedZone,
        latitude: latitude !== null ? latitude.toFixed(6) : null,
        longitude: longitude !== null ? longitude.toFixed(6) : null,
      });
    },
    onSuccess: () => {
      setEditingLocation(false);
      setGeoNotice(null);
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
      void queryClient.invalidateQueries({ queryKey: ["routes"] });
    },
  });

  const generatePinMutation = useMutation({
    mutationFn: (desired?: string) => setClientPortalPin(id, desired),
    onSuccess: (res) => {
      setPinError(null);
      setCustomPin("");
      setPinResult(res);
      void queryClient.invalidateQueries({ queryKey: ["clients", id] });
    },
    onError: (err) => {
      setPinError(
        err instanceof Error ? err.message : "No se pudo generar el PIN.",
      );
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
  const clientLat = parseCoordinate(data.latitude);
  const clientLng = parseCoordinate(data.longitude);

  const openLocationEditor = () => {
    setStreet(data.street ?? "");
    setExteriorNumber(data.exterior_number ?? "");
    setNeighborhood(data.neighborhood ?? "");
    setPostalCode(data.postal_code ?? "");
    setCity(data.city ?? DEFAULT_CITY);
    setStateName(data.state ?? DEFAULT_STATE);
    setZone(data.zone ?? "");
    setCustomZone("");
    setLatitude(clientLat);
    setLongitude(clientLng);
    setGeoNotice(null);
    setEditingLocation(true);
  };

  const handleGeocode = async () => {
    setGeocoding(true);
    setGeoNotice(null);
    try {
      const found = await geocodeTorreonAddress({
        street,
        exterior_number: exteriorNumber,
        neighborhood,
        postal_code: postalCode,
        city,
        state: stateName,
      });
      if (!found) {
        setGeoNotice(
          "No se encontró automáticamente. Haz clic en el mapa para marcar el domicilio.",
        );
        return;
      }
      setLatitude(Number(found.lat.toFixed(6)));
      setLongitude(Number(found.lng.toFixed(6)));
      setGeoNotice(
        found.approximate
          ? "Ubicación aproximada. Arrastra el pin a la casa exacta."
          : "Domicilio ubicado en el mapa. Arrastra el pin si quieres afinarlo.",
      );
    } catch {
      setGeoNotice("No se pudo buscar en el mapa. Coloca el pin manualmente.");
    } finally {
      setGeocoding(false);
    }
  };

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
              <dt className="text-xs text-slate-500">Ubicación en mapa</dt>
              <dd className="mt-1 flex flex-wrap items-center gap-2">
                {clientLat !== null && clientLng !== null ? (
                  <>
                    <Badge className="bg-green-100 text-green-800">
                      Ubicado en Torreón
                    </Badge>
                    <a
                      href={buildGoogleMapsStopUrl({
                        lat: clientLat,
                        lng: clientLng,
                        address: data.address,
                      })}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-brand-700 hover:underline"
                    >
                      Ver en Google Maps
                    </a>
                  </>
                ) : (
                  <Badge className="bg-slate-100 text-slate-600">
                    Sin pin guardado
                  </Badge>
                )}
                <button
                  type="button"
                  className="text-xs font-medium text-brand-700 hover:underline"
                  onClick={openLocationEditor}
                >
                  {editingLocation ? "Editando…" : "Editar ubicación"}
                </button>
              </dd>
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

      {editingLocation && (
        <Card className="mt-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
                Editar domicilio, zona y ubicación en mapa
              </h2>
              <p className="text-xs text-slate-500">
                Guarda calle, colonia, zona y coordenadas para que aparezca en el
                mapa de rutas de Torreón.
              </p>
            </div>
            <button
              type="button"
              className="btn-secondary px-3 py-1.5 text-xs"
              disabled={geocoding}
              onClick={() => void handleGeocode()}
            >
              {geocoding ? "Buscando…" : "Buscar en el mapa"}
            </button>
          </div>

          {updateLocationMutation.isError && (
            <div className="mb-3">
              <Alert tone="error">
                {updateLocationMutation.error instanceof Error
                  ? updateLocationMutation.error.message
                  : "No se pudo actualizar la ubicación."}
              </Alert>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-6">
            <div className="sm:col-span-4">
              <label className="label" htmlFor="edit-street">
                Calle
              </label>
              <input
                id="edit-street"
                className="input"
                value={street}
                onChange={(e) => setStreet(e.target.value)}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label" htmlFor="edit-num">
                Número
              </label>
              <input
                id="edit-num"
                className="input"
                value={exteriorNumber}
                onChange={(e) => setExteriorNumber(e.target.value)}
              />
            </div>
            <div className="sm:col-span-3">
              <label className="label" htmlFor="edit-col">
                Colonia
              </label>
              <input
                id="edit-col"
                className="input"
                value={neighborhood}
                onChange={(e) => setNeighborhood(e.target.value)}
              />
            </div>
            <div className="sm:col-span-1">
              <label className="label" htmlFor="edit-cp">
                C.P.
              </label>
              <input
                id="edit-cp"
                className="input tabular"
                maxLength={5}
                value={postalCode}
                onChange={(e) => setPostalCode(e.target.value)}
              />
            </div>
            <div className="sm:col-span-2">
              <label className="label" htmlFor="edit-zone">
                Zona
              </label>
              <select
                id="edit-zone"
                className="input"
                value={
                  zone && !zoneOptions.includes(zone) && zone !== "__custom__"
                    ? zone
                    : zone
                }
                onChange={(e) => setZone(e.target.value)}
              >
                <option value="">Sin zona</option>
                {zone &&
                  zone !== "__custom__" &&
                  !zoneOptions.includes(zone) && (
                    <option value={zone}>{zone}</option>
                  )}
                {zoneOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
                <option value="__custom__">+ Otra zona…</option>
              </select>
            </div>
            {zone === "__custom__" && (
              <div className="sm:col-span-3">
                <label className="label" htmlFor="edit-custom-zone">
                  Nueva zona
                </label>
                <input
                  id="edit-custom-zone"
                  className="input"
                  value={customZone}
                  onChange={(e) => setCustomZone(e.target.value)}
                />
              </div>
            )}
            <div className="sm:col-span-3">
              <label className="label" htmlFor="edit-city">
                Ciudad
              </label>
              <input
                id="edit-city"
                className="input"
                value={city}
                onChange={(e) => setCity(e.target.value)}
              />
            </div>
            <div className="sm:col-span-3">
              <label className="label" htmlFor="edit-state">
                Estado
              </label>
              <input
                id="edit-state"
                className="input"
                value={stateName}
                onChange={(e) => setStateName(e.target.value)}
              />
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
                  ? `Coordenadas: ${latitude.toFixed(6)}, ${longitude.toFixed(6)}`
                  : "Haz clic en el mapa para marcar el domicilio."}
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
                  Quitar pin
                </button>
              )}
            </div>
          </div>

          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setEditingLocation(false)}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={updateLocationMutation.isPending}
              onClick={() => updateLocationMutation.mutate()}
            >
              {updateLocationMutation.isPending
                ? "Guardando…"
                : "Guardar ubicación"}
            </button>
          </div>
        </Card>
      )}

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
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold tracking-wide text-slate-700 uppercase">
                Portal del cliente (CURP + PIN)
              </h2>
              <Badge
                className={
                  data.has_portal_pin || pinResult
                    ? "bg-green-100 text-green-800"
                    : "bg-slate-100 text-slate-600"
                }
              >
                {data.has_portal_pin || pinResult
                  ? "PIN configurado"
                  : "Sin PIN asignado"}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Genera un PIN de 6 dígitos para que {data.full_name} consulte el
              avance de sus préstamos en{" "}
              <Link
                to="/mi-credito"
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-brand-700 hover:underline"
              >
                /mi-credito
              </Link>
              .
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              placeholder="PIN opcional (6 dígitos)"
              className="input w-44 text-xs"
              value={customPin}
              onChange={(e) => setCustomPin(e.target.value.replace(/\D/g, ""))}
            />
            <button
              type="button"
              className="btn-primary text-xs"
              disabled={generatePinMutation.isPending}
              onClick={() => {
                if (customPin && customPin.length !== 6) {
                  setPinError("Si defines un PIN manual debe tener 6 dígitos.");
                  return;
                }
                generatePinMutation.mutate(customPin || undefined);
              }}
            >
              {generatePinMutation.isPending
                ? "Generando…"
                : data.has_portal_pin
                  ? "Regenerar PIN"
                  : "Generar PIN"}
            </button>
          </div>
        </div>

        {pinError && (
          <div className="mt-3">
            <Alert tone="error">{pinError}</Alert>
          </div>
        )}

        {pinResult && (
          <div className="mt-4">
            <Alert tone="warning">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-semibold">
                    PIN de 6 dígitos activo para {data.full_name}:{" "}
                    <code className="rounded bg-amber-100 px-2 py-0.5 font-mono text-base font-bold">
                      {pinResult.pin}
                    </code>
                  </p>
                  <p className="mt-1 text-xs">
                    El cliente ingresa en <strong>/mi-credito</strong> con su
                    CURP (<code>{data.curp}</code>) y este PIN.
                  </p>
                </div>
                <a
                  href={pinResult.whatsapp_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-primary text-xs"
                >
                  Enviar por WhatsApp
                </a>
              </div>
            </Alert>
          </div>
        )}
      </Card>

      <Card className="mt-6">
        <h2 className="mb-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
          Documentos
        </h2>
        <DocumentsSection clientId={data.id} />
      </Card>

    </div>
  );
}
