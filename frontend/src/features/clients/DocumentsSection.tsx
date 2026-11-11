/**
 * Subida y gestión de documentos del cliente.
 *
 * El archivo se envía como `multipart/form-data` con su tipo. El backend valida
 * el tamaño y el formato, y guarda con un nombre aleatorio.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  DOCUMENT_LABELS,
  formatBytes,
  listDocuments,
  type ClientDocument,
} from "@/api/clients";
import { tokens, ApiError } from "@/api/client";
import { openDocument } from "./documentActions";
import { Alert, EmptyState, Spinner } from "@/components/ui";

const DOC_TYPES = ["ine", "comprobante_domicilio", "otro"] as const;

/** Sube un archivo usando `fetch` directo porque necesita FormData. */
async function uploadDocument(
  clientId: string,
  file: File,
  docType: string,
): Promise<ClientDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", docType);

  const response = await fetch(`/api/v1/clients/${clientId}/documents`, {
    method: "POST",
    headers: tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {},
    body: form,
  });

  if (!response.ok) {
    let message = "No se pudo subir el documento.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Sin cuerpo: se usa el mensaje genérico.
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as ClientDocument;
}

/** Elimina un documento. */
async function deleteDocument(clientId: string, documentId: string): Promise<void> {
  const response = await fetch(
    `/api/v1/clients/${clientId}/documents/${documentId}`,
    {
      method: "DELETE",
      headers: tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {},
    },
  );

  if (!response.ok) {
    throw new ApiError(response.status, "No se pudo eliminar el documento.");
  }
}

export function DocumentsSection({ clientId }: { clientId: string }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [docType, setDocType] = useState<string>("ine");
  const [error, setError] = useState<string | null>(null);

  const documents = useQuery({
    queryKey: ["clients", clientId, "documents"],
    queryFn: () => listDocuments(clientId),
  });

  const upload = useMutation({
    mutationFn: ({ file, type }: { file: File; type: string }) =>
      uploadDocument(clientId, file, type),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["clients", clientId, "documents"] });
      if (inputRef.current) inputRef.current.value = "";
    },
    onError: (exc: unknown) => {
      setError(exc instanceof Error ? exc.message : "No se pudo subir el archivo.");
    },
  });

  const remove = useMutation({
    mutationFn: (documentId: string) => deleteDocument(clientId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients", clientId, "documents"] });
    },
  });

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (file.size > 10 * 1024 * 1024) {
      setError("El archivo supera el límite de 10 MB.");
      return;
    }

    upload.mutate({ file, type: docType });
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="label" htmlFor="doc_type">
            Tipo de documento
          </label>
          <select
            id="doc_type"
            className="input max-w-[240px]"
            value={docType}
            onChange={(event) => setDocType(event.target.value)}
          >
            {DOC_TYPES.map((type) => (
              <option key={type} value={type}>
                {DOCUMENT_LABELS[type]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="label" htmlFor="document-file">
            Archivo
          </label>
          <input
            id="document-file"
            ref={inputRef}
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            className="text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand-600 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-brand-700"
            onChange={handleFile}
            disabled={upload.isPending}
          />
        </div>

        {upload.isPending && <Spinner label="Subiendo…" />}
      </div>

      {error && (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      )}

      <p className="mb-4 text-xs text-slate-500">
        PDF, JPG, PNG o WEBP · máximo 10 MB. El archivo se guarda con un nombre
        aleatorio y solo puede abrirlo tu financiera.
      </p>

      {documents.isLoading && <Spinner />}

      {documents.data && documents.data.length === 0 && (
        <EmptyState
          title="Sin documentos"
          description="Sube el INE y el comprobante de domicilio del cliente."
        />
      )}

      {documents.data && documents.data.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {documents.data.map((document) => (
            <li
              key={document.id}
              className="flex flex-wrap items-center justify-between gap-2 py-3"
            >
              <div>
                <p className="text-sm font-medium text-slate-900">
                  {DOCUMENT_LABELS[document.doc_type] ?? document.doc_type}
                </p>
                <p className="tabular text-xs text-slate-500">
                  {formatBytes(document.size_bytes)} · {document.mime_type}
                </p>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary px-3 py-1 text-xs"
                  onClick={() => openDocument(clientId, document.id)}
                >
                  Abrir
                </button>
                <button
                  type="button"
                  className="px-3 py-1 text-xs text-red-600 hover:underline"
                  onClick={() => remove.mutate(document.id)}
                  disabled={remove.isPending}
                >
                  Eliminar
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
