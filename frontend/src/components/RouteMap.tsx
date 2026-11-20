/**
 * Mapa interactivo de la ruta de cobro en Torreón, Coahuila.
 *
 * Muestra las paradas numeradas con código de color según su estado de visita,
 * traza el recorrido por calles (OSRM con respaldo en línea directa) y ofrece
 * optimización por cercanía y acceso directo a Google Maps.
 */

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef, useState } from "react";

import type { RouteItem } from "@/api/routes";
import { formatCurrency } from "@/lib/format";
import {
  TORREON_CENTER,
  buildGoogleMapsRouteUrl,
  buildGoogleMapsStopUrl,
  fetchStreetRoute,
  optimizeStopOrder,
  parseCoordinate,
  type StreetRouteResult,
} from "@/lib/geo";

interface RouteMapProps {
  items: RouteItem[];
  isClosed: boolean;
  isReordering: boolean;
  onOptimizeOrder: (orderedItemIds: string[]) => void;
}

const PIN_COLORS: Record<RouteItem["visit_status"], string> = {
  pendiente: "#1d4ed8",
  pagado: "#15803d",
  no_pagado: "#b91c1c",
};

const STATUS_TEXT: Record<RouteItem["visit_status"], string> = {
  pendiente: "Pendiente",
  pagado: "Pagado",
  no_pagado: "No pagado",
};

function createNumberedIcon(
  orderIndex: number,
  status: RouteItem["visit_status"],
): L.DivIcon {
  const bg = PIN_COLORS[status];
  return L.divIcon({
    className: "",
    html: `<div style="width:30px;height:30px;border-radius:9999px;background:${bg};border:3px solid #ffffff;box-shadow:0 2px 8px rgba(15,23,42,0.35);display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:12px;font-weight:700;">${orderIndex}</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

function buildPopupElement(
  item: RouteItem,
  lat: number,
  lng: number,
): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.style.minWidth = "190px";
  wrapper.style.fontFamily = "system-ui, -apple-system, sans-serif";

  const title = document.createElement("p");
  title.style.fontWeight = "600";
  title.style.margin = "0 0 4px 0";
  title.textContent = `#${item.order_index} · ${item.client_name}`;
  wrapper.appendChild(title);

  const addr = document.createElement("p");
  addr.style.fontSize = "12px";
  addr.style.color = "#475569";
  addr.style.margin = "0 0 6px 0";
  addr.textContent = item.client_address;
  wrapper.appendChild(addr);

  const meta = document.createElement("p");
  meta.style.fontSize = "12px";
  meta.style.margin = "0 0 8px 0";
  meta.textContent = `${STATUS_TEXT[item.visit_status]} · ${formatCurrency(item.total_due)}`;
  wrapper.appendChild(meta);

  const link = document.createElement("a");
  link.href = buildGoogleMapsStopUrl({
    lat,
    lng,
    address: item.client_address,
  });
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.style.fontSize = "12px";
  link.style.fontWeight = "600";
  link.style.color = "#1d4ed8";
  link.textContent = "Cómo llegar en Google Maps →";
  wrapper.appendChild(link);

  return wrapper;
}

export function RouteMap({
  items,
  isClosed,
  isReordering,
  onOptimizeOrder,
}: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);

  const [routeSummary, setRouteSummary] = useState<StreetRouteResult | null>(
    null,
  );

  const stops = useMemo(
    () =>
      items.map((item) => ({
        item,
        lat: parseCoordinate(item.client_latitude),
        lng: parseCoordinate(item.client_longitude),
      })),
    [items],
  );

  const locatedStops = useMemo(
    () =>
      stops.filter(
        (s): s is { item: RouteItem; lat: number; lng: number } =>
          s.lat !== null && s.lng !== null,
      ),
    [stops],
  );

  const missingCount = stops.length - locatedStops.length;

  const googleMapsUrl = useMemo(
    () =>
      buildGoogleMapsRouteUrl(
        stops.map((s) => ({
          lat: s.lat,
          lng: s.lng,
          address: s.item.client_address,
        })),
      ),
    [stops],
  );

  // Inicializa el mapa Leaflet centrado en Torreón.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, {
      center: TORREON_CENTER,
      zoom: 13,
      scrollWheelZoom: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);

    layerGroupRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      layerGroupRef.current = null;
    };
  }, []);

  // Consulta el trazado por calles cuando cambian las paradas geolocalizadas.
  useEffect(() => {
    const controller = new AbortController();
    const points: [number, number][] = locatedStops.map((s) => [s.lat, s.lng]);

    if (points.length < 2) {
      return () => controller.abort();
    }

    void fetchStreetRoute(points, controller.signal).then((result) => {
      if (!controller.signal.aborted) {
        setRouteSummary(result);
      }
    });

    return () => controller.abort();
  }, [locatedStops]);

  const activeRouteSummary = locatedStops.length >= 2 ? routeSummary : null;

  // Dibuja marcadores y línea de ruta cada vez que cambian las paradas o la ruta.
  useEffect(() => {
    const map = mapRef.current;
    const group = layerGroupRef.current;
    if (!map || !group) return;

    group.clearLayers();

    if (locatedStops.length === 0) {
      map.setView(TORREON_CENTER, 13);
      return;
    }

    if (activeRouteSummary && activeRouteSummary.path.length >= 2) {
      L.polyline(activeRouteSummary.path, {
        color: "#2563eb",
        weight: 4,
        opacity: 0.85,
        dashArray: activeRouteSummary.isStreetRoute ? undefined : "6 8",
      }).addTo(group);
    } else if (locatedStops.length >= 2) {
      L.polyline(
        locatedStops.map((s) => [s.lat, s.lng] as [number, number]),
        {
          color: "#2563eb",
          weight: 3,
          opacity: 0.65,
          dashArray: "6 8",
        },
      ).addTo(group);
    }

    for (const stop of locatedStops) {
      L.marker([stop.lat, stop.lng], {
        icon: createNumberedIcon(stop.item.order_index, stop.item.visit_status),
      })
        .bindPopup(buildPopupElement(stop.item, stop.lat, stop.lng))
        .addTo(group);
    }

    if (locatedStops.length === 1) {
      map.setView([locatedStops[0].lat, locatedStops[0].lng], 16);
    } else {
      const bounds = L.latLngBounds(
        locatedStops.map((s) => [s.lat, s.lng] as [number, number]),
      );
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
    }
  }, [locatedStops, activeRouteSummary]);

  const handleOptimize = () => {
    const orderedIds = optimizeStopOrder(
      stops.map((s) => ({ id: s.item.id, lat: s.lat, lng: s.lng })),
    );
    onOptimizeOrder(orderedIds);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-brand-700" /> Pendiente
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-green-700" /> Pagado
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-red-700" /> No pagado
          </span>
          {activeRouteSummary && activeRouteSummary.distanceKm > 0 && (
            <span className="rounded-full bg-brand-50 px-2.5 py-0.5 font-medium text-brand-800">
              {activeRouteSummary.distanceKm} km · ~
              {activeRouteSummary.durationMin} min
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {!isClosed && locatedStops.length >= 3 && (
            <button
              type="button"
              className="btn-secondary px-3 py-1.5 text-xs"
              disabled={isReordering}
              onClick={handleOptimize}
            >
              {isReordering
                ? "Reordenando…"
                : "Optimizar orden por cercanía"}
            </button>
          )}
          {googleMapsUrl && (
            <a
              href={googleMapsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary px-3 py-1.5 text-xs"
            >
              Abrir ruta en Google Maps
            </a>
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        className="h-80 w-full overflow-hidden rounded-xl border border-slate-200 z-0"
        aria-label="Mapa de paradas de la ruta en Torreón"
      />

      {locatedStops.length === 0 && items.length > 0 && (
        <p className="text-xs text-amber-700">
          Ninguna parada de esta ruta tiene coordenadas guardadas todavía. Edita
          la ubicación en el perfil de cada cliente para ver los pines en el
          mapa de Torreón (aun así puedes usar «Abrir ruta en Google Maps»).
        </p>
      )}

      {locatedStops.length > 0 && missingCount > 0 && (
        <p className="text-xs text-slate-500">
          Se muestran {locatedStops.length} de {items.length} paradas en el
          mapa ({missingCount}{" "}
          {missingCount === 1
            ? "cliente sin ubicación guardada"
            : "clientes sin ubicación guardada"}
          ).
        </p>
      )}
    </div>
  );
}
