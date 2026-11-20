/**
 * Utilidades geográficas, zonas sugeridas de Torreón, Coahuila, geocodificación
 * con OpenStreetMap (Nominatim) y trazado de ruta por calles (OSRM).
 */

export const DEFAULT_CITY = "Torreón";
export const DEFAULT_STATE = "Coahuila";

/** Centro de Torreón, Coahuila (Plaza Mayor). */
export const TORREON_CENTER: [number, number] = [25.5428, -103.4068];

/** Caja delimitadora aproximada de Torreón y zona conurbada (lon1,lat1,lon2,lat2). */
const TORREON_VIEWBOX = "-103.56,25.66,-103.24,25.43";

/** Zonas sugeridas para organizar rutas en Torreón, Coahuila. */
export const SUGGESTED_TORREON_ZONES: readonly string[] = [
  "Centro",
  "Norte",
  "Sur",
  "Oriente",
  "Poniente",
  "Viñedos",
  "Senderos",
  "Torreón Jardín",
  "Campestre La Rosita",
  "Ampliación Los Ángeles",
  "Alianza",
  "Jacarandas",
  "Las Etnias",
  "Sol de Oriente",
];

/** Combina zonas existentes de la financiera con las sugeridas sin duplicar. */
export function mergeZoneOptions(existingZones: string[]): string[] {
  const seen = new Set<string>();
  const merged: string[] = [];

  for (const raw of [...existingZones, ...SUGGESTED_TORREON_ZONES]) {
    const clean = raw.trim();
    if (!clean) continue;
    const key = clean.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(clean);
  }

  return merged;
}

export interface StructuredAddressParts {
  street?: string | null;
  exterior_number?: string | null;
  neighborhood?: string | null;
  postal_code?: string | null;
  city?: string | null;
  state?: string | null;
}

/** Compone la dirección completa en el mismo formato que usa el backend. */
export function composeAddress(parts: StructuredAddressParts): string {
  const tokens: string[] = [];
  const streetLine = [parts.street?.trim(), parts.exterior_number?.trim()]
    .filter(Boolean)
    .join(" ");
  if (streetLine) tokens.push(streetLine);
  if (parts.neighborhood?.trim()) tokens.push(`Col. ${parts.neighborhood.trim()}`);
  if (parts.postal_code?.trim()) tokens.push(`C.P. ${parts.postal_code.trim()}`);
  if (parts.city?.trim()) tokens.push(parts.city.trim());
  if (parts.state?.trim()) tokens.push(parts.state.trim());
  return tokens.join(", ");
}

/** Convierte una coordenada textual/numérica en número finito o null. */
export function parseCoordinate(
  value: string | number | null | undefined,
): number | null {
  if (value === null || value === undefined || value === "") return null;
  const num = typeof value === "number" ? value : Number(value);
  return Number.isFinite(num) ? num : null;
}

export interface GeocodeResult {
  lat: number;
  lng: number;
  displayName: string;
  approximate: boolean;
}

async function queryNominatim(
  query: string,
  signal?: AbortSignal,
): Promise<{ lat: number; lng: number; displayName: string } | null> {
  const params = new URLSearchParams({
    q: query,
    format: "jsonv2",
    limit: "1",
    countrycodes: "mx",
    viewbox: TORREON_VIEWBOX,
    bounded: "1",
  });

  const response = await fetch(
    `https://nominatim.openstreetmap.org/search?${params.toString()}`,
    {
      signal,
      headers: { Accept: "application/json", "Accept-Language": "es-MX,es" },
    },
  );
  if (!response.ok) return null;

  const data = (await response.json()) as Array<{
    lat: string;
    lon: string;
    display_name: string;
  }>;
  const first = data[0];
  if (!first) return null;

  const lat = Number(first.lat);
  const lng = Number(first.lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;

  return { lat, lng, displayName: first.display_name };
}

/**
 * Busca una dirección en Torreón usando OpenStreetMap (Nominatim).
 * Intenta primero calle + número + colonia; si OSM no tiene el número exacto,
 * intenta calle + colonia y finalmente solo la colonia para acercar el pin.
 */
export async function geocodeTorreonAddress(
  parts: StructuredAddressParts,
  signal?: AbortSignal,
): Promise<GeocodeResult | null> {
  const city = parts.city?.trim() || DEFAULT_CITY;
  const state = parts.state?.trim() || DEFAULT_STATE;
  const street = parts.street?.trim() || "";
  const number = parts.exterior_number?.trim() || "";
  const neighborhood = parts.neighborhood?.trim() || "";
  const postalCode = parts.postal_code?.trim() || "";

  const candidates: Array<{ query: string; approximate: boolean }> = [];

  if (street && number && neighborhood) {
    candidates.push({
      query: `${street} ${number}, ${neighborhood}, ${city}, ${state}, México`,
      approximate: false,
    });
  }
  if (street && number) {
    candidates.push({
      query: `${street} ${number}, ${postalCode ? `${postalCode}, ` : ""}${city}, ${state}, México`,
      approximate: false,
    });
  }
  if (street && neighborhood) {
    candidates.push({
      query: `${street}, ${neighborhood}, ${city}, ${state}, México`,
      approximate: true,
    });
  }
  if (neighborhood) {
    candidates.push({
      query: `${neighborhood}, ${postalCode ? `${postalCode}, ` : ""}${city}, ${state}, México`,
      approximate: true,
    });
  }

  for (const candidate of candidates) {
    const found = await queryNominatim(candidate.query, signal);
    if (found) {
      return { ...found, approximate: candidate.approximate };
    }
  }

  return null;
}

/** Distancia en kilómetros entre dos coordenadas (fórmula de Haversine). */
export function haversineKm(
  a: [number, number],
  b: [number, number],
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const earthKm = 6371;
  const dLat = toRad(b[0] - a[0]);
  const dLng = toRad(b[1] - a[1]);
  const sinLat = Math.sin(dLat / 2);
  const sinLng = Math.sin(dLng / 2);
  const h =
    sinLat * sinLat +
    Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * sinLng * sinLng;
  return 2 * earthKm * Math.asin(Math.sqrt(h));
}

export interface StreetRouteResult {
  path: [number, number][];
  distanceKm: number;
  durationMin: number;
  isStreetRoute: boolean;
}

/**
 * Obtiene la ruta real por calles entre paradas ordenadas usando OSRM.
 * Si el servicio externo no responde, devuelve la polilínea directa con
 * distancia estimada para que el mapa siempre funcione.
 */
export async function fetchStreetRoute(
  points: [number, number][],
  signal?: AbortSignal,
): Promise<StreetRouteResult> {
  if (points.length < 2) {
    return { path: points, distanceKm: 0, durationMin: 0, isStreetRoute: false };
  }

  const fallbackDistance = points.reduce(
    (sum, pt, idx) => (idx === 0 ? 0 : sum + haversineKm(points[idx - 1], pt)),
    0,
  );
  const fallback: StreetRouteResult = {
    path: points,
    distanceKm: Number(fallbackDistance.toFixed(1)),
    durationMin: Math.max(1, Math.round((fallbackDistance / 25) * 60)),
    isStreetRoute: false,
  };

  try {
    const coords = points.map(([lat, lng]) => `${lng},${lat}`).join(";");
    const url =
      `https://router.project-osrm.org/route/v1/driving/${coords}` +
      "?overview=full&geometries=geojson";
    const response = await fetch(url, { signal });
    if (!response.ok) return fallback;

    const data = (await response.json()) as {
      routes?: Array<{
        distance: number;
        duration: number;
        geometry?: { coordinates?: [number, number][] };
      }>;
    };
    const route = data.routes?.[0];
    const rawCoords = route?.geometry?.coordinates;
    if (!route || !rawCoords || rawCoords.length < 2) return fallback;

    return {
      path: rawCoords.map(([lng, lat]) => [lat, lng]),
      distanceKm: Number((route.distance / 1000).toFixed(1)),
      durationMin: Math.max(1, Math.round(route.duration / 60)),
      isStreetRoute: true,
    };
  } catch {
    return fallback;
  }
}

export interface GeoStop {
  id: string;
  lat: number | null;
  lng: number | null;
}

/**
 * Ordena paradas por vecino más cercano empezando desde la primera parada
 * geolocalizada. Las paradas sin coordenadas se conservan al final.
 */
export function optimizeStopOrder<T extends GeoStop>(stops: T[]): string[] {
  const located = stops.filter(
    (stop): stop is T & { lat: number; lng: number } =>
      stop.lat !== null && stop.lng !== null,
  );
  const unlocated = stops.filter(
    (stop) => stop.lat === null || stop.lng === null,
  );

  if (located.length <= 2) {
    return stops.map((stop) => stop.id);
  }

  const remaining = [...located];
  const ordered: Array<T & { lat: number; lng: number }> = [remaining.shift()!];

  while (remaining.length > 0) {
    const current = ordered[ordered.length - 1];
    let bestIdx = 0;
    let bestDist = Number.POSITIVE_INFINITY;

    for (let i = 0; i < remaining.length; i += 1) {
      const candidate = remaining[i];
      const dist = haversineKm(
        [current.lat, current.lng],
        [candidate.lat, candidate.lng],
      );
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }

    ordered.push(remaining.splice(bestIdx, 1)[0]);
  }

  return [...ordered, ...unlocated].map((stop) => stop.id);
}

/** Enlace para navegar a una parada específica en Google Maps. */
export function buildGoogleMapsStopUrl(stop: {
  lat: number | null;
  lng: number | null;
  address: string;
}): string {
  const destination =
    stop.lat !== null && stop.lng !== null
      ? `${stop.lat},${stop.lng}`
      : `${stop.address}, ${DEFAULT_CITY}, ${DEFAULT_STATE}`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}&travelmode=driving`;
}

/** Enlace para abrir la ruta completa con paradas en Google Maps. */
export function buildGoogleMapsRouteUrl(
  stops: Array<{ lat: number | null; lng: number | null; address: string }>,
): string | null {
  if (stops.length === 0) return null;

  const formatted = stops.map((stop) =>
    stop.lat !== null && stop.lng !== null
      ? `${stop.lat},${stop.lng}`
      : `${stop.address}, ${DEFAULT_CITY}, ${DEFAULT_STATE}`,
  );

  if (formatted.length === 1) {
    return buildGoogleMapsStopUrl(stops[0]);
  }

  const destination = formatted[formatted.length - 1];
  const waypoints = formatted.slice(0, -1).slice(0, 9);
  const params = new URLSearchParams({
    api: "1",
    destination,
    waypoints: waypoints.join("|"),
    travelmode: "driving",
  });
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}
