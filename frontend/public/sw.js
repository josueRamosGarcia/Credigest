/**
 * Service worker de Credigest.
 *
 * Estrategia: cache de solo lectura. Se guardan los archivos de la aplicacion
 * (JS, CSS, iconos) para que abra rapido y funcione sin senal para consultar.
 *
 * Las llamadas a la API NO se cachean: los datos de prestamos y pagos deben ser
 * siempre los del servidor. Registrar un pago exige conexion (decision
 * registrada en docs/02-arquitectura.md).
 */

const CACHE_NAME = "credigest-v1";

/** Archivos minimos para que la app arranque sin red. */
const PRECACHE = ["/", "/index.html", "/manifest.webmanifest", "/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Solo se manejan GET.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Nunca se cachea la API: los datos financieros deben venir del servidor.
  if (url.pathname.startsWith("/api/")) return;

  // Navegacion: se intenta la red y, si falla, se sirve el index cacheado.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/index.html").then((cached) => cached || Response.error())),
    );
    return;
  }

  // Recursos estaticos: primero el cache, luego la red (y se guarda).
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;

      return fetch(request).then((response) => {
        if (!response || response.status !== 200 || response.type === "opaque") {
          return response;
        }

        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        return response;
      });
    }),
  );
});
