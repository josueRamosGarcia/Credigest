/**
 * Registro del service worker.
 *
 * Solo se registra en produccion: durante el desarrollo el service worker
 * cachea archivos viejos y provoca confusion al recargar.
 */

export function registerServiceWorker(): void {
  if (import.meta.env.DEV) return;
  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Si falla, la app funciona igual; solo pierde la instalacion como PWA.
    });
  });
}
