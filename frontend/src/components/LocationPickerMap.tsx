/**
 * Selector de ubicación en el mapa de Torreón, Coahuila (Leaflet + OpenStreetMap).
 *
 * Permite hacer clic en el mapa o arrastrar el pin para guardar las coordenadas
 * exactas del domicilio del cliente.
 */

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

import { TORREON_CENTER } from "@/lib/geo";

interface LocationPickerMapProps {
  latitude: number | null;
  longitude: number | null;
  onChange: (lat: number, lng: number) => void;
  heightClassName?: string;
}

function createPinIcon(): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="width:28px;height:28px;border-radius:9999px;background:#1d4ed8;border:3px solid #ffffff;box-shadow:0 2px 8px rgba(15,23,42,0.35);display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;font-weight:700;">●</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

export function LocationPickerMap({
  latitude,
  longitude,
  onChange,
  heightClassName = "h-64",
}: LocationPickerMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Inicializa el mapa una sola vez centrado en Torreón.
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

    map.on("click", (event: L.LeafletMouseEvent) => {
      const lat = Number(event.latlng.lat.toFixed(6));
      const lng = Number(event.latlng.lng.toFixed(6));
      onChangeRef.current(lat, lng);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, []);

  // Sincroniza el pin cuando cambian las coordenadas desde búsqueda o clic.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (latitude === null || longitude === null) {
      if (markerRef.current) {
        markerRef.current.remove();
        markerRef.current = null;
      }
      return;
    }

    const pos: L.LatLngExpression = [latitude, longitude];
    if (!markerRef.current) {
      const marker = L.marker(pos, {
        draggable: true,
        icon: createPinIcon(),
      }).addTo(map);

      marker.on("dragend", () => {
        const next = marker.getLatLng();
        onChangeRef.current(
          Number(next.lat.toFixed(6)),
          Number(next.lng.toFixed(6)),
        );
      });

      markerRef.current = marker;
    } else {
      markerRef.current.setLatLng(pos);
    }

    const targetZoom = Math.max(map.getZoom(), 16);
    map.setView(pos, targetZoom, { animate: true });
  }, [latitude, longitude]);

  return (
    <div
      ref={containerRef}
      className={`${heightClassName} w-full overflow-hidden rounded-xl border border-slate-200 z-0`}
      aria-label="Mapa de Torreón para seleccionar ubicación del cliente"
    />
  );
}
