/** Acciones sobre documentos que no son componentes. */

import { ApiError, authorizedFetch } from "@/api/client";

/** Abre un documento en una pestaña nueva respetando el refresh de token. */
export async function openDocument(
  clientId: string,
  documentId: string,
): Promise<void> {
  const response = await authorizedFetch(
    `/clients/${clientId}/documents/${documentId}`,
  );

  if (!response.ok) {
    throw new ApiError(response.status, "No se pudo abrir el documento.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");

  // Se libera despues de un momento para no cortar la visualizacion.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
